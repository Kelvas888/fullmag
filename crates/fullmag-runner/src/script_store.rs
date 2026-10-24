//! One mumax3-like `<script>.zarr` per accepted run (docs/specs/output-store-zarr-v1.md §2).
//!
//! `script.py` writes `script.zarr` in the resolved output directory, as mumax3
//! writes `script.mx3 -> script.zarr`. Every solver step of the run appends its
//! `fullmag.output_store.v1` arrays (`m/`, `table/`, ...) to this one store when
//! the step succeeds. Relaxation keeps the store time, as mumax3 `relax()` does;
//! time evolution advances it. Step attempt descriptors live in the hidden
//! `.fullmag/` directory, which Zarr readers ignore.

use crate::autosave_zarr::write_json_atomic;
use crate::output_store::{unit, zarray, TABLE_CHUNK_ROWS};
use fullmag_ir::ExistingOutputIR;
use serde_json::{json, Map, Value};
use std::fs::{self, File, OpenOptions};
use std::path::{Path, PathBuf};

pub const SCRIPT_STORE_SCHEMA: &str = "fullmag.script_store.v1";
pub const INTERNAL_DIR: &str = ".fullmag";
const LOCK_FILE: &str = "store.lock";
const MESH_KEYS: [&str; 9] = ["Nx", "Ny", "Nz", "dx", "dy", "dz", "Tx", "Ty", "Tz"];
const COPIED_ROOT_KEYS: [&str; 5] = ["PBCx", "PBCy", "PBCz", "origin", "output_store_schema"];

/// What a finished step contributes besides its arrays.
#[derive(Debug, Clone)]
pub struct StepRecord {
    pub step_id: String,
    pub kind: String,
    /// Time evolution advances the store time; relaxation and solves do not.
    pub advances_time: bool,
    /// Stage-local physical time and accepted steps at the end of the step.
    pub end_time_s: f64,
    pub steps: u64,
    pub provenance: Option<Value>,
    /// RFC 3339 UTC time at which the step finished.
    pub finished_at: String,
}

/// The run's `<stem>.zarr`, reserved before the first solver starts.
#[derive(Debug, Clone)]
pub struct ScriptStore {
    path: PathBuf,
}

/// Validates a script stem as one safe path component.
pub fn validate_store_stem(stem: &str) -> Result<(), String> {
    if stem.is_empty()
        || stem.len() > 160
        || matches!(stem, "." | "..")
        || stem.starts_with('.')
        || !stem.bytes().all(|c| c.is_ascii_alphanumeric() || b"-_.".contains(&c))
    {
        return Err(format!("script store name '{stem}' is not a safe file name"));
    }
    Ok(())
}

impl ScriptStore {
    /// Reserve `<output_dir>/<stem>.zarr` for `run_id`, or reopen it when the run owns it.
    ///
    /// Another run's store is handled by the collision policy: `error` stops,
    /// `overwrite` replaces a fullmag script store (never foreign data), and
    /// `timestamp` picks `<stem>-<UTC time>.zarr`. `now` is an RFC 3339 UTC time.
    pub fn acquire(
        output_dir: &Path,
        stem: &str,
        run_id: &str,
        policy: ExistingOutputIR,
        now: &str,
    ) -> Result<Self, String> {
        validate_store_stem(stem)?;
        fs::create_dir_all(output_dir).map_err(|error| io_error(output_dir, error))?;
        let primary = output_dir.join(format!("{stem}.zarr"));
        if let Some(store) = Self::reopen_or_create(&primary, run_id, now)? {
            return Ok(store);
        }
        match policy {
            ExistingOutputIR::Error => Err(format!(
                "result location already exists: {}",
                primary.display()
            )),
            ExistingOutputIR::Overwrite => {
                let owner = store_owner(&primary)?;
                if owner.is_none() {
                    return Err(format!(
                        "refusing to overwrite '{}': it is not a fullmag script store",
                        primary.display()
                    ));
                }
                // Holding the old store's lock proves no writer is merging into it.
                let lock = lock_store(&primary)?;
                fs::remove_dir_all(&primary).map_err(|error| io_error(&primary, error))?;
                drop(lock);
                Self::reopen_or_create(&primary, run_id, now)?.ok_or_else(|| {
                    format!("'{}' was recreated by another run", primary.display())
                })
            }
            ExistingOutputIR::Timestamp => {
                for entry in fs::read_dir(output_dir).map_err(|error| io_error(output_dir, error))? {
                    let path = entry.map_err(|error| io_error(output_dir, error))?.path();
                    let name = path.file_name().and_then(|name| name.to_str()).unwrap_or("");
                    if name.starts_with(&format!("{stem}-"))
                        && name.ends_with(".zarr")
                        && store_owner(&path)?.as_deref() == Some(run_id)
                    {
                        return Ok(Self { path });
                    }
                }
                // 2026-10-24T00:09:00.123Z -> 20261024T000900Z
                let digits: String = now.chars().take(19).filter(char::is_ascii_digit).collect();
                let stamp = format!("{}T{}Z", &digits[..digits.len().min(8)], digits.get(8..).unwrap_or(""));
                for attempt in 0..100 {
                    let suffix = if attempt == 0 { String::new() } else { format!("-{attempt}") };
                    let candidate = output_dir.join(format!("{stem}-{stamp}{suffix}.zarr"));
                    if let Some(store) = Self::reopen_or_create(&candidate, run_id, now)? {
                        return Ok(store);
                    }
                }
                Err("unable to reserve a fresh script store after 100 attempts".into())
            }
        }
    }

    /// `Some` when `path` is new (created now) or already owned by `run_id`.
    fn reopen_or_create(path: &Path, run_id: &str, now: &str) -> Result<Option<Self>, String> {
        match fs::create_dir(path) {
            Ok(()) => {
                let store = Self { path: path.to_path_buf() };
                store.initialize(run_id, now)?;
                Ok(Some(store))
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                // A concurrent first step of the same run may still be writing the attrs.
                for _ in 0..50 {
                    if path.join(".zattrs").is_file() || !is_initializing(path) {
                        break;
                    }
                    std::thread::sleep(std::time::Duration::from_millis(100));
                }
                if store_owner(path)?.as_deref() == Some(run_id) {
                    Ok(Some(Self { path: path.to_path_buf() }))
                } else {
                    Ok(None)
                }
            }
            Err(error) => Err(io_error(path, error)),
        }
    }

    fn initialize(&self, run_id: &str, now: &str) -> Result<(), String> {
        fs::create_dir_all(self.internal_dir()).map_err(|error| io_error(&self.path, error))?;
        write_json_atomic(&self.path.join(".zgroup"), &json!({"zarr_format": 2}))?;
        let attrs = json!({
            "engine": "fullmag",
            "start_time": now,
            "end_time": Value::Null,
            "completion": "running",
            "steps": 0,
            "total_time": 0.0,
            "fullmag": {
                "schema": SCRIPT_STORE_SCHEMA,
                "run_id": run_id,
                "build": fullmag_build_info::version(),
                "stages": [],
            },
        });
        self.write_attrs(&attrs)?;
        append_log(&self.path, &format!("//fullmag {}", fullmag_build_info::version()))?;
        append_log(&self.path, &format!("//run {run_id} started {now}"))
    }

    /// Run id that owns a fullmag script store at `path`, `None` for anything else.
    pub fn owner_of(path: &Path) -> Result<Option<String>, String> {
        store_owner(path)
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Hidden directory for step attempt descriptors and the merge lock.
    pub fn internal_dir(&self) -> PathBuf {
        self.path.join(INTERNAL_DIR)
    }

    /// Mark the store as running again before another step starts.
    pub fn mark_running(&self) -> Result<(), String> {
        let _lock = lock_store(&self.path)?;
        let mut attrs = self.read_attrs()?;
        attrs.insert("completion".into(), json!("running"));
        self.write_attrs(&Value::Object(attrs))
    }

    /// Append every output-store array of a step's staged `*.zarr` stores, then
    /// record the step. Legacy `stages/` and `continuous/` groups are not copied.
    pub fn merge_step(&self, staged_root: &Path, record: &StepRecord) -> Result<(), String> {
        let _lock = lock_store(&self.path)?;
        let mut attrs = self.read_attrs()?;
        let fullmag = attrs
            .get("fullmag")
            .and_then(Value::as_object)
            .cloned()
            .ok_or("script store has no fullmag attributes")?;
        let time_offset = attrs.get("total_time").and_then(Value::as_f64).unwrap_or(0.0);
        let step_offset = attrs.get("steps").and_then(Value::as_u64).unwrap_or(0);
        let offsets = Offsets { time_s: time_offset, step: step_offset, advances_time: record.advances_time };

        let mut sources = Vec::new();
        if staged_root.is_dir() {
            for entry in fs::read_dir(staged_root).map_err(|error| io_error(staged_root, error))? {
                let path = entry.map_err(|error| io_error(staged_root, error))?.path();
                if path.is_dir() && path.extension().is_some_and(|ext| ext == "zarr") {
                    sources.push(path);
                }
            }
        }
        sources.sort();
        let mut frames = Map::new();
        let mut rows = 0;
        for source in &sources {
            merge_root_attrs(source, &mut attrs)?;
            for entry in fs::read_dir(source).map_err(|error| io_error(source, error))? {
                let path = entry.map_err(|error| io_error(source, error))?.path();
                let name = file_name(&path);
                if name == "table" && path.join("manifest.json").is_file() {
                    rows += merge_table(&path, &self.path.join("table"), &offsets)?;
                } else if path.join(".zarray").is_file() {
                    let added = merge_field(&path, &self.path.join(&name), &offsets)?;
                    frames.insert(name, json!(added));
                }
            }
        }

        let end_time = if record.advances_time { time_offset + record.end_time_s } else { time_offset };
        let end_step = step_offset + record.steps;
        let mut stages = fullmag.get("stages").and_then(Value::as_array).cloned().unwrap_or_default();
        stages.push(json!({
            "step_id": record.step_id,
            "kind": record.kind,
            "advances_time": record.advances_time,
            "t_start": time_offset,
            "t_end": end_time,
            "step_start": step_offset,
            "step_end": end_step,
            "frames": frames,
            "table_rows": rows,
        }));
        let mut fullmag = fullmag;
        fullmag.insert("stages".into(), Value::Array(stages));
        if let Some(provenance) = &record.provenance {
            fullmag.insert("provenance".into(), provenance.clone());
        }
        attrs.insert("fullmag".into(), Value::Object(fullmag));
        attrs.insert("total_time".into(), json!(end_time));
        attrs.insert("steps".into(), json!(end_step));
        attrs.insert("end_time".into(), json!(record.finished_at));
        attrs.insert("completion".into(), json!("complete"));
        write_table_text(&self.path)?;
        self.write_attrs(&Value::Object(attrs))?;
        append_log(
            &self.path,
            &format!(
                "//{} {}: t = {end_time:e} s, {} steps, {rows} table rows",
                record.kind, record.step_id, record.steps
            ),
        )
    }

    /// Record a failed or cancelled step without touching committed data.
    pub fn record_failure(
        &self,
        step_id: &str,
        status: &str,
        error: Option<&str>,
        now: &str,
    ) -> Result<(), String> {
        let _lock = lock_store(&self.path)?;
        let mut attrs = self.read_attrs()?;
        attrs.insert("completion".into(), json!(status));
        attrs.insert("end_time".into(), json!(now));
        self.write_attrs(&Value::Object(attrs))?;
        append_log(&self.path, &format!("//{step_id} {status}: {}", error.unwrap_or("")))
    }

    fn read_attrs(&self) -> Result<Map<String, Value>, String> {
        read_json(&self.path.join(".zattrs"))?
            .as_object()
            .cloned()
            .ok_or_else(|| "script store attributes are not an object".into())
    }

    /// `.zattrs` and `run.json` carry the same document, as in mumax3.
    fn write_attrs(&self, attrs: &Value) -> Result<(), String> {
        write_json_atomic(&self.path.join("run.json"), attrs)?;
        write_json_atomic(&self.path.join(".zattrs"), attrs)
    }
}

struct Offsets {
    time_s: f64,
    step: u64,
    advances_time: bool,
}

impl Offsets {
    fn time(&self, local: f64) -> f64 {
        if self.advances_time { self.time_s + local } else { self.time_s }
    }
}

/// Run id of a fullmag script store, `None` for any other directory.
fn store_owner(path: &Path) -> Result<Option<String>, String> {
    let attrs = path.join(".zattrs");
    if !attrs.is_file() {
        return Ok(None);
    }
    let value = read_json(&attrs)?;
    let fullmag = &value["fullmag"];
    if fullmag["schema"].as_str() != Some(SCRIPT_STORE_SCHEMA) {
        return Ok(None);
    }
    Ok(fullmag["run_id"].as_str().map(str::to_owned))
}

/// A store whose creator has not written its attributes yet holds at most these entries.
fn is_initializing(path: &Path) -> bool {
    fs::read_dir(path).is_ok_and(|entries| {
        entries.flatten().all(|entry| matches!(entry.file_name().to_str(), Some(INTERNAL_DIR | ".zgroup")))
    })
}

fn lock_store(store: &Path) -> Result<File, String> {
    let internal = store.join(INTERNAL_DIR);
    fs::create_dir_all(&internal).map_err(|error| io_error(&internal, error))?;
    let path = internal.join(LOCK_FILE);
    let file = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(&path)
        .map_err(|error| io_error(&path, error))?;
    file.lock().map_err(|error| io_error(&path, error))?;
    Ok(file)
}

fn merge_root_attrs(source: &Path, attrs: &mut Map<String, Value>) -> Result<(), String> {
    let path = source.join(".zattrs");
    if !path.is_file() {
        return Ok(());
    }
    let source_attrs = read_json(&path)?;
    for key in MESH_KEYS {
        if let Some(value) = source_attrs.get(key) {
            match attrs.get(key) {
                Some(existing) if existing != value => {
                    return Err(format!(
                        "script store grid changed between steps ({key}: {existing} -> {value}); a new run needs a new store"
                    ));
                }
                Some(_) => {}
                None => {
                    attrs.insert(key.into(), value.clone());
                }
            }
        }
    }
    for key in COPIED_ROOT_KEYS {
        if let Some(value) = source_attrs.get(key) {
            attrs.entry(key.to_string()).or_insert_with(|| value.clone());
        }
    }
    Ok(())
}

/// Append the frames of one `[t, ...]` array; returns the number of frames added.
fn merge_field(source: &Path, destination: &Path, offsets: &Offsets) -> Result<usize, String> {
    let source_array = read_json(&source.join(".zarray"))?;
    let source_attrs = read_json(&source.join(".zattrs")).unwrap_or_else(|_| json!({}));
    let shape = shape(&source_array)?;
    let times = source_attrs["t"].as_array().cloned().unwrap_or_default();
    let fullmag = source_attrs["fullmag"].clone();
    let local_steps = fullmag["step"].as_array().cloned().unwrap_or_default();
    let local_stages = fullmag["stage"].as_array().cloned().unwrap_or_default();
    let frames = shape[0].min(times.len());

    let (mut array, mut attrs) = if destination.join(".zarray").is_file() {
        let array = read_json(&destination.join(".zarray"))?;
        let existing = self::shape(&array)?;
        if existing[1..] != shape[1..]
            || array["dtype"] != source_array["dtype"]
            || array["chunks"] != source_array["chunks"]
        {
            return Err(format!(
                "array '{}' changed its shape, dtype or chunks between steps",
                file_name(destination)
            ));
        }
        (array, read_json(&destination.join(".zattrs"))?)
    } else {
        fs::create_dir_all(destination).map_err(|error| io_error(destination, error))?;
        let mut array = source_array.clone();
        array["shape"][0] = json!(0);
        let mut attrs = source_attrs.clone();
        attrs["t"] = json!([]);
        if attrs["fullmag"].is_object() {
            attrs["fullmag"]["step"] = json!([]);
            attrs["fullmag"]["stage"] = json!([]);
        }
        (array, attrs)
    };
    let base = self::shape(&array)?[0];

    for entry in fs::read_dir(source).map_err(|error| io_error(source, error))? {
        let path = entry.map_err(|error| io_error(source, error))?.path();
        let name = file_name(&path);
        if name.starts_with('.') || name.contains(".tmp.") {
            continue;
        }
        let (index, rest) = name.split_once('.').unwrap_or((name.as_str(), ""));
        let Ok(index) = index.parse::<usize>() else { continue };
        if index >= frames {
            continue;
        }
        let key = if rest.is_empty() { (base + index).to_string() } else { format!("{}.{rest}", base + index) };
        move_file(&path, &destination.join(key))?;
    }

    let mut all_t = attrs["t"].as_array().cloned().unwrap_or_default();
    all_t.extend(times[..frames].iter().map(|t| json!(offsets.time(t.as_f64().unwrap_or(f64::NAN)))));
    attrs["t"] = Value::Array(all_t);
    if attrs["fullmag"].is_object() {
        let mut steps = attrs["fullmag"]["step"].as_array().cloned().unwrap_or_default();
        steps.extend(
            (0..frames).map(|i| json!(offsets.step + local_steps.get(i).and_then(Value::as_u64).unwrap_or(0))),
        );
        let mut stages = attrs["fullmag"]["stage"].as_array().cloned().unwrap_or_default();
        stages.extend((0..frames).map(|i| local_stages.get(i).cloned().unwrap_or(Value::Null)));
        attrs["fullmag"]["step"] = Value::Array(steps);
        attrs["fullmag"]["stage"] = Value::Array(stages);
    }
    array["shape"][0] = json!(base + frames);
    // Chunks first, then the shape, then the time list (spec §8).
    write_json_atomic(&destination.join(".zarray"), &array)?;
    write_json_atomic(&destination.join(".zattrs"), &attrs)?;
    Ok(frames)
}

/// Append the committed rows of a step table; returns the number of rows added.
fn merge_table(source: &Path, destination: &Path, offsets: &Offsets) -> Result<usize, String> {
    let (source_columns, mut source_rows) = read_table(source)?;
    if let Some(t) = source_columns.iter().position(|column| column == "t") {
        for row in &mut source_rows {
            row[t] = offsets.time(row[t]);
        }
    }
    let (mut columns, mut rows) = if destination.join("manifest.json").is_file() {
        read_table(destination)?
    } else {
        (Vec::new(), Vec::new())
    };
    for column in &source_columns {
        if !columns.contains(column) {
            columns.push(column.clone());
            for row in &mut rows {
                row.push(f64::NAN);
            }
        }
    }
    let added = source_rows.len();
    for source_row in source_rows {
        let row = columns
            .iter()
            .map(|column| {
                source_columns
                    .iter()
                    .position(|name| name == column)
                    .map_or(f64::NAN, |index| source_row[index])
            })
            .collect();
        rows.push(row);
    }
    write_table(destination, &columns, &rows)?;
    Ok(added)
}

fn read_table(group: &Path) -> Result<(Vec<String>, Vec<Vec<f64>>), String> {
    let manifest = read_json(&group.join("manifest.json"))?;
    let columns: Vec<String> = manifest["columns"]
        .as_array()
        .ok_or("table manifest has no columns")?
        .iter()
        .filter_map(|column| column.as_str().map(str::to_owned))
        .collect();
    let committed = manifest["committed_rows"].as_u64().unwrap_or(0) as usize;
    let chunk_rows = manifest["chunk_rows"].as_u64().unwrap_or(TABLE_CHUNK_ROWS as u64) as usize;
    let mut rows = vec![vec![0.0; columns.len()]; committed];
    for (index, column) in columns.iter().enumerate() {
        for chunk in 0..committed.div_ceil(chunk_rows.max(1)) {
            let path = group.join(column).join(chunk.to_string());
            let bytes = fs::read(&path).map_err(|error| io_error(&path, error))?;
            for (offset, value) in bytes.chunks_exact(8).enumerate() {
                let row = chunk * chunk_rows + offset;
                if row >= committed {
                    break;
                }
                rows[row][index] = f64::from_le_bytes(value.try_into().expect("8-byte chunk"));
            }
        }
    }
    Ok((columns, rows))
}

fn write_table(group: &Path, columns: &[String], rows: &[Vec<f64>]) -> Result<(), String> {
    fs::create_dir_all(group).map_err(|error| io_error(group, error))?;
    write_json_atomic(&group.join(".zgroup"), &json!({"zarr_format": 2}))?;
    for (index, column) in columns.iter().enumerate() {
        let path = group.join(column);
        fs::create_dir_all(&path).map_err(|error| io_error(&path, error))?;
        for (chunk, chunk_rows) in rows.chunks(TABLE_CHUNK_ROWS).enumerate() {
            let mut bytes = Vec::with_capacity(TABLE_CHUNK_ROWS * 8);
            for row in chunk_rows {
                bytes.extend_from_slice(&row[index].to_le_bytes());
            }
            bytes.resize(TABLE_CHUNK_ROWS * 8, 0);
            write_bytes(&path.join(chunk.to_string()), &bytes)?;
        }
        write_json_atomic(&path.join(".zarray"), &zarray(&[rows.len()], &[TABLE_CHUNK_ROWS], "<f8"))?;
        write_json_atomic(&path.join(".zattrs"), &json!({"name": column, "unit": unit(column)}))?;
    }
    write_json_atomic(
        &group.join("manifest.json"),
        &json!({
            "schema": "fullmag.output_store.table.v1",
            "columns": columns,
            "units": columns.iter().map(|column| unit(column)).collect::<Vec<_>>(),
            "committed_rows": rows.len(),
            "chunk_rows": TABLE_CHUNK_ROWS,
        }),
    )
}

/// mumax3 `table.txt`: `# t (s)\tmx ()...` and tab-separated rows.
fn write_table_text(store: &Path) -> Result<(), String> {
    let group = store.join("table");
    if !group.join("manifest.json").is_file() {
        return Ok(());
    }
    let (columns, rows) = read_table(&group)?;
    let mut text = String::from("# ");
    text.push_str(
        &columns
            .iter()
            .map(|column| format!("{column} ({})", unit(column)))
            .collect::<Vec<_>>()
            .join("\t"),
    );
    text.push('\n');
    for row in rows {
        text.push_str(&row.iter().map(|value| value.to_string()).collect::<Vec<_>>().join("\t"));
        text.push('\n');
    }
    write_bytes(&store.join("table.txt"), text.as_bytes())
}

fn append_log(store: &Path, line: &str) -> Result<(), String> {
    use std::io::Write;
    let path = store.join("log.txt");
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| io_error(&path, error))?;
    writeln!(file, "{line}").map_err(|error| io_error(&path, error))
}

fn shape(array: &Value) -> Result<Vec<usize>, String> {
    array["shape"]
        .as_array()
        .filter(|shape| !shape.is_empty())
        .map(|shape| shape.iter().map(|n| n.as_u64().unwrap_or(0) as usize).collect())
        .ok_or_else(|| "Zarr array has no shape".into())
}

fn move_file(source: &Path, destination: &Path) -> Result<(), String> {
    if fs::rename(source, destination).is_ok() {
        return Ok(());
    }
    // Staging and results may be on different file systems.
    let bytes = fs::read(source).map_err(|error| io_error(source, error))?;
    write_bytes(destination, &bytes)?;
    fs::remove_file(source).map_err(|error| io_error(source, error))
}

fn write_bytes(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let temporary = path.with_extension(format!("tmp.{}", uuid::Uuid::new_v4()));
    fs::write(&temporary, bytes).map_err(|error| io_error(&temporary, error))?;
    fs::rename(&temporary, path).map_err(|error| io_error(path, error))
}

fn read_json(path: &Path) -> Result<Value, String> {
    let bytes = fs::read(path).map_err(|error| io_error(path, error))?;
    serde_json::from_slice(&bytes).map_err(|error| format!("failed to decode '{}': {error}", path.display()))
}

fn file_name(path: &Path) -> String {
    path.file_name().and_then(|name| name.to_str()).unwrap_or("").to_string()
}

fn io_error(path: &Path, error: impl std::fmt::Display) -> String {
    format!("'{}': {error}", path.display())
}

#[cfg(test)]
#[path = "script_store_tests.rs"]
mod tests;
