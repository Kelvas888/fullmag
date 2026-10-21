# Aktualny status refaktoryzacji — implementacja i odbiór

Data: **20.10.2026**. Baza implementacji:
`master@42d92610312871d591db16a5b60a8f7a6d6339b5`.
Podstawa: [reaudyt 08](08-reaudyt-master-2026-10-20.md), odczyt źródeł
i zachowane checkpointy. Pełny plan: **IN PROGRESS**.

## Jak czytać tabelę

- **Zaimplementowane źródłowo**: istnieje kod i zidentyfikowany konsument;
  nie oznacza świeżego PASS runtime.
- **Częściowe**: istnieje konkretny fragment, ale nie całe wymaganie etapu.
- **HISTORYCZNY PASS/FAIL**: checkpoint zapisuje wykonanie na określonych
  wcześniejszych źródłach. Nie sprawdzano ponownie surowych receiptów ani
  aktualnego GitHub CI podczas reaudytu.
- **NOT VERIFIED**: nie ma w tym rebaseline wystarczającego dowodu dla
  wymagania na bieżącej bazie. Nie jest synonimem FAIL ani NOT IMPLEMENTED.
- **NOT RUN**: danej kontroli nie uruchomiono w tej aktualizacji.

Poprzednie procenty **85/98/59/94/90/50/1/99/52/0/2** oraz globalne **49%**
pozostają wyłącznie w [archiwum](06-status-historyczny-do-2026-10-15.md)
i ich cytatach w reaudytach.
Nie mają aktualnego mianownika. Nie liczymy procentu kwalifikacji z liczby
plików, testów jednostkowych ani obecności typów.

## 1. Tabela etapów

| Etap | Co jest zaimplementowane — potwierdzone źródłowo | Co faktycznie przetestowano według zapisanych checkpointów | Czego dowód nie obejmuje / następny odbiór |
|---|---|---|---|
| **P0 — dane i baseline** | GC preview i ponowna walidacja planu pod lease, reachability, primary/aux chunks, state przed markerem, walidacja ścieżek, natywny writer lock; świeże inventory 371 operacji | **H01:** 70 testów storage/session PASS na historycznej bazie; syntetyczny roundtrip primary/aux i minimalna macierz awarii. **C01:** bieżący odczyt inventory PASS | Aktualny baseline wydajności; pełna macierz durability/recovery i właściwych filesystemów, power-loss. Nowy code review nie rekwalifikuje dawnych testów |
| **P1 — dokument projektu** | `ProjectApplication`, create/open/save/Save As/close i transport dokumentu bez RuntimeSession; UI dokumentu; osobny panel preparation zamiast starego global gate | **H02:** wcześniejsze CLI/Python/API i browser project lifecycle. **H03:** browser fixture nieblokującego workspace. **H04:** nowszy rzeczywisty lifecycle miał częściowy sukces i FAIL verifiera | Pełne CAE-01–04, recovery i fizyczny desktop. Nie utożsamiać zapisu archiwum z pełnym edytorem projektu |
| **P2 — authoring** | Parametry AST/SI, typed Model/Component/PhysicsConfiguration i projekcje, semantic Undo/Redo, pending forms i revision fences; główny flow sceny związany z sesją | **H05:** wspólny fixture canonical digest 12/12 Python i 104/104 Rust; zapisane testy historii i paneli | Pełny UI→Python→IR→UI, wszystkie mutacje/gesty i szkice, selection/transform oraz niezależność definicji od runu. Kompletne browser acceptance NOT VERIFIED |
| **P3 — studies i Submit** | Study/catalog lowering, immutable RunSpec, durable Submit, task/attempt identities, coordinator i accepted workers | **H06:** historyczne process E2E FDM CPU oraz FDM GPU z powiązaniem UUID i lease; odrębne checkpointy retry/cancel/recovery | Aktualne process proof wymaganych realizacji i całego publicznego przepływu; cross-host i pozostałe wymagania według planu |
| **P3a — scope API** | Middleware i immutable context, scope klienta, resource/cache/decode identity; `current` pozostaje kompatybilnym adresem | **H07:** ukierunkowane źródłowe/regresyjne i historyczne scope checks. **C01:** obecne operacje/handlery odnalezione | Nowa macierz 371 operacji wymaga review. Dawne 276 SOURCE PASS/15 OPEN/13 GLOBAL nie są aktualnym odbiorem. Pełny A→B, stale write/decode/reconnect NOT VERIFIED |
| **P4 — preparation** | PreparationPlan/Receipt/certyfikaty, accepted-run binding, preparer/supervisor FEM, polecenia Grid/Mesh i last-good identity | **H08:** historyczny router preparation 5/5 oraz browser Build Grid/Operations. **H04:** późniejsza macierz meshing zakończyła się 1 error/1 skip | Native mesh/space, automatyczny pipeline, golden parity, last-good i nauka. Historyczna odmowa tet4 nie jest automatycznie bieżącym FAIL |
| **B — backend** | Dziewięć modułów FDM fields oraz wydzielone elementy FEM; aktualny CPU dispatch to nadal `CpuReference` | **H09:** porównania ciał/sygnatur i source review ekstrakcji; część dawnych buildów obejmowała wyłącznie wcześniejsze slice’y | Nie utożsamiać ekstrakcji z kwalifikacją. ABI/lifecycle, B-CORE/FDM/FEM/DEMAG/WORKFLOW/STATE/ABI/OBS i wymagane lane’y rozliczać oddzielnie |
| **P5 — izolacja wykonania** | Coordinator, durable ownership/recovery, accepted-state adapters FDM i FEM CPU/GPU; legacy scratch nadal reaguje na zmianę sceny | **H06/H10:** historyczne accepted FDM process proof i ograniczone snapshot/checkpoint/observation checks | Pełny steering, ExactResume, rejected-step state i edycja podczas solve per adapter/lane; pełny cutover legacy NOT VERIFIED |
| **P6 — wyniki** | Trwałe SolutionSet catalogs, project/run scoped materialized dataset i binary slices, pinned UI/Inspector | **H11:** historyczny browser fixture saved/current viewport, WebGL i brak mutacji runtime | Ogólny derived compute/projectory, plot/export, wszyscy writers, duże dane i rzeczywisty archive/native roundtrip; brak pełnej kwalifikacji |
| **P7 — kampanie i projekty** | Independent batch expansion, durable parent intent, Submit/list/commands/cases i materializacja dzieci | W tym rebaseline **brak przypisanego wykonanego odbioru batch E2E**. Testy istniejące w repo nie są wynikiem uruchomienia | Continuation/graph nie są realizowane przez independent expander. Multi-project, targety i reports wymagają osobnego rozliczenia, nie deklaracji ich ukończenia |
| **P8 — cutover i wydanie** | Ścieżka Docker DEV, historyczne packaging/versioning i zmiany cutover; udokumentowany cel samodzielnego Windows | **H04:** historyczny natywny build exit 0, UI CI 8537 PASS/13 skip oraz build Next. **C02:** bieżące kontrole dokumentacji | Docker build/runtime aktualnego HEAD, pełna macierz CAE, cztery wymagane lane’y, clean install/upgrade/rollback i Windows bez Docker/WSL pozostają NOT VERIFIED w tym rebaseline |

## 2. Rejestr dowodów przywołanych w tabeli

Poniższe historyczne wykonania są zapisane w dokumentach. Ich scope i tożsamość
pozostają przy oryginalnym receipcie; nie oznaczamy całego bieżącego etapu PASS.

| ID | Źródło | Zakres wyniku / ograniczenie |
|---|---|---|
| **C01** | [Reaudyt 08](08-reaudyt-master-2026-10-20.md), [inventory aktualne](p0/07-current-api-inventory.md) | `audit_refactor_p0.py --check` exit 0 na audytowanym HEAD: 371 operacji i handlerów, 0 unresolved, 2 router-only; osobno 307 paths. Heurystyczne źródła, bez runtime |
| **C02** | [Reaudyt 08](08-reaudyt-master-2026-10-20.md) | 476 lokalnych odnośników w ośmiu dawnych głównych dokumentach bez brakującej ścieżki; to wynik przed niniejszą reorganizacją. Końcowy wynik aktualizacji: [09](09-weryfikacja-aktualizacji.md) |
| **H01** | [P0 minimal gate](p0/05-minimal-gate.md), [P0 completion audit](p0/06-completion-audit.md), [P0 README](p0/README.md) | Historyczny run `4315e35f99d74ffdb77159aaee82a9f5`, 70 PASS; brak power-loss i ogólnego ExactResume |
| **H02** | [P1](p1/README.md), [dawny status](06-status-historyczny-do-2026-10-15.md) | Ograniczone historyczne use cases, API/WS i browser. Nie zalicza automatycznie pełnej edycji projektu ani Tauri |
| **H03** | [P8-53CY](p8/53cy-nonblocking-preparation-workspace.md) | 15.10: fixture, retained draft/focus/canvas i WebGL; nie dowód obecnego całego launchera |
| **H04** | [P8-53DA](p8/53da-native-capture-and-runtime-free-browser.md) | 15.10: Windows build manifest `340c667b3756a46f089338ac9216897598631d674eaef6b72472ea2072678a32`; UI CI dla `c689caee2188a86e645e26aa03270e9212c1f7ca` 8537 PASS/13 skip; browser nie odebrany w całości; Python meshing 1 error/1 skip |
| **H05** | [P2](p2/README.md), [historia semantyczna](p2/05-semantic-history.md), [dawny status](06-status-historyczny-do-2026-10-15.md) | Digest fixture i ukierunkowane suites; nie pełny canonical/browser roundtrip |
| **H06** | [P3 GPU runtime](p3/58-accepted-fdm-gpu-runtime.md), [CLI cutover](p3/59-cli-run-json-cutover.md), [dawny status](06-status-historyczny-do-2026-10-15.md) | Pinned accepted FDM execution; nie parytet wszystkich solverów ani pełne FEM |
| **H07** | [P3a coverage](p3a/05-endpoint-coverage.md), [dawny plan domknięcia](07-domkniecie-historyczne-2026-10-02.md) | Ukierunkowane kontrole; ośmiometodowy workspace harness miał 11/11 regresji skryptu, a jego HTTP/runtime pozostawał osobną bramką |
| **H08** | [P4](p4/README.md), [Build Grid](p4/17-explicit-fdm-build-grid.md), [Operations](p4/18-operations-problems-projection.md) | Ograniczony API/browser evidence, bez pełnej fizycznej preparacji FEM |
| **H09** | [Demag owner](b/02-fdm-cpu-demag-owner.md), [Zeeman owner](b/08-fdm-cpu-zeeman-owner.md), [dawny README](README-historyczny-2026-10-20.md) | Source equivalence; późniejsze ekstrakcje nie dziedziczą wcześniejszego buildu |
| **H10** | [FDM CPU accepted state](p5/03-fdm-cpu-accepted-state-snapshot.md), [FDM GPU](p5/06-fdm-gpu-accepted-state.md), [checkpoint compatibility](p5/07-checkpoint-compatibility.md) | Ograniczone adaptery i kontrakty; scope dowodów odczytywać per checkpoint |
| **H11** | [Saved viewport](p6/65-saved-field-single-viewport.md), [powrót do current](p6/65a-direct-current-viewport.md) | Fixture/browser PASS z 02.10; nie ogólny native/archive lub scientific proof |

Między historycznym CI H04 a audytowanym HEAD zmieniło się m.in. 469 plików
Control Room. Nie odrzucamy automatycznie wszystkich wcześniejszych testów:
ich aktualność wymaga sprawdzenia właściwych źródeł, wejść i środowiska.
Nie potwierdzono tutaj aktualnego statusu CI na GitHub.

## 3. Warunki dalszego raportowania

Każdy przyrost otrzymuje identyfikator z planu 03, owner/symbol i konsumentów,
pełny source SHA lub manifest źródeł, stan implementacji oraz osobne wyniki:
source checks, managed runtime, browser, science/release. Do testu dopisujemy
receptę, target/lane, receipt, terminalny exit code i zakres.

Etap może mieć dużo zaimplementowanego kodu i nadal nieodebrane zachowanie.
Nie przyznajemy 100% za sam typ, endpoint, compilation PASS ani fixture.
Brakujący wymagany lane nie jest przenoszony poza zakres, żeby zamknąć etap.

Aktualizując tę stronę, najpierw rozliczamy zmienione kryteria i ich dowody.
Nowy szacunek procentowy wymaga uprzednio jawnego zbioru podzadań i wag;
do tego czasu obowiązuje tabela zakresów powyżej.
