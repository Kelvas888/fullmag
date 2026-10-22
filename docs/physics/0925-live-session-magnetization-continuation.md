# Live-session magnetization continuation between commands

- Status: draft (ADR 0068 F5)
- Owners: fullmag core
- Last updated: 2026-10-22
- Related ADRs: docs/adr/0068-python-live-session-client.md
- Related specs: docs/specs/python-live-client-v1.md §5.3, §9;
  docs/physics/0532-fem-fdm-magnetization-state-transfer.md

## 1. Problem statement

In a live session (Control Room or the Python live mode) every `relax` or
`run` command is a separate accepted run. Today each run starts from the
authored initial magnetization of the scene. Interactive micromagnetics
(mumax, Boris, OOMMF) instead continues: `relax()` followed by `run(t)`
integrates from the relaxed state. Without continuation a script such as

```python
fm.relax()
fm.b_ext(0.02, 0, 0)
fm.run(1e-9)
```

computes the dynamics of the *authored* state, not of the relaxed one, which
is a different initial-value problem.

This note fixes the semantics of carrying the magnetization state from the
last successful live command into the next one. It introduces no new field
equation, no new interaction and no resampling.

## 2. Model

### 2.1 Initial-value problem of a command

Each command solves the LLG initial-value problem on its discretization
$\mathcal{D}$ (FDM cell centres or FEM P1 nodes):

$$
\partial_t \mathbf{m}_i = -\gamma_0\, \mathbf{m}_i \times \mathbf{H}_{\mathrm{eff},i}
 + \alpha\, \mathbf{m}_i \times \partial_t \mathbf{m}_i,
\qquad \mathbf{m}_i(t_0) = \mathbf{m}^{(0)}_i ,\quad i \in \mathcal{D}.
$$

Continuation chooses the initial vector $\mathbf{m}^{(0)}$:

$$
\mathbf{m}^{(0)}_i =
\begin{cases}
\mathbf{m}^{\text{prev}}_i(t_{\text{end}}) & \text{if } \mathcal{D} = \mathcal{D}^{\text{prev}}
 \text{ and the previous command succeeded},\\[2pt]
\mathbf{m}^{\text{authored}}_i & \text{otherwise.}
\end{cases}
$$

### 2.2 Symbols and SI units

| Symbol | Meaning | Unit |
|---|---|---|
| $\mathbf{m}_i$ | unit magnetization at discretization point $i$ | $1$ |
| $\mathbf{m}^{\text{prev}}_i(t_{\text{end}})$ | final state published by the previous successful live command | $1$ |
| $\mathbf{m}^{\text{authored}}_i$ | state realized from the scene's magnetization assets | $1$ |
| $\mathcal{D}$ | discretization identity: realized grid or mesh, region membership, active mask | — |
| $\gamma_0$ | gyromagnetic ratio times $\mu_0$ | $\mathrm{m\,A^{-1}\,s^{-1}}$ |
| $\alpha$ | Gilbert damping | $1$ |
| $\mathbf{H}_{\mathrm{eff}}$ | effective field | $\mathrm{A\,m^{-1}}$ |

### 2.3 Assumptions and validity

1. Only $\mathbf{m}$ is carried. Time $t_0$ restarts at $0$ for each command
   (`until_seconds` is a segment duration). Derived fields, energies and
   demag potentials are recomputed by the next command from its own scene.
2. Material parameters, fields, damping and solver settings come from the
   scene at the time of the new command; changing them between commands is
   the intended interactive use (e.g. a field step).
3. The state is carried **only** when the discretization identity is
   unchanged: same backend, same realized grid or mesh topology revision,
   same region membership and active mask, same number of points and
   components. Any geometry, mesh, cell-size or region change starts from the
   authored state. There is no interpolation; FEM↔FDM transfer remains the
   explicit operation of note 0532.
4. Only the session's latest live run is a candidate. A failed, rejected or
   cancelled (stopped) latest run publishes no final state, so the next
   command starts from the authored state and records why; it does not reach
   back to an older run. Continuation is restricted to the same session id and
   session epoch.
5. Editing the scene's magnetization assets between commands means the user
   authored a new initial state: the authored state wins and continuation is
   not applied for that command.
6. The carried state is the exact published artifact bytes (CAS digest);
   no renormalization is applied because the producer already publishes unit
   vectors.

## 3. Numerical realization

Every live command declares a `final_state` output port of kind `State` on its
selected step, so the worker publishes the final magnetization as a typed
`state` study artifact (`DecodedStudyArtifact::MagnetizationState` with its
layout). The decision is taken in the API before the RunIntent is published
(`crates/fullmag-api/src/live_accepted_continuation.rs`,
`decide_initial_state`), with the same predicate the worker applies. The next
accepted run declares one study input port of kind `initial_state` with
source `StudyInputSource::PinnedArtifact { artifact_id, content_sha256 }`.
The worker binds it with `fullmag_runner::materialize_study_magnetization_input`,
which rejects a layout that does not match the pinned execution plan. The
same path serves FDM and FEM, CPU and GPU, because the binding happens before
backend execution and only replaces the initial state vector.

| Lane | Status |
|---|---|
| FDM CPU | applies when the layout matches; runtime evidence pending |
| FDM GPU | same binding before upload; runtime evidence pending |
| FEM CPU | same binding on P1 node order; runtime evidence pending |
| FEM GPU | same binding before upload; runtime evidence pending |

## 4. Provenance

Every live run records `live_workspace.initial_state_source` in its RunSpec parameters:
`{"kind": "continuation", "previous_run_id", "previous_step_id", "artifact_id", "content_sha256"}`
or `{"kind": "authored", "reason"}` with the reason (no previous run,
previous run not successful, discretization changed, magnetization assets
edited). Requested intent (the authored state) and the resolved initial state
stay separate.

## 5. Validation

- Relax a uniform state in a non-zero field, then run with zero time step
  budget (`until_seconds` small): the first sample of the run equals the
  relaxed final state (component-wise, to the stored precision).
- Change the cell size between commands: the run starts from the authored
  state and records `discretization changed`.
- Stop a running command: the next command starts from the authored state and
  records `previous live command did not succeed`.
