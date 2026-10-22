# Canonical Zarr output store v1

Status: proposed implementation contract, Phase 0, 2026-10-22. No writer is
implemented by this document. D1–D5 are accepted user decisions; D6–D9 are
recommendations, not approvals. Authority: [plan](../plans/active/zarr-output-store-v1.md),
[ADR 0068](../adr/0068-canonical-zarr-output-store.md),
[OutputStorage](project-output-storage.md), and
[output capabilities](capability-matrix-v0.md#saved-output-capabilities).

## 1. Scope and evidence boundary

`fullmag.output_store.v1` is one solver-neutral store for time-domain fields
and tables from FDM CPU, FDM GPU, FEM CPU, and FEM GPU. It does not make an
unsupported realization legal. One DSL, one ProblemIR, SI units, explicit
requested/resolved execution, and no silent fallback remain invariants.

All statements labelled **Base** refer to source inspection at
`9902410b016dbe934669122ef00a7825bbd2d5b0`, not runtime qualification.
Citations identify repository-relative `path:line` and stable symbols.
Everything stated as **v1** or with “must” below is a future contract.

| Base evidence | Checked source and symbol |
|---|---|
| Stage autosave creates `stages/stage_NNNN_<id>/table` as one array and `fields/<q>` as flat arrays; dtype is `<f8`, compressor is null | `crates/fullmag-runner/src/autosave_zarr.rs:79-183` (`ZarrAutosaveWriter::begin_stage`, `append_field_sample`), `:222-239` (`initialize_array`) |
| Native field series use `[sample, component, cell]`, `<f4` or `<f8`, and `samples.csv`; the implementation is feature-gated | `crates/fullmag-runner/src/artifact_pipeline.rs:1350-1448` (`ZarrFieldSeriesWriter::open`), `:1651-1683` (`write_zarray_metadata`, `zarr_dtype`) |
| Native f32 values can be reread as f64 for autosave | `crates/fullmag-runner/src/artifact_pipeline.rs:1621-1649` (`last_chunk_values_f64`) |
| Writer jobs run through one queue and preserve CSV output | `crates/fullmag-runner/src/artifact_pipeline.rs:1685-1734` (`writer_loop`) |
| Periodic output advances a fixed cadence grid; table time cadence coalesces missed grid times to one accepted state | `crates/fullmag-runner/src/schedules.rs:160-179` (`is_due`, `advance_due_schedules`), `crates/fullmag-runner/src/table_autosave.rs:166-198` (`TableStore::append_if_due`) |
| CPU FDM reports absolute time; CUDA reports stage-local time | `crates/fullmag-runner/src/dispatch.rs:1895-1902` (`fdm_stage_step_time_frame`) |
| OutputStorage preserves requested policy and reserves collision-safe paths | `crates/fullmag-ir/src/output_storage.rs:9-42` (`OutputStorageIR`), `crates/fullmag-runner/src/project_storage.rs:46-110` (`ProjectStorageLease::prepare`) |
| Failed accepted attempts are not published through the success branch | `crates/fullmag-api/src/accepted_project_storage.rs:225-258` (`AcceptedProjectStorage::finish`) |
| MeshIR has CSR cells/facets, node coordinates, and markers, not just tetrahedra | `crates/fullmag-ir/src/mesh_hints.rs:1617-1632` (`FemCellView`, `FemFacetConnectivityIR`), `:1730-1744` (`MeshIR`) |
| Python declares zarr 2.18 through 3.x; flate2 exists in the lock | `packages/fullmag-py/pyproject.toml:15` (`project.dependencies`), `Cargo.lock:1084` (`flate2`) |

## 2. Ownership, location, and naming

**v1:** A run owns exactly one canonical Zarr store. All stages append to it;
there is no stage-owned field store. Output requests remain solver-neutral.
The planner validates quantity, realization, location, precision, writer,
and required state carriers before Solve. Failure uses the proposed stable
codes in the capability matrix, not substitution with `m`, CPU, or zeros.

The store is user data under resolved OutputStorage, never a build/cache
volume. The default script name is `<script-stem>.zarr` beside the script.
For ordinary CLI/Python, explicit `OutputStorage.output_dir` takes precedence
and is the store root itself, not a parent to which another `.zarr` is
appended. Without a script, use OutputStorage's existing model-name/source-
directory policy. Keep requested policy and resolved paths separately.

Accepted Study execution has a different ownership hierarchy. **Base:**
`AcceptedProjectStorage::preflight` and `prepare` reserve
`<output_dir>/<run_id>/<step_id>-attempt-<epoch>`
(`crates/fullmag-api/src/accepted_project_storage.rs:118-169`). Its
`finish` creates `data_root/run.json` with schema
`fullmag.accepted_project_output.v1`, using create-new
(`crates/fullmag-api/src/accepted_project_storage.rs:225-240`).

**v1:** retain those attempt leaves and their descriptors. The accepted
run owner reserves one separate canonical store at
`<output_dir>/<run_id>/output.zarr`. A run-scoped writer receives sequential
stage samples from successful worker attempts; step workers must not create
one canonical store per stage or write concurrently to the shared store.
Keep its working store in owned private staging until authorized successful
publication. An attempt's `run.json` remains outside `output.zarr`; it must
not overwrite or be overwritten by canonical `output.zarr/run.json`.
Existing descriptor consumers keep their old path/schema. Add the canonical
store path to run-level artifact discovery; do not repurpose that descriptor.
Integration must provide the run-scoped lease/aggregation before enabling
accepted v1 output. Record a separate `canonical_store_path` in execution
provenance; do not change the meaning of `resolved_output_storage.output_dir`
for existing accepted consumers. This is a future integration obligation,
not evidence that the base already consolidates multi-step outputs.

Retain OutputStorage's `timestamp`/`error` collision policy, ownership,
path validation, private temporary directory, and cleanup rules. Never
replace existing user data or reuse another run's root. Permission or
format failure stops preflight; no alternate writable directory or format
is chosen silently. HDF5 remains a separate writer contract.

A solver-neutral writer library owns bytes and metadata. Runner adapters
provide typed snapshots with quantity id, dtype, component order, location,
layout digest, absolute study time, accepted step, and stage id. Perform
SoA-to-AoS conversion and derived-output work on the writer thread, outside
solver hot loops and GPU fences. Solver physics ownership does not move.

## 3. Zarr v2 layout

Every group has `.zgroup = {"zarr_format":2}`. Arrays use C order, little
endian, `dimension_separator="."`, `filters=null`, and `fill_value=0`.
Root names `table`, `mesh`, and `active_mask` are reserved. Quantity and
column ids must be safe single path components. Root fields use canonical
quantity ids; table aliases are defined in §6.

```text
<name>.zarr/
  .zgroup
  .zattrs                   JSON equal to run.json after each metadata commit
  run.json
  <quantity>/               m, H_eff, B_eff, torque, eden_ex, ...
    .zarray
    .zattrs
    0.0.0.0.0               FDM frame 0; FEM uses 0.0.0
  table/
    .zgroup
    manifest.json
    t/  step/  stage/  mx/  my/  mz/  ...
  table.csv
  active_mask/              FDM non-box geometry only
  mesh/                     FEM only
```

Each quantity has its own sample count and cadence. Do not align unrelated
arrays by sample index. Join by actual time, stage, and accepted step.
A run uses one immutable discretization/layout digest. A topology or grid
change requires a new run/store; it cannot silently change an array shape.

### 3.1 FDM fields

Shape is `[nt, Nz, Ny, Nx, ncomp]`; chunks are
`[1, Nz, Ny, Nx, ncomp]`. Components are fastest (AoS), then x, y, z.
A complete frame has chunk key `<sample>.0.0.0.0`.
Vector components are `x,y,z`; scalar fields have `ncomp=1`, component
`scalar`. Never compact out inactive cells. Store `m=0` in inactive cells.
Other fields retain their declared full-grid scope, including airbox fields;
the mask does not authorize masking a full-domain demagnetizing field.

For non-box geometry, `active_mask` is a static `|u1` array of shape
`[Nz,Ny,Nx]`, one chunk of that shape, with values 0 or 1. Omission means
all cells are active. Its attrs include `unit="1"`, dims `z,y,x`, and the
layout digest. The lower corner is `origin` in metres. Cell centres are
`origin + ((x+0.5)dx,(y+0.5)dy,(z+0.5)dz)`.

### 3.2 FEM fields and mesh

Nodal fields have shape `[nt,n_nodes,ncomp]`, chunks
`[1,n_nodes,ncomp]`, and `location="node"`. DG0 element fields, when a
realization can provide them, have `[nt,n_cells,ncomp]`, chunks
`[1,n_cells,ncomp]`, and `location="element"`. Both use AoS and frame
key `<sample>.0.0`. A defined shape is not proof of DG0 export support.
Do not interpolate FEM values to an FDM grid to claim compatibility.

Write `mesh/` once before publishing any field sample. Preserve MeshIR
node order and cell/facet order, including mixed topology. Static arrays:

| Array | dtype | shape / meaning |
|---|---|---|
| `nodes` | `<f8` | `[n_nodes,3]`, coordinates in m |
| `cells/offsets`, `cells/nodes` | `<u4` | CSR offsets `[n_cells+1]` and zero-based node indices `[n_cell_indices]` |
| `cells/global_ordinals` | `<u8` | `[n_cells]`, original global ids |
| `cells/types` | `|u1` | `[n_cells]`, enum mapping in attrs |
| `element_markers` | `<u4` | `[n_cells]`, material/domain ids |
| `facets/offsets`, `facets/nodes` | `<u4` | CSR offsets and node indices |
| `facets/global_ordinals` | `<u8` | original facet ids |
| `facets/types`, `facets/roles` | `|u1` | enum mappings in attrs |
| `boundary_markers` | `<u4` | `[n_facets]`, boundary ids |

Each static array is one chunk of its full shape (zero-length axes use a
chunk extent of 1). `mesh/.zattrs` contains `layout_digest`, coordinate
unit `m`, enum code-to-MeshIR-token maps, and serialized MeshIR
`periodic_boundary_pairs` and `periodic_node_pairs` when present. Enum
maps must use the actual input tokens, not assumptions about tetrahedra.
Markers reference material metadata in `run.json`. No implicit node
renumbering or periodic-node collapse is allowed.

## 4. Dtype and per-array metadata

D1: field dtype follows resolved execution precision: single is `<f4`,
double is `<f8`. Do not upcast single snapshots to claim double precision.
No per-quantity precision fallback is allowed. Tables are always `<f8`;
static mesh coordinates stay `<f8` and indices retain integer dtypes.
Derived fields are computed with sufficient intermediate precision and
rounded once to the resolved field dtype. Source availability, not just
writer byte support, controls whether the request is legal.

Every field `.zattrs` has:

- `t`: actual absolute study times, JSON f64 values in s.
- `name`: canonical quantity id; `unit`: SI unit string (`1`, `A/m`, `T`,
  `J/m^3`, `J`, or `A` as appropriate).
- `fullmag.quantity_id`, `location`, `dims`, `components`, `dtype`.
- `fullmag.step`: accepted global step counters.
- `fullmag.stage`: stage ids, one per frame.
- `fullmag.layout_digest`: SHA-256 binding field order to grid/mesh.
- `fullmag.scope`: `full_domain` or `magnetic_domain`, never inferred.
- `fullmag.derivation`: formula/convention id for derived quantities.

The time, step, and stage lists have identical committed lengths. The
components list matches `ncomp`; dtype repeats `.zarray.dtype`. Dims are
`["t","z","y","x","c"]`, `["t","node","c"]`, or
`["t","element","c"]`. A reader uses only the committed prefix (§8).

## 5. Root metadata

`run.json` is authoritative; `.zattrs` mirrors the same JSON object. Both
contain `schema="fullmag.output_store.v1"` and a monotone
`metadata_revision`. A mismatch after interruption means use `run.json`,
not a false complete result. Required root fields:

- `run_id`, `completion` (`running`, `complete`, `failed`, `interrupted`),
  `reason` (null only while running or on normal completion),
  `started_at`, `ended_at` (RFC3339 UTC or null), and `step_count`.
- `requested_execution` and `resolved_execution`: engine, device,
  precision, mode, integrator, and dt policy. Preserve `auto` in requested
  fields. Resolved fields are concrete, never inferred from dtype.
- `stages`: ordered objects with `id`, `index`, `kind`, and
  `start_time_s`; this maps numeric table stage indices to ids.
- `materials`: numeric SI parameters by material/object id, with a
  `material_units` map; heterogeneous parameters are not flattened into
  a fictitious uniform material. Record effective damping provenance.
- `problem_ir_sha256`, `script_sha256`: SHA-256 of exact UTF-8 input
  bytes, with the serialized ProblemIR bytes retained by run provenance.
  If there is no source script, use null plus `script_absence_reason`.
- `fullmag_version`, `fullmag_commit` (full hash), `device_name`,
  `requested_output_storage`, `resolved_output_storage`, `layout_digest`.
- FDM: integer `Nx,Ny,Nz`; SI `dx,dy,dz`; `Tx=Nx*dx`, `Ty=Ny*dy`,
  `Tz=Nz*dz` (total extents in m); `origin`; nonnegative integer
  `PBCx,PBCy,PBCz` repetition counts, not booleans.
- FEM: `mesh` summary with counts, `location="mesh"`, and layout digest.
  Do not synthesize FDM mesh keys for an unstructured mesh.

The legacy artifact manifests, CAS receipts, and execution attestations
retain their identities. `run.json` does not replace or forge them.

## 6. Table group and CSV

`table/` is a group with one 1-D `<f8` array per column, shape `[n]`,
chunks `[1024]`. Chunk keys are `0`, `1`, etc. Partial chunks are padded to
1024 entries with fill zero; only committed rows are meaningful. Each
column has `name`, `unit`, and `fullmag.quantity_id` attrs. The manifest is:

```json
{"schema":"fullmag.output_store.table.v1","columns":["t","step","stage","mx","my","mz"],"units":["s","1","1","1","1","1"],"committed_rows":1,"chunk_rows":1024}
```

Columns and units are ordered parallel lists. Require `t`, `step`, and
`stage`; stage is the zero-based index into root `stages`. Integer values
must be exactly representable in f64 (at most 2^53); reject overflow.
Other columns follow the authored schema, not every catalog quantity.
When stages request different columns, the planner builds an ordered
union before Solve; absent values are NaN, never zero. Schema cannot
change after the first row. Manifest JSON itself contains no NaN.

Use mumax counterpart names `t`, `mx`, `my`, `mz`, `B_extx`, `B_exty`,
`B_extz`. Preserve canonical Fullmag ids such as `E_total`, `E_ani`,
`E_dmi`, and `max_torque_T` for other scalars. Averages of saved fields
must carry their quantity, component, scope, and averaging measure in
column attrs; use `<quantity>_avg_<component>` to avoid collisions.
Use the canonical observable reduction, not an unweighted average of
FEM nodes. Reject a reduction that the realization cannot supply.

`table.csv` is a readable projection of committed rows in manifest order,
with a header. It is not the transaction authority. Preserve legacy
`scalars.csv`, `tables/<id>/table.csv`, and JSON outputs unchanged (D3).
Do not silently rename their columns to the new table aliases.

## 7. Time, sampling, and new quantities

For time-based requests, keep the fixed output grid: take the first accepted
state at or after a due time. Coalesce multiple crossed grid points into one
sample; record actual time, never interpolate inside the writer or alter
integrator dt. For accepted-step requests, preserve the authored positive
step interval, initial state, and the terminal accepted relaxation state,
even when it is not divisible by the interval. Do not duplicate a terminal
state already saved at that step. **Base:** these table branches are
`TableStore::append_if_due` and `append_final_if_needed`
(`crates/fullmag-runner/src/table_autosave.rs:189-207`). Constant physical
time in relaxation does not suppress accepted-step samples.
Normalize stage-local CUDA time in the pipeline. Use nondecreasing
absolute study times and global accepted steps across stages. Relaxation
can repeat time; stage/step distinguishes frames. Frequency analysis that
assumes strictly increasing t must exclude relax samples.

The following are **v1 additions**, not claims of current saved support:

- `B_eff` [T] is μ0 times `H_eff` [A/m]. Before enabling a lane, verify
  that its effective field includes every enabled field drive at the same
  accepted state. Never add drives twice or label `H_ext` as `B_eff`.
- `torque` [T] for precessional LLG uses the mumax convention
  `-1/(1+alpha^2) * (m cross B_eff + alpha*m cross (m cross B_eff))`.
  This is a field-like torque, not `dm/dt` and not a stopping residual.
  Use local material damping and same-state m/H_eff. CUDA may derive it
  on the writer thread only from a matched snapshot pair.
- Base `compute_torque_field` also has a precession-disabled branch
  `-m cross (m cross B_eff)`, not the precessional expression
  (`crates/fullmag-runner/src/derived_fields.rs:1-34`). A minimizer's
  reported residual must not silently become saved mumax torque.
  Relax torque convention remains an open question; reject unresolved
  requests before Solve until the Phase 3 scientific note settles it.
- `B_ext{x,y,z}` [T] is static applied field plus field drives at actual
  sample time. For global spatially uniform drives, evaluate the IR
  waveform with its authored time origin. Spatially varying drives need
  the declared canonical spatial reduction; reject when unavailable.
- Add table `E_ani` and `E_dmi` [J], and averages of saved fields.
  Availability still depends on executable reductions. Base scalar
  scheduling omits these energies (`crates/fullmag-runner/src/schedules.rs:51-70`,
  `collect_scalar_schedules`); a catalog entry alone is insufficient.

A spatial `B_ext` field array is outside v1. Source checks and numerical
parity for each new observable are Phase 3 gates; this storage contract
is not a scientific qualification or a new solver equation owner.

## 8. Durability and failure

One writer owns the store. For each field frame:

1. Write complete chunk bytes to a unique temporary sibling; flush,
   sync, and atomically rename to the final chunk key.
2. Publish `.zarray` with the extended shape through the same protocol.
3. Publish `.zattrs` with all extended time/step/stage lists atomically.

Sync parent directories where supported before acknowledging durability.
Atomic replacement must work on Windows as well as POSIX. A reader uses
`min(shape[0],len(t),len(step),len(stage))` and validates the prefix.
Incomplete trailing chunks are not frames. Readers reopening a running
store must refresh metadata; no consolidated `.zmetadata` is authoritative.

For a table row, atomically replace affected chunk files for every column,
then shapes, then `manifest.json` with increased `committed_rows` last.
Previously committed prefixes must not change. Readers clip every column
to `committed_rows`, also bounded by its shape; missing committed bytes
are corruption, not fill-valued measurements. Cross-column and cross-array
atomic snapshots are not promised. The CSV can lag and can be rebuilt.

Initialize `run.json` as running before data. After joining the writer and
syncing all data, publish terminal `run.json`, then its root attrs mirror.
`complete` means the requested outputs finished and their committed data
are durable. An I/O or serialization failure fails the run; never report
success with missing output. Preserve already committed data. Best-effort
terminal metadata must not hide the original failure.

An observed failure records `failed` and reason. An observed cancellation
records `interrupted`. A killed process may leave `running`; readers treat
that as incomplete, never complete. Only an owner-aware recovery operation
may mark it interrupted; opening the store is read-only, not recovery.

D9 remains a recommendation: keep and publish failed accepted-attempt
stores with failed completion. It is not approved by D1–D5. Until decided,
retain partial data under the existing ownership/cleanup policy; do not
claim failed accepted results are publicly published. If the metadata
write itself fails, report the exact path and preserve the last prefix.

## 9. Compression and reader compatibility

D2 default is `compressor=null`. Optional zlib uses the standard Zarr v2
codec descriptor `{"id":"zlib","level":1}`; record the chosen descriptor
per array. Do not require zstd or silently select it. zstd is later work.
Whole-frame chunks favor append and direct frame reads; large-frame
memory and compression costs require later measurement, not a performance
claim in this contract.

The compatibility target from the input research is `MateuszZelent/3`
`v3.12.21-20261022`: FDM `[t,z,y,x,c]`, per-array `t/name/unit`, root
`run.json`, and per-column table arrays with committed-row manifest.
This external format description is a design input, not a new checked
claim about an external checkout or installed binary. Its exact mesh-key
semantics still require pinned-fork validation. No remote was accessed.

Zarr 2.18 and zarr-python 3.x must read this **v2** format; version 3 of
the Python package does not mean Zarr v3 on disk. Any future Python writer
must explicitly select v2 using that installed version's supported API.
FDM frames must open with pyzfn; double precision and no compression are
intentional differences from the fork's f32/zstd choice. FEM is readable
with generic Zarr, not claimed compatible with pyzfn grid analysis.
Fullmag writes CSV rather than requiring mumax `table.txt`.

Phase 1 conformance must open actual stores under both zarr versions and
pyzfn, compare values/dtypes/axes, and test interrupted field/table commits.
Phase 2 must generate stores on all legal lanes, including CUDA single;
source availability does not prove GPU execution or parity.

## 10. Migration and exclusions

D3 replaces, rather than indefinitely dual-writes, the stage Zarr layout
and `fields/<q>.zarr` series. Before removal, inventory in-repo consumers
and local comparison readers. Update each to detect
`run.json.schema="fullmag.output_store.v1"`, use root quantity arrays,
read time from attrs, and clip table rows to its manifest. Keep explicit
legacy readers for old runs as needed; never reinterpret old bytes as v1.
Do not mutate, delete, or backfill historical stores. Missing old time or
component-order metadata must be reported, not guessed during conversion.

Integration owners: writer core owns serialization; pipeline adapters own
sample normalization; Python/IR/planner owners own request legality;
reader owners own cutover. Accepted Study orchestration owns the run-scoped
writer/lease and artifact-discovery mapping; keep its step/attempt descriptor
outside the canonical store. Add a multi-stage accepted-run check that proves
one store, noncolliding run.json schemas, sequential appends, and preserved
attempt receipts. Remove old writers only after migrated-reader checks and
unchanged CSV/JSON comparison gates pass. Rollback uses the
previous executable and a new output directory, not an in-place downgrade.

Excluded: hysteresis, eigen, frequency-domain, CLI helper and SaveState
writers; ExactResume; accepted CAS bundles; live-preview/UI binary planes;
UI browsing; Zarr v3; zstd; mesh changes within a run; cross-run aggregation.
No OpenAPI, generated frontend type, resource hook, codec, or viewport
change is authorized by Phase 0.

## 11. Concrete examples (illustrative contract fixtures)

These are JSON format examples, not executed simulations. Hashes are
synthetic valid hex values. Each example has one committed frame/row.

### FDM CPU double, 2 × 1 × 1 full box

```text
fdm.zarr/
  .zgroup  .zattrs  run.json
  m/.zarray  m/.zattrs  m/0.0.0.0.0
  table/.zgroup  table/manifest.json
  table/t/.zarray  table/t/.zattrs  table/t/0
  table/step/.zarray  table/step/.zattrs  table/step/0
  table/stage/.zarray  table/stage/.zattrs  table/stage/0
  table/mx/.zarray  table/mx/.zattrs  table/mx/0
  table.csv
```

`m/.zarray`:
```json
{"zarr_format":2,"shape":[1,1,1,2,3],"chunks":[1,1,1,2,3],"dtype":"<f8","compressor":null,"fill_value":0,"order":"C","filters":null,"dimension_separator":"."}
```
`m/.zattrs`:
```json
{"t":[0.0],"name":"m","unit":"1","fullmag":{"quantity_id":"m","location":"cell","dims":["t","z","y","x","c"],"components":["x","y","z"],"dtype":"<f8","step":[0],"stage":["run"],"scope":"full_domain","layout_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","derivation":null}}
```
`run.json` (root `.zattrs` is identical):
```json
{"schema":"fullmag.output_store.v1","metadata_revision":2,"run_id":"fdm-example","completion":"complete","reason":null,"started_at":"2026-10-22T00:00:00Z","ended_at":"2026-10-22T00:00:01Z","step_count":0,"Nx":2,"Ny":1,"Nz":1,"dx":5e-9,"dy":5e-9,"dz":5e-9,"Tx":1e-8,"Ty":5e-9,"Tz":5e-9,"origin":[-5e-9,-2.5e-9,-2.5e-9],"PBCx":0,"PBCy":0,"PBCz":0,"requested_execution":{"engine":"fdm","device":"cpu","precision":"double","mode":"strict","integrator":"rk45","dt_policy":{"kind":"fixed","dt_s":1e-13}},"resolved_execution":{"engine":"fdm_cpu_reference","device":"cpu","precision":"double","mode":"strict","integrator":"rk45","dt_policy":{"kind":"fixed","dt_s":1e-13}},"stages":[{"id":"run","index":0,"kind":"run","start_time_s":0.0}],"materials":{"body":{"Ms":860000.0,"Aex":1.3e-11,"alpha":0.2}},"material_units":{"Ms":"A/m","Aex":"J/m","alpha":"1"},"problem_ir_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","script_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","fullmag_version":"example","fullmag_commit":"9902410b016dbe934669122ef00a7825bbd2d5b0","device_name":"example CPU","requested_output_storage":{"data_format":"zarr"},"resolved_output_storage":{"output_dir":"/data/fdm.zarr","data_format":"zarr"},"layout_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```
`table/manifest.json`:
```json
{"schema":"fullmag.output_store.table.v1","columns":["t","step","stage","mx"],"units":["s","1","1","1"],"committed_rows":1,"chunk_rows":1024}
```

### FEM CPU double, one tet4

```text
fem.zarr/
  .zgroup  .zattrs  run.json
  m/.zarray  m/.zattrs  m/0.0.0
  mesh/.zgroup  mesh/.zattrs
  mesh/nodes/  mesh/cells/{.zgroup,offsets/,nodes/,types/,global_ordinals/}
  mesh/element_markers/  mesh/boundary_markers/
  mesh/facets/{.zgroup,offsets/,nodes/,types/,roles/,global_ordinals/}
  table/.zgroup  table/manifest.json
  table/t/  table/step/  table/stage/  table/mx/
  table.csv
```
Every static-array directory contains `.zarray`, `.zattrs`, and its chunk.
Example nodes are `(0,0,0),(1e-9,0,0),(0,1e-9,0),(0,0,1e-9)` m.
Cell CSR offsets are `[0,4]`, nodes `[0,1,2,3]`, global ordinals `[0]`,
marker `[1]`. Facets preserve the four input boundary triangles and markers.

`m/.zarray`:
```json
{"zarr_format":2,"shape":[1,4,3],"chunks":[1,4,3],"dtype":"<f8","compressor":null,"fill_value":0,"order":"C","filters":null,"dimension_separator":"."}
```
`m/.zattrs`:
```json
{"t":[0.0],"name":"m","unit":"1","fullmag":{"quantity_id":"m","location":"node","dims":["t","node","c"],"components":["x","y","z"],"dtype":"<f8","step":[0],"stage":["run"],"scope":"full_domain","layout_digest":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","derivation":null}}
```
`run.json`:
```json
{"schema":"fullmag.output_store.v1","metadata_revision":2,"run_id":"fem-example","completion":"complete","reason":null,"started_at":"2026-10-22T00:00:00Z","ended_at":"2026-10-22T00:00:01Z","step_count":0,"mesh":{"location":"mesh","n_nodes":4,"n_cells":1,"n_facets":4,"layout_digest":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"},"requested_execution":{"engine":"fem","device":"cpu","precision":"double","mode":"strict","integrator":"rk45","dt_policy":{"kind":"fixed","dt_s":1e-13}},"resolved_execution":{"engine":"fem","device":"cpu","precision":"double","mode":"strict","integrator":"rk45","dt_policy":{"kind":"fixed","dt_s":1e-13}},"stages":[{"id":"run","index":0,"kind":"run","start_time_s":0.0}],"materials":{"1":{"Ms":860000.0,"Aex":1.3e-11,"alpha":0.2}},"material_units":{"Ms":"A/m","Aex":"J/m","alpha":"1"},"problem_ir_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","script_sha256":null,"script_absence_reason":"programmatic fixture","fullmag_version":"example","fullmag_commit":"9902410b016dbe934669122ef00a7825bbd2d5b0","device_name":"example CPU","requested_output_storage":{"data_format":"zarr"},"resolved_output_storage":{"output_dir":"/data/fem.zarr","data_format":"zarr"},"layout_digest":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"}
```
`table/manifest.json` uses the same columns, units, and committed count as
the FDM example. A column `.zarray` is:
```json
{"zarr_format":2,"shape":[1],"chunks":[1024],"dtype":"<f8","compressor":null,"fill_value":0,"order":"C","filters":null,"dimension_separator":"."}
```

## 12. Open questions

1. D9: approve publication of failed accepted-attempt stores, including
   retention and discovery, or retain current successful-only publication?
2. D6–D8: approve the batch launcher without frontend, fixed-dt comparison
   settings, and rebuilding the pinned mumax fork? They are later-phase
   recommendations; Phase 0 performs none of them.
3. Which saved torque convention applies to precession-disabled relax and
   minimizers? Phase 3 must resolve this in the scientific observable note.
4. Confirm pinned-fork mesh-key meanings (`Tx/Ty/Tz`, PBC) and pyzfn behavior
   with f64 fields, repeated t, and extra metadata through conformance tests.

These questions do not block documenting D1–D5. They do block the affected
future capability or publication claim; no guessed default authorizes it.
