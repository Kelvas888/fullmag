//! User output publication kept separate from immutable worker receipts/CAS.

use anyhow::{bail, Context, Result};
use fullmag_application::TaskClaim;
use fullmag_ir::{OutputStorageIR, ProblemIR};
use fullmag_runner::project_storage::ProjectStorageLease;
use fullmag_runner::script_store::{ScriptStore, StepRecord};
use fullmag_session::SessionStore;
use fullmag_workspace_inspect::manifest::{
    collect_outputs, write_run_manifest, RunManifest, RunSource,
};
use fullmag_workspace_inspect::read_layout;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

pub(crate) struct AcceptedProjectStorage {
    lease: ProjectStorageLease,
    data_root: PathBuf,
    finalized: bool,
    manifest: RunManifest,
    outcome: Option<(&'static str, Option<String>)>,
    /// The run's `<script>.zarr` and this step's identity in it.
    script: Option<(ScriptStore, StepRecord)>,
}

/// Where an accepted run writes: the output directory, the script store name,
/// and the collision policy of that store.
struct StoreTarget {
    settings: OutputStorageIR,
    source_dir: PathBuf,
    base: PathBuf,
    stem: String,
}

/// `fullmag-run.json` of an accepted project run, as known when its results
/// leaf is reserved. `source.path` stays empty: the accepted run knows the
/// project id and definition revision, not the `.fms` file it was opened from.
/// `requested` is the accepted request; `resolved` is the backend of the
/// accepted plan and the device of the claimed resource lease.
pub(crate) fn accepted_run_manifest(
    snapshot: &fullmag_application::ProjectSnapshot,
    requested: &fullmag_application::RequestedExecution,
    specification_fingerprint: &str,
    claim: &TaskClaim,
    resolved_backend: fullmag_ir::BackendTarget,
) -> RunManifest {
    let mut manifest = RunManifest::new(
        format!("{}-{}", claim.run_id.as_str(), claim.ownership_epoch.value()),
        RunSource {
            kind: "project".into(),
            path: String::new(),
            sha256: Some(snapshot.definition_sha256.clone()),
            project_id: Some(snapshot.project_id.as_str().to_string()),
            revision: Some(snapshot.definition_revision),
        },
        fullmag_build_info::version(),
        fullmag_workspace::now_rfc3339(),
    );
    manifest.requested = serde_json::to_value(requested).unwrap_or(serde_json::Value::Null);
    manifest.resolved = serde_json::json!({
        "backend": resolved_backend,
        "device": claim.lease.kind,
        "precision": requested.precision,
        "mode": requested.mode,
    });
    manifest.launched_by = Some("api".into());
    manifest.run_spec_sha256 = Some(specification_fingerprint.to_string());
    manifest
}

impl AcceptedProjectStorage {
    fn configuration(
        problem: &ProblemIR,
        store: &SessionStore,
        step_id: &str,
    ) -> Result<Option<StoreTarget>> {
        let Some(value) = problem.problem_meta.runtime_metadata.get("output_storage") else {
            // Legacy accepted runs keep their original artifact contract. New
            // UI/Python projects carry an explicit canonical storage policy.
            return Ok(None);
        };
        let mut settings: OutputStorageIR =
            serde_json::from_value(value.clone()).context("read accepted project output policy")?;
        settings
            .validate()
            .map_err(|errors| anyhow::anyhow!(errors.join("; ")))?;
        let expected = match settings.data_format {
            fullmag_ir::OutputDataFormatIR::Zarr => fullmag_ir::AutosaveFormatIR::Zarr,
            fullmag_ir::OutputDataFormatIR::Hdf5 => fullmag_ir::AutosaveFormatIR::Hdf5,
        };
        if problem
            .study
            .sampling()
            .stage_autosave
            .as_ref()
            .is_some_and(|policy| policy.format != expected)
        {
            bail!("accepted stage format conflicts with project output_storage; no solver was launched");
        }
        fullmag_session::repository_path::validate_store_id(step_id)?;
        let script_dir = problem
            .problem_meta
            .runtime_metadata
            .get("output_storage_source_dir")
            .and_then(serde_json::Value::as_str)
            .map(PathBuf::from);
        let source_dir = script_dir.clone().unwrap_or_else(|| store.root().to_path_buf());
        // script.py -> script.zarr, as mumax3 writes script.mx3 -> script.zarr.
        let stem = problem
            .problem_meta
            .runtime_metadata
            .get("output_storage_source_stem")
            .and_then(serde_json::Value::as_str)
            .filter(|stem| !stem.is_empty())
            .unwrap_or(problem.problem_meta.name.as_str())
            .to_string();
        fullmag_runner::script_store::validate_store_stem(&stem).map_err(anyhow::Error::msg)?;
        let requested_base = settings
            .output_dir
            .as_ref()
            .map(PathBuf::from)
            .or(script_dir)
            .unwrap_or_else(|| store.root().join("project-results"));
        let base = if requested_base.is_absolute() {
            requested_base
        } else {
            source_dir.join(requested_base)
        };
        // A Zarr run owns <base>/<stem>.zarr only, so scratch may sit beside it in <base>.
        let zarr = settings.data_format == fullmag_ir::OutputDataFormatIR::Zarr;
        let checked = if zarr { base.join(format!("{stem}.zarr")) } else { base };
        let mut checked_settings = settings.clone();
        checked_settings.output_dir = Some(checked.to_string_lossy().into_owned());
        let (checked, temp_parent) = fullmag_runner::project_storage::preflight_project_storage(
            &checked_settings,
            &checked,
            &source_dir,
        )
        .map_err(anyhow::Error::msg)?;
        let base = if zarr {
            checked
                .parent()
                .context("script store has no parent directory")?
                .to_path_buf()
        } else {
            checked
        };
        settings.temp_dir = Some(temp_parent.to_string_lossy().into_owned());
        Ok(Some(StoreTarget { settings, source_dir, base, stem }))
    }

    /// Validate paths/capabilities before reserving the durable worker attempt.
    pub(crate) fn preflight(
        problem: &ProblemIR,
        store: &SessionStore,
        claim: &TaskClaim,
        step_id: &str,
    ) -> Result<()> {
        let Some(target) = Self::configuration(problem, store, step_id)? else {
            return Ok(());
        };
        if target.settings.data_format != fullmag_ir::OutputDataFormatIR::Zarr {
            return Self::preflight_leaf(target, claim, step_id);
        }
        let script = target.base.join(format!("{}.zarr", target.stem));
        if target.settings.existing_output == fullmag_ir::ExistingOutputIR::Error
            && script.exists()
            && ScriptStore::owner_of(&script).map_err(anyhow::Error::msg)?.as_deref()
                != Some(claim.run_id.as_str())
        {
            bail!(
                "accepted project result location already exists: {}",
                script.display()
            );
        }
        Ok(())
    }

    pub(crate) fn prepare(
        problem: &ProblemIR,
        store: &SessionStore,
        claim: &TaskClaim,
        step_id: &str,
        manifest: RunManifest,
    ) -> Result<Option<Self>> {
        let Some(target) = Self::configuration(problem, store, step_id)? else {
            return Ok(None);
        };
        if target.settings.data_format != fullmag_ir::OutputDataFormatIR::Zarr {
            return Self::prepare_leaf(target, claim, step_id, manifest).map(Some);
        }
        let StoreTarget { mut settings, source_dir, base, stem } = target;
        // All steps of one run append to one <script>.zarr; this step's attempt
        // descriptors go to its hidden .fullmag/ directory.
        let script = ScriptStore::acquire(
            &base,
            &stem,
            claim.run_id.as_str(),
            settings.existing_output,
            &fullmag_workspace::now_rfc3339(),
        )
        .map_err(anyhow::Error::msg)
        .context("reserve the run's script store")?;
        script.mark_running().map_err(anyhow::Error::msg)?;
        let leaf = script.internal_dir().join(format!(
            "{step_id}-attempt-{}",
            claim.ownership_epoch.value()
        ));
        settings.output_dir = Some(leaf.to_string_lossy().into_owned());
        settings.existing_output = fullmag_ir::ExistingOutputIR::Timestamp;
        let run_id = format!(
            "{}-{}",
            claim.run_id.as_str(),
            claim.ownership_epoch.value()
        );
        let lease = ProjectStorageLease::prepare(&settings, &leaf, &source_dir, &run_id)
            .map_err(anyhow::Error::msg)
            .context("reserve accepted project output and scratch")?;
        let data_root = lease.resolved().temp_dir.join("data");
        fs::create_dir(&data_root).context("create owned staging directory for numerical data")?;
        let kind = serde_json::to_value(&problem.study)
            .ok()
            .and_then(|study| study.get("kind").and_then(|kind| kind.as_str()).map(str::to_owned))
            .unwrap_or_else(|| "unknown".into());
        let record = StepRecord {
            step_id: step_id.to_string(),
            advances_time: kind == "time_evolution",
            kind,
            end_time_s: 0.0,
            steps: 0,
            provenance: None,
            finished_at: String::new(),
        };
        let mut storage = Self {
            lease,
            data_root,
            finalized: false,
            manifest,
            outcome: None,
            script: Some((script, record)),
        };
        storage.write_manifest();
        Ok(Some(storage))
    }

    /// HDF5 keeps one published leaf per step: `<output_dir>/<run_id>/<step_id>-attempt-<epoch>`.
    fn preflight_leaf(target: StoreTarget, claim: &TaskClaim, step_id: &str) -> Result<()> {
        let StoreTarget { mut settings, source_dir, base, .. } = target;
        let leaf = base.join(claim.run_id.as_str()).join(format!(
            "{step_id}-attempt-{}",
            claim.ownership_epoch.value()
        ));
        settings.output_dir = Some(leaf.to_string_lossy().into_owned());
        fullmag_runner::project_storage::preflight_project_storage(&settings, &leaf, &source_dir)
            .map_err(anyhow::Error::msg)?;
        if settings.existing_output == fullmag_ir::ExistingOutputIR::Error && leaf.exists() {
            bail!(
                "accepted project result location already exists: {}",
                leaf.display()
            );
        }
        Ok(())
    }

    fn prepare_leaf(
        target: StoreTarget,
        claim: &TaskClaim,
        step_id: &str,
        manifest: RunManifest,
    ) -> Result<Self> {
        let StoreTarget { mut settings, source_dir, base, .. } = target;
        fullmag_runner::project_storage::initialize_result_container(&base, settings.data_format)
            .map_err(anyhow::Error::msg)?;
        let run_root = base.join(claim.run_id.as_str());
        fullmag_runner::project_storage::initialize_result_container(
            &run_root,
            settings.data_format,
        )
        .map_err(anyhow::Error::msg)?;
        let leaf = run_root.join(format!(
            "{step_id}-attempt-{}",
            claim.ownership_epoch.value()
        ));
        settings.output_dir = Some(leaf.to_string_lossy().into_owned());
        let run_id = format!(
            "{}-{}",
            claim.run_id.as_str(),
            claim.ownership_epoch.value()
        );
        let lease = ProjectStorageLease::prepare(&settings, &leaf, &source_dir, &run_id)
            .map_err(anyhow::Error::msg)
            .context("reserve accepted project output and scratch")?;
        let data_root = lease.resolved().temp_dir.join("data");
        fs::create_dir(&data_root).context("create owned staging directory for numerical data")?;
        let storage = Self {
            lease,
            data_root,
            finalized: false,
            manifest,
            outcome: None,
            script: None,
        };
        storage.write_manifest();
        Ok(storage)
    }

    /// Record how the run ended when it is not plain success or failure.
    pub(crate) fn note_outcome(&mut self, status: &'static str, error: Option<String>) {
        self.outcome = Some((status, error));
    }

    /// Best effort, like the script manifest: a failed write is reported and
    /// never changes the outcome. Only the reserved results leaf is written.
    fn write_manifest(&self) {
        let dir = &self.lease.resolved().output_dir;
        if let Err(error) = write_run_manifest(dir, &self.manifest) {
            tracing::warn!("could not write the run manifest in {}: {error}", dir.display());
        }
    }

    fn write_final_manifest(&mut self, status: &str, error: Option<String>) {
        let dir = self.lease.resolved().output_dir.clone();
        self.manifest.status = status.to_string();
        self.manifest.error = error;
        self.manifest.finished_at = Some(fullmag_workspace::now_rfc3339());
        self.manifest.stages = read_layout(&dir).stages;
        self.manifest.outputs = collect_outputs(&dir);
        self.write_manifest();
    }

    pub(crate) fn data_root(&self) -> &Path {
        &self.data_root
    }

    pub(crate) fn resolved(&self) -> &fullmag_runner::project_storage::ResolvedOutputStorage {
        self.lease.resolved()
    }

    /// The runner has joined its artifact writer before returning. Publish
    /// finalized data and retain immutable attempt receipts in their store.
    pub(crate) fn finish(&mut self, success: bool, attempt_dir: &Path) -> Result<()> {
        if self.finalized {
            return Ok(());
        }
        let publication = if success {
            (|| {
                let descriptor = serde_json::json!({
                    "schema": "fullmag.accepted_project_output.v1",
                    "resolved_output_storage": self.resolved(),
                    "attempt_receipt_directory": attempt_dir,
                });
                let mut file = OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(self.data_root.join("run.json"))?;
                file.write_all(&serde_json::to_vec_pretty(&descriptor)?)?;
                file.sync_all()?;
                // The final-state artifact is an editable/reproducible output;
                // the store still owns the authoritative accepted state/CAS.
                let final_state = attempt_dir.join("solver").join("m_final.json");
                if final_state.is_file() {
                    let solver = self.data_root.join("solver");
                    fs::create_dir(&solver)?;
                    fullmag_runner::project_storage::copy_owned_artifact(
                        attempt_dir,
                        Path::new("solver/m_final.json"),
                        &solver.join("m_final.json"),
                    )
                    .map_err(anyhow::Error::msg)?;
                }
                if let Some((script, record)) = &self.script {
                    let provenance = serde_json::json!({
                        "requested": self.manifest.requested,
                        "resolved": self.manifest.resolved,
                    });
                    merge_step_data(script, record, &self.data_root, attempt_dir, provenance)?;
                }
                self.lease
                    .publish_directory(&self.data_root)
                    .map_err(anyhow::Error::msg)
            })()
        } else {
            Ok(())
        };
        let finished = self
            .lease
            .finish(success && publication.is_ok())
            .map_err(anyhow::Error::msg)
            .context("finalize accepted project temporary storage");
        self.finalized = true;
        let (status, error) = match (&self.outcome, &publication) {
            (Some((status, error)), _) => (*status, error.clone()),
            (None, Err(error)) => ("failed", Some(error.to_string())),
            (None, Ok(())) if success => ("completed", None),
            (None, Ok(())) => ("failed", None),
        };
        if status != "completed" {
            if let Some((script, record)) = &self.script {
                if let Err(record_error) = script.record_failure(
                    &record.step_id,
                    status,
                    error.as_deref(),
                    &fullmag_workspace::now_rfc3339(),
                ) {
                    tracing::warn!("could not record the step outcome in the script store: {record_error}");
                }
            }
        }
        self.write_final_manifest(status, error);
        finished?;
        publication.context("publish accepted project numerical data")
    }
}

/// Append a successful step's staged arrays to the run's `<script>.zarr`. The
/// staged `*.zarr` directories are removed afterwards, so the hidden attempt
/// leaf keeps descriptors only and never a second copy of the data.
fn merge_step_data(
    script: &ScriptStore,
    record: &StepRecord,
    data_root: &Path,
    attempt_dir: &Path,
    provenance: serde_json::Value,
) -> Result<()> {
    let mut record = record.clone();
    let final_state = attempt_dir.join("solver").join("m_final.json");
    if final_state.is_file() {
        let state: serde_json::Value = serde_json::from_slice(&fs::read(&final_state)?)
            .context("read the step's final state for the script store")?;
        record.end_time_s = state.get("time").and_then(serde_json::Value::as_f64).unwrap_or(0.0);
        record.steps = state.get("step").and_then(serde_json::Value::as_u64).unwrap_or(0);
    }
    record.provenance = Some(provenance);
    record.finished_at = fullmag_workspace::now_rfc3339();
    script
        .merge_step(data_root, &record)
        .map_err(anyhow::Error::msg)
        .context("append the step outputs to the script store")?;
    for entry in fs::read_dir(data_root)? {
        let path = entry?.path();
        if path.is_dir() && path.extension().is_some_and(|ext| ext == "zarr") {
            fs::remove_dir_all(&path)?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use fullmag_application::{
        AttemptId, LeaseToken, OwnershipEpoch, ProjectId, ProjectSnapshot, RequestedExecution,
        ResourceBudget, ResourceKind, ResourceLease, RunId, TaskId,
    };
    use fullmag_workspace_inspect::manifest::read_run_manifest;

    fn claim(kind: ResourceKind) -> TaskClaim {
        TaskClaim {
            run_id: RunId::parse("run-test").unwrap(),
            task_id: TaskId::parse("task-test").unwrap(),
            attempt_id: AttemptId::parse("attempt-test").unwrap(),
            ownership_epoch: OwnershipEpoch::new(2).unwrap(),
            lease: ResourceLease {
                resource_id: "res-test".into(),
                kind,
                budget: ResourceBudget {
                    cpu_millis: 1000,
                    memory_bytes: 1 << 20,
                    gpu_memory_bytes: 0,
                    storage_bytes: 1 << 20,
                },
                lease_token: LeaseToken::parse("lease-test").unwrap(),
                heartbeat_sequence: 1,
            },
        }
    }

    fn manifest() -> RunManifest {
        let snapshot = ProjectSnapshot {
            project_id: ProjectId::parse("project-0123456789abcdef").unwrap(),
            definition_revision: 7,
            definition_sha256: "ab".repeat(32),
        };
        let requested = RequestedExecution {
            backend: "auto".into(),
            device: "auto".into(),
            precision: "double".into(),
            mode: "strict".into(),
            minimum_resources: None,
        };
        accepted_run_manifest(
            &snapshot,
            &requested,
            &"cd".repeat(32),
            &claim(ResourceKind::Cpu),
            fullmag_ir::BackendTarget::Fdm,
        )
    }

    fn reserve(root: &Path) -> (AcceptedProjectStorage, PathBuf) {
        let settings = OutputStorageIR::default();
        let (mut settings, temp_parent) = {
            let (_, temp_parent) = fullmag_runner::project_storage::preflight_project_storage(
                &settings,
                &root.join("results"),
                root,
            )
            .unwrap();
            (settings, temp_parent)
        };
        settings.temp_dir = Some(temp_parent.to_string_lossy().into_owned());
        let base = root.join("results");
        fullmag_runner::project_storage::initialize_result_container(&base, settings.data_format)
            .unwrap();
        let leaf = base.join("run-test").join("step-attempt-2");
        fullmag_runner::project_storage::initialize_result_container(
            leaf.parent().unwrap(),
            settings.data_format,
        )
        .unwrap();
        settings.output_dir = Some(leaf.to_string_lossy().into_owned());
        let lease = ProjectStorageLease::prepare(&settings, &leaf, root, "run-test-2").unwrap();
        let data_root = lease.resolved().temp_dir.join("data");
        fs::create_dir(&data_root).unwrap();
        let storage = AcceptedProjectStorage {
            lease,
            data_root,
            finalized: false,
            manifest: manifest(),
            outcome: None,
            script: None,
        };
        storage.write_manifest();
        (storage, leaf)
    }

    #[test]
    fn the_manifest_links_a_project_run_by_id_and_revision() {
        let manifest = manifest();
        assert_eq!(manifest.schema, "fullmag.run_manifest.v1");
        assert_eq!(manifest.run_id, "run-test-2");
        assert_eq!(manifest.source.kind, "project");
        assert_eq!(manifest.source.path, "");
        assert_eq!(
            manifest.source.project_id.as_deref(),
            Some("project-0123456789abcdef")
        );
        assert_eq!(manifest.source.revision, Some(7));
        assert_eq!(manifest.source.sha256, Some("ab".repeat(32)));
        assert_eq!(manifest.run_spec_sha256, Some("cd".repeat(32)));
        // Requested stays what was asked; resolved is what the plan and lease say.
        assert_eq!(manifest.requested["device"], "auto");
        assert_eq!(manifest.resolved["device"], "cpu");
        assert_eq!(manifest.resolved["backend"], "fdm");
        assert_eq!(manifest.launched_by.as_deref(), Some("api"));
        assert_eq!(manifest.status, "running");
    }

    #[test]
    fn the_leaf_gets_running_then_completed_and_nothing_outside_it() {
        let dir = tempfile::tempdir().unwrap();
        let (mut storage, leaf) = reserve(dir.path());
        let running = read_run_manifest(&leaf).unwrap().unwrap();
        assert_eq!(running.status, "running");
        assert_eq!(running.finished_at, None);

        let attempt = dir.path().join("attempt");
        fs::create_dir(&attempt).unwrap();
        storage.finish(true, &attempt).unwrap();
        let done = read_run_manifest(&leaf).unwrap().unwrap();
        assert_eq!(done.status, "completed");
        assert!(done.finished_at.is_some());
        assert!(done.outputs.iter().any(|o| o.path == "output-storage.json"));
        assert_eq!(done.source.revision, Some(7));
        // The manifest and published data live in the leaf only.
        assert!(!dir.path().join("results").join(RUN_MANIFEST_NAME).exists());
        assert!(!dir
            .path()
            .join("results")
            .join("run-test")
            .join(RUN_MANIFEST_NAME)
            .exists());
    }

    const RUN_MANIFEST_NAME: &str = fullmag_workspace_inspect::manifest::RUN_MANIFEST_FILE;

    #[test]
    fn a_failed_or_cancelled_run_is_never_left_running() {
        for (outcome, expected) in [
            (None, "failed"),
            (Some(("cancelled", None)), "cancelled"),
            (Some(("failed", Some("solver stopped".to_string()))), "failed"),
        ] {
            let dir = tempfile::tempdir().unwrap();
            let (mut storage, leaf) = reserve(dir.path());
            if let Some((status, error)) = outcome.clone() {
                storage.note_outcome(status, error);
            }
            storage.finish(false, dir.path()).unwrap();
            let done = read_run_manifest(&leaf).unwrap().unwrap();
            assert_eq!(done.status, expected);
            if let Some((_, Some(error))) = outcome {
                assert_eq!(done.error.as_deref(), Some(error.as_str()));
            }
        }
    }
}
