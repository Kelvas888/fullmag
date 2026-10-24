//! Magnetization continuation between live accepted commands (ADR 0068 F5).
//!
//! Every live `run`/`relax` command is its own accepted run. The selected
//! step publishes its final magnetization on the `final_state` port, and the
//! next command pins that exact CAS object as its initial state when the
//! accepted execution plan has the same magnetization layout. The decision is
//! taken here, before the RunIntent is published, with the same predicate the
//! worker applies (`fullmag_runner::materialize_study_magnetization_input`),
//! so a layout mismatch selects the authored state instead of failing the
//! command. Semantics: docs/physics/0925-live-session-magnetization-continuation.md.

use fullmag_application::{DecodedStudyArtifact, ResolvedStudyArtifact};
use fullmag_authoring::{
    StudyInputPort, StudyInputSource, StudyOutputPort, StudyPortDataKind, StudyStep,
};
use fullmag_session::{FmsArtifactStatus, FmsTaskLifecycle, SessionStore};
use serde_json::{json, Value};

/// Output port carrying the final state of a live command (FEM requires this id).
pub(crate) const FINAL_STATE_PORT: &str = "final_state";
/// Input port pinning the previous command's final state.
pub(crate) const INITIAL_STATE_PORT: &str = "initial_state";
const OUTPUT_CASE_ID: &str = "default";

/// The verified final state of a previous live command.
#[derive(Debug, Clone)]
pub(crate) struct ContinuationSource {
    pub run_id: String,
    pub step_id: String,
    pub artifact_id: String,
    pub content_sha256: String,
    pub layout: Value,
    pub values: Vec<[f64; 3]>,
}

/// Whether a live command starts from the previous final state or the authored one.
#[derive(Debug, Clone)]
pub(crate) enum InitialStateDecision {
    Continuation(ContinuationSource),
    Authored { reason: String },
}

impl InitialStateDecision {
    /// Provenance recorded in the RunSpec `live_workspace.initial_state_source`.
    pub(crate) fn provenance(&self) -> Value {
        match self {
            Self::Continuation(source) => json!({
                "kind": "continuation",
                "previous_run_id": source.run_id,
                "previous_step_id": source.step_id,
                "artifact_id": source.artifact_id,
                "content_sha256": source.content_sha256,
            }),
            Self::Authored { reason } => json!({"kind": "authored", "reason": reason}),
        }
    }
}

/// Make the selected step publish its final magnetization.
pub(crate) fn declare_final_state_output(step: &mut StudyStep) {
    if !step.outputs.iter().any(|port| port.port_id == FINAL_STATE_PORT) {
        step.outputs.push(StudyOutputPort {
            port_id: FINAL_STATE_PORT.to_string(),
            data_kind: StudyPortDataKind::State,
        });
    }
}

/// Pin the continuation source as the selected step's initial state.
pub(crate) fn declare_pinned_initial_state(step: &mut StudyStep, source: &ContinuationSource) {
    step.inputs.retain(|port| port.port_id != INITIAL_STATE_PORT);
    step.inputs.push(StudyInputPort {
        port_id: INITIAL_STATE_PORT.to_string(),
        data_kind: StudyPortDataKind::State,
        required: true,
        source: StudyInputSource::PinnedArtifact {
            artifact_id: source.artifact_id.clone(),
            content_sha256: source.content_sha256.clone(),
        },
    });
}

/// Decide the initial state of a command whose accepted plan is `plan`.
///
/// `previous_run_id` is the session's latest live run as seen by the API; it is
/// only a hint and is verified durably (same session and epoch, every task
/// succeeded, published and decodable `final_state`).
pub(crate) fn decide_initial_state(
    store: &SessionStore,
    previous_run_id: Option<&str>,
    session_id: &str,
    session_epoch: u64,
    plan: &fullmag_ir::ExecutionPlanIR,
) -> InitialStateDecision {
    let Some(previous_run_id) = previous_run_id else {
        return authored("no previous live command in this session");
    };
    let source = match load_final_state(store, previous_run_id, session_id, session_epoch) {
        Ok(Some(source)) => source,
        Ok(None) => return authored("previous live command published no final state"),
        Err(reason) => return authored(&reason),
    };
    match fullmag_runner::materialize_study_magnetization_input(plan, &source.layout, &source.values) {
        Ok(_) => InitialStateDecision::Continuation(source),
        Err(error) => authored(&format!("discretization changed: {}", error.message)),
    }
}

fn authored(reason: &str) -> InitialStateDecision {
    InitialStateDecision::Authored {
        reason: reason.to_string(),
    }
}

fn load_final_state(
    store: &SessionStore,
    run_id: &str,
    session_id: &str,
    session_epoch: u64,
) -> Result<Option<ContinuationSource>, String> {
    let intent = store
        .read_run_intent(run_id)
        .map_err(|error| format!("previous run intent unreadable: {error}"))?
        .ok_or_else(|| "previous run intent is missing".to_string())?;
    let live = intent
        .specification
        .pointer("/parameters/live_workspace")
        .ok_or_else(|| "previous run is not a live command".to_string())?;
    if live.get("session_id").and_then(Value::as_str) != Some(session_id)
        || live.get("session_epoch").and_then(Value::as_u64) != Some(session_epoch)
    {
        return Err("previous run belongs to another session or epoch".into());
    }
    let catalog = store
        .read_run_catalog(run_id)
        .map_err(|error| format!("previous run catalog unreadable: {error}"))?
        .ok_or_else(|| "previous run catalog is missing".to_string())?;
    let mut succeeded = catalog
        .tasks
        .iter()
        .filter(|task| task.lifecycle == FmsTaskLifecycle::Succeeded);
    let Some(task) = succeeded.next() else {
        return Err("previous live command did not succeed".into());
    };
    if succeeded.next().is_some() {
        return Err("previous live run has more than one completed task".into());
    }
    let (Some(attempt_id), Some(ownership_epoch)) = (task.attempt_id.as_deref(), task.ownership_epoch)
    else {
        return Err("previous live task has no attempt identity".into());
    };
    let artifacts = store
        .read_artifact_catalog(run_id)
        .map_err(|error| format!("previous artifact catalog unreadable: {error}"))?
        .ok_or_else(|| "previous artifact catalog is missing".to_string())?;
    let mut manifests = artifacts.entries.iter().filter(|entry| {
        entry.artifact_type == "study_output_manifest"
            && entry.task_id == task.task_id
            && entry.attempt_id == attempt_id
            && entry.ownership_epoch == ownership_epoch
            && entry.status == FmsArtifactStatus::Published
    });
    let Some(manifest_entry) = manifests.next() else {
        return Ok(None);
    };
    if manifests.next().is_some() {
        return Err("previous live task has ambiguous output manifests".into());
    }
    let manifest_ref = manifest_entry
        .object_ref
        .as_deref()
        .filter(|object_ref| *object_ref == manifest_entry.content_sha256)
        .ok_or_else(|| "previous output manifest digest is not pinned".to_string())?;
    let manifest_bytes = store
        .cas()
        .get(manifest_ref)
        .map_err(|error| format!("previous output manifest unreadable: {error}"))?
        .ok_or_else(|| "previous output manifest is missing from CAS".to_string())?;
    let manifest: fullmag_session::FmsStudyOutputManifest = serde_json::from_slice(&manifest_bytes)
        .map_err(|error| format!("previous output manifest is invalid: {error}"))?;
    manifest
        .validate()
        .map_err(|error| format!("previous output manifest failed validation: {error}"))?;
    if manifest.run_id != run_id
        || manifest.task_id != task.task_id
        || manifest.attempt_id != attempt_id
        || manifest.ownership_epoch != ownership_epoch
    {
        return Err("previous output manifest ownership identity mismatch".into());
    }
    let Some(output) = manifest
        .outputs
        .iter()
        .find(|output| output.port_id == FINAL_STATE_PORT && output.case_id == OUTPUT_CASE_ID && output.data_kind == "state")
    else {
        return Ok(None);
    };
    let pinned = artifacts.entries.iter().any(|entry| {
        entry.artifact_id == output.artifact_id
            && entry.status == FmsArtifactStatus::Published
            && entry.object_ref.as_deref() == Some(output.object_ref.as_str())
            && entry.content_sha256 == output.content_sha256
    });
    if !pinned || output.object_ref != output.content_sha256 {
        return Err("previous final state is not pinned by the artifact catalog".into());
    }
    let bytes = store
        .cas()
        .get(&output.object_ref)
        .map_err(|error| format!("previous final state unreadable: {error}"))?
        .ok_or_else(|| "previous final state is missing from CAS".to_string())?;
    let decoded = fullmag_application::decode_study_artifact(
        &ResolvedStudyArtifact {
            artifact_id: output.artifact_id.clone(),
            object_ref: output.object_ref.clone(),
            data_kind: output.data_kind.clone(),
            codec_id: output.codec_id.clone(),
            codec_version: output.codec_version.clone(),
        },
        &bytes,
    )
    .map_err(|error| format!("previous final state decode failed: {error}"))?;
    let DecodedStudyArtifact::MagnetizationState(state) = decoded else {
        return Err("previous final state is not a magnetization state".into());
    };
    Ok(Some(ContinuationSource {
        run_id: run_id.to_string(),
        step_id: manifest.step_id.clone(),
        artifact_id: output.artifact_id.clone(),
        content_sha256: output.content_sha256.clone(),
        layout: state.layout,
        values: state.values,
    }))
}
