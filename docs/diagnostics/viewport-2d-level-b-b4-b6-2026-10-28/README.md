# Widok 2D, poziom B: B4–B6 — dowody 2026-10-28

## B4 — nawigator migawek
- Implementacja: `PlanarSnapshotNavigator` nad mapą 2D. Kroki ‹ › po migawkach `m` wybranego etapu
  histerezy, odtwarzanie klatka po klatce (krok dopiero po narysowaniu bieżącej klatki), „Live”.
  Używa tego samego zaznaczenia, które publikuje wykres histerezy.
- Runtime **BLOCKED na masterze**: aktywacja fixture histerezy (`examples/fdm_hysteresis_snapshot_smoke.py`,
  także `viewport_2d_planar_monitor_fdm_smoke.py`) jest odrzucana komunikatem
  `study pipeline primitive stage 'hysteresis' is not yet executable by the runtime; materialize it
  into explicit stages first`. Bez runu nie ma migawek, więc nawigator nie ma czego pokazać.
  Weryfikacja: `tsc --noEmit`, eslint, vitest `planarSnapshotNavigation` (napisany).

## B5 — uchwyt płaszczyzny w 3D
Grupa DEV `viewport-2d-snapshot-navigator-20261028` (checkout B5), fixture
`examples/viewport_2d_planar_monitor_fdm_multi_object_smoke.py` (scena wczytana, start symulacji
odrzucony przez master jak wyżej), Chromium headless (SwiftShader):
- wybór monitora „XY plane”, zmiana `Origin Z` na 5 nm w Inspectorze → szkic → podgląd ramki i
  uchwyt wzdłuż normalnej (`b5-handle-before-drag.png`);
- przeciągnięcie uchwytu o 60 px w górę → `Origin Z` w Inspectorze = 32,88 nm, ramka przesunięta,
  kamera bez obrotu (`b5-handle-after-drag.png`); 0 błędów strony.
- Smoke wykrył dwie wady, naprawione: zbyt cienki cel trafienia; menedżer zdarzeń 3D odkładał
  `pointerdown` do kliknięcia (sonda tylko dla `move-axis`), więc przeciąganie obracało kamerę.

## B6 — indeks przestrzenny
Grupa DEV `viewport-2d-element-index-20261028`, fixture `examples/viewport_2d_fem_mixed_smoke.py`
(FEM CPU, Prism6 + Pyramid5 + Tet4), stan początkowy `m`:
- profil po przekątnej ramki: 327 punktów (256 równomiernych) w 28 ms, 2121 punktów (2048) w 42 ms;
  73 przecięcia ze ścianami elementów;
- 61 punktów profilu (lokalizacja przez BVH) porównanych z sondą w tych samych (u, v) (skan
  bezpośredni): wartość i zajętość identyczne bitowo, 0 rozbieżności.
