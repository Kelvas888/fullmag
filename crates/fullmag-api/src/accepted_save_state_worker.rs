//! Save an immutable predecessor state without entering a solver.
use super::*;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SaveState {
    artifact_name: String,
    format: Option<String>,
    dataset: Option<String>,
}

pub(super) fn execute(
    store: &SessionStore,
    accepted: &fullmag_runtime_control::AcceptedStudySnapshot,
    start: &fullmag_application::WorkerCommandEnvelope,
    accepted_step: &AcceptedWorkerStep,
    study_step: &fullmag_authoring::StudyStep,
    case_id: &str,
    interrupt_requested: Option<&AtomicBool>,
) -> Result<AcceptedRunnerExecution> {
    let action: SaveState = serde_json::from_value(
        accepted_step.problem.problem_meta.runtime_metadata.get("accepted_save_state")
            .context("accepted SaveState has no pinned action")?.clone(),
    ).context("decode accepted SaveState action")?;
    let (name, format) = export_name(&action)?;
    if accepted_step.study_inputs.len() != 1
        || accepted_step.resolved_input.inputs.len() != 1
        || case_id != "default"
    {
        bail!("accepted SaveState requires exactly one predecessor state in the default case");
    }
    let port = &accepted_step.study_inputs[0];
    if port.port_id != "state" || port.data_kind != StudyPortDataKind::State || !port.required
        || !matches!(&port.source, StudyInputSource::StepOutput { step_id, port, case_id }
            if step_id != &accepted_step.step_id && port == "state" && case_id == "default")
    {
        bail!("accepted SaveState requires the explicit predecessor state output");
    }
    if study_step.outputs.iter().any(|port| port.port_id != "state" || port.data_kind != StudyPortDataKind::State) {
        bail!("accepted SaveState can only pass through its state output");
    }
    let input = accepted_step.resolved_input.inputs.get("state")
        .context("accepted SaveState predecessor state is missing")?;
    let artifact = input.study_artifact.as_ref().context("SaveState requires a typed CAS artifact")?;
    let length = store.cas().verified_length(&artifact.object_ref)?
        .context("SaveState predecessor CAS object is missing")?;
    let bytes = read_recovered_worker_object(
        store, &artifact.object_ref, length, accepted_step.claim.lease.budget.storage_bytes,
    )?;
    // Validate the claim, plan fingerprint, port bindings and same-space state.
    // The returned plan is never executed; the CAS size was bounded above.
    materialize_resolved_study_inputs(store, accepted_step)?;
    let DecodedStudyArtifact::MagnetizationState(state) =
        fullmag_application::decode_study_artifact(artifact, &bytes)? else {
            bail!("SaveState input is not magnetization");
        };
    let identity = worker_execution_receipt_identity(start, accepted_step, case_id)?;
    match existing_private_attempt_output_dir(store, &accepted_step.claim) {
        Ok(path) => {
            refuse_known_prelaunch_failure(&path, &identity)?;
            return recover_completed_worker_execution(
                store, &path, &identity, &study_step.outputs,
                accepted_step.claim.lease.budget.storage_bytes, None, None,
            );
        }
        Err(error) if is_not_found_error(&error) => {}
        Err(error) => return Err(error),
    }
    crate::accepted_project_storage::AcceptedProjectStorage::preflight(
        &accepted_step.problem, store, &accepted_step.claim, &accepted_step.step_id,
    )?;
    let attempt = retry_store_writer_busy(|| create_private_attempt_output_dir(store, &accepted_step.claim))?;
    write_immutable_attempt_receipt(&attempt, WORKER_EXECUTION_STARTED_RECEIPT,
        &WorkerExecutionStartedReceipt { identity: identity.clone() })?;
    let mut storage = prepare_accepted_project_storage(
        &accepted_step.problem, store, accepted, accepted_step, &identity, &attempt,
    )?;
    let result = (|| -> Result<AcceptedRunnerExecution> {
        if interrupt_requested.is_some_and(|flag| flag.load(Ordering::Acquire)) {
            bail!("accepted SaveState was interrupted before export");
        }
        let root = storage.as_ref().map(|storage| storage.data_root()).unwrap_or(&attempt);
        let directory = ensure_real_child_directory(root, "states")?;
        let output = directory.join(&name);
        let source = attempt.join("save_state_source.json");
        write_immutable_attempt_receipt(&attempt, "save_state_source.json", &serde_json::json!({
            "kind": "magnetization_state", "observable": "m", "format": "json",
            "vector_count": state.values.len(), "values": state.values,
        }))?;
        if format == "json" {
            fullmag_runner::project_storage::copy_owned_artifact(
                &attempt, Path::new("save_state_source.json"), &output,
            ).map_err(anyhow::Error::msg)?;
        } else {
            convert_state(&source, &output, &format, action.dataset.as_deref(), &attempt, interrupt_requested)?;
        }
        let metadata = fs::symlink_metadata(&output)?;
        if !metadata.is_file() || metadata.len() > accepted_step.claim.lease.budget.storage_bytes {
            bail!("SaveState export is not a bounded regular file");
        }
        fs::File::open(&output)?.sync_all()?;
        let outputs = study_step.outputs.iter().map(|port| StudyOutputPayload {
            port_id: port.port_id.clone(), case_id: case_id.into(),
            codec_id: artifact.codec_id.clone(), codec_version: artifact.codec_version.clone(),
            bytes: bytes.clone(),
        }).collect::<Vec<_>>();
        if let Some(storage) = &mut storage {
            storage.finish(true, &attempt)?;
        }
        persist_completed_worker_execution(
            store, &attempt, &identity, &study_step.outputs, RunStatus::Completed, 1,
            &outputs, None, None,
        )?;
        Ok(AcceptedRunnerExecution {
            status: RunStatus::Completed, completed_step_count: 1, outputs,
            attempt_output_dir: attempt.clone(), recovered_from_receipt: false,
            accepted_state_ref: None, observation_source: None,
        })
    })();
    if let Some(storage) = &mut storage {
        if let Err(error) = &result {
            storage.note_outcome("failed", Some(format!("{error:#}")));
        }
        storage.finish(result.is_ok(), &attempt)?;
    }
    result
}

fn export_name(action: &SaveState) -> Result<(String, String)> {
    let name = action.artifact_name.trim();
    if name.is_empty() || name == "." || name == ".." || name.len() > 200
        || name.contains(['/', '\\']) || name.chars().any(char::is_control)
    {
        bail!("SaveState artifact_name must be a bounded file name");
    }
    let lower = name.to_ascii_lowercase();
    let format = match action.format.as_deref().unwrap_or("auto").trim().to_ascii_lowercase().as_str() {
        "auto" | "" if lower.ends_with(".zarr") || lower.ends_with(".zarr.zip") => "zarr",
        "auto" | "" if lower.ends_with(".h5") || lower.ends_with(".hdf5") => "h5",
        "auto" | "" | "json" => "json",
        "zarr" => "zarr",
        "h5" | "hdf5" => "h5",
        _ => bail!("accepted SaveState supports only json, zarr or hdf5"),
    };
    let suffix = match format { "zarr" => ".zarr.zip", "h5" => ".h5", _ => ".json" };
    let name = if lower.ends_with(suffix) || format == "h5" && lower.ends_with(".hdf5") {
        name.to_owned()
    } else if format == "zarr" && lower.ends_with(".zarr") {
        format!("{name}.zip")
    } else {
        format!("{name}{suffix}")
    };
    Ok((name, format.into()))
}

fn convert_state(
    source: &Path,
    output: &Path,
    format: &str,
    dataset: Option<&str>,
    attempt: &Path,
    interrupt_requested: Option<&AtomicBool>,
) -> Result<()> {
    let executable = std::env::current_exe()?;
    let root = executable.parent().and_then(Path::parent).context("worker package root is missing")?;
    let interpreter = fullmag_runtime_control::python_runtime::resolve_interpreter(root)?;
    let log = OpenOptions::new().write(true).create_new(true).open(attempt.join("save_state_conversion.log"))?;
    let mut command = interpreter.command(root)?;
    command.args(["-m", "fullmag.runtime.helper", "convert-magnetization-state", "--input-path"])
        .arg(source).arg("--output-path").arg(output)
        .args(["--input-format", "json", "--output-format", format])
        .stdin(std::process::Stdio::null()).stdout(log.try_clone()?).stderr(log);
    if let Some(dataset) = dataset {
        command.args(["--output-dataset", dataset]);
    }
    let mut child = command.spawn().context("start SaveState format conversion")?;
    let deadline = Instant::now() + Duration::from_secs(30);
    loop {
        if let Some(status) = child.try_wait()? {
            if !status.success() {
                bail!("SaveState format conversion failed; see save_state_conversion.log");
            }
            return Ok(());
        }
        if Instant::now() >= deadline || interrupt_requested.is_some_and(|flag| flag.load(Ordering::Acquire)) {
            child.kill()?;
            child.wait()?;
            bail!("SaveState format conversion interrupted or timed out");
        }
        std::thread::sleep(Duration::from_millis(20));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn state_export_preserves_format_and_rejects_path_traversal() {
        for (name, format, expected_name, expected_format) in [
            ("relaxed_m.zarr", Some("zarr"), "relaxed_m.zarr.zip", "zarr"),
            ("relaxed.hdf5", None, "relaxed.hdf5", "h5"),
            ("relaxed", None, "relaxed.json", "json"),
        ] {
            let action = SaveState {
                artifact_name: name.into(),
                format: format.map(str::to_owned),
                dataset: Some("m".into()),
            };
            assert_eq!(export_name(&action).unwrap(), (expected_name.into(), expected_format.into()));
        }
        for name in ["../state", "/state", "a/b", "a\\b", ".", "..", ""] {
            assert!(export_name(&SaveState {
                artifact_name: name.into(), format: None, dataset: None,
            }).is_err());
        }
        assert!(export_name(&SaveState {
            artifact_name: "state".into(), format: Some("unsupported".into()), dataset: None,
        }).is_err());
    }
}
