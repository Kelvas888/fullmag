# P8-53BF — admission anizotropii materiałowej w FDM

Data: 13.10.2026. Status: **CLOSED dla warunku admission i podanego zakresu
regresji**. P8-53BE, odtworzenie workspace, Compute i cały plan pozostają otwarte.

## Przyczyna i poprawka

Planner wymagał globalnego Exchange/Demag/Zeeman/StaticFieldMap/RotatedDmi,
pomijając realizowaną już anizotropię materiałową. Przy modelu z Ku1=1000 J/m³
i osią Z eksport Python przechodził, lecz Grid kończył się odmową plannera.

`crates/fullmag-plan/src/fdm.rs::has_referenced_material_anisotropy` uwzględnia
materiały przypisane do magnesów, skończone niezerowe współczynniki i poprawne
osie. Single-grid i multilayer korzystają z tego samego warunku. Uniaxial
wymaga obecnego Ku1, zgodnie z konstrukcją runtime. Brak osi zachowuje
dotychczasowe domyślne Z lub X/Y. Nie dodano globalnych oddziaływań, nowej
formuły, fallbacku ani zmiany żądanego device/precision/mode.
Kontrakty: `docs/physics/0402-uniaxial-anisotropy.md` i `0403-cubic-anisotropy.md`.

## Dowody

- Managed build `native-build-512469b6d89f42708b86926e2f540f2e.log`: completed,
  exit 0. Manifest `fe245a03ab381c0d6a8eea5560a157fe4ca2e20fd2915b514487833e6eb9f730`.
  Planner byte-equal z frozen snapshotem; SHA-256
  `b71f03126564ea732d2c11023c3856f52841c3585c890d6e95286459bc53e5e2`.
- Receipt `523affb9b5dd4a13820b33e52171b550`: dziesięć produkcyjnych
  `plan-json --execution-plan` przypadków PASS; Ku1±, Ku2 z Ku1=0, cubic
  dopuszczone; brak/zero/nieużywany materiał, Ku2 bez Ku1 i złe osie odrzucone.
  EXE SHA-256 `55082a2438d2721fa0961d140b34981bc210b6a3a862fa3a3bf55b4ba79b4ad9`.
- Rzeczywisty Grid 4×4×1: komenda `fm-3da7e6ce-68ca-40a5-9328-07b160e6383f`,
  child PID 129268, normalny wait exit 0, kill_requested=false.
- Managed handoff `80afe98f862447cca0045d1706fe05c1`: 158 testów PASS, exit 0.
  Scoped review plannera po korektach bez findings; parser/format check PASS.
  Rust regression source dodane, **NOT RUN** z powodu zakazu kompilowania testów.

## Granice odbioru

| Zakres | Dowód |
|---|---|
| FDM CPU single-grid, double/strict | Planner i Grid PASS; skończony Compute po restore NOT VERIFIED. |
| FDM CPU multilayer | Wspólny warunek i source review; nowy runtime NOT VERIFIED. |
| FDM GPU | Source review zgodności konstrukcji; runtime/parytet NOT VERIFIED. |
| FEM CPU/GPU | Bez zmiany; ten przyrost nie dostarcza kwalifikacji tych lane'ów. |

Cała próba browserowa jest **failed, exit 1**, ponieważ acquisition przed
restartem została odrzucona. Odczyt wykazał disconnected/commandability=forbidden;
ogólna odpowiedź nie dowodzi, która wcześniejsza bramka odmówiła pierwsza.
Zachowano `acquisition-refusal-observation.json`. Własną kartę zamknięto,
API i frontend zatrzymano po weryfikacji PID/EXE; EOF pozwolił native ownerowi
zakończyć cleanup. Receipt potwierdza wait 20/20 procesów i frontend.
Nie jest to graceful API shutdown ani zaliczenie P8-53BE.
