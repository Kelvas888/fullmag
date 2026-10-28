# Audyt scenariusza UI: universe → dwie sfery → parametry siatki → build → jakość

Data: 28.10.2026. Branch: `codex/ui-mesh-build-scenario-20261028`.

## Scenariusz i środowisko

Użytkownik uruchamia Fullmag bez skryptu, tworzy pustą symulację FEM, definiuje
universe, dodaje dwie sfery (r = 50 nm, środki x = ±60 nm), ustawia w Inspektorze
parametry siatki, buduje siatkę i ocenia jej jakość.

Scenariusz odtworzono w przeglądarce na grupie `fullmag-master` (port 3198, backend
`0.1.0-dev.20261028.g44dccd0dc40d`, tryb Docker API-only). Grupy dla worktree zadania
nie zbudowano: bramka launchera wymaga 32 GiB wolnego miejsca na dysku C:, na którym
leży `docker_data.vhdx`, a dostępne było 28 GiB.

Wynik: scenariusz nie przechodzi w obecnym stanie. Siatkę udało się zbudować dopiero
po siedmiu obejściach przez API, i to dla prostopadłościanów zamiast sfer. Po pierwszym
buildzie nie da się już zmienić ani geometrii, ani parametrów siatki.

## Ustalenia

Ważność: **B** – blokuje scenariusz, **W** – daje błędny wynik lub wprowadza w błąd,
**N** – utrudnia pracę.

| # | Waga | Objaw w UI | Przyczyna | Status |
|---|---|---|---|---|
| 1 | B | Apply polityki shared-domain kończy się błędem 400 `invalid type: boolean true, expected a string` | `SharedDomainMeshPolicySection` wysyła `h_max`/`h_min` jako liczby i `optimize` jako bool. Backend (`ScriptBuilderMeshState`) oczekuje `hmax`/`hmin`/`growth_rate` jako tekstu, a `optimize` jako nazwy optymalizatora. Odczyt też używał złych kluczy, więc zapisane wartości nie wracały do pól | poprawione na branchu |
| 2 | B | Build sfery: „Sphere is preview-only for fem and cannot feed the production mesh pipeline yet” | `crates/fullmag-authoring/src/geometry.rs` oznacza `Sphere`/`Ellipsoid` jako `GEOMETRY_KIND_PREVIEW_ONLY`, a ribbon Geometry oferuje sferę bez ostrzeżenia. IR, konwersja `commands.rs` i mesher Pythona (`Ellipsoid` w OCC i voxelizacji) sferę obsługują | otwarte – zmiana w Rust wymaga grupy Docker |
| 3 | B | Build bez materiału: „Object references a missing material” | Walidacja geometrii blokuje `build_mesh` bez materiału i magnetyzacji, choć siatkowanie zależy tylko od geometrii | otwarte – decyzja architektoniczna (pkt A) |
| 4 | B | Build bez interakcji: `IncompletePhysicsError: Problem requires at least one interaction` | Ścieżka buildu renderuje pełny skrypt `Problem`. Nowa sesja FEM ma `exchange_enabled = false` i `demag_enabled = false` | otwarte – pkt A |
| 5 | B | Build bez etapu study: 422 „legacy live execution migration has no authored source for the StudyPlan” | W trybie Docker `mesh_build` wywołuje `ensure_live_accepted_study_with_transition`, który tworzy pełny, wykonywalny StudyPlan | otwarte – pkt A |
| 6 | B | Universe w trybie Auto (domyślnym): „FEM demag requires a conformal shared-domain mesh … Call study.build_domain_mesh()” | Planowanie study przed buildem wymaga istniejącej siatki z powietrzem. Bez jawnego universe (Manual) to zależność cykliczna | otwarte – pkt A |
| 7 | B | Apply universe/Airbox: 409 „universe mesh policy changed since revision 0 (current 7)” | Rewizja polityki to `mesh_revision`, który rośnie przy każdym commicie sceny. Zasób polityki nie był unieważniany przy zmianie sceny, a brudny draft zachowywał starą rewizję | poprawione na branchu (unieważnianie i rebase) |
| 8 | B | Po pierwszym udanym buildzie każda zmiana geometrii lub polityki siatki kończy się 409 `accepted_execution_input_locked`, a przycisk Stop jest nieaktywny | Build tworzy zaakceptowany run czekający na Compute. `validate_active_scene_mutation` blokuje zmiany wejścia nieterminalnego runu. W praktyce sesja zamarza i trzeba utworzyć nową | otwarte – pkt A |
| 9 | W | Siatka zbudowana z h_max = 10 nm ma w obiektach elementy o rozmiarze ~20–24 nm (313 tetraedrów na sześcian 80 nm). Raport deklaruje cel 1e-8 ze źródłem `workflow_default`, a „Size field kinds: none” | Rozmiar per-obiekt nie trafia do pola rozmiaru gmsh w ścieżce Docker. Trop: polityka shared-domain jest przekazywana tylko w `canonical_policy_snapshot` (`manual_remesh.rs`), a `remesh_cli` czyta rozmiary z top-level `mesh_options` | otwarte – wymaga śledzenia w grupie Docker |
| 10 | W | Krok „sprawdzam jakość” jest niemożliwy. `GET …/shared-domain/quality` zwraca `{"revision":10}`, Latest Success = 0, Elements = unknown, log builda jest pusty, fazy pipeline mają status „pending”, a drzewo pokazuje „Mesh outdated – no source-scene provenance” | Ścieżka Docker publikuje siatkę i statystyki w raporcie (`mesh_statistics`: SICN min 0,44–0,47), ale nie wypełnia `mesh_quality_summary`, provenance ani historii buildów | otwarte |
| 11 | W | Readiness po udanym buildzie nadal pokazuje „Build a current shared-domain mesh before running” | Skutek braku provenance z pkt 10 | otwarte |
| 12 | N | Ponowny build zaraz po zmianie polityki: „mesh_revision precondition failed: expected 7, got 8” | `MeshBuildDialog` bierze `mesh_revision` z bieżącego statusu sesji. Status nie odświeżył się po commicie polityki | częściowo: pkt 7 unieważnia polityki; odświeżenie statusu do weryfikacji |
| 13 | N | Manifest siatki ma `object_id: "sphere_left"` (nazwę), a nie `sphere-left-mvscroi3` | Segmenty obiektów kluczowane nazwą geometrii, wbrew kontraktowi `object_id` ≠ `name` | otwarte |
| 14 | N | „Mesh editor capabilities 0/8 – Capability fem is not advertised” w sesji FEM | Zasób meshingu nie publikuje capabilities | otwarte |
| 15 | N | Po utworzeniu symulacji z „Configure now” Inspektor pokazywał „Nothing selected” zamiast Universe | Nieustalona. Wybór opcji nie został potwierdzony zrzutem; możliwa utrata `pendingDomainNavigationSessionIdRef` przy przemontowaniu po zmianie trasy | do weryfikacji |
| 16 | N | Readiness uznaje interakcje za włączone na podstawie `physics_stack` obiektu, a renderer skryptu używa `study.exchange_enabled`/`demag_enabled` | Dwa źródła prawdy dla exchange/demag | otwarte |

## Poprawki na branchu

1. `sharedDomainMeshPolicyDraft.ts` (wydzielone z `SharedDomainMeshPolicySection.tsx`)
   zapisuje i czyta kanoniczne klucze `ScriptBuilderMeshState`: rozmiary jako tekst,
   aliasy COMSOL zachowane, `optimize` jako nazwa optymalizatora (`Netgen` lub pusty
   ciąg). Usuwa też starsze klucze `h_max`/`h_min`.
2. `RealtimeInvalidationBridge` unieważnia semantykę i polityki siatki (universe,
   shared-domain, obiekty) przy każdej zmianie dokumentu sceny.
3. `rebaseAirboxMeshPolicyDraft` przenosi brudny draft Airbox na nowszą rewizję, gdy
   autorska polityka universe na serwerze się nie zmieniła. Prawdziwa współbieżna
   edycja polityki nadal kończy się konfliktem.

Testy regresyjne: `sharedDomainMeshPolicyDraft.test.ts` i nowe przypadki w
`airboxMeshPolicyDraft.test.ts`.

## Plan dla pozostałych blokad

**A. Odsprzęgnięcie siatkowania od fizyki i zaakceptowanego runu** (pkt 3–6, 8, 11).
To decyzja architektoniczna dla ścieżki Docker API-only. Rekomendacja: `mesh_build`
przygotowuje wyłącznie artefakt siatki z geometrii, universe i polityk, bez tworzenia
zaakceptowanego RunIntent. Walidacja materiałów, interakcji i etapów przechodzi do
Compute. Siatka niesie provenance `source_scene_revision`, a zmiana geometrii lub
polityki oznacza ją jako nieaktualną, zamiast blokować edycję. Wariant minimalny:
run przygotowawczy, który nie blokuje wejść i jest zastępowany przy kolejnej zmianie
sceny. Ten wariant nadal wymaga fizyki.

**B. Sfera i elipsoida jako geometria produkcyjna FEM/FDM** (pkt 2), z testem siatki
dwóch sfer w `packages/fullmag-py/tests`.

**C. Egzekwowanie rozmiarów i publikacja jakości** (pkt 9–10, 13): przekazanie
polityki shared-domain i per-obiekt do `mesh_options` w ścieżce Docker, publikacja
`mesh_quality_summary`, provenance i historii buildu, segmenty kluczowane `object_id`.

## Weryfikacja

- Odtworzenie scenariusza: przeglądarka, grupa `fullmag-master`, sesja
  `mesh-two-spheres-probe`. Dowodem są komunikaty błędów i odpowiedzi API cytowane
  w tabeli.
- Poprawki 1–3: NOT VERIFIED w runtime ani w kontroli typów. Zarządzana trasa
  `check-control-room-production-source` wymaga workspace zależności, którego nie da
  się przygotować bez grupy Docker worktree. Testów jednostkowych nie uruchamiano
  (obowiązujący zakaz).
