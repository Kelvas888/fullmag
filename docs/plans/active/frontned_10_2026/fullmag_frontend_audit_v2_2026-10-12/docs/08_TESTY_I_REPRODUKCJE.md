# Testy wykonawcze, fixtures, recepty i dowody — v2

**72 scenariusze planowane; nie są wynikami testów Fullmaga.** T01–T50 zachowują identyfikatory v1; T02/T16/T18/T25/T42/T49 zostały uzgodnione z nową semantyką. T51–T72 uzupełniają kontrakty i kwalifikację. Oryginalne R01–R07 są zamrożonym historycznym modelem starego zachowania. Nie uruchamiano ponownie ich skryptu nad starym `results.json`.

## 1. Typ dowodu a dozwolone wykonanie

| Warstwa | Co sprawdza | Czego nie potwierdza |
|---|---|---|
| SPEC | Niezależne liczby oracles, JSON, linki, macierz | Zachowania produkcyjnych reducerów / backendu |
| BROWSER fixture | DOM i cykl interakcji z kontrolowanym API | Meshera, solvera, serwerowej atomowości |
| API real | Schema, CAS, receipts, lifecycle rzeczywistego API | WebGL ani nauki |
| WEBGL real | Widoczny canvas, `isContextLost()===false`, dodatni drawing buffer, ray/drag | Poprawności physical lowering |
| MANAGED runtime | Prawdziwy planner/mesh/solver w zatwierdzonym profilu | Innych urządzeń/precision automatycznie |
| PHYSICS | Zatwierdzona nota + numeryczne invariants/convergence | Sam screenshot nie jest oracle |
| PERFORMANCE | Porównywalny baseline i pomiary | Nie można ogłosić pass bez danych |

Repo tymczasowo zakazuje kompilowania testów jednostkowych. Nie uruchamiać `cargo test`, `vitest` ani zadania generującego/kompilującego unit suite pod pretekstem tej macierzy. Poniższe scenariusze opisują testy do napisania i kwalifikacji w dozwolonej ścieżce. Gdy wymagana bramka nie może być uruchomiona w ramach obowiązującej polityki, zapisać **blocked**, a nie zwolnienie z bramki. Plain Python walidacji tego pakietu nie importuje produkcyjnych modułów. [S32: `AGENTS.md`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/AGENTS.md)

## 2. Recepty i zależności środowiska

| ID | Recepta / punkt wejścia | Preconditions i dowód |
|---|---|---|
| Q-POLICY | Odczyt AGENTS, frontend.md, rejestru i storage governance na aktualnym task SHA | Zakres, owner, worktree/profile/storage; żadnego override zakazu unit compilation |
| Q-TYPES | `pnpm --dir apps/control-room typecheck` | Zatwierdzony storage/profile; dokładny Node/pnpm z checkoutu, nie instalacja latest |
| Q-LINT | `pnpm --dir apps/control-room lint` | ESLint `--max-warnings=0`; warning to fail |
| Q-HYGIENE | `pnpm --dir apps/control-room check:architecture-hygiene` i `check:api-hygiene` | API/schema/resource boundaries; dołączyć log obu recept |
| Q-DOCTOR | Adekwatna repo recepta React Doctor z przypiętą wersją profilu | Nie używać bezrefleksyjnie root `@latest`; reviewer uzasadnia changed-component scope |
| Q-BROWSER | Istniejące `smoke:scratch-authoring-ui`, `smoke:inspector`; nowy browser-regression adapter T55/67 | Reuse zatwierdzonego dev server tylko read/use, bez przejmowania procesu. Konfiguracja URL/session/storage według skryptu |
| Q-WEBGL | Istniejące `smoke:viewport-3d` plus nowy authoring scenario driver | Widoczny canvas, context not lost, buffer width/height>0 po load i operacji; screenshot + trace; lifecycle teardown oddzielnie |
| Q-API | Nowy minimalny driver real-API z fault injection dla T51–53/65 | Driver nie jest jeszcze w repo; przed implementacją ustalić zatwierdzony start API/profile. Nie podszywać stub-a pod real API |
| Q-MANAGED | Właściwa istniejąca recepta managed runtime ustalona z `justfile` na task SHA | Nie wybrano tutaj nieprzeczytanej recepty/profilu. Host preflight, lane/precision requested/resolved, builder/mesher version |
| Q-PHYSICS | Recepta z zatwierdzonej noty naukowej PR13/14 | Parametry/tolerancje/precision i niezależne oracle; każda deklarowana lane oddzielnie |
| Q-PERF | Istniejące `audit:idle-performance`, `audit:viewport-3d-memory-churn` + PERF-01 driver | D14, stały model/quality/hardware; brak pomiarów = not_measured |

Nazwy istniejących skryptów pochodzą z package.json odczytanego w audycie v1; przed uruchomieniem przeczytać ich aktualny kontrakt parametrów. Nie są tu uruchomione i nie obejmują automatycznie wszystkich nowych przypadków. [S24: `package.json`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/package.json) [S31: `frontend.md`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/.agents/instructions/frontend.md)

## 3. Macierz test → PR → fixture → oracle

Fixture JSON jest kontraktem danych, nie gotowym projektem `.fms` ani skryptem produkcyjnej inicjalizacji. PR owner dopisuje adapter używający rzeczywistego API/DSL i dołącza hash zmaterializowanego fixture. Żaden wymyślony helper nie jest podawany jako istniejący Fullmag DSL.

| Test / release | PR | Scenariusz | Fixture | Oracle / odbiór | Recepty |
|---|---|---|---|---|---|
| T01 · R1 | PR01, PR02 | Dwie kolejne edycje wymiaru jednego Box. | [authoring_sequences](../fixtures/authoring_sequences.json) | Drugi request używa rewizji po pierwszym ACK. | Q-API, Q-BROWSER |
| T02 · R1 | PR01, PR07 | Zmiana promienia → drag → pointerup → Revert albo Apply | [authoring_sequences](../fixtures/authoring_sequences.json) | Pointerup 0 mutation; Revert przywraca wymiar+position; Apply jeden patch_object_geometry z pełnym transform, jedna rewizja i ≤1 Undo. | Q-API, Q-BROWSER |
| T03 · R1 | PR02, PR07 | 409 → refetch → rebase → retry success. | [authoring_sequences](../fixtures/authoring_sequences.json) | Conflict phase cleared, dirty=false, nowy baseline. | Q-API, Q-BROWSER |
| T04 · R1 | PR02, PR07 | Revert po konflikcie. | [authoring_sequences](../fixtures/authoring_sequences.json) | Pola baseline i brak stale conflict banner. | Q-API, Q-BROWSER |
| T05 · R1 | PR02, PR06, PR07 | Zmiana selekcji podczas wysyłania. | [authoring_sequences](../fixtures/authoring_sequences.json) | ACK nie czyści draftu drugiego obiektu. | Q-API, Q-BROWSER |
| T06 · R1 | PR02, PR06, PR07 | Zmiana sesji A→B; ten sam objectId. | [authoring_sequences](../fixtures/authoring_sequences.json) | Brak obcych invalidacji, historii i feedbacku. | Q-API, Q-BROWSER |
| T07 · R1 | PR02 | Draft Box→Cylinder przed Create. | [authoring_sequences](../fixtures/authoring_sequences.json) | Właściwy typ, nowe draftId, jawna decyzja o poprzednich danych. | Q-API, Q-BROWSER |
| T08 · R1 | PR04 | Puste, whitespace, '-', '1e', NaN, infinity. | [authoring_sequences](../fixtures/authoring_sequences.json) | Stany incomplete/invalid, nigdy niejawne zero. | Q-API, Q-BROWSER |
| T09 · R1 | PR04 | nm/µm/mm/m i zapis scientific notation. | [authoring_sequences](../fixtures/authoring_sequences.json) | Jeden wynik SI, brak podwójnej konwersji. | Q-API, Q-BROWSER |
| T10 · R1 | PR04 | Ujemny wymiar, zero radius/height. | [authoring_sequences](../fixtures/authoring_sequences.json) | Inline error i zablokowany commit. | Q-API, Q-BROWSER |
| T11 · R1 | PR04 | Unsupported imported/CSG geometry. | [authoring_sequences](../fixtures/authoring_sequences.json) | Prawdziwy read-only inspector; bez fałszywego edytora Size. | Q-API, Q-BROWSER |
| T12 · R1 | PR04 | Walidacja loading/error/absent/stale. | [authoring_sequences](../fixtures/authoring_sequences.json) | Brak zielonego „no issues” bez dowodu. | Q-API, Q-BROWSER |
| T13 · R2-T | PR13, PR15 | Czterowymiarowy quaternion nienormalny/zerowy. | [transform_oracles](../fixtures/transform_oracles.json) | Jawna walidacja/normalizacja według kontraktu. | Q-API, Q-BROWSER |
| T14 · R2-T | PR13, PR14, PR15 | TRS-01: niezerowy pivot + rotation + nonuniform scale | [transform_oracles](../fixtures/transform_oracles.json) | M/punkty/AABB według fixtures/transform_oracles.json; algebra 1e−20 m, linear 1e−14. Produkcyjny path musi niezależnie spełnić oracle. | Q-API, Q-MANAGED, Q-PHYSICS |
| T15 · R2-T | PR13, PR14, PR15 | Pivot-only change. | [transform_oracles](../fixtures/transform_oracles.json) | World geometry nie zmienia się; deterministyczny round-trip. | Q-API, Q-BROWSER |
| T16 · R1/R2 reject; R3 future | PR13 | Parent transform/hierarchia w R1/R2, fixture shear dla przyszłej implementacji | [transform_oracles](../fixtures/transform_oracles.json) | R1/R2 jawna odmowa capability; nie uruchamiać niewdrożonej hierarchii. Oracle diag(2,1,1)Rz45 column dot = −1.5 ilustruje brak naiwnego TRS. | Q-API, Q-BROWSER |
| T17 · R2-T | PR13, PR15 | Mirror/zero scale. | [transform_oracles](../fixtures/transform_oracles.json) | Fail closed do czasu kwalifikacji kontraktu. | Q-API, Q-BROWSER |
| T18 · R1 | PR01, PR03, PR07 | Podczas committing A użytkownik próbuje rozpocząć gesture B | [authoring_sequences](../fixtures/authoring_sequences.json) | W R1 B jest zablokowany tylko dla tej transakcji; ACK A nie czyści innych rawText/draftów. Historyczny R01 zachowany; overlap mode nie jest w release. | Q-BROWSER, Q-WEBGL |
| T19 · R1 | PR03 | Click osi bez ruchu. | [authoring_sequences](../fixtures/authoring_sequences.json) | Bez zapisującego requestu i wpisu historii. | Q-BROWSER, Q-WEBGL |
| T20 · R1 | PR03, PR07, PR15 | Escape / lost capture / pointercancel / unmount. | [authoring_sequences](../fixtures/authoring_sequences.json) | Dokładnie jedno cleanup; OrbitControls odblokowane. | Q-BROWSER, Q-WEBGL |
| T21 · R1/R2-T | PR03, PR15 | Kamera orthographic/perspective, oś prawie równoległa do ray. | [authoring_sequences](../fixtures/authoring_sequences.json) | Stabilny solver gestu; brak skoku do starego intersection. | Q-BROWSER, Q-WEBGL |
| T22 · R1 | PR03, PR15 | Przeciągnięcie poza obszar osi i viewport. | [authoring_sequences](../fixtures/authoring_sequences.json) | Kontynuacja lub jawne cancel według ustalonego kontraktu. | Q-BROWSER, Q-WEBGL |
| T23 · R2-T | PR15 | Plane handles XY/XZ/YZ, World vs Local. | [transform_oracles](../fixtures/transform_oracles.json) | Zmieniają tylko dozwolone DOF we właściwej ramie. | Q-BROWSER, Q-WEBGL |
| T24 · R2-T | PR15 | Snap + numeric entry. | [transform_oracles](../fixtures/transform_oracles.json) | Ta sama wynikowa wartość i preview; brak dryfu kumulacyjnego. | Q-BROWSER, Q-WEBGL |
| T25 · R1 | PR03, PR07, PR12 | Move draft → Apply → Undo → Redo | [authoring_sequences](../fixtures/authoring_sequences.json) | Pointerup bez wpisu historii; Apply ≤1 wpis; Undo/Redo nowe warunkowe mutacje; unknown nie generuje drugiej historii. | Q-API, Q-BROWSER |
| T26 · R1 | PR03, PR06, PR12 | History capture failure. | [authoring_sequences](../fixtures/authoring_sequences.json) | Zapis zachowany, Undo degraded widoczne, brak fałszywego sukcesu historii. | Q-API, Q-BROWSER |
| T27 · R2-I | PR16, PR17, PR18 | ASCII STL / binary STL. | [import_cases](../fixtures/import_cases.json) | Rozpoznanie, units, preview, asset identity, commit. | Q-API, Q-BROWSER, Q-MANAGED |
| T28 · R2-I | PR16, PR18 | STL truncated, counts mismatch, invalid/nonfinite vertex. | [import_cases](../fixtures/import_cases.json) | Odrzucenie z przyczyną, bez częściowego scene-object. | Q-API, Q-BROWSER, Q-MANAGED |
| T29 · R2-I | PR16, PR17, PR18 | STL open surface/non-manifold/self-intersections. | [import_cases](../fixtures/import_cases.json) | Rzeczywisty raport checks; brak nieuprawnionej zgody na volume. | Q-API, Q-BROWSER, Q-MANAGED |
| T30 · R2-I | PR16, PR17, PR18 | Source units zmienione mm→nm. | [import_cases](../fixtures/import_cases.json) | Bbox po konwersji czytelny; object scale niezależne. | Q-API, Q-BROWSER, Q-MANAGED |
| T31 · R2-I | PR16, PR17, PR18 | Cancel po upload / reconnect. | [import_cases](../fixtures/import_cases.json) | Brak przypadkowego obiektu; reuse identity zgodnie z retencją. | Q-API, Q-BROWSER, Q-MANAGED |
| T32 · R2-I | PR17, PR18 | Reimport ze zmianą triangulacji. | [import_cases](../fixtures/import_cases.json) | Regiony nie przypisują się według starego ordinalu. | Q-API, Q-BROWSER, Q-MANAGED |
| T33 · R1 | PR01, PR08, PR12 | Pierwszy mesh od pustej sceny. | [mesh_generations](../fixtures/mesh_generations.json) | Absent previous artifact nie blokuje first-build. | Q-API, Q-BROWSER |
| T34 · R1 | PR07, PR11, PR12 | Dirty geometry przy Build Mesh. | [authoring_sequences](../fixtures/authoring_sequences.json) | Apply/Discard/Cancel; zakres modelu jednoznaczny. | Q-API, Q-BROWSER |
| T35 · R1 | PR08, PR11, PR20 | Zmiana hmax i Apply bez Build. | [mesh_generations](../fixtures/mesh_generations.json) | Recepta nowa, artefakt stale, bez niejawnego kosztownego jobu. | Q-API, Q-BROWSER |
| T36 · R1 | PR11, PR20 | Apply & Build, szybki double click. | [mesh_generations](../fixtures/mesh_generations.json) | Jeden zapis intencji i jeden build. | Q-API, Q-BROWSER |
| T37 · R1 | PR08, PR09, PR11 | Geometry zmienia się podczas meshowania. | [mesh_generations](../fixtures/mesh_generations.json) | Wynik nie jest oznaczany current bez kompatybilności. | Q-API, Q-BROWSER |
| T38 · R1 | PR11 | Lost ACK + więcej niż osiem późniejszych jobów. | [mesh_generations](../fixtures/mesh_generations.json) | Lookup właściwego client_intent_id lub jawne unknown; zero duplikatów. | Q-API, Q-BROWSER |
| T39 · R1 | PR11, PR12 | Reconnect/reload podczas jobu. | [mesh_generations](../fixtures/mesh_generations.json) | Przywrócenie tej samej obserwacji bez resubmit. | Q-API, Q-BROWSER |
| T40 · R1 | PR08, PR09, PR11 | Failure quality/publication po poprzednim sukcesie. | [mesh_generations](../fixtures/mesh_generations.json) | Retained artifact z prawidłową identity i stale label. | Q-API, Q-BROWSER |
| T41 · R1 | PR08, PR10, PR11 | Backend completed, viewport fetch fails. | [mesh_generations](../fixtures/mesh_generations.json) | Retry Loading bez ponownej budowy. | Q-API, Q-BROWSER |
| T42 · R1 | PR08, PR09, PR10 | sourceSceneRev > currentSceneRev, brak identity i błąd odczytu | [mesh_generations](../fixtures/mesh_generations.json) | Przyszła rewizja inconsistent; brak identity unknown; load error osobno. Nigdy optymistyczny current. | Q-API, Q-BROWSER |
| T43 · R1 | PR08, PR10, PR19, PR20 | Worst element → remesh → klik ponownie. | [mesh_generations](../fixtures/mesh_generations.json) | Stale selection nie trafia w nową generację. | Q-BROWSER, Q-WEBGL |
| T44 · R1 | PR08, PR09, PR10, PR19, PR20 | Quality metric z rewizji różnej od topologii. | [mesh_generations](../fixtures/mesh_generations.json) | Wstrzymanie koloru lub jawny snapshot, zgodna legenda. | Q-BROWSER, Q-WEBGL |
| T45 · R2-Q | PR19 | SLICE-01 tetra plane z=25nm oraz degeneracje | [slice_oracle](../fixtures/slice_oracle.json) | Trójkąt (0,0,25),(75,0,25),(0,75,25)nm; abs point tolerance 1e−20m, area 1e−28m². Następnie rzeczywisty mixed-family mesh, nie rzut. | Q-BROWSER, Q-WEBGL, Q-MANAGED |
| T46 · R1 | PR10, PR19 | Wireframe/opacity/clipping. | [mesh_generations](../fixtures/mesh_generations.json) | Brak nowych komend build i zapisów modelu. | Q-BROWSER, Q-WEBGL |
| T47 · R1 | PR10, PR14 | FDM Build Grid po zmianie spacing. | [mesh_generations](../fixtures/mesh_generations.json) | Grid i membership tej samej generacji/fingerprint. | Q-API, Q-BROWSER |
| T48 · R1 | PR10 | FDM display stride. | [mesh_generations](../fixtures/mesh_generations.json) | Zmiana wyłącznie próbkowania widoku, nie liczby komórek solvera. | Q-BROWSER, Q-WEBGL |
| T49 · R1 | PR01, PR19 | Baseline i powtarzalny stress bez redukcji jakości | [performance_scenarios](../fixtures/performance_scenarios.json) | Pomiary zgodnie z D14 i PERF-01. Do czasu zebranych danych budgets=null, status not_measured; zero udawanych FPS. | Q-BROWSER, Q-WEBGL, Q-PERF |
| T50 · R1 | PR07, PR12, PR15, PR18 | Klawiatura, disabled reason, focus dialogs. | [authoring_sequences](../fixtures/authoring_sequences.json) | Każdy krytyczny workflow bez wyłącznej zależności od myszy/koloru. | Q-API, Q-BROWSER |
| T51 · R1 | PR05 | Niedozwolona geometria + poprawny transform w tym samym payloadzie | [authoring_sequences](../fixtures/authoring_sequences.json) | Żadne pole nie zmienia kanonicznej sceny, rewizji ani historii; jednoznaczne odrzucenie. | Q-API, Q-BROWSER |
| T52 · R1 | PR05 | Dwaj writerzy z jednym base_revision | [authoring_sequences](../fixtures/authoring_sequences.json) | Końcowy CAS: dokładnie jeden commit i conflict drugiego; żadna utracona aktualizacja, także po asynchronicznych etapach walidacji. | Q-API, Q-BROWSER |
| T53 · R1 | PR05, PR06 | Effect/receipt crash + replay tego samego intent | [authoring_sequences](../fixtures/authoring_sequences.json) | Jedna zmiana modelu; lookup potwierdza ten sam wynik; crash window nie pozwala drugiej mutacji. | Q-API, Q-BROWSER |
| T54 · R1 | PR02, PR06, PR07 | Wpis rawText po submit przed ACK | [authoring_sequences](../fixtures/authoring_sequences.json) | Nowa edycja pozostaje w tym samym polu i ma dirty=true; ACK aktualizuje baseline, nie nadpisuje nowszego tekstu. | Q-API, Q-BROWSER |
| T55 · R1 | PR01, PR02, PR07, PR12, PR15, PR18 | Object/Airbox stability przy pending/refetch/ACK | [authoring_sequences](../fixtures/authoring_sequences.json) | Ten sam DOM root, focus i scroll; zero unrelated disabled/opacity zmian i aktywnych opacity animations; request/render counts zapisane. | Q-API, Q-BROWSER |
| T56 · R1 | PR03, PR04, PR15 | Subnanometrowa zmiana i tolerancja no-op | [transform_oracles](../fixtures/transform_oracles.json) | 1 pm przy 100 nm nie jest no-op; epsilon SI zgodnie z D04; próg 3px nie usuwa wpisu liczbowego. | Q-API, Q-BROWSER |
| T57 · R1 | PR06, PR07 | SSR → hydration → journal restore i unmount | [authoring_sequences](../fixtures/authoring_sequences.json) | Pierwszy client snapshot zgodny z SSR; brak cross-session draft; remount viewport nie niszczy journal. | Q-API, Q-BROWSER |
| T58 · R1 | PR11 | Build Selected z drugim obiektem/interfejsem/airbox | [mesh_generations](../fixtures/mesh_generations.json) | Raport actual scope jest zgodny z potwierdzonym full shared-domain planem; selection context nie udaje local artifact. | Q-API, Q-BROWSER, Q-MANAGED |
| T59 · R2-I | PR17, PR18 | Przeniesienie projektu offline na inny host | [import_cases](../fixtures/import_cases.json) | Oryginalny asset SHA256 i source-unit/version zachowane, brak bezwzględnych ścieżek wymaganych do odtworzenia. | Q-API, Q-BROWSER, Q-MANAGED |
| T60 · R1 | PR08, PR09, PR10, PR20 | Crash przed/po activation marker + quality optional | [mesh_generations](../fixtures/mesh_generations.json) | Aktywna generacja jest kompletna; stara pozostaje przed markerem; brak optional quality nie unieważnia poprawnej topologii. | Q-API, Q-BROWSER, Q-MANAGED |
| T61 · R1 | PR05, PR13 | Start run konkuruje z Apply/import/remesh | [authoring_sequences](../fixtures/authoring_sequences.json) | Backend admission serializuje rozstrzygnięcie; aktywny run nie zostaje zmodyfikowany, local draft pozostaje. | Q-API, Q-BROWSER, Q-MANAGED |
| T62 · R2-T | PR13, PR14 | Legacy nonzero pivot → pivot-v1 migration | [transform_oracles](../fixtures/transform_oracles.json) | Zachowanie zadeklarowanej world matrix po jawnej migracji; brak automatycznej interpretacji nieznanej legacy semantyki. | Q-API, Q-BROWSER |
| T63 · R1 | PR05, PR13, PR16, PR17 | API schema/OpenAPI/facade i starszy klient | [authoring_sequences](../fixtures/authoring_sequences.json) | Nowe typy i kontrolki powiązane z capability; transform full DTO nie resetuje q/p/s; unsupported write odrzucony. | Q-API, Q-BROWSER |
| T64 · R2-T | PR13, PR14, PR17 | Macierz FDM CPU/GPU i FEM CPU/GPU | [transform_oracles](../fixtures/transform_oracles.json) | Osobne wyniki points/bounds/occupancy/mesh/physics dla deklarowanych lane i precision; zero silent fallback. | Q-API, Q-MANAGED, Q-PHYSICS |
| T65 · R1 | PR05, PR06 | Unknown ordinary mutation po reload; receipt expired/indeterminate | [authoring_sequences](../fixtures/authoring_sequences.json) | Bez ślepego resubmit; owner-scoped lookup; tombstone i brak bezpiecznego dowodu blokują powtórzenie; historia deduplikowana. | Q-API, Q-BROWSER |
| T66 · R1 | PR11 | Policy saved → build rejected / scene changed | [mesh_generations](../fixtures/mesh_generations.json) | Nie cofa poprawnego zapisu; komunikat częściowego sukcesu, nowa confirmation po zmianie sceny; zero duplicate job. | Q-API, Q-BROWSER |
| T67 · R1 | PR07, PR12 | Geometry→Placement→Mesh Policy / inne object / Start | [authoring_sequences](../fixtures/authoring_sequences.json) | Ten sam draft przy zmianie view tego obiektu; jawny guard przy zmianie scope; Apply-and-continue nie usuwa post-submit edits. | Q-API, Q-BROWSER |
| T68 · R1 | PR08, PR09, PR10 | Rename-only kontra legacy revision-only freshness | [mesh_generations](../fixtures/mesh_generations.json) | Digest path pozostaje current dla nieistotnej zmiany nazwy; legacy path konserwatywnie stale; jeden resolver we wszystkich panelach/Run. | Q-API, Q-BROWSER |
| T69 · R2-Q | PR09, PR19, PR20 | Metric/family/orientation/invalid elements i refinement | [mesh_generations](../fixtures/mesh_generations.json) | Zgodna generation+metric/version+domain; orientation oddzielna, invalid flags blokują gdy mandatory; refinement tworzy receptę, nie topologię w UI. | Q-API, Q-BROWSER, Q-MANAGED |
| T70 · R1 | PR12 | Bramki release/host storage/test restrictions | [authoring_sequences](../fixtures/authoring_sequences.json) | Żadna blocked gate nie ma PASS; dowody SHA/środowisko; respect unit-compilation ban i managed-runtime ownership. | Q-POLICY |
| T71 · R2-T | PR14 | Transform frames a pole world / lokalna anizotropia / reinit | [transform_oracles](../fixtures/transform_oracles.json) | Wynik zgodny z zatwierdzoną notą naukową; nie projektować poprzedniej magnetyzacji bez zakwalifikowanego transferu. | Q-API, Q-MANAGED, Q-PHYSICS |
| T72 · R2-I | PR16, PR17, PR18 | Limity stage, worker quotas, lease, referenced asset cleanup | [import_cases](../fixtures/import_cases.json) | Bytes/count checked przed alokacją; cancellation idempotent; expiring stage nie usuwa source referencjonowanego przez projekt. | Q-API, Q-BROWSER, Q-MANAGED |

Parser/no-op: [NUM-01](../fixtures/numeric_oracles.json). Pełna tabela faz: [state_contracts.json](../state_contracts.json). Powiązanie przeglądu: [review_traceability.json](../review_traceability.json).

## 4. Konkretne tolerancje T14, T16, T45

T14: expected matrix/points/AABB w TRS-01. Binary64 algebra tego fixture porównuje współczynniki liniowe z absolute tolerance 1e−14 i punkty w SI z 1e−20m. To zapas błędu zaokrągleń przy tej skali, nie uniwersalna tolerancja CAD ani próg LLG. Dla GPU single precision osobny oracle/profil określa tolerancję od uwarunkowania i reprezentacji; nie kopiować f64 progu. T16: w R1/R2 hierarchia ma zostać odrzucona; dot kolumn −1.5 to fixture przyszłego shear kontraktu, nie żądanie wdrożenia hierarchy. T45: dokładny tetra+plane daje trójkąt z SLICE-01; punkty do1e−20m, pole do1e−28m² w niezależnej algebrze binary64. Test realnej implementacji musi sprawdzić też orientację polygonu względem n, degeneracje (face/edge/vertex), pusty przekrój i wszystkie zadeklarowane rodziny elementów.

Dla liczności HTTP obowiązują funkcjonalne invariants: pointermove/up=0 scene writes w R1; jeden admitted Apply=1 effect; no-op=0 effect; Retry Loading=0 build; ordinary lost ACK=lookup/replay same ID tylko zgodnie z kontraktem. Liczba GET/renderów ma granice dopiero po PR01; należy zapisać measured counts, a nie uznać każde refetch za bug.

## 5. Oracle nie jest testem poprawionej produkcji

`verification/check_spec_oracles.py` sprawdza wyłącznie liczby i kontrakty tego pakietu. `verification/package_checks.json` opisuje integralność pakietu. Nie wolno tymi wynikami zamknąć żadnego Txx wymagającego produkcyjnego modułu, realnego API, WebGL, meshera lub fizyki. Stare reprodukcje Rxx pozostają byte-for-byte; nowe dowody napraw muszą mieć inne ścieżki oraz rzeczywisty SHA implementacji.

## 6. Manifest dowodu implementacji

Każdy test: task/PR, pełny SHA i dirty state, fixture hash, test-driver hash, nazwa recepty, node/browser/OS/GPU/driver/mesher/precision, requested/resolved execution, app/scene/session/generation identities, expected/actual, tolerance i uzasadnienie, log oraz capture gdzie dotyczy. Dane osobowe i sekrety sanitizowane; hash zanonimizowanych logs odnotowany. `pass` wyłącznie z dostępnym wynikiem; `blocked`, `not_run`, `failed`, `not_applicable` są oddzielne. Ostateczna kwalifikacja feature jest przecięciem kontraktów i wymaganych testów, nie liczbą zielonych unit helperów.
