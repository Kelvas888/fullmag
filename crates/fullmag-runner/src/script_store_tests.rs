use super::*;
use crate::output_store::{ComponentOrder, FdmGrid, FdmOutputStore};

const NOW: &str = "2026-10-24T00:09:00.123Z";

fn grid() -> FdmGrid {
    FdmGrid { cells: [2, 1, 1], cell_size: [5e-9, 5e-9, 5e-9], origin: [0.0; 3] }
}

/// A staged step with `frames` m samples at `times` and one table row per time.
fn stage_step(root: &Path, stage: &str, times: &[f64]) {
    let mut store = FdmOutputStore::new(root.join("main.zarr"), grid());
    store.write_root_attrs().unwrap();
    // Legacy groups next to the output-store arrays are not merged.
    fs::create_dir_all(root.join("main.zarr/stages/stage_0000_x")).unwrap();
    let quantities = vec!["t".to_string(), "mx".to_string()];
    for (index, time) in times.iter().enumerate() {
        let value = index as f64;
        store
            .append_field("m", *time, index as u64 * 10, stage, &[value; 6], ComponentOrder::Interleaved, true)
            .unwrap();
        store.append_table_row(*time, &quantities, &[*time, value]).unwrap();
    }
}

fn record(step_id: &str, advances_time: bool, end_time_s: f64, steps: u64) -> StepRecord {
    StepRecord {
        step_id: step_id.into(),
        kind: if advances_time { "time_evolution" } else { "relaxation" }.into(),
        advances_time,
        end_time_s,
        steps,
        provenance: None,
        finished_at: NOW.into(),
    }
}

fn json_at(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

#[test]
fn relax_then_run_writes_one_mumax_like_store() {
    let dir = tempfile::tempdir().unwrap();
    let store = ScriptStore::acquire(dir.path(), "example_1", "run-a", ExistingOutputIR::Overwrite, NOW).unwrap();
    assert_eq!(store.path(), dir.path().join("example_1.zarr"));

    // Relaxation without saved outputs contributes no frames and keeps t.
    let relax = dir.path().join("relax-data");
    fs::create_dir_all(&relax).unwrap();
    store.merge_step(&relax, &record("relax", false, 4.4e-9, 4435)).unwrap();

    let run = dir.path().join("run-data");
    stage_step(&run, "run", &[0.0, 2e-10]);
    store.merge_step(&run, &record("run", true, 1e-9, 10000)).unwrap();

    let root = store.path();
    let m = json_at(&root.join("m/.zattrs"));
    assert_eq!(m["t"], json!([0.0, 2e-10]));
    assert_eq!(m["fullmag"]["step"], json!([4435, 4445]));
    assert_eq!(json_at(&root.join("m/.zarray"))["shape"], json!([2, 1, 1, 2, 3]));
    assert!(root.join("m/1.0.0.0.0").is_file());
    assert!(!root.join("stages").exists());
    let attrs = json_at(&root.join(".zattrs"));
    assert_eq!(attrs, json_at(&root.join("run.json")));
    assert_eq!(attrs["Nx"], json!(2));
    assert_eq!(attrs["total_time"], json!(1e-9));
    assert_eq!(attrs["steps"], json!(14435));
    assert_eq!(attrs["completion"], json!("complete"));
    assert_eq!(attrs["fullmag"]["stages"].as_array().unwrap().len(), 2);
    assert_eq!(json_at(&root.join("table/manifest.json"))["committed_rows"], json!(2));
    let text = fs::read_to_string(root.join("table.txt")).unwrap();
    assert!(text.starts_with("# t (s)\tmx ()\n0\t0\n"));
    assert!(root.join("log.txt").is_file());
}

#[test]
fn a_second_run_continues_the_store_time() {
    let dir = tempfile::tempdir().unwrap();
    let store = ScriptStore::acquire(dir.path(), "s", "run-a", ExistingOutputIR::Error, NOW).unwrap();
    let first = dir.path().join("first");
    stage_step(&first, "a", &[0.0, 1e-9]);
    store.merge_step(&first, &record("a", true, 1e-9, 100)).unwrap();
    let second = dir.path().join("second");
    stage_step(&second, "b", &[0.0, 5e-10]);
    store.merge_step(&second, &record("b", true, 5e-10, 50)).unwrap();

    let m = json_at(&store.path().join("m/.zattrs"));
    assert_eq!(m["t"], json!([0.0, 1e-9, 1e-9, 1e-9 + 5e-10]));
    assert_eq!(m["fullmag"]["stage"], json!(["a", "a", "b", "b"]));
    let (columns, rows) = read_table(&store.path().join("table")).unwrap();
    assert_eq!(columns, vec!["t", "mx"]);
    assert_eq!(rows.iter().map(|row| row[0]).collect::<Vec<_>>(), vec![0.0, 1e-9, 1e-9, 1e-9 + 5e-10]);
    // The same run reopens its store instead of colliding with it.
    let again = ScriptStore::acquire(dir.path(), "s", "run-a", ExistingOutputIR::Error, NOW).unwrap();
    assert_eq!(again.path(), store.path());
}

#[test]
fn collision_policies_never_replace_foreign_data() {
    let dir = tempfile::tempdir().unwrap();
    let old = ScriptStore::acquire(dir.path(), "s", "run-old", ExistingOutputIR::Error, NOW).unwrap();
    fs::write(old.path().join("marker"), b"old").unwrap();

    assert!(ScriptStore::acquire(dir.path(), "s", "run-new", ExistingOutputIR::Error, NOW).is_err());

    let stamped = ScriptStore::acquire(dir.path(), "s", "run-new", ExistingOutputIR::Timestamp, NOW).unwrap();
    assert_eq!(stamped.path(), dir.path().join("s-20261024T000900Z.zarr"));
    let reopened = ScriptStore::acquire(dir.path(), "s", "run-new", ExistingOutputIR::Timestamp, NOW).unwrap();
    assert_eq!(reopened.path(), stamped.path());

    let replaced = ScriptStore::acquire(dir.path(), "s", "run-third", ExistingOutputIR::Overwrite, NOW).unwrap();
    assert_eq!(replaced.path(), dir.path().join("s.zarr"));
    assert!(!replaced.path().join("marker").exists());
    assert_eq!(store_owner(replaced.path()).unwrap().as_deref(), Some("run-third"));

    let foreign = dir.path().join("f.zarr");
    fs::create_dir_all(&foreign).unwrap();
    fs::write(foreign.join("data"), b"user").unwrap();
    assert!(ScriptStore::acquire(dir.path(), "f", "run-x", ExistingOutputIR::Overwrite, NOW).is_err());
    assert!(foreign.join("data").is_file());
    assert!(validate_store_stem("../x").is_err());
}

#[test]
fn a_grid_change_between_steps_is_rejected() {
    let dir = tempfile::tempdir().unwrap();
    let store = ScriptStore::acquire(dir.path(), "s", "run-a", ExistingOutputIR::Error, NOW).unwrap();
    let first = dir.path().join("first");
    stage_step(&first, "a", &[0.0]);
    store.merge_step(&first, &record("a", true, 1e-12, 1)).unwrap();
    let second = dir.path().join("second");
    let mut other = FdmOutputStore::new(
        second.join("main.zarr"),
        FdmGrid { cells: [3, 1, 1], cell_size: [5e-9, 5e-9, 5e-9], origin: [0.0; 3] },
    );
    other.write_root_attrs().unwrap();
    assert!(store.merge_step(&second, &record("b", true, 1e-12, 1)).is_err());
}
