# P8 — odbiór meshera w CI i kontrakty sceny Python

Data: 15.10.2026. Baza: `f4c15a8781a8bc43fa72464b81d074aaa973898c`,
współdzielony master; cudze zmiany compute/API/frontend pozostawione.

## Wynik CI i przyczyny

[Python job 116307821097](https://github.com/MateuszZelent/fullmag/actions/runs/38700675368/job/116307821097)
potwierdził SUCCESS kroku `Run real Gmsh exact-layer airbox grading regressions`
(07:47:09 UTC). Tym samym poprawka body-first z 53CU ma również odbiór
tej bramki na Linux CI, odrębny od lokalnych receiptów Windows.
Nie oznacza to wykonania solvera FEM ani kwalifikacji fizycznej.

Następny krok `Run eigensolve scene and execution profile merge contracts`
zakończył się **119 PASS / 8 FAIL**:

- siedem przypadków wywoływało `_render_scene_stage_bootstrap` bez wymaganego
  keyword-only `magnet_vars`; trzy bezpośrednie call sites otrzymały `{}`,
  bo testują samodzielne etapy eigen bez powiązanych magnet handles;
- test auxiliary ID oczekiwał usuniętego błędu unsupported, mimo że renderer
  przekazuje publiczne `geometry_object(..., object_id=...)`, a
  `Problem.to_ir` publikuje auxiliary identity w `physics_objects`.
  Zmieniono test na kontrolę całego obiektu identity i braku dodatkowego magnetu.

Nie zmieniono kodu produkcyjnego, solvera ani asercji invalid authored eigen,
Floquet, parametrów solvera i konfliktów k-vector/path. Dostosowanie testów
wynika z bieżących konsumentów i kontraktu oddzielenia object_id/name/type.

## Wykonanie lokalne

Dokładnie pięć plików kroku CI (eigen scene merge, scene→IR, STL owner fallback,
execution profile authoring roundtrip, scene execution config):
**127/127 PASS**, 0 failures/errors/skipped, pytest exit 0, 4.33 s.

Receipt:
`C:/git/fullmag/storage/runs/fullmag-0950f4dca4ffe38f/python-scene-authoring-contracts/d88c362632a641e789f49c3af326de48/receipt.json`.
Resolver użył istniejącego profilu `windows-native-fdm-cpu-dev`; testy działały
pod `build_lock`, bez heavy builda, kompilacji native/Rust, pip install,
bytecode i cache pytest. Temp/JUnit/log znajdują się w tym run root.
Fingerprint wszystkich źródeł pakietu Python i pięciu testów oraz HEAD
pozostał stabilny. Dodatkowy ukierunkowany eigen fixture: 11 PASS.
AST i diff checks PASS; root source review bez konkretnego P0–P2.

## Retencja i granice

Zachować ten dokładny run root jako dowód i jego log/JUnit/receipt/temp.
Nie wykazano zbędności i nie ma autoryzacji usunięcia. Ponowna ocena po
odbiorze nowego CI i trwałym archiwum dowodów. Wolne C: 46720737280 B;
nie jest to pomiar odzysku. Brak prune, usuwania cache i cudzych buildów.
Rust CI job `116307821115` nadal aktywny; nie zaliczać nowych regresji IR
ani całego planu na podstawie sukcesu Python. Pełny plan **IN PROGRESS**.
