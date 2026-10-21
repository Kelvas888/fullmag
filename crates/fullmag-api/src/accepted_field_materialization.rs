//! Adopt verified accepted quantity bundles into the current API session.

use std::{collections::BTreeSet, sync::Arc};
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use fullmag_session::{FmsArtifactStatus, SessionStore};
use crate::{error::ApiError, types::{AppState, CurrentLiveFieldFrameRequest}};
use crate::accepted_field_binary::AcceptedFieldReader;
use crate::accepted_quantity_bundle::{
    field_key, read_record, MaterializationRecord, ARTIFACT_TYPE, SCHEMA,
};

struct LoadedBundle {
    record: MaterializationRecord,
    state_fingerprint: String,
    specification: Value,
}

fn load_latest_bundle(store_root: &std::path::Path, run_id: &str) -> Result<LoadedBundle> {
    let store = SessionStore::open_existing(store_root)?;
    let intent = store.read_run_intent(run_id)?.context("accepted run intent missing")?;
    intent.validate()?;
    let project_id = serde_json::from_value::<fullmag_application::RunSpecification>(intent.specification.clone())?
        .snapshot.project_id;
    let accepted = fullmag_runtime_control::load_accepted_study_snapshot(&store,
        &fullmag_application::RunId::parse(run_id)?, &project_id)?;
    let run = store.read_run_catalog(run_id)?.context("accepted run catalog missing")?;
    let catalog = store.read_artifact_catalog(run_id)?.context("accepted artifact catalog missing")?;
    run.validate()?; catalog.validate()?;
    // Choose the latest state-producing step, never an older available bundle.
    let mut selected = None;
    for step in &accepted.lowered.steps {
        let task_id = fullmag_session::task_id_for_study_step(run_id, &step.step_id)?;
        let Some(task) = run.tasks.iter().find(|task| task.task_id == task_id
            && task.lifecycle == fullmag_session::FmsTaskLifecycle::Succeeded) else { continue; };
        let entries = catalog.entries.iter().filter(|entry| entry.task_id == task.task_id
            && Some(entry.attempt_id.as_str()) == task.attempt_id.as_deref()
            && Some(entry.ownership_epoch) == task.ownership_epoch
            && entry.status == FmsArtifactStatus::Published
            && task.artifact_ids.contains(&entry.artifact_id)).collect::<Vec<_>>();
        let mut manifests = entries.iter().filter(|entry| entry.artifact_type == "study_output_manifest");
        let Some(manifest_entry) = manifests.next() else { continue; };
        if manifests.next().is_some() { bail!("accepted output manifest is ambiguous"); }
        let manifest_ref = manifest_entry.object_ref.as_deref().context("manifest CAS reference missing")?;
        if manifest_ref != manifest_entry.content_sha256 { bail!("manifest CAS digest differs"); }
        let bytes = store.cas().get_bounded(manifest_ref, crate::accepted_observation_spool::MAX_MANIFEST_BYTES)?
            .context("accepted manifest missing from CAS")?;
        if fullmag_application::study_artifact_content_sha256(&bytes) != manifest_ref {
            bail!("accepted manifest content digest differs");
        }
        let manifest: fullmag_session::FmsStudyOutputManifest = serde_json::from_slice(&bytes)?;
        manifest.validate()?;
        if manifest.run_id != run_id || manifest.task_id != task_id
            || manifest.step_id != step.step_id || Some(manifest.attempt_id.as_str()) != task.attempt_id.as_deref()
            || Some(manifest.ownership_epoch) != task.ownership_epoch { bail!("manifest ownership differs"); }
        let mut states = manifest.outputs.iter().filter(|output| output.data_kind == "state");
        let Some(state_output) = states.next() else { continue; };
        if states.next().is_some() { bail!("accepted state output is ambiguous"); }
        let state_entry = entries.iter().find(|entry| entry.artifact_id == state_output.artifact_id
            && entry.object_ref.as_deref() == Some(state_output.object_ref.as_str())
            && entry.content_sha256 == state_output.content_sha256).context("accepted state catalog binding missing")?;
        let admission = store.read_task_admission(run_id, &task.task_id, &manifest.attempt_id)?
            .context("accepted state admission budget missing")?;
        admission.validate()?;
        if admission.lease.ownership_epoch != manifest.ownership_epoch
            || admission.lease.run_id != run_id || admission.lease.task_id != task.task_id {
            bail!("accepted state admission ownership differs");
        }
        let state_budget = (admission.lease.budget.memory_bytes / 4)
            .min(admission.lease.budget.storage_bytes);
        let state_bytes = store.cas().get_bounded(&state_entry.content_sha256, state_budget)?
            .context("accepted state CAS bytes missing")?;
        if fullmag_application::study_artifact_content_sha256(&state_bytes) != state_output.object_ref {
            bail!("accepted state content digest differs");
        }
        let fullmag_application::DecodedStudyArtifact::MagnetizationState(state) =
            fullmag_application::decode_study_artifact_bytes("state", &state_output.codec_id,
                &state_output.codec_version, &state_bytes)? else { bail!("invalid state output"); };
        drop(state_bytes);
        let mut bundles = entries.iter().filter(|entry| entry.artifact_type == ARTIFACT_TYPE);
        let record = match bundles.next() {
            Some(entry) => {
                if bundles.next().is_some() { bail!("accepted quantity bundle is ambiguous"); }
                let record = read_record(&store, entry)?;
                if Some(&record.source) != manifest.accepted_state_ref.as_ref()
                    || record.state_object_ref != state_output.object_ref
                    || record.source.id.accepted_step != state.step {
                    bail!("accepted quantity bundle differs from final state manifest");
                }
                if let Some(batch) = record.batch.as_ref() {
                    for field in &batch.fields {
                        if let Some(reference) = record.binary_fields.get(&field_key(field)) {
                            if reference.max_read_bytes > admission.lease.budget.memory_bytes / 16 {
                                bail!("binary quantity read budget exceeds its producing admission");
                            }
                            let samples = if field.role == "airbox" {
                                let count = field.layout.pointer("/grid/cells").and_then(Value::as_array)
                                    .filter(|axes| axes.len() == 3)
                                    .and_then(|axes| axes.iter().try_fold(1_u64,
                                        |count, axis| count.checked_mul(axis.as_u64()?)))
                                    .context("binary Airbox grid missing")?;
                                usize::try_from(count)?
                            } else { state.values.len() };
                            if samples.checked_mul(field.n_comp) != Some(reference.value_count) {
                                bail!("binary quantity count differs from its accepted carrier");
                            }
                            let mut objects = reference.chunks.iter().map(|chunk| chunk.object_ref.as_str()).collect::<Vec<_>>();
                            if let Some(hash) = field.layout.get("field_artifact_object_ref").and_then(Value::as_str) { objects.push(hash); }
                            for hash in objects {
                                if !entries.iter().any(|entry| entry.artifact_type == "accepted_quantity_payload"
                                    && entry.content_sha256 == hash && entry.object_ref.as_deref() == Some(hash)) {
                                    bail!("binary quantity object lacks its exact task/attempt/epoch catalog binding");
                                }
                            }
                        }
                    }
                }
                Some(LoadedBundle { record, state_fingerprint: state.space_fingerprint,
                    specification: intent.specification.clone() })
            }
            None => None,
        };
        selected = Some(record);
    }
    selected.flatten().context("latest accepted state has no quantity bundle; rerun with this worker version")
}

/// Caller owns the transition fence. This path only reads CAS; it cannot solve,
/// allocate devices, or reinterpret a bundle belonging to an older scene.
pub(crate) async fn adopt_current_bundle(
    state: &Arc<AppState>, energies_only: bool,
    requirements: &[crate::schemas::runtime::FieldMaterializationRequirement],
) -> Result<(), ApiError> {
    adopt_bundle(state, energies_only, energies_only, false, requirements).await
}

/// The terminal projector already owns the transition fence and exact final
/// state. Publish its complete observation generation without a UI command or
/// another evaluator; explicit Compute commands can replay the same CAS data.
pub(crate) async fn adopt_terminal_bundle(state: &Arc<AppState>) -> Result<(), ApiError> {
    adopt_bundle(state, false, true, true, &[]).await
}

async fn adopt_bundle(
    state: &Arc<AppState>, energies_only: bool, include_energies: bool,
    all_fields: bool,
    requirements: &[crate::schemas::runtime::FieldMaterializationRequirement],
) -> Result<(), ApiError> {
    if !energies_only && !all_fields && requirements.is_empty() {
        return Err(ApiError::conflict("accepted field materialization requires an explicit resolved scope"));
    }
    let before = state.current_live_state.read().await.as_ref().cloned()
        .ok_or_else(|| ApiError::not_found("no current workspace"))?;
    let run = before.run.as_ref().ok_or_else(|| ApiError::conflict("no accepted run"))?;
    if !matches!(run.status.as_str(), "completed" | "failed" | "cancelled") {
        return Err(ApiError::conflict("accepted quantities require a terminal run and its verified state"));
    }
    let run_id = run.run_id.clone();
    let root = state.submit_store_root.clone().ok_or_else(|| ApiError::conflict("accepted store unavailable"))?;
    let reader_root = root.clone();
    let loaded = tokio::task::spawn_blocking(move || load_latest_bundle(&root, &run_id)).await
        .map_err(|error| ApiError::internal(error.to_string()))?
        .map_err(|error| ApiError::conflict_with_code("accepted_materialization_unavailable", format!("{error:#}")))?;
    let record = loaded.record;
    let batch = record.batch.ok_or_else(|| ApiError::conflict_with_code(
        "accepted_materialization_unsupported", record.error.unwrap_or_default()))?;
    let automatic_requirements;
    let requirements = if all_fields {
        automatic_requirements = vec![crate::schemas::runtime::FieldMaterializationRequirement {
            quantity_ids: batch.fields.iter().filter(|field| field.role != "airbox")
                .map(|field| field.quantity_id.clone()).collect(),
            scope_kind: "full".into(), scope_id: None,
            generation_id: crate::router_v2::handlers::sessions::status::domain_generation_id(&before),
            carrier_fingerprint: None,
        }];
        automatic_requirements.as_slice()
    } else { requirements };
    if batch.source != record.source || batch.magnetization_content_sha256 != record.state_object_ref
        || batch.clock.accepted_step != record.source.id.accepted_step {
        return Err(ApiError::conflict("bundle source differs"));
    }
    batch.clock.validate().map_err(|error| ApiError::conflict(error.to_string()))?;
    let mut current = state.current_live_state.write().await;
    let snapshot = current.as_mut().ok_or_else(|| ApiError::not_found("no current workspace"))?;
    if snapshot.session.session_id != before.session.session_id
        || snapshot.scene_document.as_ref().map(|scene| scene.revision) != before.scene_document.as_ref().map(|scene| scene.revision)
        || snapshot.run.as_ref().map(|run| &run.run_id) != before.run.as_ref().map(|run| &run.run_id) {
        return Err(ApiError::conflict("current accepted source changed"));
    }
    let scene = snapshot.scene_document.as_ref().ok_or_else(|| ApiError::conflict("accepted scene missing"))?;
    let execution_input = crate::live_execution_binding::input_identity(scene)?;
    crate::live_execution_binding::validate_input_binding(&loaded.specification,
        &execution_input, scene.revision)?;
    let live = loaded.specification.pointer("/parameters/live_workspace");
    if live.and_then(|value| value.get("api_instance_id")).and_then(Value::as_str)
        != Some(state.request_scope_instance_id.as_str())
        || live.and_then(|value| value.get("session_id")).and_then(Value::as_str)
            != Some(snapshot.session.session_id.as_str())
        || live.and_then(|value| value.get("session_epoch")).and_then(Value::as_u64)
            != Some(state.current_live_session_epoch.load(std::sync::atomic::Ordering::Acquire)) {
        return Err(ApiError::conflict("accepted bundle belongs to another live owner"));
    }
    let m = snapshot.latest_fields.get("m").ok_or_else(|| ApiError::conflict("accepted state projection is pending"))?;
    let domain_generation = crate::router_v2::handlers::sessions::status::domain_generation_id(snapshot);
    if requirements.iter().any(|requirement| requirement.generation_id != domain_generation)
        || !crate::session::latest_field_source_is_qualified(snapshot, "m", m)
    {
        return Err(ApiError::conflict("materialization domain changed after command admission"));
    }
    if m.get("state_object_ref").and_then(Value::as_str) != Some(record.state_object_ref.as_str())
        || m.get("accepted_state_ref") != Some(&serde_json::to_value(&record.source)
            .map_err(|error| ApiError::internal(error.to_string()))?)
        || m.get("carrier_fingerprint").and_then(Value::as_str) != Some(loaded.state_fingerprint.as_str())
        || m.get("source_step").and_then(Value::as_u64) != Some(batch.clock.accepted_step)
        || m.get("source_time_seconds").and_then(Value::as_f64) != Some(batch.clock.time_seconds) {
        return Err(ApiError::conflict("displayed magnetization differs from materialized state"));
    }
    let frame = crate::session::accepted_observation_frame_ref(snapshot,
        batch.clock.accepted_step, Some(batch.clock.time_seconds));
    let mut next = snapshot.clone();
    let wanted = requirements.iter().flat_map(|requirement| requirement.quantity_ids.iter()
        .map(String::as_str)).collect::<BTreeSet<_>>();
    let mut fields = crate::types::LatestFields::default();
    let mut readers = Vec::new();
    if !energies_only {
        let mut identities = BTreeSet::new();
        for field in &batch.fields {
            if !matches!(field.role.as_str(), "magnetic" | "layer_native" | "airbox")
                || !identities.insert((field.quantity_id.as_str(), field.role == "airbox")) {
                return Err(ApiError::conflict("accepted quantity carrier is ambiguous or has an unknown role"));
            }
        }
        for requirement in requirements {
            for quantity in &requirement.quantity_ids {
                if !batch.fields.iter().any(|field| field.quantity_id == *quantity
                    && (field.role == "airbox") == (requirement.scope_kind == "airbox")) {
                    let key = format!("{}:{quantity}", requirement.scope_kind);
                    let reason = batch.unavailable_scopes.get(&key).map(String::as_str)
                        .unwrap_or("the accepted evaluator did not publish this carrier");
                    return Err(ApiError::conflict_with_code("accepted_materialization_unsupported", format!(
                        "{quantity} for {}: {reason}", requirement.scope_kind)));
                }
            }
        }
        for field in &batch.fields {
            // Target-only carriers are adopted separately; never overwrite a
            // layer-native field with an array from a different observation grid.
            if field.role == "airbox" || field.quantity_id == "m" { continue; }
            if !wanted.is_empty() && !wanted.contains(field.quantity_id.as_str()) { continue; }
            let spec = fullmag_quantities::quantity_spec(&field.quantity_id)
                .ok_or_else(|| ApiError::conflict("accepted quantity is unknown"))?;
            let binary = record.binary_fields.get(&field_key(field));
            let value_count = binary.map_or(field.values.len(), |reference| reference.value_count);
            if field.n_comp != spec.n_comp as usize || field.n_comp == 0
                || value_count == 0 || value_count % field.n_comp != 0
                || field.values.iter().any(|value| !value.is_finite()) {
                return Err(ApiError::conflict("accepted quantity field shape is invalid"));
            }
            let mut raw = json!({
                "n_comp": field.n_comp, "layout": field.layout,
                "carrier_id": field.carrier_id,
                "spatial_kind": field.spatial_kind,
                "unavailable_scopes": batch.unavailable_scopes,
                "source_step": batch.clock.accepted_step, "source_time_seconds": batch.clock.time_seconds,
                "solver_dt": batch.clock.dt_seconds, "observation_frame": frame,
                "provenance": {"source": SCHEMA, "accepted_state_ref": batch.source,
                    "state_object_ref": record.state_object_ref, "execution_input": execution_input,
                    "plan_sha256": batch.plan_sha256, "lane": batch.lane,
                    "evaluator_build_identity": batch.evaluator_build_identity},
            });
            if let Some(reference) = binary {
                raw["accepted_binary_field"] = serde_json::to_value(reference)
                    .map_err(|error| ApiError::internal(error.to_string()))?;
                readers.push((field.quantity_id.clone(), Arc::new(
                    AcceptedFieldReader::new(reader_root.clone(), reference.clone())?)));
            } else { raw["values"] = json!(field.values); }
            fields.insert(field.quantity_id.clone(), raw);
        }
        for field in batch.fields.iter().filter(|field| field.role == "airbox") {
            if !wanted.is_empty() && !wanted.contains(field.quantity_id.as_str()) { continue; }
            let mut raw = fields.get(&field.quantity_id).cloned().ok_or_else(|| {
                ApiError::conflict("target-only Airbox carrier cannot replace a missing magnetic carrier")
            })?;
            if field.layout.get("manifest").is_none() || (field.layout.get("field_artifact").is_none()
                && field.layout.get("field_artifact_object_ref").is_none()) {
                return Err(ApiError::conflict("accepted Airbox carrier lacks its validated manifest and artifact"));
            }
            raw["accepted_airbox"] = field.layout.clone();
            if let Some(reference) = record.binary_fields.get(&field_key(field)) {
                raw["accepted_airbox"]["accepted_binary_field"] = serde_json::to_value(reference)
                    .map_err(|error| ApiError::internal(error.to_string()))?;
            }
            fields.insert(field.quantity_id.clone(), raw);
        }
    }
    for (quantity, reader) in readers { fields.attach_binary(quantity, reader)?; }
    if include_energies {
        let standard = ["E_total", "E_ex", "E_demag", "E_ext", "E_ani", "E_dmi"];
        if standard.iter().any(|quantity| !batch.energies.contains_key(*quantity))
            || batch.energies.values().any(|value| !value.is_finite()) {
            return Err(ApiError::conflict("accepted energy decomposition unavailable"));
        }
        // Global quantities remain scalar; do not broadcast a total energy to
        // every cell and accidentally present joules as an energy density.
        for (quantity, value) in &batch.energies {
            let spec = fullmag_quantities::quantity_spec(quantity)
                .ok_or_else(|| ApiError::conflict("unknown accepted energy quantity"))?;
            if spec.location != fullmag_quantities::QuantityLocation::Global || spec.unit != "J" {
                return Err(ApiError::conflict("accepted energy quantity is not a global value in joules"));
            }
            fields.insert(quantity.clone(), json!({"values": [value], "n_comp": 1,
                "source_step": batch.clock.accepted_step, "source_time_seconds": batch.clock.time_seconds,
                "observation_frame": frame, "layout": {"kind": "global_scalar"},
                "provenance": {"source": SCHEMA, "accepted_state_ref": batch.source,
                    "state_object_ref": record.state_object_ref, "execution_input": execution_input,
                    "evaluator_build_identity": batch.evaluator_build_identity}}));
        }
        // Do not rewrite a solver history row matched only by step/time:
        // separate stages may reuse that clock. These global results retain
        // the full accepted source identity in the same quantity data plane.
    }
    crate::session::apply_current_live_accepted_field_frame(&mut next, CurrentLiveFieldFrameRequest {
        session_id: before.session.session_id, latest_fields: Some(fields), replace_latest_fields: false,
        field_generation: None, preview_fields: None, clear_preview_cache: false,
    }, frame)?;
    if !energies_only {
        // A newly materialized target can appear before the previous catalog
        // knew about it. Validate it even when it was not an existing command
        // requirement; it still must never replace the magnetic carrier.
        for field in batch.fields.iter().filter(|field| field.role == "airbox"
            && wanted.contains(field.quantity_id.as_str())) {
            crate::router_v2::handlers::data::fields::load_fdm_multilayer_airbox_carrier_for_quantity(&next, &field.quantity_id)
                .map_err(ApiError::conflict)?.ok_or_else(|| ApiError::conflict("accepted Airbox target does not resolve"))?;
        }
        for requirement in requirements {
            for quantity in &requirement.quantity_ids {
                let spec = fullmag_quantities::quantity_spec(quantity)
                    .ok_or_else(|| ApiError::conflict("unknown requested quantity"))?;
                match requirement.scope_kind.as_str() {
                    "full" => {
                        if crate::router_v2::handlers::data::resolved_spatial_field::resolve_current_spatial_field_metadata(
                            &next, quantity, spec.n_comp as usize,
                        )?.is_none() {
                            return Err(ApiError::conflict("materialized field does not resolve in the current domain"));
                        }
                    }
                    "airbox" => {
                        let carrier = crate::router_v2::handlers::data::fields::load_fdm_multilayer_airbox_carrier_for_quantity(&next, quantity)
                            .map_err(ApiError::conflict)?.ok_or_else(|| ApiError::conflict("materialized Airbox carrier unavailable"))?;
                        if requirement.carrier_fingerprint.as_deref()
                            .is_some_and(|fingerprint| fingerprint != carrier.carrier_fingerprint) {
                            return Err(ApiError::conflict("materialized Airbox target changed"));
                        }
                        if carrier.sample_count == 0 || !carrier.published_quantities.contains(quantity)
                            || carrier.unavailable_quantities.contains_key(quantity) {
                            return Err(ApiError::conflict("materialized Airbox quantity unavailable"));
                        }
                    }
                    _ => return Err(ApiError::conflict("unsupported materialization scope")),
                }
            }
        }
    }
    *snapshot = next;
    Ok(())
}

/// A global observation is a single value in joules, never a spatial field.
/// Preserve the exact accepted state and authored-input fences even when two
/// stages happen to share a step/time clock and the same mesh.
pub(crate) fn current_global_energy(
    current: &crate::types::SessionStateResponse, quantity: &str,
) -> Option<f64> {
    let spec = fullmag_quantities::quantity_spec(quantity)?;
    if spec.location != fullmag_quantities::QuantityLocation::Global || spec.unit != "J" { return None; }
    let raw = current.latest_fields.get(quantity)?;
    let provenance = raw.get("provenance")?;
    if provenance.get("source")?.as_str()? != SCHEMA { return None; }
    let source: fullmag_quantities::AcceptedStateRef = serde_json::from_value(provenance.get("accepted_state_ref")?.clone()).ok()?;
    if current.run.as_ref()?.run_id != source.id.run_id { return None; }
    let m = current.latest_fields.get("m")?;
    if !crate::session::latest_field_source_is_qualified(current, "m", m)
        || m.get("state_object_ref")? != provenance.get("state_object_ref")?
        || m.get("accepted_state_ref")? != provenance.get("accepted_state_ref")? { return None; }
    let input: fullmag_authoring::SceneExecutionInputIdentity =
        serde_json::from_value(provenance.get("execution_input")?.clone()).ok()?;
    if input != crate::live_execution_binding::input_identity(current.scene_document.as_ref()?).ok()? { return None; }
    let values = raw.get("values")?.as_array()?;
    if values.len() != 1 { return None; }
    values[0].as_f64().filter(|value| value.is_finite())
}

/// Current-energy consumers use the existing resource shape. Solver history
/// remains untouched; only this source-qualified current observation wins.
pub(crate) fn current_energy_observation(
    current: &crate::types::SessionStateResponse,
) -> Option<crate::schemas::runtime::SolverEnergyCurrentResource> {
    let total = current_global_energy(current, "E_total")?;
    let raw = current.latest_fields.get("E_total")?;
    let proof = raw.get("provenance")?;
    let frame = raw.get("observation_frame")?;
    let component = |quantity: &str| -> Option<f64> {
        let value = current.latest_fields.get(quantity)?;
        if value.get("provenance")? != proof || value.get("observation_frame")? != frame {
            return None;
        }
        let values = value.get("values")?.as_array()?;
        if values.len() != 1 { return None; }
        values[0].as_f64().filter(|value| value.is_finite())
    };
    Some(crate::schemas::runtime::SolverEnergyCurrentResource {
        revision: current.scalar_revision.saturating_add(
            crate::router_v2::handlers::sessions::status::field_revision(current),
        ),
        step: raw.get("source_step")?.as_u64()?,
        time_seconds: raw.get("source_time_seconds")?.as_f64()?,
        exchange: component("E_ex")?, demag: component("E_demag")?,
        zeeman: component("E_ext")?, anisotropy: component("E_ani")?,
        dmi: component("E_dmi")?, total,
    })
}
