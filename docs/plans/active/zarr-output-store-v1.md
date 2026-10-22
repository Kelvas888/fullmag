# Plan: canonical Zarr output store v1

- Status: Phase 0 contract work authorized. D1–D5 are user decisions (2026-10-22); D6–D9 remain recommendations. Runtime implementation is not authorized by Phase 0.
- Phase 0 deliverables: [store contract](../../specs/output-store-zarr-v1.md), [ADR 0068](../../adr/0068-canonical-zarr-output-store.md), and [output capabilities](../../specs/capability-matrix-v0.md#saved-output-capabilities).
- Evidence note: §2 is the input research baseline, not new runtime qualification. See the store contract and capability matrix for source checks and limits. External host paths below identify future work, not repository links.
- Date: 2026-10-22. Base: `master` `9902410b0`.
- Origin: copied from the orchestration input plan, then adapted for Phase 0. Its research-only claims are not promoted to verified runtime facts. The source checks below use base `9902410b016dbe934669122ef00a7825bbd2d5b0`; the task report records limits.
- Input research identifies `/home/kelv/git/graphify-out` as an AST graph at the base. Phase 0 uses source checks, not that graph as proof; its refresh state is NOT VERIFIED here.

## 1. Goal

1. Give fullmag one Zarr output store for every realization (FDM CPU, FDM GPU, FEM CPU, FEM GPU) and for all data: m, torque, B_eff, other fields, energies and scalar tables.
2. Make the store comparable with the Zarr output of the mumax3 fork `MateuszZelent/3`, so the same readers (pyzfn, zarr-python) open both.
3. Run FDM GPU scripts without the UI, from code only, like an `.mx3` file in mumax3.
4. Run mumax3 example 1 in both codes (`~/git/simulations/{amumax,fullmag}/example_1.{mx3,py}`). Compare fullmag FDM GPU single with mumax3 through the Zarr outputs.
5. Keep the fullmag contract: one DSL, one ProblemIR, one output storage, four separate realizations, no silent fallback, explicit provenance.

## 2. Verified current state

### 2.1 Writers

- One shared pipeline seam exists. `run_planned_problem_with_live_preview_artifact_context` starts `ArtifactPipeline` and supplies the writer to FDM, multilayer, FEM evolution and FEM relax (`crates/fullmag-runner/src/lib.rs:4543-4677`). `writer_loop` receives scalar/field/native/provenance jobs (`crates/fullmag-runner/src/artifact_pipeline.rs:1685-2053`). The accepted API worker uses the autosave-root wrapper (`crates/fullmag-api/src/accepted_study_worker.rs:2549-2564`). Interactive execution starts a pipeline directly, not through that entry point (`crates/fullmag-runner/src/interactive/runtime.rs:471-492`, `InteractiveRuntime` streaming execution). These are source-routing observations, not runtime qualification.
- `ZarrAutosaveWriter::begin_stage` and `initialize_array` (`crates/fullmag-runner/src/autosave_zarr.rs:79-183,222-239,319-337`) write `<target>.zarr/stages/stage_NNNN_<id>/{table,fields/<q>}`. Arrays are Zarr v2, flat `[sample, width]`, always `<f8`, uncompressed, with no grid axes and no units. The writer does not attach a per-array time list. Its per-sample coordinate index is `continuous/index.jsonl`, omitted in separate layout. Component-order evidence belongs to the capability matrix, not an assumed universal layout.
- `ZarrFieldSeriesWriter` (`crates/fullmag-runner/src/artifact_pipeline.rs:1350-1683`, `open`, `write_zarray_metadata`) writes `fields/<q>.zarr` as `[sample, component, cell]`, `<f4|<f8`, plus `samples.csv`. It is compiled only with the `cuda` or `fem-gpu` features. `writer_loop` keeps a JSON field branch as well (`crates/fullmag-runner/src/artifact_pipeline.rs:1685-1985`).
- Other independent Zarr v2 writers: `crates/fullmag-runner/src/hysteresis.rs:1581,1926-1937` (`write_hysteresis_magnetization_zarr_snapshot`); `crates/fullmag-runner/src/fem/eigen_output.rs:1908-1946` (`zarr_group_artifact`, `mode_zarr_array_metadata_artifact`); `backends/fem/src/frequency_domain/driven_response_solver.cpp:6844-6903` (`write_zarr_group_artifact`, `write_response_zarr_array_artifacts`); `crates/fullmag-cli/src/step_utils.rs:71-76` (`initialize_zarr_group`). SaveState format normalization accepts directory/ZIP Zarr, HDF5 and JSON (`packages/fullmag-py/src/fullmag/init/state_io.py:286-325`, `_normalize_state_format`, `_normalize_field_state_format`). The accepted API bundle is separate (`crates/fullmag-api/src/accepted_field_materialization_worker.rs:19,269-292`, `SCHEMA`, f64le chunk serialization).
- Source dependencies: `Cargo.lock:1084` contains `flate2`; a package-name scan finds no Zarr or zstd crate. Python declares `zarr>=2.18,<4` (`packages/fullmag-py/pyproject.toml:15`, `project.dependencies`); its lock resolves 3.2.1 (`packages/fullmag-py/uv.lock:457-458`, `zarr`). External environment versions in the input research were not rechecked in Phase 0.

### 2.2 DSL and IR

- Output IR types: `TableAutosaveIR`, `FieldAutosaveIR`, `StageAutosaveIR`, `OutputIR` (`crates/fullmag-ir/src/study.rs:1023,1095,1119,1824`) and `OutputStorageIR` (`crates/fullmag-ir/src/output_storage.rs:9`). `StudyBuilder.storage` stores the policy in runtime metadata (`packages/fullmag-py/src/fullmag/world.py:6185-6214`).
- ADR 0051 requires one OutputStorage and a real writer behind each format. An unsupported writer must fail before Solve.
- A sample lands on the first accepted step at or after its grid time (`crates/fullmag-runner/src/schedules.rs:160-179`, `is_due`, `advance_due_schedules`; `crates/fullmag-runner/src/table_autosave.rs:166-198`, `TableStore::append_if_due`). CUDA reports stage-local time; CPU reports absolute time (`crates/fullmag-runner/src/dispatch.rs:1895-1902`, `fdm_stage_step_time_frame`). This does not prove numerical execution.

### 2.3 Quantities

- `H_eff` is A/m and torque is T with `supports_export=false` (`crates/fullmag-quantities/src/catalog.rs:199-239`, HEff/Torque catalog entries). `SaveField` excludes `torque` and `B_eff` (`packages/fullmag-py/src/fullmag/model/outputs.py:85-86,127-137`, `SaveField.__post_init__`, `_SUPPORTED_FIELDS`). Python legacy aliases B_exch/B_demag/B_ext/B_eff exist but do not prove usable saved B output (`packages/fullmag-py/src/fullmag/world.py:2920-2925,3003-3015`, `_B_ALIAS_TO_H`, `_vector_average_from_last_step`).
- Readout, public saved-export legality, component order, and precision must be distinguished. The [saved-output capability matrix](../../specs/capability-matrix-v0.md#saved-output-capabilities) records the verified quantity × lane × dtype source evidence. Its conditional/unsupported cells replace the broad readout summary in the input plan; they are not runtime qualification.
- Native single snapshots can be reread as f64 (`crates/fullmag-runner/src/artifact_pipeline.rs:1621-1649`, `last_chunk_values_f64`). Stage writer interfaces accept f64 slices (`crates/fullmag-runner/src/autosave_storage.rs:99-113`, `AutosaveTargetWriter`); v1 must remove that loss of dtype identity.

### 2.4 Headless execution and FDM GPU single — research leads, NOT VERIFIED

- Input research proposed checking `just docker-dev-script <script>` and CLI `fullmag script.py --headless`. Phase 0 did not execute either path, inspect installed binaries, or qualify in-process Python. Treat their deployment behavior as NOT VERIFIED.
- Input inference, NOT VERIFIED: Docker DEV output-policy materialization may need a fix. P2.5 must test this before changing behavior.
- The source publication branch is successful-only (`crates/fullmag-api/src/accepted_project_storage.rs:225-258`, `AcceptedProjectStorage::finish`).
- Input research reported an SP4 epoch-2 relaxation failure and a stale simulations status. Phase 0 did not inspect its runtime artifacts or status file. It cannot establish a “never executed” claim from source. P4.1 must obtain new device/runtime evidence before comparison.
- The §6 example remains a draft for P5.2. Phase 0 does not claim its execution or qualify the FP32 regional-drive kernel. See the capability matrix for source support and its limits.

### 2.5 mumax3-fork compatibility input — not reverified in Phase 0

The following is the copied external research target, not a claim about code
checked in this worktree. P1/P5 must validate it against the pinned fork.
No remote or installed mumax binary was accessed in Phase 0.

Target: `MateuszZelent/3`, tag `v3.12.21-20261022`.

- Zarr v2, hand-written writer. Fields:
  - One array per quantity `<name>/`, shape `[t, Nz, Ny, Nx, ncomp]`, `<f4`, zstd level 1.
  - Chunks `[1, ...]`, one frame per chunk, with keys `step.iz.iy.ix.ic`.
  - Per-array `.zattrs`: `{"t": [...], "name", "unit"}`.
- Root `.zattrs` equals `run.json`. It holds the mesh keys (`Nx..`, `dx..`, `Tx..`, `PBC*`), the script assignments, provenance and completion.
- Table:
  - Group `table/` with one 1-D `<f8` array per column (`t`, `mx`, ...), chunked at 1024 rows.
  - `manifest.json` with `committed_rows`.
  - `table.txt` is always written.
- Input research reported an older local binary without the target metadata. Its installed version and behavior are NOT VERIFIED here; D8 remains a recommendation.

## 3. Proposed design: `fullmag.output_store.v1`

### 3.1 Principles

- One writer library and one layout for all realizations. Solver code does not change. The writer runs in `writer_loop`, off the hot loop and outside GPU fences.
- Requests stay solver-agnostic in the DSL and IR. The planner checks each request against the output capability of the resolved realization. It fails before Solve with a stable reason code. No quantity maps silently to another.
- The store is user data. It goes to the resolved output storage, never into build volumes.
- An autosave frame is not an ExactResume checkpoint. SaveState stays separate.

### 3.2 Layout

```text
<name>.zarr/              default name: script stem (mumax convention); OutputStorage may override
  .zgroup                 {"zarr_format": 2}
  .zattrs                 same content as run.json
  run.json                schema, run metadata, provenance, completion
  <quantity>/             one field array per saved quantity (m, B_eff, torque, H_demag, ...)
    .zarray  .zattrs  <chunk files>
  table/                  group: one 1-D <f8 array per column
    .zgroup  manifest.json  t/  mx/  my/  mz/  ...
  table.csv               readable copy of the table
  active_mask/            FDM, only when the geometry is not the full box: [Nz, Ny, Nx] |u1
  mesh/                   FEM only: nodes, cells, markers, written once
```

- Use one store per study run. All stages append to the same arrays in time order. Per-sample `step` and `stage` lists keep stage boundaries visible.

### 3.3 Field arrays

- FDM: shape `[t, Nz, Ny, Nx, ncomp]`, C order, components fastest (AoS), chunks `[1, Nz, Ny, Nx, ncomp]`. This matches mumax3 and pyzfn. The writer transposes SoA native snapshots on the writer thread.
- FEM: shape `[t, n_nodes, ncomp]` for nodal fields and `[t, n_cells, ncomp]` for DG0 fields. `mesh/` holds the topology from MeshIR.
- Scalar fields use `ncomp = 1`.

### 3.4 Metadata

- Per-array `.zattrs`:
  - `t`: absolute study time in seconds, a list of f64.
  - `name` and `unit`: SI unit string, same keys as mumax3.
  - `fullmag` object:
    - `quantity_id`
    - `location`: `cell` | `node` | `element`
    - `dims`: `["t","z","y","x","c"]` or `["t","node","c"]`
    - `components`
    - `dtype`
    - `step` list
    - `stage` list
- Root `run.json`:
  - `schema = "fullmag.output_store.v1"`.
  - `completion`: `running` | `complete` | `failed` | `interrupted`, with a reason. Also start time, end time and step count.
  - For FDM, the mumax3 mesh keys `Nx Ny Nz dx dy dz Tx Ty Tz PBCx PBCy PBCz`, plus `origin`.
  - Requested and resolved execution: engine, device, precision, mode, integrator, dt policy.
  - Material parameters as numbers.
  - SHA-256 of the ProblemIR and of the script.
  - fullmag version and commit, and the device name.

### 3.5 Table

- `table/` follows the fork's HEAD layout:
  - One 1-D `<f8` array per column, chunked at 1024 rows.
  - `manifest.json` with `columns`, `units`, `committed_rows` and `chunk_rows`.
  - Readers clip to `committed_rows`.
- Column names follow mumax3 where it has a counterpart (`t`, `mx`, `my`, `mz`, `B_extx`, ...). Other columns keep the fullmag names (`E_total`, `max_torque_T`, ...).
- Keep the existing CSV outputs (`scalars.csv`, `tables/<id>/table.csv`) unchanged in v1. Current comparison scripts read them.

### 3.6 Precision and dtype

- Field arrays use the resolved execution precision: `<f4` for single, `<f8` for double. The writer does not upcast. Table columns are always `<f8`.

### 3.7 Time

- The pipeline delivers absolute study time, step number and stage for every sample. Normalize the CUDA stage-local clock in the pipeline, not in native code.
- Keep the current sampling rule, which mumax3 also uses: the first accepted step at or after the grid time. The store records the actual time, so a comparison interpolates.

### 3.8 Quantities added in v1

- `B_eff` = μ0·H_eff [T]. Before you add it, verify on each realization that H_eff includes the field drives.
- `torque` [T], mumax convention: τ = −1/(1+α²)(m×B_eff + α m×(m×B_eff)). `crates/fullmag-runner/src/derived_fields.rs` already has this formula. On FDM CUDA, derive it on the writer thread from the m and H_eff snapshots of the same accepted state.
- Table columns:
  - `B_ext{x,y,z}`: static field plus drives. For uniform drives it is exact: evaluate the IR waveform at the sample time.
  - Averages of saved fields.
  - `E_ani` and `E_dmi`, which are missing from the allowlist in `schedules.rs:51-70`.
- A spatial `B_ext` field array is not in v1: CUDA does not export H_drive.

### 3.9 Durability

- Write each sample in this order: chunk file, then `.zarray` (shape), then `.zattrs` (`t` list). Write every file to a temp name, then rename it. Readers use `min(shape[0], len(t))`.
- On failure or interruption, keep the store and set `completion`. Publishing failed accepted attempts is recommendation D9 and still needs a user decision; current successful-only publication is not changed by this plan.

### 3.10 Compression

- v1 default: no compressor. It is the fastest and simplest option, and every zarr version reads it. Offer optional `zlib` through the existing `flate2` dependency. zstd, the mumax3 default, needs a new dependency; defer it.

### 3.11 Out of scope for v1

- Hysteresis, eigen, frequency-domain and SaveState writers.
- The accepted CAS bundle and the UI binary data plane; live preview stays as it is.
- UI browsing of stores.
- Zarr v3.
- Phase 6 moves these in separate tasks.

## 4. Decisions needed

| ID | Decision | Recommendation or outcome |
|---|---|---|
| D1 | dtype of field arrays | **Decided 2026-10-22:** resolved precision: f32 for single, f64 for double |
| D2 | FDM array layout | **Decided 2026-10-22:** mumax3/pyzfn-compatible `[t, z, y, x, c]`, no compression by default |
| D3 | existing `stages/` Zarr layout and `fields/<q>.zarr` series | **Decided 2026-10-22:** replace them and migrate in-repo readers; keep CSV/JSON |
| D4 | v1 scope | **Decided 2026-10-22:** time-domain fields and tables for all four realizations through the runner pipeline |
| D5 | unit-test compile ban (`AGENTS.md:74`) | **Decided 2026-10-22:** lifted for this work's Rust tests only, compiled inside the task worktree's Compose group; the ban stays for other work |
| D6 | headless batch path | Recommendation: launcher-managed batch recipe without the frontend requirement |
| D7 | comparison settings | Recommendation: same γ and fixed dt on both sides first; adaptive RK45 later |
| D8 | mumax3 binary | Recommendation: rebuild at tag `v3.12.21-20261022` (`run.json`, committed table rows) |
| D9 | failed runs | Recommendation: keep and publish the store with `completion = failed` |

## 5. Work plan

Rules for every task:

- Use one task worktree `worktrees/<task-id>` on branch `codex/<task-id>`. Commit each verified deliverable. Phase 0 stays local: do not merge, push, open a PR, or remove its worktree. Claude reviews and integrates.
- Phase 0 changes documents only: no builds, cargo, Docker, Compose, or container operations. Later authorized implementation must use its worktree Compose group, never the host or another group.
- Phase 0 runs headlessly in Pi. Record open questions instead of asking. Later phases require separate authorization.
- Write docs in English, which overrides the Polish rule in `AGENTS.md`. Use `scientific-documentation-contract` for physics notes.

### Phase 0 — Contract

- **P0.1 Spec and ADR.**
  - Files: `docs/specs/output-store-zarr-v1.md`, `docs/adr/0068-canonical-zarr-output-store.md`.
  - Reconcile the docs that contradict the code: `docs/physics/0910*` §4.4, `docs/specs/output-naming-policy-v0.md` §3 and §7, `docs/superpowers/specs/2026-07-28*` §4.1. Update them or mark them superseded.
  - Output: the contract for every later task.
  - Check: review, link check.
- **P0.2 Output capabilities.**
  - Add a quantity × realization × dtype table for outputs to `docs/specs/capability-matrix-v0.md`, and define the plan-time reason codes.
  - Verify the stale regional-drive rows (:548, :751) before you change them.
  - Check: review.

### Phase 1 — Writer core

- **P1.1 `fullmag-output-store` crate** (`crates/fullmag-output-store`, no solver dependencies).
  - Content: Zarr v2 metadata, chunk keys, f32/f64 arrays, FDM and FEM layouts, the table group with its manifest, `run.json`, completion updates, atomic writes, optional zlib.
  - Interface sketch:
    ```rust
    OutputStore::create(root, RunMetadata) -> OutputStore
    OutputStore::field(spec: FieldSpec /* quantity, unit, location, Discretization, dtype */) -> FieldHandle
    FieldHandle::append(sample: FieldSample /* t, step, stage, values: F32 | F64, order: Aos | Soa */)
    OutputStore::table_row(row: &[(&str, f64)])
    OutputStore::set_completion(state, reason)
    ```
  - Check: Rust unit tests for metadata bytes, chunk keys, append and write order. These need D5; without it, the code is checked only through the Phase 2 runtime stores.
- **P1.2 Reader conformance check** `scripts/test_output_store_v1.py`.
  - It validates a store against the spec with zarr 2.18 and with zarr 3 (`zarr_format=2`), and opens it with pyzfn.
  - Check: `python -B scripts/test_output_store_v1.py <store>`.

### Phase 2 — Pipeline integration

- **P2.1 Typed samples** in `artifact_pipeline.rs` and `types.rs`. Each sample carries quantity id, dtype, component order, location, layout digest, absolute time, step and stage. Normalize the CUDA clock (`dispatch.rs:1895-1902`).
- **P2.2 Route outputs.**
  - With `data_format = "zarr"`, `save`, `snapshot`, `tableautosave` and `StageAutosave` write through `fullmag-output-store` (`project_storage.rs`, `autosave_storage.rs`, `project_output_policy.rs`).
  - Remove the `stages/` layout and `ZarrFieldSeriesWriter` only after you migrate their in-repo readers (D3). Keep CSV and JSON outputs.
- **P2.3 Precision.** Keep f32 for single precision. Remove the f64 upcast and the duplicate CUDA store.
- **P2.4 Metadata and failure.**
  - Fill `run.json` from `ExecutionProvenance` and the plan (`FdmPlanIR`, `FemPlanIR`).
  - Keep the store on failure. Publishing failed accepted attempts is recommendation D9, not an accepted decision.
- **P2.5 Accepted-lane default.** Check at runtime whether Docker DEV runs get an output policy. If they do not, fix the materialization order.
- **P2.6 Interactive runtime.** Use the same writer.
- Check for Phase 2:
  - In the task group, run small scripts on FDM CPU double, FDM GPU double, FDM GPU single and FEM CPU, plus FEM GPU when available. Each saves `m`, `H_eff` and a table.
  - P1.2 passes on every store.
  - Values match the legacy outputs of the same run within dtype precision.

### Phase 3 — Quantities

- **P3.1 Exportable quantities.** Add `B_eff` and `torque` (§3.8) in `crates/fullmag-quantities/src/catalog.rs` and `packages/fullmag-py/src/fullmag/model/outputs.py`. Derive them on the writer thread (`derived_fields.rs`). Take the capability per realization from P0.2.
- **P3.2 Table columns.** Add `B_ext{x,y,z}`, field averages, `E_ani` and `E_dmi`.
- **P3.3 Scientific notes** for the derived outputs: equations, units, and the torque convention in relax mode.
- Check:
  - Compare the derived values on FDM GPU and FDM CPU for one small double-precision problem.
  - Compare the `B_ext` column with the analytic waveform.

### Phase 4 — Headless runs (can start in parallel with Phase 1)

- **P4.1 GPU single readiness.**
  - Reproduce the residency failure (`residency.rs:224-236`) on a small time-evolution Run, not on PG-BB, and fix it with `systematic-debugging`.
  - Run the FP32 `RegionalFieldDrive` once.
  - Treat the PG-BB non-convergence as a separate issue.
- **P4.2 Batch recipe (D6).** Add a launcher-managed recipe that runs one script without the UI in the group backend, writes the store to user storage and returns a receipt. It must not require the frontend.
- Check: a small FDM GPU single Run with a sinusoidal drive completes headless, and its store passes P1.2.

### Phase 5 — Example 1 comparison

- **P5.1** `~/git/simulations/amumax/example_1.mx3` (§6).
- **P5.2** `~/git/simulations/fullmag/example_1.py` (§6): same physics, same outputs.
- **P5.3 Runs.** Run mumax3 (D8). Then run fullmag: FDM GPU double first as the baseline, then FDM GPU single.
- **P5.4** `~/git/simulations/compare_example_1.py`, run with `/home/kelv/working_env/bin/python`.
  - Table metrics: max and RMS of Δ⟨m⟩ after interpolation to common times, and a B_ext check.
  - Field metrics: RMS and max of |Δm| and the max angle per frame.
  - Report in JSON and Markdown.
  - Set the acceptance thresholds after the double baseline.
- **P5.5** Record the results in `~/git/simulations/STATUS.md` and correct its stale SP4 entry.

### Phase 6 — Later, separate tasks

- Move hysteresis, FEM eigen, FEM frequency domain, CLI `step_utils`, SaveState and Python Zarr writes onto `fullmag-output-store`. Pin Python writes to Zarr v2.
- Evaluate zstd.
- Add UI access to stores.

## 6. Example 1 drafts

mumax3, `example_1.mx3`. The user's script, plus comparison settings marked `added`:

```text
SetGridSize(128, 32, 4)
SetCellSize(5e-9, 5e-9, 5e-9)
Msat  = 860e3
Aex   = 13e-12
alpha = 0.2
m = Uniform(1, 1, 0)
f := 1e9  // 1GHz
A := 0.01 // 10mT
B_ext = Vector(0.1, A*sin(2*pi*f*t), 0)
GammaLL = 1.7595e11      // added: the same gamma on both sides
FixDt = 1e-13            // added: fixed step first (D7)
TableAdd(B_ext)          // added
TableAutosave(10e-12)    // added
AutoSave(m, 100e-12)     // added; also B_eff and torque
run(10e-9)
```

fullmag, `example_1.py`. This is a draft; check each call against the DSL during P5.2:

```python
import math
import fullmag as fm

study = fm.study("example_1")
study.engine("fdm"); study.device("gpu", precision="single"); study.mode("strict")
study.universe(mode="manual", size=(640e-9, 160e-9, 20e-9),
               center=(0.0, 0.0, 0.0), padding=(0.0, 0.0, 0.0))
study.cell(5e-9, 5e-9, 5e-9)                          # 128 x 32 x 4
body = study.geometry(fm.Box(size=(640e-9, 160e-9, 20e-9), name="body"), name="body")
body.Ms = 860e3; body.Aex = 13e-12; body.alpha = 0.2
s = 1 / math.sqrt(2)
body.m = fm.init.UniformMagnetization((s, s, 0.0))    # fullmag does not normalize
study.exchange(); study.demag()
study.b_ext(0.1, 0.0, 0.0)                            # static B_x = 0.1 T
study.field_drives.add(fm.RegionalFieldDrive(         # B_y = 0.01 sin(2*pi*1e9*t) T
    id="by_rf", name="By 10 mT 1 GHz", target=fm.FieldTarget.global_domain(),
    amplitude_B_T=0.01, direction=(0.0, 1.0, 0.0),
    spatial_profile=fm.UniformFieldProfile(),
    waveform=fm.Sinusoidal(frequency_hz=1e9), time_origin="absolute"))
study.solver(integrator="rk45", fix_dt=1e-13, gamma=1.7595e11 * 4e-7 * math.pi)
study.storage(data_format="zarr")
study.stages.add_run(10e-9, stage_id="run").autosave(fm.StageAutosave(
    table=fm.TableAutosave(t_sampl=10e-12, quantities=["t", "mx", "my", "mz"]),  # + B_ext (P3.2)
    fields=[fm.FieldAutosave("m", every=100e-12)]))                              # + B_eff, torque (P3.1)
```

## 7. Risks

1. The input-reported GPU single residency failure needs runtime verification and may block Phase 5. P4.1 is on the critical path.
2. The unit-test compile ban limits verification of the writer core (D5).
3. D3 breaks readers of the old layouts. Search `~/git/simulations` and other local repositories for readers before you remove anything.
4. Input research reports a shared RTX 5050 (8 GB). Hardware and active users are NOT VERIFIED in Phase 0; coordinate and verify before any later GPU run.
5. Explicitly select Zarr v2 for every later Python-side write with the installed package's supported API. Reader/writer conformance across package versions is a Phase 1 gate.
6. Time does not advance in relax stages. The `step` and `stage` lists keep frames distinct, but tools that use only `t` (pyzfn frequency analysis) must skip relax frames.
7. The contradictions found between docs and code may hide other expectations. P0.1 resolves them before any code changes.
