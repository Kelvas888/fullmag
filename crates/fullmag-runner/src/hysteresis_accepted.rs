//! Accepted-lane outputs of a hysteresis stage.
//!
//! The hysteresis runner writes its own point artifacts. An accepted worker also
//! needs the common final-state artifacts (`m_final.json`, `m_initial.json`,
//! the accepted state snapshot), and the run's `<script>.zarr` gets one table
//! row per field point, as mumax3 `tablesave()` after each `minimize()`.

use crate::observation::{
    FdmGpuAcceptedStateSnapshotV1, ObservationClock, FDM_GPU_ACCEPTED_STATE_SNAPSHOT_FILE,
};
use crate::output_store::{FdmGrid, FdmOutputStore};
use crate::types::{AuxiliaryArtifact, ExecutedRun, ExecutionProvenance, RunError, RunResult};
use fullmag_ir::{BackendPlanIR, ExecutionPlanIR, ProblemIR};
use serde_json::Value;
use std::fs;
use std::path::Path;

const TABLE_COLUMNS: [&str; 7] = ["t", "mx", "my", "mz", "B_extx", "B_exty", "B_extz"];

fn run_error(context: &str, error: impl std::fmt::Display) -> RunError {
    RunError { message: format!("{context}: {error}") }
}

/// Write the final-state artifacts of a finished FDM hysteresis run and its
/// point table. `output_dir` holds the hysteresis artifacts; the table goes to
/// the stage autosave root, which the accepted storage merges into the script store.
pub(crate) fn publish_accepted_hysteresis_outputs(
    problem: &ProblemIR,
    plan: &ExecutionPlanIR,
    output_dir: &Path,
    autosave_root: &Path,
    result: &RunResult,
) -> Result<(), RunError> {
    let BackendPlanIR::Fdm(fdm) = &plan.backend_plan else {
        return Ok(());
    };
    let provenance_path = output_dir.join("hysteresis_execution_provenance.json");
    let provenance: ExecutionProvenance = serde_json::from_slice(
        &fs::read(&provenance_path).map_err(|error| run_error("read hysteresis provenance", error))?,
    )
    .map_err(|error| run_error("decode hysteresis provenance", error))?;

    let mut auxiliary_artifacts = Vec::new();
    if provenance.fdm_gpu_execution_receipt.is_some() {
        // The snapshot identifies the final accepted state of the whole sweep.
        let last = result.steps.last();
        let clock = ObservationClock {
            accepted_step: last.map_or(0, |stats| stats.step),
            time_seconds: last.map_or(0.0, |stats| stats.time),
            dt_seconds: last.and_then(|stats| (stats.dt > 0.0).then_some(stats.dt)),
        };
        let snapshot =
            FdmGpuAcceptedStateSnapshotV1::from_final_magnetization(clock, &result.final_magnetization)
                .map_err(|error| run_error("materialize hysteresis accepted state snapshot", error))?;
        auxiliary_artifacts.push(AuxiliaryArtifact {
            relative_path: FDM_GPU_ACCEPTED_STATE_SNAPSHOT_FILE.to_string(),
            bytes: serde_json::to_vec_pretty(&snapshot)
                .map_err(|error| run_error("serialize hysteresis accepted state snapshot", error))?,
        });
    }
    let executed = ExecutedRun {
        result: result.clone(),
        initial_magnetization: fdm.initial_magnetization.clone(),
        field_snapshots: Vec::new(),
        field_snapshot_count: 0,
        auxiliary_artifacts,
        provenance,
    };
    crate::artifacts::write_artifacts(output_dir, problem, plan, &executed, None)
        .map_err(|error| run_error("write hysteresis final-state artifacts", error))?;

    let grid = FdmGrid {
        cells: fdm.grid.cells.map(|cells| cells as usize),
        cell_size: fdm.cell_size,
        origin: fdm.origin_m,
    };
    write_point_table(&output_dir.join("hysteresis_points.json"), autosave_root, grid)
}

/// One `t, mx, my, mz, B_ext{x,y,z}` row per settled field point, in sweep order.
/// Minimization does not advance physical time, so `t` stays at the stage start.
fn write_point_table(points_path: &Path, autosave_root: &Path, grid: FdmGrid) -> Result<(), RunError> {
    let points: Vec<Value> = serde_json::from_slice(
        &fs::read(points_path).map_err(|error| run_error("read hysteresis points", error))?,
    )
    .map_err(|error| run_error("decode hysteresis points", error))?;
    let mut rows = Vec::with_capacity(points.len());
    for point in &points {
        let id = point["point_id"].as_u64().unwrap_or(u64::MAX);
        let m = &point["m_avg"];
        let h = &point["field_vector_A_per_m"];
        let component = |value: &Value, index: usize| value[index].as_f64().unwrap_or(f64::NAN);
        rows.push((
            id,
            [
                0.0,
                component(m, 0),
                component(m, 1),
                component(m, 2),
                crate::MU0 * component(h, 0),
                crate::MU0 * component(h, 1),
                crate::MU0 * component(h, 2),
            ],
        ));
    }
    rows.sort_by_key(|(id, _)| *id);
    let mut store = FdmOutputStore::new(autosave_root.join("main.zarr"), grid);
    let table_error = |error: String| run_error("write hysteresis point table", error);
    store.write_root_attrs().map_err(table_error)?;
    let columns: Vec<String> = TABLE_COLUMNS.iter().map(|column| column.to_string()).collect();
    for (_, row) in rows {
        store.append_table_row(row[0], &columns, &row).map_err(table_error)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn point_rows_follow_point_ids_with_b_ext_in_tesla() {
        let directory = tempfile::tempdir().unwrap();
        let points = serde_json::json!([
            {"point_id": 1, "m_avg": [0.5, 0.0, 0.0], "field_vector_A_per_m": [1e-3 / crate::MU0, 0.0, 0.0]},
            {"point_id": 0, "m_avg": [0.0, 0.1, 0.0], "field_vector_A_per_m": [0.0, 0.0, 0.0]},
        ]);
        let points_path = directory.path().join("hysteresis_points.json");
        fs::write(&points_path, serde_json::to_vec(&points).unwrap()).unwrap();
        let grid = FdmGrid { cells: [2, 1, 1], cell_size: [4e-9, 4e-9, 30e-9], origin: [0.0; 3] };
        write_point_table(&points_path, directory.path(), grid).unwrap();
        let table = directory.path().join("main.zarr/table");
        let manifest: Value = serde_json::from_slice(&fs::read(table.join("manifest.json")).unwrap()).unwrap();
        assert_eq!(manifest["columns"], serde_json::json!(TABLE_COLUMNS));
        assert_eq!(manifest["committed_rows"], serde_json::json!(2));
        let column = |name: &str, row: usize| {
            let bytes = fs::read(table.join(name).join("0")).unwrap();
            f64::from_le_bytes(bytes[row * 8..row * 8 + 8].try_into().unwrap())
        };
        assert_eq!(column("my", 0), 0.1);
        assert_eq!(column("mx", 1), 0.5);
        assert!((column("B_extx", 1) - 1e-3).abs() < 1e-15);
    }
}
