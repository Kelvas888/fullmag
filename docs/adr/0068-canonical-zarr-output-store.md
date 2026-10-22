# ADR 0068 — Canonical Zarr output store

Date: 2026-10-22. Status: accepted scope/layout decisions D1–D5;
implementation planned. D6–D9 remain recommendations.

## Context

Fullmag needs comparable scientific outputs from FDM CPU, FDM GPU, FEM CPU,
and FEM GPU without solver-specific scripting or hidden dtype changes.
The invariant is one Python DSL, one ProblemIR, one OutputStorage, SI units,
and separate requested/resolved execution. Store ownership must not move
physics or GPU hot-loop work into the artifact layer.

At base `9902410b016dbe934669122ef00a7825bbd2d5b0`:

- `ZarrAutosaveWriter::begin_stage` and `initialize_array` write flat f64
  stage arrays, not spatial axes (`crates/fullmag-runner/src/autosave_zarr.rs:79-135,222-239`).
- `ZarrFieldSeriesWriter::write_zarray_metadata` writes separate
  `[sample,component,cell]` arrays with native f32/f64 dtype
  (`crates/fullmag-runner/src/artifact_pipeline.rs:1350-1351,1651-1683`).
- `last_chunk_values_f64` converts native f32 snapshots when rereading
  for autosave (`crates/fullmag-runner/src/artifact_pipeline.rs:1621-1649`).
- Accepted project publication runs only in the success branch
  (`crates/fullmag-api/src/accepted_project_storage.rs:225-258`,
  `AcceptedProjectStorage::finish`).

- Accepted leaves are per run/step/attempt, and their existing `run.json`
  is an accepted-output descriptor, not canonical store metadata
  (`crates/fullmag-api/src/accepted_project_storage.rs:118-169,225-240`,
  `AcceptedProjectStorage::preflight`, `prepare`, `finish`).

These are source observations, not four-lane runtime qualification.
[ADR 0051](0051-project-output-storage.md) still owns output path, collision,
format, and temporary-data policy. This ADR changes the future Zarr payload
layout only. It does not approve a new failed-result publication policy.

## Decision

Adopt [fullmag.output_store.v1](../specs/output-store-zarr-v1.md) for
runner-pipeline time-domain fields and tables. The spec is authoritative
for byte layout, metadata, sampling, write order, and failure handling.

- D1: resolved single produces f32 fields; resolved double produces f64.
  Tables use f64. No silent precision or realization fallback.
- D2: FDM fields use `[t,z,y,x,c]`, compatible in layout with the mumax3
  fork/pyzfn target. Default compression is off. Optional zlib is allowed;
  zstd is deferred. FEM uses explicit node/element axes and MeshIR topology,
  not a pretend regular grid.
- D3: replace `stages/` Zarr payloads and `fields/<q>.zarr` series after
  migrating readers. Preserve CSV/JSON and historical stores. No indefinite
  dual-write requirement and no automatic in-place conversion.
- D4: one writer library and one store per time-domain run across all four
  realizations. Adapters supply typed snapshots and explicit location,
  order, absolute time, stage, step, and layout identity. All stages append
  to root quantity arrays and a per-column table group.
- D5: the Rust unit-test compile exception applies only to this work's
  later tests inside the task Compose group. Phase 0 remains documents
  only and does not build anything.

Keep requested intent (including `auto`) and concrete resolved execution
in `run.json`. Validate output legality before Solve with the proposed
[capability codes](../specs/capability-matrix-v0.md#saved-output-capabilities).
Do not substitute missing quantities. A dtype-capable writer is not evidence
that a lane can export a quantity or run in that precision.

D6 (batch without frontend), D7 (fixed-dt comparison), D8 (pinned mumax
rebuild), and D9 (failed accepted-result publication) remain recommendations.
The spec's open questions track the remaining decisions. Partial stores
must not be reported as complete.

## Alternatives considered

| Alternative | Outcome |
|---|---|
| Always write f64 | Reject: loses D1's native single-precision identity and increases output size. |
| Keep flat stage arrays | Reject as canonical v1: no explicit spatial axes; split reader contracts remain. Retain only for historical reads. |
| Keep component-major field series | Reject for canonical FDM v1: conflicts with D2's mumax/pyzfn layout. |
| Keep both old layouts indefinitely | Reject: contradicts D3 and duplicates ownership. Migrate consumers before removal. |
| One solver-specific store per lane | Reject: conflicts with one solver-neutral output contract. |
| Default zstd to match the fork | Defer: D2 selects no compression; avoid a new mandatory codec. |
| Zarr v3 on disk | Defer: v1 targets Zarr v2 readers, including pyzfn. zarr-python 3.x must read v2. |
| Include every ancillary writer now | Reject: D4 limits v1 to runner time-domain fields/tables. SaveState, hysteresis, eigen, frequency-domain, CAS, and UI remain separate. |
| Publish failed accepted stores now | Not decided: D9 needs a separate user decision, retention policy, and discovery checks. |

## Consequences and implementation obligations

The writer owns serialization, not numerical solvers. SoA conversion and
same-state derived outputs run off the solver hot loop. The pipeline must
normalize clocks without changing cadence or integrator dt. Large-frame
chunks and growing metadata lists need measured cost checks later.

Implement a solver-independent writer core; typed pipeline adapters;
Python/catalog/planner output capabilities; reader migration; and the new
B_eff, torque, external-field table columns, energies, and reductions only
after their per-lane scientific and source gates. No frontend/OpenAPI,
resource-hook, binary codec, or viewport changes are part of this decision.
Live preview and CAS keep their existing contracts. Accepted Study integration
must provide one run-scoped writer and `output.zarr` under its run directory,
separate from step/attempt leaves. Preserve their descriptor `run.json` files;
add canonical-store artifact discovery without changing existing descriptor
consumers. This is an integration obligation, not a second layout or a claim
that per-step publication already implements run-level consolidation.

The [active plan](../plans/active/zarr-output-store-v1.md) assigns these
steps. Old writers can be removed only after consumers detect the new
schema and pass conformance. Historical results must remain readable.
Rollback selects the old executable with a fresh output root; never write
legacy bytes into a v1 store. Interrupted data remain incomplete until
owner-aware recovery; a reader cannot mark completion.

## Validation and state

Phase 0 checks links, JSON examples, matrix agreement, scientific-document
limits, and source citations. Later gates must read generated v2 stores
with zarr 2.18, zarr-python 3.x, and pyzfn (FDM only), including interrupted
writes and correct committed prefixes. Run all legal time-domain lanes
and compare preserved CSV/JSON values. GPU source presence is not execution
or parity evidence. No runtime, physics, or performance claim is made here.
