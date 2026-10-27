# 2D Slice Capabilities

Ten status rozróżnia implementację, wykonanie zarządzane, dowód przeglądarkowy
i walidację naukową dla kanonicznej powierzchni `field-map`. Raporty z lipca
2026 są **historycznym punktem odniesienia**, a nie dowodem aktualnego `HEAD`.
Aktualny smoke wymaga zgodności telemetryki aktualnego żądania z wyrenderowanym
rastrem, zanim może zapisać `pass: true`.

| Feature | FDM CPU | FEM CPU | FEM GPU run | Evidence status |
|---|---|---|---|---|
| Session `Default` source: XY/XZ/YZ plane sample | implemented, source-tested | implemented, source-tested | implemented, source-tested; runtime pending | managed science/browser qualification not yet available on current HEAD |
| Session `Default` source: slab average | implemented, source-tested | implemented, source-tested | implemented, source-tested; runtime pending | managed science/browser qualification not yet available on current HEAD |
| Plane heatmap and probe | yes | yes | yes | historycznie validated; wymaga świeżego smoke HEAD |
| Slab average | yes | yes | yes | historycznie validated; wymaga świeżego smoke HEAD |
| Depth projection (tylko monitor autorski) | yes | yes | yes | historycznie validated; wymaga świeżego smoke HEAD |
| Surface projection | unsupported (422) | yes | yes | historycznie validated dla FEM; wymaga świeżego smoke HEAD |
| Magnetic vectors | yes | yes | yes | historycznie browser verified; wymaga świeżego smoke HEAD |
| Contours and masked holes | yes | yes | yes | focused model tested |
| Mesh overlay | structured outline | exact FEM section | exact FEM section | historycznie browser verified; wymaga świeżego smoke HEAD |
| PNG export | yes | yes | yes | contract tested |
| 3D frame preview | yes | yes | yes | historycznie browser verified; wymaga świeżego smoke HEAD |

## Parity z forkiem MuMax3 (2026-10-27)

Wzorzec: `external_solvers/3` @ `984c6e9d`. Szczegóły i luki:
`docs/audits/2026-10-27-viewport-2d-mumax3-fork-parity-audit.md`.

| Element | Stan | Dowód |
|---|---|---|
| Ilość wybrana w 2D w zapotrzebowaniu runtime (`observation_quantities`) | implemented | test API `observation_demand_includes_visible_planar_quantity_only` (napisany, nieuruchomiony: zakaz kompilacji testów) |
| Pełnorozdzielcze pola obserwowane w trakcie runu FDM CPU / FEM CPU | implemented | testy runnera (nie uruchomione lokalnie) |
| FDM `plane_sample` jako średnia powierzchniowa (`fdm_cell_area_plane`) | implemented | nota 0970 PM-N15, testy samplera (napisane, nieuruchomione) |
| Pasek sekcji nad powierzchnią: płaszczyzna, `Single layer / Average`, warstwa FDM | implemented, browser smoke | vitest `PlanarSectionStrip`, `planarSectionModel` (napisane, nieuruchomione); smoke 2026-10-27 niżej |
| Inspector: dyskretna warstwa FDM, średnia po pełnej grubości | implemented | vitest `PlanarVisualizationSection` (napisane, nieuruchomione) |
| Presety rozdzielczości siatki natywnej FDM | implemented | vitest `planarSectionModel` (napisane, nieuruchomione) |
| Zakres `layer` (multilayer FDM) i odblokowany FDM Airbox | implemented | vitest `fieldMapDataPlan`, `VisualizationViewContext` (napisane, nieuruchomione) |
| `render.png` z paletą i zakresem sesji | implemented (palety backendu: viridis, gray, coolwarm; inne → viridis) | — |
| Push klatek 2D przez WebSocket, sampler GPU | not implemented | — |

## Etap F1 planu `viewport-2d-mumax-parity-2026-10-27` (2026-10-27)

Dowody: produkcyjny typecheck i ESLint `apps/control-room` w kontenerze
frontendu grupy `fullmag-worktree-viewport-2d-production-20261027-…` (exit 0);
backend skompilowany w kontenerze `backend` tej grupy; codegen OpenAPI z
receiptem; smoke przeglądarkowy (Playwright 1.62.1, Chromium 1234 headless,
fixture `examples/viewport_2d_mumax_parity_fdm_smoke.py`, FDM CPU double,
128×128×2): otwarcie 2D klawiszem `2` → gotowa klatka w 0,3 s, krok warstwy
`[`/`]` w ~20 ms bez placeholdera, składowa `z`, 98 glifów ze strzałkami,
powrót do 3D z `isContextLost=false` i niezerowym buforem, 0 błędów konsoli i
strony. Smoke jest sesyjny (nie jest receptą repozytorium) i nie jest
kwalifikacją produkcyjną. Testy jednostkowe są napisane, ale nieuruchomione
(zakaz kompilacji testów).

| Element | FDM CPU | FEM | Dowód |
|---|---|---|---|
| Pasek kontrolek nad mapą (wielkość, składowa, sekcja, strzałki, siatka) | browser smoke | source | smoke 2026-10-27 |
| Koło barw mumax3 (`hsl_direction`) w 2D, 3D i `render.png` | browser smoke | source | smoke; zrzut z ciemnymi strzałkami |
| Strzałki na siatce ekranowej z grotami, min. długość, ⊙/⊗ | browser smoke | source | smoke (98 glifów) |
| Retencja klatki przy kroku warstwy, odczyt `showing … · loading …` | browser smoke | source | smoke (`placeholderSeen=false`) |
| Proporcje fizyczne u:v (kontener rozmiaru) | browser smoke | source | zrzut: dysk okrągły |
| `meta.section` (żądane/rozwiązane, indeks warstwy) i Inspector | implemented | implemented | testy Rust napisane; codegen OK |
| Skróty `[ ] { } V X Y Z M A G`, `fit`, `reset-view`, `export-data` | browser smoke (`[ ] z a v`) | source | smoke |
| Inspector `Live` tylko po dowodzie klatki | implemented | implemented | typecheck |

## Status Language

Use these messages consistently:

- `Requires FEM explicit topology` for FEM-only mesh and airbox controls on unsupported domains.
- `No airbox mesh part in current domain` when FEM topology exists but has no airbox part.
- `Using local fallback` or `mesh: local fallback after backend error` when backend mesh overlay cannot be used.
- `Not implemented E2E yet` for contour, primitives, and airbox vectors;
  slab sampling is implemented in the shared sampler but still needs fresh
  managed/browser evidence on the current HEAD.
- `Default` is a session-resolved source, not an authored monitor; it is not
  added to `SceneDocument`, `ProblemIR`, canonical Python, or Explorer.
- `source-tested` means the contract, resolver, transport, or UI behavior was
  exercised locally. It is not a managed-runtime or production qualification.
- FDM GPU remains `not_qualified`: the required managed launcher and an
  executed device/carrier proof do not exist, so no green status is inherited
  from FDM CPU.

## Historyczne evidence zarządzane (2026-07-18)

- `fdm-cpu`: science and browser reports pass; requested/resolved `fdm/cpu`; 100 switches; 61,594,483-byte heap growth.
- `fem-cpu`: science and browser reports pass; requested/resolved `fem/cpu`; 100 switches; 7,936,018-byte heap growth.
- `fem-gpu`: science and browser reports pass; requested `cuda` (GPU alias), resolved `fem/gpu`; 100 switches; 7,457,770-byte heap growth.
- Cross-backend manufactured linear-field relative RMS is about `1.19e-3` for both FEM lanes.

Raporty i screenshoty są pod `.fullmag/reports/viewport-2d-planar-monitor-smoke/`,
ale nie kwalifikują aktualnego `HEAD`. Planar sampling jest obecnie jawnym CPU
postprocessorem nawet, gdy symulacja rozwiązuje się na FEM GPU; raport ma to
rejestrować zamiast sugerować sampler rezydujący na urządzeniu.

## Baseline authored-monitor smoke contract (2026-08-12)

- Smoke `viewport-2d-browser-smoke-v2` publikuje monitor ID, operator kind,
  quantity/component, `meta.etag` jako tymczasową sample identity,
  field revision, status, checksum/range rastra oraz liczby glyph/contour/mesh.
- `pass: true` jest dozwolone wyłącznie, gdy każdy obserwowany raster jest
  `ready` i jego identity oraz field revision zgadzają się z odpowiedzią
  `meta` zużytą przez przeglądarkę.
- Fixture do kolejnego świeżego uruchomienia: compact FEM
  `examples/viewport_2d_planar_monitor_fem_compact_smoke.py` i multi-object
  FDM `examples/viewport_2d_planar_monitor_fdm_multi_object_smoke.py`.
- To nie jest managed-runtime qualification; wymagane jest osobne uruchomienie
  repozytoryjnej receptury `just` po jej przełączeniu na te fixture.

## Default planar source implementation (2026-08-16)

- `visualization/state.planar` now has typed `source` and `default_slice`
  state. A fresh session resolves `Default`, `xy`, and `position_fraction=0.5`;
  selecting 2D does not list monitors, create a draft, or mutate the model.
- The `planar-default` data family uses the same backend planar sampler as an
  authored monitor and publishes source-aware meta, identity, frame, operator,
  and canonical child links.
- The Inspector exposes `Default`/authored monitor selection, XY/XZ/YZ,
  position fraction, resolved coordinate, and plane/slab sampling controls.
- Local evidence currently includes the validator suite, focused frontend/API
  tests, typecheck, and API/architecture hygiene. The managed recipe and
  browser/science reports for the current HEAD remain pending because the
  managed native runtime storage is full; no lane is `production-qualified`.

## Release Policy

Powyższe authored-monitor lane'y są zaimplementowane, lecz ich browser/science
status z lipca pozostaje historyczny do czasu świeżego dowodu. Airbox-specific
field availability nadal wynika z kanonicznego quantity catalog, a nie z samej
widocznej geometrii airboxa. Scena bez monitorów otwiera teraz sesyjny `Default`
po przygotowaniu domeny; nie tworzy niezatwierdzonego draftu i nie wymaga Apply.
Utworzenie trwałego monitora pozostaje wyłącznie jawną akcją authoringową.
