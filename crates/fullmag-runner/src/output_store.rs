//! `fullmag.output_store.v1` arrays for FDM grids (docs/specs/output-store-zarr-v1.md).
//!
//! Field quantities are written mumax3-compatibly as `<quantity>/` arrays
//! `[t, z, y, x, c]` with a per-array `t` attribute, in the resolved precision.
//! The table is a group of 1-D `<f8` columns with `manifest.json`. Root
//! attributes carry the mumax3 mesh keys, so pyzfn and mmpp open the store
//! directly. The legacy `stages/` layout is still written next to it.

use crate::autosave_zarr::write_json_atomic;
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

pub(crate) const SCHEMA: &str = "fullmag.output_store.v1";
pub(crate) const TABLE_CHUNK_ROWS: usize = 1024;

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct FdmGrid {
    pub cells: [usize; 3],
    pub cell_size: [f64; 3],
    pub origin: [f64; 3],
}

impl FdmGrid {
    /// Reads the FDM field layout published by `artifacts::field_layout`.
    pub(crate) fn from_layout(layout: &Value) -> Option<Self> {
        if layout.get("backend")?.as_str()? != "fdm" {
            return None;
        }
        let triple = |key: &str| -> Option<[f64; 3]> {
            let values = layout.get(key)?.as_array()?;
            Some([values.first()?.as_f64()?, values.get(1)?.as_f64()?, values.get(2)?.as_f64()?])
        };
        let cells = triple("grid_cells")?;
        Some(Self {
            cells: [cells[0] as usize, cells[1] as usize, cells[2] as usize],
            cell_size: triple("cell_size")?,
            origin: triple("origin_m").unwrap_or([0.0; 3]),
        })
    }

    fn cell_count(&self) -> usize {
        self.cells.iter().product()
    }
}

/// Component order of a flat field sample as produced by the pipeline.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ComponentOrder {
    /// `[x0, y0, z0, x1, ...]` (host snapshots).
    Interleaved,
    /// `[x0, x1, ..., y0, ..., z0, ...]` (native snapshot chunks).
    ComponentMajor,
}

struct FieldSeries {
    components: usize,
    single: bool,
    t: Vec<f64>,
    step: Vec<u64>,
    stage: Vec<String>,
}

struct TableSeries {
    columns: Vec<String>,
    rows: Vec<Vec<f64>>,
}

pub(crate) struct FdmOutputStore {
    root: PathBuf,
    grid: FdmGrid,
    fields: BTreeMap<String, FieldSeries>,
    table: Option<TableSeries>,
}

impl FdmOutputStore {
    pub(crate) fn new(root: impl Into<PathBuf>, grid: FdmGrid) -> Self {
        Self { root: root.into(), grid, fields: BTreeMap::new(), table: None }
    }

    /// Merges the mumax3 mesh keys into the root attributes, keeping existing keys.
    pub(crate) fn write_root_attrs(&self) -> Result<(), String> {
        let path = self.root.join(".zattrs");
        let mut attrs = match fs::read(&path) {
            Ok(bytes) => serde_json::from_slice::<Map<String, Value>>(&bytes)
                .map_err(|error| format!("failed to decode '{}': {error}", path.display()))?,
            Err(_) => Map::new(),
        };
        let [nx, ny, nz] = self.grid.cells;
        let [dx, dy, dz] = self.grid.cell_size;
        for (key, value) in [
            ("output_store_schema", json!(SCHEMA)),
            ("Nx", json!(nx)), ("Ny", json!(ny)), ("Nz", json!(nz)),
            ("dx", json!(dx)), ("dy", json!(dy)), ("dz", json!(dz)),
            ("Tx", json!(dx * nx as f64)), ("Ty", json!(dy * ny as f64)), ("Tz", json!(dz * nz as f64)),
            ("PBCx", json!(0)), ("PBCy", json!(0)), ("PBCz", json!(0)),
            ("origin", json!(self.grid.origin)),
        ] {
            attrs.insert(key.into(), value);
        }
        fs::create_dir_all(&self.root).map_err(|error| error.to_string())?;
        write_json_atomic(&path, &Value::Object(attrs))
    }

    /// Appends one sample of a cell-centred field (vector or scalar).
    pub(crate) fn append_field(
        &mut self,
        quantity: &str,
        time_s: f64,
        step: u64,
        stage_id: &str,
        values: &[f64],
        order: ComponentOrder,
        single: bool,
    ) -> Result<(), String> {
        let cells = self.grid.cell_count();
        if cells == 0 || values.len() % cells != 0 {
            return Err(format!(
                "output store field '{quantity}' has {} values for {cells} cells",
                values.len()
            ));
        }
        let components = values.len() / cells;
        let series = self.fields.entry(quantity.to_string()).or_insert_with(|| FieldSeries {
            components,
            single,
            t: Vec::new(),
            step: Vec::new(),
            stage: Vec::new(),
        });
        if series.components != components || series.single != single {
            return Err(format!("output store field '{quantity}' changed its shape or precision"));
        }
        let path = self.root.join(quantity);
        fs::create_dir_all(&path).map_err(|error| error.to_string())?;
        let sample = series.t.len();
        let bytes = interleaved_bytes(values, cells, components, order, single);
        write_bytes_atomic(&path.join(format!("{sample}.0.0.0.0")), &bytes)?;
        series.t.push(time_s);
        series.step.push(step);
        series.stage.push(stage_id.to_string());
        let [nx, ny, nz] = self.grid.cells;
        let dtype = if single { "<f4" } else { "<f8" };
        write_json_atomic(
            &path.join(".zarray"),
            &zarray(&[series.t.len(), nz, ny, nx, components], &[1, nz, ny, nx, components], dtype),
        )?;
        let dims = if components == 1 { json!(["t", "z", "y", "x"]) } else { json!(["t", "z", "y", "x", "c"]) };
        write_json_atomic(
            &path.join(".zattrs"),
            &json!({
                "t": series.t,
                "name": quantity,
                "unit": unit(quantity),
                "fullmag": {
                    "quantity_id": quantity,
                    "location": "cell",
                    "dims": dims,
                    "components": if components == 3 { json!(["x", "y", "z"]) } else { json!([]) },
                    "dtype": dtype,
                    "step": series.step,
                    "stage": series.stage,
                },
            }),
        )
    }

    /// Appends one table row; the first column is always `t`.
    pub(crate) fn append_table_row(
        &mut self,
        time_s: f64,
        quantities: &[String],
        values: &[f64],
    ) -> Result<(), String> {
        let time_column = quantities.iter().position(|name| name == "t");
        let table = self.table.get_or_insert_with(|| TableSeries {
            columns: std::iter::once("t".to_string())
                .chain(quantities.iter().filter(|name| *name != "t").cloned())
                .collect(),
            rows: Vec::new(),
        });
        let row: Vec<f64> = std::iter::once(time_column.map_or(time_s, |index| values[index]))
            .chain(quantities.iter().zip(values).filter(|(name, _)| *name != "t").map(|(_, value)| *value))
            .collect();
        if row.len() != table.columns.len() {
            return Err("output store table row does not match its columns".into());
        }
        table.rows.push(row);
        let rows = table.rows.len();
        let chunk = (rows - 1) / TABLE_CHUNK_ROWS;
        let group = self.root.join("table");
        fs::create_dir_all(&group).map_err(|error| error.to_string())?;
        write_json_atomic(&group.join(".zgroup"), &json!({"zarr_format": 2}))?;
        for (index, column) in table.columns.iter().enumerate() {
            let path = group.join(column);
            fs::create_dir_all(&path).map_err(|error| error.to_string())?;
            let mut bytes = Vec::with_capacity(TABLE_CHUNK_ROWS * 8);
            for row in table.rows[chunk * TABLE_CHUNK_ROWS..].iter() {
                bytes.extend_from_slice(&row[index].to_le_bytes());
            }
            bytes.resize(TABLE_CHUNK_ROWS * 8, 0);
            write_bytes_atomic(&path.join(chunk.to_string()), &bytes)?;
            write_json_atomic(&path.join(".zarray"), &zarray(&[rows], &[TABLE_CHUNK_ROWS], "<f8"))?;
            write_json_atomic(&path.join(".zattrs"), &json!({"name": column, "unit": unit(column)}))?;
        }
        write_json_atomic(
            &group.join("manifest.json"),
            &json!({
                "schema": "fullmag.output_store.table.v1",
                "columns": table.columns,
                "units": table.columns.iter().map(|column| unit(column)).collect::<Vec<_>>(),
                "committed_rows": rows,
                "chunk_rows": TABLE_CHUNK_ROWS,
            }),
        )
    }
}

fn interleaved_bytes(
    values: &[f64],
    cells: usize,
    components: usize,
    order: ComponentOrder,
    single: bool,
) -> Vec<u8> {
    let width = if single { 4 } else { 8 };
    let mut bytes = Vec::with_capacity(values.len() * width);
    for cell in 0..cells {
        for component in 0..components {
            let value = match order {
                ComponentOrder::Interleaved => values[cell * components + component],
                ComponentOrder::ComponentMajor => values[component * cells + cell],
            };
            if single {
                bytes.extend_from_slice(&(value as f32).to_le_bytes());
            } else {
                bytes.extend_from_slice(&value.to_le_bytes());
            }
        }
    }
    bytes
}

pub(crate) fn zarray(shape: &[usize], chunks: &[usize], dtype: &str) -> Value {
    json!({
        "zarr_format": 2,
        "shape": shape,
        "chunks": chunks,
        "dtype": dtype,
        "compressor": null,
        "fill_value": 0,
        "order": "C",
        "filters": null,
        "dimension_separator": "."
    })
}

pub(crate) fn unit(quantity: &str) -> &'static str {
    match quantity {
        "t" | "time" => "s",
        _ if quantity.starts_with("H_") => "A/m",
        _ if quantity.starts_with("B_") || quantity.ends_with("_T") => "T",
        _ if quantity.starts_with("eden_") => "J/m3",
        _ if quantity.starts_with("e_") || quantity.starts_with("E_") => "J",
        _ => "",
    }
}

fn write_bytes_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let temporary = path.with_extension(format!("tmp.{}", uuid::Uuid::new_v4()));
    fs::write(&temporary, bytes).map_err(|error| error.to_string())?;
    fs::rename(&temporary, path).map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn grid() -> FdmGrid {
        FdmGrid { cells: [2, 1, 1], cell_size: [5e-9, 5e-9, 5e-9], origin: [0.0; 3] }
    }

    #[test]
    fn grid_is_read_from_fdm_layout_only() {
        let layout = json!({"backend": "fdm", "grid_cells": [2, 1, 1], "cell_size": [5e-9, 5e-9, 5e-9], "origin_m": [0.0, 0.0, 0.0]});
        assert_eq!(FdmGrid::from_layout(&layout), Some(grid()));
        assert_eq!(FdmGrid::from_layout(&json!({"backend": "fem"})), None);
    }

    #[test]
    fn component_major_single_sample_is_written_as_tzyxc_f32() {
        let directory = tempfile::tempdir().unwrap();
        let mut store = FdmOutputStore::new(directory.path(), grid());
        store.write_root_attrs().unwrap();
        // two cells, component-major: x = [1, 2], y = [3, 4], z = [5, 6]
        store
            .append_field("m", 1e-12, 7, "run", &[1.0, 2.0, 3.0, 4.0, 5.0, 6.0], ComponentOrder::ComponentMajor, true)
            .unwrap();
        let bytes = fs::read(directory.path().join("m/0.0.0.0.0")).unwrap();
        let values: Vec<f32> = bytes.chunks_exact(4).map(|c| f32::from_le_bytes(c.try_into().unwrap())).collect();
        assert_eq!(values, vec![1.0, 3.0, 5.0, 2.0, 4.0, 6.0]);
        let zarray: Value = serde_json::from_slice(&fs::read(directory.path().join("m/.zarray")).unwrap()).unwrap();
        assert_eq!(zarray["shape"], json!([1, 1, 1, 2, 3]));
        assert_eq!(zarray["dtype"], json!("<f4"));
        let attrs: Value = serde_json::from_slice(&fs::read(directory.path().join("m/.zattrs")).unwrap()).unwrap();
        assert_eq!(attrs["t"], json!([1e-12]));
        assert_eq!(attrs["fullmag"]["step"], json!([7]));
        let root: Value = serde_json::from_slice(&fs::read(directory.path().join(".zattrs")).unwrap()).unwrap();
        assert_eq!(root["Nx"], json!(2));
        assert_eq!(root["dx"], json!(5e-9));
    }

    #[test]
    fn table_rows_are_columns_with_committed_rows() {
        let directory = tempfile::tempdir().unwrap();
        let mut store = FdmOutputStore::new(directory.path(), grid());
        let quantities = vec!["mx".to_string(), "my".to_string()];
        store.append_table_row(0.0, &quantities, &[0.5, 0.25]).unwrap();
        store.append_table_row(1e-11, &quantities, &[0.75, 0.125]).unwrap();
        let manifest: Value =
            serde_json::from_slice(&fs::read(directory.path().join("table/manifest.json")).unwrap()).unwrap();
        assert_eq!(manifest["columns"], json!(["t", "mx", "my"]));
        assert_eq!(manifest["committed_rows"], json!(2));
        let bytes = fs::read(directory.path().join("table/mx/0")).unwrap();
        assert_eq!(bytes.len(), TABLE_CHUNK_ROWS * 8);
        assert_eq!(f64::from_le_bytes(bytes[8..16].try_into().unwrap()), 0.75);
        let t = fs::read(directory.path().join("table/t/0")).unwrap();
        assert_eq!(f64::from_le_bytes(t[8..16].try_into().unwrap()), 1e-11);
    }

    #[test]
    fn shape_or_precision_drift_is_rejected() {
        let directory = tempfile::tempdir().unwrap();
        let mut store = FdmOutputStore::new(directory.path(), grid());
        store.append_field("m", 0.0, 0, "run", &[0.0; 6], ComponentOrder::Interleaved, false).unwrap();
        assert!(store.append_field("m", 1.0, 1, "run", &[0.0; 6], ComponentOrder::Interleaved, true).is_err());
        assert!(store.append_field("m", 1.0, 1, "run", &[0.0; 5], ComponentOrder::Interleaved, false).is_err());
    }
}
