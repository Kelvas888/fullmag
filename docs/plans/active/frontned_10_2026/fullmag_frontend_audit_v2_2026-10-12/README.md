# Fullmag — plan refaktoryzacji geometry/mesh authoring, v2

**Rewizja dokumentacji po Q01–Q24, 12.10.2026.** Kod odniesienia: `2a3c6becb9c7e111ae1497ec0cd9ac9576acba95`. To ten sam snapshot mastera co w audycie v1, nie deklaracja stanu nowszego HEAD. Nie zmieniono repozytorium ani cudzych plików. Nowa wersja nie jest wykonaniem refaktoryzacji ani kwalifikacją runtime.

## Najpierw przeczytaj

[00 — odpowiedzi Q01–Q24 i decyzje wymagające akceptacji](docs/00_ROZSTRZYGNIECIA_Q01_Q24.md). Następnie [D07 — plan 20 proponowanych PR-ów](docs/07_PLAN_WDROZENIA.md) i [D08 — 72 scenariusze odbioru](docs/08_TESTY_I_REPRODUKCJE.md). [Galeria i czytnik HTML](index.html) działa bez pobierania zasobów z sieci; diagramy Mermaid i wzory LaTeX mają w nim czytelne źródło tekstowe, a diagramy DOT są pokazane jako obrazy.

## Co poprawiono

Pointerup kończy gest i zmienia draft; jeden Apply zatwierdza wymiary oraz położenie. Wykorzystujemy istniejący `patch_object_geometry` z pełnym transformem. `Transform3D` już zawiera quaternion/scale/pivot — nowy plan rozdziela te pola od brakujących/niezakwalifikowanych etapów lowering. Draft ma właściciela w kernelu; Inspector jest widokiem, a viewport właścicielem wyłącznie podglądu i zasobów gestu/GPU.

Przyjęto jeden rekomendowany wariant rebase, identyfikatorów, wpisywania podczas ACK, pivot/Position i parsera. Recovery zwykłych mutacji, kanoniczne digesty oraz marker generacji są **proponowanymi nowymi kontraktami**, nie uznanymi za już działające. Apply Policy + Build to dwa kroki z jawnym częściowym sukcesem. Import wymaga source version, checks, lease i portable asset, a nie samej ścieżki STL.

## Granice gotowości

15 rozdziałów Markdown, 28 ustaleń z niezmienioną klasą C/L/R/G, 32 rekordy źródeł (24 odziedziczone + 8 nowych celowanych odczytów), 20 propozycji PR, 72 planowane testy, 7 makiet i 4 schematy. **Żaden z testów produkcyjnych T01–T72 nie został uruchomiony w ramach tej rewizji.** R1 jest pierwszym użytecznym publicznym zakresem, R0 wewnętrznym hotfiksem, R2-T/I/Q niezależnymi rozszerzeniami po kwalifikacji, R3 świadomie odłożonym zakresem.

Siedem ADR w D00 ma status proposed/do akceptacji. Końcowa gwarancja CAS/trwałego zapisu nie została tutaj dowiedziona przez pełny trace committera ani test konkurencji. PR05 i T51/T52 są bramkami. Nie wykonano rzeczywistego Fullmaga, WebGL, meshera, czterech lane ani pomiarów wydajności; nie podano fikcyjnych FPS. Ograniczenia dowodów: [D01](docs/01_ZRODLA_I_METODYKA.md).

## Rozdziały

- [Rozstrzygnięcia przeglądu Q01–Q24](docs/00_ROZSTRZYGNIECIA_Q01_Q24.md)
- [Źródła i metodyka V2](docs/01_ZRODLA_I_METODYKA.md)
- [Rejestr ustaleń — wersja 2](docs/02_REJESTR_USTALEN.md)
- [Stan źródłowy i różnica wobec celu V2](docs/03_STAN_OBECNY_I_WORKFLOW.md)
- [Wspólna edycja obiektu — kontrakt wykonawczy V2](docs/04_ARCHITEKTURA_DOCELOWA_I_TRANSFORMACJE.md)
- [UI, Explorer, Inspector i narzędzia](docs/05_SPECYFIKACJA_UI_I_INSPEKTOROW.md)
- [Mesh: tożsamość, aktualność, publikacja i rebuild](docs/06_MESH_WORKFLOW_I_JAKOSC.md)
- [Plan dostaw, pliki i bramki — v2](docs/07_PLAN_WDROZENIA.md)
- [Testy wykonawcze, fixtures, recepty i dowody — v2](docs/08_TESTY_I_REPRODUKCJE.md)
- [Wzorce z COMSOL, 3ds Max i bibliotek viewportu](docs/09_BENCHMARKI_I_DECYZJE_PROJEKTOWE.md)
- [Makiety i schematy — semantyka v2](docs/10_MAKIETY_I_SCHEMATY.md)
- [API, ordinary mutation recovery i capabilities](docs/11_KONTRAKTY_API_I_RECOVERY.md)
- [Import i reimport — kontrakt projektu R2-I](docs/12_IMPORT_I_REIMPORT.md)
- [TRS, pivot, migracja i kwalifikacja realizacji](docs/13_TRANSFORMACJE_I_KWALIFIKACJA_FIZYCZNA.md)
- [Baseline i budżety wydajnościowe — Q22](docs/14_BASELINE_I_BUDZETY_WYDAJNOSCIOWE.md)

## Dane i weryfikacja

[findings.json](findings.json), [sources.json](sources.json), [backlog.json](backlog.json), [tests.json](tests.json), [review_traceability.json](review_traceability.json), [state_contracts.json](state_contracts.json) i [benchmark_plan.json](benchmark_plan.json) są zsynchronizowane z tekstem. [Manifest](manifest.json) zawiera SHA256 wszystkich pozostałych plików pakietu.

[verification/package_checks.json](verification/package_checks.json) opisuje kontrolę struktury/linków/tożsamości; [verification/spec_oracle_results.json](verification/spec_oracle_results.json) zawiera obliczenia niezależnych oracle. Skrypty kontrolne są dostarczone i nie importują kodu Fullmaga. PASS pakietu nie oznacza PASS implementacji.

Katalog `reproductions/` zachowano bajtowo z v1, wraz z jego historycznymi wynikami i datą. Stary skrypt nadpisuje swój wynik przy uruchomieniu; nie używać go jako testu naprawionej produkcji. Oryginalne rejestry/manifest oraz uwagi przeglądu zachowano w `historical/`. Zmiana klasyfikacji ustaleń wymaga nowych dowodów, nie tylko lepszego opisu.

Makiety mają oznaczenia release i V2 PROPOSAL/DEMO DATA. Nie są screenshotami uruchomionej aplikacji. Układ ma zostać wdrożony w istniejącym shellu i tokenach, nie jako druga aplikacja.
