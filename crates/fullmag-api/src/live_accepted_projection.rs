//! Project durable accepted Study output into the one current live workspace.
//!
//! Accepted workers own RunIntent, task leases, CAS publication, and the
//! immutable artifact catalogs.  This module is only a bounded read-model
//! projector for the Docker API-only lane: it never claims a task, starts a
//! solver, allocates a device, or writes a durable catalog.

use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};

use crate::error::ApiError;
use crate::types::{AppState, CurrentLiveFieldFrameRequest, SessionStateResponse};

const POLL_INTERVAL: Duration = Duration::from_millis(500);

#[derive(Debug, Clone)]
struct ProjectionContext {
    session_id: String,
    run_id: String,
    session_epoch: u64,
    scene_revision: u64,
    api_instance_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProjectionCursor {
    api_instance_id: String,
    session_id: String,
    session_epoch: u64,
    scene_revision: u64,
    run_id: String,
    run_revision: u64,
    artifact_revision: u64,
    status: &'static str,
    latest_output_identity: Option<String>,
}

#[derive(Debug, Clone)]
struct VerifiedOutput {
    task_order: usize,
    object_ref: String,
    data_kind: String,
    decoded: fullmag_application::DecodedStudyArtifact,
}

#[derive(Debug, Clone)]
struct DurableProjection {
    run_catalog_revision: u64,
    artifact_catalog_revision: u64,
    status: &'static str,
    command_id: Option<String>,
    latest_state: Option<VerifiedOutput>,
    latest_total_energy: Option<fullmag_application::StudyScalarArtifact>,
    latest_output_identity: Option<String>,
}

/// Start the read-only accepted-output projector for the Docker API-only
/// runtime.  The task remains idle for the native/legacy API lane and exits
/// only with the process; current-session fencing makes a stale poll harmless.
pub(crate) fn spawn(state: Arc<AppState>) {
    if !crate::live_accepted_execution::docker_api_only_runtime() {
        return;
    }
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(POLL_INTERVAL);
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        let mut cursor: Option<ProjectionCursor> = None;
        loop {
            interval.tick().await;
            match poll_once(&state, &mut cursor).await {
                Ok(()) => {}
                Err(error) => {
                    tracing::warn!(
                        code = ?error.code,
                        error = %error,
                        "accepted live read-model projection deferred"
                    );
                }
            }
        }
    });
}

async fn poll_once(
    state: &Arc<AppState>,
    cursor: &mut Option<ProjectionCursor>,
) -> Result<(), ApiError> {
    let Some(context) = capture_context(state).await? else {
        return Ok(());
    };
    let Some(store_root) = state.submit_store_root.clone() else {
        return Ok(());
    };
    let expected = context.clone();
    let previous_cursor = cursor.clone();
    let projection = tokio::task::spawn_blocking(move || {
        load_durable_projection(&store_root, &expected, previous_cursor.as_ref())
    })
    .await
    .map_err(|error| ApiError::internal(format!("accepted projection task failed: {error}")))??;
    let Some(projection) = projection else {
        return Ok(());
    };
    let next_cursor = ProjectionCursor {
        api_instance_id: context.api_instance_id.clone(),
        session_id: context.session_id.clone(),
        session_epoch: context.session_epoch,
        scene_revision: context.scene_revision,
        run_id: context.run_id.clone(),
        run_revision: projection.run_catalog_revision,
        artifact_revision: projection.artifact_catalog_revision,
        status: projection.status,
        latest_output_identity: projection.latest_output_identity.clone(),
    };
    if cursor.as_ref() == Some(&next_cursor) {
        return Ok(());
    }
    apply_projection(state, &context, projection).await?;
    *cursor = Some(next_cursor);
    Ok(())
}

async fn capture_context(state: &AppState) -> Result<Option<ProjectionContext>, ApiError> {
    let current = state.current_live_state.read().await;
    let Some(snapshot) = current.as_ref() else {
        return Ok(None);
    };
    let Some(run) = snapshot.run.as_ref() else {
        return Ok(None);
    };
    let Some(scene) = snapshot.scene_document.as_ref() else {
        return Ok(None);
    };
    if run.run_id.trim().is_empty() || snapshot.session.session_id.trim().is_empty() {
        return Ok(None);
    }
    Ok(Some(ProjectionContext {
        session_id: snapshot.session.session_id.clone(),
        run_id: run.run_id.clone(),
        session_epoch: state
            .current_live_session_epoch
            .load(std::sync::atomic::Ordering::Acquire),
        scene_revision: scene.revision,
        api_instance_id: state.request_scope_instance_id.clone(),
    }))
}

fn load_durable_projection(
    store_root: &std::path::Path,
    context: &ProjectionContext,
    previous_cursor: Option<&ProjectionCursor>,
) -> Result<Option<DurableProjection>, ApiError> {
    let store = fullmag_session::SessionStore::open_existing(store_root).map_err(|error| {
        ApiError::with_status_and_code(
            axum::http::StatusCode::SERVICE_UNAVAILABLE,
            "accepted_projection_store_unavailable",
            format!("failed to open accepted projection store: {error}"),
        )
    })?;
    let Some(intent) = store
        .read_run_intent(&context.run_id)
        .map_err(|error| ApiError::internal(format!("read accepted RunIntent: {error}")))?
    else {
        return Ok(None);
    };
    intent
        .validate()
        .map_err(|error| ApiError::conflict(format!("accepted RunIntent is invalid: {error}")))?;
    validate_live_intent(context, &intent.specification)?;

    let Some(run_catalog) = store
        .read_run_catalog(&context.run_id)
        .map_err(|error| ApiError::internal(format!("read accepted run catalog: {error}")))?
    else {
        return Ok(None);
    };
    let Some(artifact_catalog) = store
        .read_artifact_catalog(&context.run_id)
        .map_err(|error| ApiError::internal(format!("read accepted artifact catalog: {error}")))?
    else {
        return Ok(None);
    };
    run_catalog
        .validate()
        .map_err(|error| ApiError::conflict(format!("accepted run catalog is invalid: {error}")))?;
    artifact_catalog.validate().map_err(|error| {
        ApiError::conflict(format!("accepted artifact catalog is invalid: {error}"))
    })?;
    if run_catalog.run_id != context.run_id || artifact_catalog.run_id != context.run_id {
        return Err(ApiError::conflict_with_code(
            "accepted_projection_run_identity_mismatch",
            "accepted catalog identity differs from the current live run",
        ));
    }

    let status = accepted_projection_status(&store, &context.run_id, &run_catalog.tasks)?;
    if previous_cursor.is_some_and(|cursor| {
        cursor_matches_context(cursor, context)
            && cursor.run_revision == run_catalog.revision
            && cursor.artifact_revision == artifact_catalog.revision
            && cursor.status == status
    }) {
        // Run/artifact catalog revisions are the durable change signal.  Do
        // not decode every CAS object on the steady-state polling interval.
        return Ok(None);
    }
    let specification: fullmag_application::RunSpecification =
        serde_json::from_value(intent.specification.clone()).map_err(|error| {
            ApiError::conflict(format!(
                "accepted RunIntent specification is not typed: {error}"
            ))
        })?;
    if specification.run_id.as_str() != context.run_id {
        return Err(ApiError::conflict_with_code(
            "accepted_projection_specification_run_mismatch",
            "accepted RunIntent specification differs from the current live run",
        ));
    }
    let accepted = fullmag_runtime_control::load_accepted_study_snapshot(
        &store,
        &specification.run_id,
        &specification.snapshot.project_id,
    )
    .map_err(|error| {
        ApiError::conflict(format!(
            "accepted Study snapshot cannot be loaded for projection: {error:#}"
        ))
    })?;
    let task_order = accepted
        .lowered
        .steps
        .iter()
        .enumerate()
        .map(|(order, step)| {
            fullmag_session::task_id_for_study_step(&context.run_id, &step.step_id)
                .map(|task_id| (task_id, order))
                .map_err(|error| {
                    ApiError::conflict(format!(
                        "accepted Study step identity cannot be projected: {error}"
                    ))
                })
        })
        .collect::<Result<std::collections::BTreeMap<_, _>, _>>()?;
    let verified = load_verified_outputs(&store, &run_catalog, &artifact_catalog, &task_order)?;
    let latest_state = verified
        .iter()
        .filter(|output| output.data_kind == "state")
        .max_by(|left, right| compare_magnetization_outputs(left, right))
        .cloned();
    let latest_total_energy = verified
        .iter()
        .filter_map(|output| match &output.decoded {
            fullmag_application::DecodedStudyArtifact::Scalar(scalar)
                if scalar.quantity_id == "E_total" =>
            {
                Some(output)
            }
            _ => None,
        })
        .max_by(|left, right| compare_scalar_outputs(left, right))
        .and_then(|output| match &output.decoded {
            fullmag_application::DecodedStudyArtifact::Scalar(scalar) => Some(scalar.clone()),
            _ => None,
        });
    let latest_output_identity = latest_state
        .as_ref()
        .map(|output| output.object_ref.clone())
        .or_else(|| latest_total_energy.as_ref().map(scalar_identity));
    let command_id = intent
        .specification
        .pointer("/parameters/live_workspace/command_id")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned);
    Ok(Some(DurableProjection {
        run_catalog_revision: run_catalog.revision,
        artifact_catalog_revision: artifact_catalog.revision,
        status,
        command_id,
        latest_state,
        latest_total_energy,
        latest_output_identity,
    }))
}

fn cursor_matches_context(cursor: &ProjectionCursor, context: &ProjectionContext) -> bool {
    cursor.api_instance_id == context.api_instance_id
        && cursor.session_id == context.session_id
        && cursor.session_epoch == context.session_epoch
        && cursor.scene_revision == context.scene_revision
        && cursor.run_id == context.run_id
}

fn compare_magnetization_outputs(
    left: &VerifiedOutput,
    right: &VerifiedOutput,
) -> std::cmp::Ordering {
    let fullmag_application::DecodedStudyArtifact::MagnetizationState(state) = &left.decoded else {
        return std::cmp::Ordering::Less;
    };
    let fullmag_application::DecodedStudyArtifact::MagnetizationState(right_state) = &right.decoded
    else {
        return std::cmp::Ordering::Greater;
    };
    left.task_order
        .cmp(&right.task_order)
        .then_with(|| state.step.cmp(&right_state.step))
        .then_with(|| state.time_s.total_cmp(&right_state.time_s))
        .then_with(|| left.object_ref.cmp(&right.object_ref))
}

fn compare_scalar_outputs(left: &VerifiedOutput, right: &VerifiedOutput) -> std::cmp::Ordering {
    let fullmag_application::DecodedStudyArtifact::Scalar(left_scalar) = &left.decoded else {
        return std::cmp::Ordering::Less;
    };
    let fullmag_application::DecodedStudyArtifact::Scalar(right_scalar) = &right.decoded else {
        return std::cmp::Ordering::Greater;
    };
    left.task_order
        .cmp(&right.task_order)
        .then_with(|| left_scalar.step.cmp(&right_scalar.step))
        .then_with(|| left_scalar.time_s.total_cmp(&right_scalar.time_s))
        .then_with(|| scalar_identity(left_scalar).cmp(&scalar_identity(right_scalar)))
}

fn scalar_identity(scalar: &fullmag_application::StudyScalarArtifact) -> String {
    format!(
        "scalar:{}:{}:{}",
        scalar.step,
        scalar.time_s.to_bits(),
        scalar.value_si.to_bits()
    )
}

fn validate_live_intent(
    context: &ProjectionContext,
    specification: &Value,
) -> Result<(), ApiError> {
    let live = specification
        .pointer("/parameters/live_workspace")
        .and_then(Value::as_object)
        .ok_or_else(|| ApiError::conflict("accepted RunIntent has no live workspace binding"))?;
    if live.get("api_instance_id").and_then(Value::as_str) != Some(context.api_instance_id.as_str())
        || live.get("session_id").and_then(Value::as_str) != Some(context.session_id.as_str())
        || live.get("session_epoch").and_then(Value::as_u64) != Some(context.session_epoch)
        || live.get("scene_revision").and_then(Value::as_u64) != Some(context.scene_revision)
    {
        return Err(ApiError::conflict_with_code(
            "accepted_projection_live_binding_mismatch",
            "accepted RunIntent is not bound to the current session epoch and scene revision",
        ));
    }
    Ok(())
}

fn catalog_status(tasks: &[fullmag_session::FmsTaskCatalogEntry]) -> &'static str {
    if tasks.is_empty() {
        return "waiting_for_compute";
    }
    if tasks.iter().any(|task| {
        matches!(
            task.lifecycle,
            fullmag_session::FmsTaskLifecycle::Failed
                | fullmag_session::FmsTaskLifecycle::Interrupted
        )
    }) {
        return "failed";
    }
    if tasks
        .iter()
        .any(|task| task.lifecycle == fullmag_session::FmsTaskLifecycle::Cancelled)
    {
        return "cancelled";
    }
    if tasks
        .iter()
        .all(|task| task.lifecycle == fullmag_session::FmsTaskLifecycle::Succeeded)
    {
        return "completed";
    }
    if tasks
        .iter()
        .any(|task| task.lifecycle == fullmag_session::FmsTaskLifecycle::Running)
    {
        return "running";
    }
    "waiting_for_compute"
}

fn accepted_projection_status(
    store: &fullmag_session::SessionStore,
    run_id: &str,
    tasks: &[fullmag_session::FmsTaskCatalogEntry],
) -> Result<&'static str, ApiError> {
    let catalog_status = catalog_status(tasks);
    let start_permitted = store
        .accepted_run_start_permitted(run_id)
        .map_err(|error| {
            ApiError::conflict(format!(
                "accepted run start gate cannot be read for projection: {error}"
            ))
        })?;
    Ok(projected_status_for_gate(catalog_status, start_permitted))
}

fn projected_status_for_gate(catalog_status: &'static str, start_permitted: bool) -> &'static str {
    if catalog_status == "waiting_for_compute" && !start_permitted {
        // A manual startup run has a durable whole-Study catalog before the
        // interactive Compute command. Keep the run-level gate visible so the
        // next command releases this exact run instead of creating a second
        // accepted RunIntent.
        return "waiting_for_solve";
    }
    catalog_status
}

fn load_verified_outputs(
    store: &fullmag_session::SessionStore,
    run_catalog: &fullmag_session::FmsRunCatalog,
    artifact_catalog: &fullmag_session::FmsArtifactCatalog,
    task_order: &std::collections::BTreeMap<String, usize>,
) -> Result<Vec<VerifiedOutput>, ApiError> {
    let mut outputs = Vec::new();
    for task in &run_catalog.tasks {
        if task.lifecycle != fullmag_session::FmsTaskLifecycle::Succeeded {
            continue;
        }
        let (Some(attempt_id), Some(ownership_epoch)) =
            (task.attempt_id.as_deref(), task.ownership_epoch)
        else {
            return Err(ApiError::conflict(
                "succeeded accepted task has no attempt/ownership identity",
            ));
        };
        let task_order = task_order.get(&task.task_id).copied().ok_or_else(|| {
            ApiError::conflict(
                "accepted task is not present in the canonical Study execution order",
            )
        })?;
        let mut manifests = artifact_catalog.entries.iter().filter(|entry| {
            entry.artifact_type == "study_output_manifest"
                && entry.task_id == task.task_id
                && entry.attempt_id == attempt_id
                && entry.ownership_epoch == ownership_epoch
                && entry.status == fullmag_session::FmsArtifactStatus::Published
                && task.artifact_ids.contains(&entry.artifact_id)
        });
        let Some(manifest_entry) = manifests.next() else {
            return Err(ApiError::conflict(
                "succeeded accepted task has no published output manifest",
            ));
        };
        if manifests.next().is_some() {
            return Err(ApiError::conflict(
                "accepted task has multiple published output manifests",
            ));
        }
        let manifest_ref = manifest_entry
            .object_ref
            .as_deref()
            .filter(|object_ref| *object_ref == manifest_entry.content_sha256)
            .ok_or_else(|| ApiError::conflict("accepted output manifest digest is not pinned"))?;
        let manifest_bytes = store
            .cas()
            .get(manifest_ref)
            .map_err(|error| ApiError::internal(format!("read accepted output manifest: {error}")))?
            .ok_or_else(|| ApiError::conflict("accepted output manifest is missing from CAS"))?;
        let manifest: fullmag_session::FmsStudyOutputManifest =
            serde_json::from_slice(&manifest_bytes).map_err(|error| {
                ApiError::conflict(format!("accepted output manifest is invalid: {error}"))
            })?;
        manifest.validate().map_err(|error| {
            ApiError::conflict(format!(
                "accepted output manifest failed validation: {error}"
            ))
        })?;
        if manifest.run_id != run_catalog.run_id
            || manifest.task_id != task.task_id
            || manifest.attempt_id != attempt_id
            || manifest.ownership_epoch != ownership_epoch
        {
            return Err(ApiError::conflict(
                "accepted output manifest ownership identity mismatch",
            ));
        }
        for output in manifest.outputs {
            let artifact = artifact_catalog
                .entries
                .iter()
                .find(|entry| {
                    entry.artifact_id == output.artifact_id
                        && entry.task_id == task.task_id
                        && entry.attempt_id == attempt_id
                        && entry.ownership_epoch == ownership_epoch
                        && entry.status == fullmag_session::FmsArtifactStatus::Published
                        && entry.object_ref.as_deref() == Some(output.object_ref.as_str())
                        && entry.content_sha256 == output.content_sha256
                        && entry.study_output.as_ref().is_some_and(|study_output| {
                            study_output.step_id == manifest.step_id
                                && study_output.port_id == output.port_id
                                && study_output.case_id == output.case_id
                        })
                })
                .ok_or_else(|| {
                    ApiError::conflict("accepted output is not pinned by the artifact catalog")
                })?;
            let object_ref = artifact
                .object_ref
                .clone()
                .ok_or_else(|| ApiError::conflict("accepted output has no CAS reference"))?;
            let bytes = store
                .cas()
                .get(&object_ref)
                .map_err(|error| ApiError::internal(format!("read accepted output CAS: {error}")))?
                .ok_or_else(|| ApiError::conflict("accepted output CAS object is missing"))?;
            let decoded = fullmag_application::decode_study_artifact(
                &fullmag_application::ResolvedStudyArtifact {
                    artifact_id: output.artifact_id.clone(),
                    object_ref: object_ref.clone(),
                    data_kind: output.data_kind.clone(),
                    codec_id: output.codec_id.clone(),
                    codec_version: output.codec_version.clone(),
                },
                &bytes,
            )
            .map_err(|error| {
                ApiError::conflict(format!("accepted output decode failed: {error}"))
            })?;
            outputs.push(VerifiedOutput {
                task_order,
                object_ref,
                data_kind: output.data_kind,
                decoded,
            });
        }
    }
    Ok(outputs)
}

async fn apply_projection(
    state: &Arc<AppState>,
    context: &ProjectionContext,
    projection: DurableProjection,
) -> Result<(), ApiError> {
    let _transition = state.current_live_session_transition.lock().await;
    let mut next = state
        .current_live_state
        .read()
        .await
        .as_ref()
        .cloned()
        .ok_or_else(|| ApiError::not_found("no active local live workspace"))?;
    if next.session.session_id != context.session_id
        || next.run.as_ref().map(|run| run.run_id.as_str()) != Some(context.run_id.as_str())
        || next.scene_document.as_ref().map(|scene| scene.revision) != Some(context.scene_revision)
        || state
            .current_live_session_epoch
            .load(std::sync::atomic::Ordering::Acquire)
            != context.session_epoch
    {
        return Err(ApiError::conflict_with_code(
            "accepted_projection_current_session_changed",
            "current live session changed while accepted output was being projected",
        ));
    }

    let previous_status = next.session.status.clone();
    let terminal = matches!(projection.status, "completed" | "failed" | "cancelled");
    let mut changed = false;
    if let Some(run) = next.run.as_mut() {
        if run.status != projection.status {
            run.status = projection.status.to_string();
            changed = true;
        }
        if let Some(scalar) = projection.latest_total_energy.as_ref() {
            if scalar.time_s.is_finite() && scalar.time_s >= 0.0 {
                if run.final_time != Some(scalar.time_s) {
                    run.final_time = Some(scalar.time_s);
                    changed = true;
                }
                if run.final_e_total != Some(scalar.value_si) {
                    run.final_e_total = Some(scalar.value_si);
                    changed = true;
                }
            }
        }
        if let Some(fullmag_application::DecodedStudyArtifact::MagnetizationState(state_output)) =
            projection
                .latest_state
                .as_ref()
                .map(|output| &output.decoded)
        {
            if state_output.time_s.is_finite()
                && state_output.time_s >= 0.0
                && run.final_time != Some(state_output.time_s)
            {
                // The observation timestamp is a real value from the pinned
                // accepted state artifact. It is useful even for studies that
                // do not publish an E_total scalar output.
                run.final_time = Some(state_output.time_s);
                changed = true;
            }
        }
    }
    let public_status = if projection.status == "waiting_for_solve" {
        "awaiting_command"
    } else {
        projection.status
    };
    if next.session.status != public_status {
        next.session.status = public_status.to_string();
        changed = true;
    }
    next.runtime_status = crate::session::build_runtime_status_view(public_status);
    if terminal && next.session.finished_at_unix_ms == 0 {
        next.session.finished_at_unix_ms = unix_time_millis_now();
        changed = true;
    }

    if let Some(output) = projection.latest_state.as_ref() {
        if let fullmag_application::DecodedStudyArtifact::MagnetizationState(state_output) =
            &output.decoded
        {
            let frame = accepted_output_frame(&next, state_output.step, state_output.time_s)?;
            let mut fields = crate::types::LatestFields::default();
            fields.insert(
                "m".to_string(),
                json!({
                    "source_step": state_output.step,
                    "source_time_seconds": state_output.time_s,
                    "solver_dt": state_output.solver_dt_s,
                    "source_revision": projection.artifact_catalog_revision,
                    "carrier_fingerprint": state_output.space_fingerprint.clone(),
                    "values": state_output.values.clone(),
                    "layout": state_output.layout.clone(),
                    "provenance": state_output.provenance.clone(),
                    "observation_frame": frame,
                }),
            );
            crate::session::apply_current_live_accepted_field_frame(
                &mut next,
                CurrentLiveFieldFrameRequest {
                    session_id: context.session_id.clone(),
                    latest_fields: Some(fields),
                    replace_latest_fields: false,
                    field_generation: None,
                    preview_fields: None,
                    clear_preview_cache: false,
                },
                frame,
            )?;
            changed = true;
        }
    }
    if !changed && previous_status == projection.status {
        return Ok(());
    }
    next.state_version = next.state_version.saturating_add(1);

    if terminal {
        complete_bound_command(
            state,
            &next,
            projection.command_id.as_deref(),
            projection.status,
        )
        .await?;
    }
    {
        let mut current = state.current_live_state.write().await;
        *current = Some(next.clone());
    }
    crate::router_v2::handlers::sessions::status::record_current_live_heartbeat(state).await;
    let display_revision = state.current_display_selection.read().await.revision;
    let realtime_state =
        crate::current_live_realtime_state_from_snapshot(state, &next, display_revision).await;
    crate::publish_current_live_realtime_batch_changed(state, &realtime_state, true, 100).await
}

fn accepted_output_frame(
    snapshot: &SessionStateResponse,
    source_step: u64,
    source_time_seconds: f64,
) -> Result<crate::schemas::common::AcceptedObservationFrameRef, ApiError> {
    if !source_time_seconds.is_finite() || source_time_seconds < 0.0 {
        return Err(ApiError::conflict(
            "accepted output has invalid observation time",
        ));
    }
    Ok(crate::session::accepted_observation_frame_ref(
        snapshot,
        source_step,
        Some(source_time_seconds),
    ))
}

async fn complete_bound_command(
    state: &AppState,
    snapshot: &SessionStateResponse,
    command_id: Option<&str>,
    status: &str,
) -> Result<(), ApiError> {
    let Some(command_id) = command_id else {
        return Ok(());
    };
    let completion = match status {
        "completed" => crate::types::CommandCompletionState::Completed,
        "cancelled" => crate::types::CommandCompletionState::Cancelled,
        "failed" => crate::types::CommandCompletionState::Failed,
        _ => return Ok(()),
    };
    let completed_at = unix_time_millis_now();
    crate::live_command_journal::mutate(state, snapshot, |records| {
        let mut changed = false;
        for record in records.iter_mut() {
            if record.command.command_id != command_id
                || matches!(
                    record.status,
                    crate::types::CommandLifecycleState::Completed
                        | crate::types::CommandLifecycleState::Failed
                        | crate::types::CommandLifecycleState::Rejected
                )
            {
                continue;
            }
            record.status = match completion {
                crate::types::CommandCompletionState::Failed => {
                    crate::types::CommandLifecycleState::Failed
                }
                _ => crate::types::CommandLifecycleState::Completed,
            };
            record.completed_at_unix_ms = Some(completed_at);
            record.completion_status = Some(completion);
            record.error = (completion == crate::types::CommandCompletionState::Failed)
                .then(|| "accepted Study execution failed".to_string());
            changed = true;
        }
        Ok(((), changed))
    })
    .await
}

fn unix_time_millis_now() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn task(lifecycle: fullmag_session::FmsTaskLifecycle) -> fullmag_session::FmsTaskCatalogEntry {
        fullmag_session::FmsTaskCatalogEntry {
            task_id: "task".into(),
            input_fingerprint: "a".repeat(64),
            lifecycle,
            readiness: Default::default(),
            observation: None,
            attempt_id: None,
            ownership_epoch: None,
            resolved_input_fingerprint: None,
            artifact_ids: Vec::new(),
            resource_id: None,
            coordinator_watermark: None,
            coordinator_genesis: None,
        }
    }

    #[test]
    fn catalog_status_is_fail_closed_for_failed_or_cancelled_tasks() {
        assert_eq!(
            catalog_status(&[task(fullmag_session::FmsTaskLifecycle::Running)]),
            "running"
        );
        assert_eq!(
            catalog_status(&[task(fullmag_session::FmsTaskLifecycle::Cancelled)]),
            "cancelled"
        );
        assert_eq!(
            catalog_status(&[task(fullmag_session::FmsTaskLifecycle::Failed)]),
            "failed"
        );
        assert_eq!(
            catalog_status(&[task(fullmag_session::FmsTaskLifecycle::Succeeded)]),
            "completed"
        );
    }

    #[test]
    fn fdm_output_frame_uses_the_existing_field_admission_revision() {
        let request: crate::types::CurrentLiveSnapshotRequest = serde_json::from_value(json!({
            "session_id": "accepted-fdm-frame",
            "metadata": {"artifact_layout": {"backend": "fdm", "grid_cells": [2, 1, 1]}},
        }))
        .unwrap();
        let mut snapshot = crate::session::default_current_live_state(&request);
        snapshot.mesh_revision = 7;
        let frame = accepted_output_frame(&snapshot, 3, 1e-12).unwrap();
        assert_eq!(frame.topology_revision, "7");
        let mut fields = crate::types::LatestFields::default();
        fields.insert(
            "m".into(),
            json!({
                "values": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                "layout": {"backend": "fdm", "grid_cells": [2, 1, 1]},
                "source_step": 3,
                "source_time_seconds": 1e-12,
                "observation_frame": frame,
            }),
        );
        crate::session::apply_current_live_accepted_field_frame(
            &mut snapshot,
            CurrentLiveFieldFrameRequest {
                session_id: "accepted-fdm-frame".into(),
                latest_fields: Some(fields),
                replace_latest_fields: false,
                field_generation: None,
                preview_fields: None,
                clear_preview_cache: false,
            },
            frame,
        )
        .expect("the producer frame must pass the existing FDM field-source admission");
        assert_eq!(
            snapshot.latest_fields.get("m").unwrap()["values"][1],
            json!([0.0, 1.0, 0.0])
        );
        assert!(snapshot.scalar_rows.is_empty());
    }

    #[test]
    fn manual_startup_poll_preserves_wait_gate_until_compute_release() {
        assert_eq!(
            projected_status_for_gate("waiting_for_compute", false),
            "waiting_for_solve"
        );
        assert_eq!(
            projected_status_for_gate("waiting_for_compute", true),
            "waiting_for_compute"
        );
        assert_eq!(projected_status_for_gate("running", false), "running");
    }

    #[test]
    fn canonical_study_order_wins_over_reused_solver_step_numbers() {
        fn state_output(
            task_order: usize,
            object_ref: &str,
            step: u64,
            time_s: f64,
        ) -> VerifiedOutput {
            VerifiedOutput {
                task_order,
                object_ref: object_ref.into(),
                data_kind: "state".into(),
                decoded: fullmag_application::DecodedStudyArtifact::MagnetizationState(
                    fullmag_application::MagnetizationStateArtifact {
                        step,
                        time_s,
                        solver_dt_s: 0.1,
                        space_fingerprint: "layout".into(),
                        layout: json!({"grid_cells": [1, 1, 1]}),
                        provenance: json!({"source": "accepted"}),
                        values: vec![[0.0, 0.0, 1.0]],
                        native_state_snapshot: None,
                        native_node_map: None,
                    },
                ),
            }
        }

        let outputs = [
            state_output(0, "first", 99, 99.0),
            state_output(1, "second", 1, 0.1),
        ];
        let latest = outputs
            .iter()
            .max_by(|left, right| compare_magnetization_outputs(left, right))
            .expect("one accepted state output");
        assert_eq!(latest.object_ref, "second");
    }

    #[test]
    fn live_binding_rejects_stale_session_epoch_or_scene_revision() {
        let context = ProjectionContext {
            api_instance_id: "api".into(),
            session_id: "session".into(),
            session_epoch: 4,
            scene_revision: 9,
            run_id: "run".into(),
        };
        let specification = json!({
            "parameters": {
                "live_workspace": {
                    "api_instance_id": "api",
                    "session_id": "session",
                    "session_epoch": 4,
                    "scene_revision": 9
                }
            }
        });
        assert!(validate_live_intent(&context, &specification).is_ok());
        let mut stale = specification.clone();
        stale["parameters"]["live_workspace"]["scene_revision"] = json!(10);
        assert!(validate_live_intent(&context, &stale).is_err());
    }

    #[test]
    fn projection_cursor_cannot_skip_a_new_live_run_with_reused_revisions() {
        let context = ProjectionContext {
            api_instance_id: "instance".into(),
            session_id: "session-b".into(),
            session_epoch: 2,
            scene_revision: 7,
            run_id: "run-b".into(),
        };
        let previous = ProjectionCursor {
            api_instance_id: "instance".into(),
            session_id: "session-a".into(),
            session_epoch: 1,
            scene_revision: 7,
            run_id: "run-a".into(),
            run_revision: 1,
            artifact_revision: 1,
            status: "running",
            latest_output_identity: None,
        };
        assert!(!cursor_matches_context(&previous, &context));
    }
}
