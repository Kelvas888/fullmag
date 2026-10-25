# Airbox i Mesh — plan naprawy

**Cel:** poprawne, aktualne i jawnie opisane informacje Airboxa w Inspectorze, także dla siatki mieszanej; dowody API i przeglądarki, PR, merge i cleanup.

**Kontrakt:** wykonanie solvera, opublikowana topologia oraz polityka autorska mają niezależne stany. Brak rozstrzygnięcia wykonania nie odbiera prawa odczytu zgodnego artefaktu. Jakość markera 0 dotyczy Airboxa; jakość całej domeny pozostaje osobna. Brak metryki nigdy nie oznacza pass.

**Baza:** `28f4fcf5bba4387025944b8fb276c94b3eef5eb5`. Worktree zarządzane przez Codex: `/home/kkingstoun/.codex/worktrees/airbox-inspector-mesh-quality/fullmag`; branch `codex/airbox-inspector-mesh-quality`; rejestr `fullmag-d57a89a82a23172e`. Lokalizacja wynika z natywnego narzędzia worktree.

**Ograniczenia:** zachować obce zmiany; tylko grupa Docker wybranego checkoutu; bez hostowych buildów i instalacji; bez kompilacji testów jednostkowych zgodnie z poleceniem użytkownika; żadnego fallbacku GPU→CPU ani fałszywego SICN z proxy.

## Etapy i właściciele

- [ ] Python (worker mixed_quality): publikacja statystyk tet4/prism6/pyramid5 i pozostałych obsługiwanych rodzin, obliczenia per marker i global, jednostki SI, zachowanie pochodzenia metryk. Testy analityczne i nota naukowa przed zmianą obliczeń.
- [ ] API (root): prawdziwy wynik bramek Airboxa z istniejących progów i dowodów, liczba wspólnych węzłów, fallback z raportu budowy dla effective target, kontrola niepełnych danych.
- [ ] UI (worker airbox_frontend): żywe statusy, niezależność inspekcji artefaktu od gotowości solvera, zakres jakości i jednostki, aktualność, poprawne stany FDM.
- [ ] Weryfikacja (root): uruchomienie grupy Compose worktree, adekwatne lint/typecheck i interpretowane sprawdzenia, rzeczywiste dane siatki mieszanej, przegląd wszystkich paneli Airbox Mesh w przeglądarce oraz stanów loading/empty/stale/error. Zmiany edycji wymagają stabilności Object i Airbox.
- [ ] Integracja (root): review diffu i dowodów, logiczne commity, PR do master, wymagane kontrole/akceptacje, merge, bezpieczny fast-forward i cleanup wyłącznie zasobów zadania.

## Kryteria odbioru

1. Root/Mesh i nawigacja wewnętrzna nie generują bezpodstawnego unknown.
2. Published FEM z unresolved execution pozostaje dostępny do inspekcji, bez odblokowania nielegalnych poleceń.
3. Siatka mieszana ma zgodne sumy elementów, węzłów i objętości; miary mają jawny zakres, jednostki i źródło. Test obejmuje również brak i błędne dane.
4. Bramki jakości rozróżniają pass/fail/unknown; loading, brak publikacji i stale nie dają pass.
5. Przeglądarka i API pokazują tę samą rewizję oraz wartości; brak błędów konsoli i utraty tożsamości panelu podczas odświeżeń.
6. Ukończenie wymaga dowodu merge i cleanup; blokady są zapisane z następnym krokiem.

## Ryzyka do review

- Stary manifest po zmianie sceny/polityki i równoczesne odświeżanie zasobów.
- Mieszane rodziny elementów, wspólne węzły i kwadratowe ściany.
- Brak per-element Gmsh quality; nie wolno zastępować jej metryką o innym znaczeniu.
- Rozbieżność authored/runtime/published artifact FEM/FDM.
- Parametry efektywne to ustawienia, nie dowód osiągniętego rozmiaru elementów.

## Dowody

W trakcie implementacji uzupełnić wyniki i pełne hashe commitów. Audyt wejściowy: API master posiadało mixed mesh 1087250 elementów, Airbox 1057639 elementów, 183713 węzłów, quality null oraz unresolved active lane. To nie jest dowód stanu worktree po naprawie.

### Grupa i pierwsze uruchomienie

- Grupa: `fullmag-worktree-fullmag-d57a89a82a23172e`, port `3269`.
- Toolchain: próba `b9ba7444bed64577a4ee011f91cac24d`, sukces; obraz `sha256:411d6a179d9c3323741fe8fa64af5e619b6ee9704f658edad4afcfb0b2273cd2`.
- Pierwszy DEV: próba `a586d153bbc543808ed6b80b6d1b43cb`, sukces; konfiguracja `dde8746005f869facdc35a261a7d1b17cba908c01361edb7a7038bed4b50be44`. Potwierdzony start API; nie jest to jeszcze dowód poprawek ani przeglądarki.
- Receipty są w wolumenie kontrolnym `fullmag-build-control-fullmag-worktree-fullmag-d57a89a82a23172e-7b581684b085de65`.
- Po pierwszym etapie: około 24 GB wolnego miejsca na filesystemie checkoutu. Cache i pakiet grupy pozostają potrzebne do przyrostowej weryfikacji. Brak kandydatów do usunięcia w tym etapie; ponowna ocena po integracji i zatrzymaniu grupy.
- Testy Rust dodane dla pokrycia braków i zgodności danych pozostają niewykonane zgodnie z zakazem kompilacji testów jednostkowych. Kompilacja aplikacji oraz interpretowane sprawdzenia i dowody runtime są osobnymi bramkami.
