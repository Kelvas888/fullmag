# Audyt scenariusza UI: universe → dwie sfery → parametry siatki → build → jakość

Data: 28.10.2026. Branch: `codex/ui-mesh-build-scenario-20261028`.

## Scenariusz i środowisko

Użytkownik uruchamia Fullmag bez skryptu, tworzy pustą symulację FEM, definiuje
universe, dodaje dwie sfery (r = 50 nm, środki x = ±60 nm), ustawia w Inspektorze
parametry siatki, buduje siatkę i ocenia jej jakość. Potem zmienia geometrię albo
parametry i przebudowuje siatkę.

**Stan wyjściowy.** Odtworzenie w przeglądarce na grupie `fullmag-master` (backend
`0.1.0-dev.20261028.g44dccd0dc40d`, tryb Docker API-only) pokazało, że scenariusz nie
przechodzi. Siatkę udało się zbudować dopiero po siedmiu obejściach przez API i tylko
dla prostopadłościanów. Po pierwszym buildzie nie dało się już zmienić ani geometrii,
ani parametrów siatki.

**Stan po poprawkach.** Cały scenariusz przechodzi z UI na grupie Docker kopii
weryfikacyjnej worktree (`ui-mesh-build-verify-20261028`, port 3310). Szczegóły
w sekcji Weryfikacja.

## Ustalenia

Waga: **B** – blokuje scenariusz, **W** – daje błędny wynik lub wprowadza w błąd,
**N** – utrudnia pracę.

| # | Waga | Objaw w UI | Przyczyna | Status |
|---|---|---|---|---|
| 1 | B | Apply polityki shared-domain kończy się błędem 400 `invalid type: boolean true, expected a string` | `SharedDomainMeshPolicySection` wysyłała `h_max`/`h_min` jako liczby i `optimize` jako bool. Backend (`ScriptBuilderMeshState`) oczekuje `hmax`/`hmin`/`growth_rate` jako tekstu, a `optimize` jako nazwy optymalizatora. Odczyt używał złych kluczy | naprawione, zweryfikowane w UI |
| 2 | B | Build sfery: „Sphere is preview-only for fem” | `geometry.rs` oznaczał `Sphere`/`Ellipsoid` jako preview, choć IR i mesher je obsługują | naprawione dla FEM, zweryfikowane w UI |
| 3 | B | Build bez materiału: „Object references a missing material” | Walidacja geometrii blokowała `build_mesh` bez materiału i magnetyzacji | naprawione (blokują tylko Compute), zweryfikowane |
| 4 | B | Build bez interakcji: `IncompletePhysicsError` | Build renderował pełny skrypt `Problem` | naprawione (ADR 0074), zweryfikowane |
| 5 | B | Build bez etapu study: 422 „no authored source for the StudyPlan” | `mesh_build` tworzył pełny, zaakceptowany StudyPlan | naprawione (ADR 0074), zweryfikowane |
| 6 | B | Universe Auto: „FEM demag requires a conformal shared-domain mesh …” | Planowanie study przed buildem wymagało istniejącej siatki z powietrzem | build nie planuje study; Auto bez paddingu daje czytelny błąd (pytest) |
| 7 | B | Apply Airbox: 409 „changed since revision 0 (current 7)” | Zasób polityki nie był unieważniany przy zmianie sceny, a brudny draft trzymał starą rewizję | naprawione, zweryfikowane w UI |
| 8 | B | Po pierwszym buildzie każda zmiana geometrii lub polityki siatki kończy się 409 `accepted_execution_input_locked`, a Stop jest nieaktywny | Build tworzył run czekający na Compute, który zamrażał wejścia | naprawione (ADR 0074), zweryfikowane w UI |
| 9 | W | Elementy w obiektach ~20–24 nm przy h_max = 10 nm | (a) ścieżka Docker nie przekazywała polityki do top-level `mesh_options`; (b) mesher nie zaciskał ciała bez receptury, gdy `airbox_hmax` > `hmax` | naprawione; (b) pytest, (a) UI: ~2270 tetraedrów na sferę zamiast 88–176 |
| 10 | W | Brak jakości w UI: pusty `/quality`, Latest Success = 0, brak provenance | Ścieżka Docker nie publikowała `mesh_quality_summary` ani historii | naprawione: SICN/gamma w `/quality`, historia, `source_scene_revision` |
| 11 | W | Readiness po buildzie: „Build a current shared-domain mesh” | Skutek pkt 10 | naprawione, zweryfikowane |
| 12 | N | Build: „mesh_revision precondition failed: expected 3, got 4” | Status sesji nie odświeżał się po zmianie siatki | naprawione (status przy zdarzeniu Mesh), zweryfikowane |
| 13 | N | Manifest z `object_id` równym nazwie | Segmenty kluczowane nazwą geometrii | naprawione w ścieżce ADR 0074 (`object_id` z dokumentu sceny) |
| 14 | N | „Mesh editor capabilities 0/8 – fem is not advertised” | Zasób meshingu nie publikuje capabilities | otwarte |
| 15 | N | „Configure now” w oknie New simulation nie otwiera Inspektora Universe | Potwierdzone (`aria-checked=true`, a Inspektor pokazuje „Nothing selected”); przyczyna nieustalona | otwarte |
| 16 | N | Readiness uznaje interakcje na podstawie `physics_stack`, a renderer skryptu używa `study.exchange_enabled`/`demag_enabled` | Dwa źródła prawdy | otwarte |
| 17 | W | „Element growth rate” = 1,3 kończy build błędem `adjacent_size_growth_exceeded` | `_mesh_result_payload` traktuje `growth_rate` jako twardą bramkę po siatkowaniu (tolerancja 0) | otwarte – decyzja: bramka czy wskazówka |
| 18 | B | Build z sekcji Inspektora: „Choose FEM or FDM in Study settings” | Kontekst polecenia w Inspektorze nie miał statusu sesji | naprawione (Shared-Domain i Airbox), zweryfikowane |
| 19 | N | Dialog buildu: „scene_revision precondition failed: expected 4, got 5” | Zasób sceny w dialogu podawał rewizję z cache | naprawione (nowsza z rewizji: zasób sceny albo status), zweryfikowane |
| 20 | B | Druga edycja Airbox blokuje Compute: `scene_document_universe_conflict` | Trasa polityki universe aktualizowała `scene.universe` tylko przy pierwszym zapisie | naprawione, zweryfikowane |
| 21 | B | Compute FEM po buildzie tylko z geometrii: „simulation preparation unavailable” | Frontend wymagał przygotowania, które dawniej powstawało przy buildzie | naprawione: przy braku przygotowania przygotowuje serwer; Compute zakończony |
| 22 | N | Po udanym Apply Inspektory Universe i geometrii nadal zgłaszają niezapisane zmiany | Draft pozostaje „dirty” względem nowej bazy | otwarte |
| 23 | N | Polecenie `close` w trybie Docker zostaje w kolejce (`queued`) | Brak konsumenta journala w trybie API-only | otwarte |

## Commity

- `664902d6e`, `ccc864c53` – raport audytu.
- `7a8701987` – zacisk rozmiaru ciała w mesherze, nota 0102, test pytest.
- `3da221619` – moduł `fullmag.meshing.geometry_mesh_build` i ADR 0074.
- `49b9caf51` – API: build siatki tylko z geometrii (bez RunIntent), bramki
  authoringu, sfera i elipsoida FEM, pakowanie w planerze, payload w runnerze.
- `cf8bfb283` – synchronizacja `universe` z `study.universe_mesh`.
- `117efbdf4` – format polityki shared-domain i kontekst polecenia w Inspektorze.
- `d7397891f` – aktualne rewizje buildu, rebase Airbox, Compute bez przygotowania.

## Weryfikacja

- **pytest** (Python hosta: miniconda, gmsh 4.15.2; nie interpreter zarządzany przez
  repo): `test_shared_domain_body_hmax.py` i `test_geometry_mesh_build.py` przechodzą.
  W `test_meshing.py`, `test_meshing_fallbacks.py`,
  `test_conformal_occ_degenerate_retry_regression.py` i `test_mixed_element_meshing.py`
  przechodzi 602 testów. 9 pada identycznie z poprawką i bez niej (środowisko hosta).
- **Kompilacja Rust:** backend grupy weryfikacyjnej zbudował się z całą zmianą
  (`development: succeeded`, potem restart `iteration: succeeded` po zmianie `mesh.rs`).
  Testów jednostkowych Rust nie kompilowano (obowiązujący zakaz).
- **Frontend:** `tsc --noEmit` na kodzie produkcyjnym (bez plików testów) i ESLint
  `--max-warnings=0` na zmienionych plikach przechodzą w kontenerze `frontend` grupy.
  Testów vitest nie uruchamiano.
- **Przeglądarka (port 3310), krok po kroku:**
  1. Nowa symulacja FEM.
  2. Universe Manual 400×240×240 nm, `airbox_hmax` 30 nm (Apply z Inspektora).
  3. Dwie sfery z wstążki, bez materiałów.
  4. Polityka shared-domain h_max 10 nm, h_min 3 nm, Netgen (zapis i odczyt).
  5. Build z sekcji Inspektora: 12 325 tetraedrów, ~2270 na sferę, SICN p5 0,62,
     segmenty z `object_id`, readiness bez blokady siatki.
  6. Zmiana promienia prawej sfery na 40 nm (bez 409) i rebuild: 1215 elementów.
  7. Zmiana h_max na 20 nm i `airbox_hmax` na 40 nm (200) i rebuild: 336/198 elementów.
  8. Fizyka, etap relax i Compute: `solve` zakończony, 8 kroków.

  Canvas WebGL jest widoczny, kontekst nie jest utracony, bufor rysowania ma 684×449,
  a dialog potwierdził renderowanie nowej rewizji siatki.
- **Środowisko:** grupy pierwotnego worktree nie dało się uruchomić. Najpierw zabrakło
  pul adresów sieci Docker; za zgodą użytkownika usunięto 8 pustych sieci. Potem
  launcher zostawił znacznik aktywnej operacji bez usług. Do weryfikacji użyto
  odłączonej kopii worktree na tym samym commicie z tymi samymi zmianami. Bramkę
  wolnego miejsca launchera (32 GiB) na polecenie użytkownika obniżono lokalnie do
  24 GiB tylko na czas weryfikacji; zmiana nie weszła do commitów.
