//! Interactive session supervisor.
//!
//! Owns the session-level context (IDs, paths, timestamps, plan summaries)
//! needed by the interactive command loop to publish session/run manifests.
//!
//! The supervisor does NOT own the runtime itself — that stays in
//! `InteractiveRuntimeHost`. Instead, the supervisor provides the context
//! struct that the runtime actor needs when publishing state transitions.

use std::path::PathBuf;

use crate::step_utils::stage_artifact_dir;
use crate::types::*;

/// Session-level context needed to build manifests during interactive dispatch.
///
/// This struct is populated once when the interactive mode begins and
/// passed by reference to the command loop and state-transition helpers.
pub(crate) struct InteractiveSessionContext {
    pub session_id: String,
    pub run_id: String,
    pub interactive_requested: bool,
    pub script_path: PathBuf,
    pub final_problem_name: String,
    pub runtime_selection: SessionRuntimeSelection,
    pub artifact_dir: PathBuf,
    #[allow(dead_code)]
    pub workspace_dir: PathBuf,
    pub started_at_unix_ms: u128,
    #[allow(dead_code)]
    pub field_every_n: u64,
}

impl InteractiveSessionContext {
    /// Build a session manifest with the given status.
    pub(crate) fn build_session(
        &self,
        status: &str,
        plan_summary: &serde_json::Value,
        now_unix_ms: u128,
    ) -> SessionManifest {
        crate::orchestrator::build_session_manifest(
            &self.session_id,
            &self.run_id,
            status,
            self.interactive_requested,
            &self.script_path,
            &self.final_problem_name,
            &self.runtime_selection,
            &self.artifact_dir,
            self.started_at_unix_ms,
            now_unix_ms,
            plan_summary.clone(),
        )
    }

    /// Build a run manifest from aggregated steps with the given status.
    pub(crate) fn build_run(
        &self,
        status: &str,
        aggregated_steps: &[fullmag_runner::StepStats],
    ) -> RunManifest {
        crate::orchestrator::run_manifest_from_steps(
            &self.run_id,
            &self.session_id,
            status,
            &self.artifact_dir,
            aggregated_steps,
        )
    }

    /// Create a stage artifact directory path.
    #[allow(dead_code)]
    pub(crate) fn stage_artifact_dir(
        &self,
        stage_index: usize,
        stage_count: usize,
        entrypoint_kind: &str,
    ) -> PathBuf {
        stage_artifact_dir(
            &self.workspace_dir,
            &self.artifact_dir,
            stage_index,
            stage_count,
            entrypoint_kind,
        )
    }
}

/// Recover the full runtime selection already recorded in a session manifest.
///
/// Interactive transitions use this as their starting selection so publishing
/// an awaiting or paused session does not replace the accepted device or its
/// resolved execution provenance with a synthetic `auto` request.
pub(crate) fn runtime_selection_from_manifest(
    manifest: &SessionManifest,
) -> SessionRuntimeSelection {
    SessionRuntimeSelection {
        requested_backend: manifest.requested_backend.clone(),
        explicit_selection: manifest.explicit_selection,
        authored_requested_device: manifest.authored_requested_device.clone(),
        requested_device: manifest.requested_device.clone(),
        requested_precision: manifest.requested_precision.clone(),
        requested_mode: manifest.requested_mode.clone(),
        requested_cpu_threads: manifest.requested_cpu_threads,
        resolved_backend: manifest.resolved_backend.clone(),
        resolved_device: manifest.resolved_device.clone(),
        resolved_precision: manifest.resolved_precision.clone(),
        resolved_mode: manifest.resolved_mode.clone(),
        resolved_runtime_family: manifest.resolved_runtime_family.clone(),
        resolved_engine_id: manifest.resolved_engine_id.clone(),
        resolved_worker: manifest.resolved_worker.clone(),
        resolved_cpu_threads: manifest.resolved_cpu_threads,
        resolved_fallback: manifest.resolved_fallback.clone(),
        fem_crossover_decision: manifest.fem_crossover_decision.clone(),
    }
}

/// Outcome of a single iteration of the interactive command loop.
#[derive(Debug)]
#[allow(dead_code)]
pub(crate) enum InteractiveLoopOutcome {
    /// Continue processing commands.
    Continue,
    /// The interactive session should close.
    Close,
}

/// Holds a paused interactive stage that can be resumed.
#[allow(dead_code)]
pub(crate) struct PausedInteractiveStage {
    pub command: SessionCommand,
    pub source_kind: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn awaiting_and_paused_manifests_keep_the_full_runtime_selection() {
        let mut cpu_selection = crate::orchestrator::requested_runtime_selection(
            "fdm",
            true,
            "cpu",
            "double",
            "strict",
            Some(4),
        );
        cpu_selection.resolved_backend = Some("fdm".to_string());
        cpu_selection.resolved_device = Some("cpu".to_string());
        cpu_selection.resolved_precision = Some("double".to_string());
        cpu_selection.resolved_mode = Some("strict".to_string());
        cpu_selection.resolved_runtime_family = Some("fdm_cpu".to_string());
        cpu_selection.resolved_engine_id = Some("fdm_cpu_reference".to_string());
        cpu_selection.resolved_worker = Some("local".to_string());
        cpu_selection.resolved_cpu_threads = Some(4);

        let mut fallback_selection = crate::orchestrator::requested_runtime_selection(
            "fdm",
            false,
            "auto",
            "double",
            "strict",
            Some(8),
        );
        fallback_selection.resolved_backend = Some("fdm".to_string());
        fallback_selection.resolved_device = Some("cpu".to_string());
        fallback_selection.resolved_precision = Some("double".to_string());
        fallback_selection.resolved_mode = Some("strict".to_string());
        fallback_selection.resolved_runtime_family = Some("fdm_cpu".to_string());
        fallback_selection.resolved_engine_id = Some("fdm_cpu_reference".to_string());
        fallback_selection.resolved_worker = Some("local".to_string());
        fallback_selection.resolved_cpu_threads = Some(8);
        fallback_selection.resolved_fallback = Some(fullmag_runner::ResolvedFallback {
            occurred: true,
            original_engine: "fdm_cuda".to_string(),
            fallback_engine: "fdm_cpu_reference".to_string(),
            reason: "requested_engine_unavailable".to_string(),
            message: "using the available CPU engine".to_string(),
        });

        for (selection, expected_requested_device, expected_explicit, expected_threads) in [
            (cpu_selection, "cpu", true, 4),
            (fallback_selection, "auto", false, 8),
        ] {
            let initial_manifest = crate::orchestrator::build_session_manifest(
                "session-test",
                "run-test",
                "running",
                true,
                std::path::Path::new("fixture.py"),
                "fixture",
                &selection,
                std::path::Path::new("artifacts"),
                10,
                10,
                serde_json::json!({"status": "running"}),
            );
            let context = InteractiveSessionContext {
                session_id: initial_manifest.session_id.clone(),
                run_id: initial_manifest.run_id.clone(),
                interactive_requested: initial_manifest.interactive_session_requested,
                script_path: std::path::PathBuf::from(&initial_manifest.script_path),
                final_problem_name: initial_manifest.problem_name.clone(),
                runtime_selection: runtime_selection_from_manifest(&initial_manifest),
                artifact_dir: std::path::PathBuf::from(&initial_manifest.artifact_dir),
                workspace_dir: std::path::PathBuf::from("workspace"),
                started_at_unix_ms: initial_manifest.started_at_unix_ms,
                field_every_n: 1,
            };

            for status in ["awaiting_command", "paused"] {
                let manifest =
                    context.build_session(status, &serde_json::json!({"status": status}), 20);
                assert_eq!(manifest.status, status);
                assert_eq!(manifest.requested_device, expected_requested_device);
                assert_eq!(manifest.explicit_selection, expected_explicit);
                assert_eq!(manifest.resolved_device.as_deref(), Some("cpu"));
                assert_eq!(manifest.requested_cpu_threads, Some(expected_threads));
                assert_eq!(manifest.resolved_cpu_threads, Some(expected_threads));
                assert_eq!(manifest.resolved_fallback, selection.resolved_fallback);
                assert_eq!(
                    manifest.resolved_engine_id.as_deref(),
                    Some("fdm_cpu_reference")
                );
            }
        }
    }
}
