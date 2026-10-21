# Reaudyt dokumentacji refaktoryzacji względem mastera — 20.10.2026

## 1. Werdykt

**Kierunek architektury pozostaje zasadny. Dokumentacja wykonawcza i jej procenty nie są aktualnym obrazem mastera.** Nie należy zaczynać refaktoryzacji od początku ani dosłownie wykonywać wszystkich dawnych zadań: część zabezpieczeń i funkcji już istnieje. Potrzebne jest ponowne powiązanie wymagań z kodem, konsumentami i dowodami odbioru.

Najważniejsze rozbieżności:

1. Plan nadal nakazuje development przez dawny build runner, mimo późniejszej decyzji o Docker Compose.
2. Historyczny audyt opisuje luki storage, których konkretne przyczyny zostały już usunięte w źródłach.
3. Liczniki API i macierz P3a opierają się na starszym zakresie.
4. Dokument domknięcia nadal opisuje pełnoekranowy modal i `inert`; zatwierdzony kod ma oddzielny panel przygotowania.
5. Tabela nie uwzględnia istniejącego odczytu datasetów, independent batches i części adapterów accepted state FEM.
6. Wysokie szacunki P1/P3/P5 nie oznaczają zamknięcia odpowiednich scenariuszy produktu.

To audyt dokumentacji i źródeł. **Nie wykonano nowego buildu, testów jednostkowych, browser smoke, solve ani kwalifikacji naukowej/release.** Nie potwierdzono działania aktualnego pakietu tylko na podstawie obecności kodu.

## 2. Tożsamość i zakres

| Pozycja | Ustalenie |
|---|---|
| Checkout | `C:\git\fullmag\fullmag` |
| Branch / HEAD | `master`, `42d92610312871d591db16a5b60a8f7a6d6339b5` |
| Lokalny ref `origin/master` | Ten sam SHA; nie wykonywano fetch. Nie jest to świeże sprawdzenie serwera GitHub. |
| Baza audytu z 20.09 | `14c8e73a6f3c55f4fc080835a6156f2a4db8f111`, potwierdzony przodek HEAD |
| Odległość Git | 3195 commitów w `baza..HEAD`; liczba commitów nie mierzy ukończenia planu |
| Główne dokumenty | `README.md`, `01`–`07` w tym katalogu |
| Dodatkowe źródła | Wybrane checkpointy P0/P3a/P8, ADR 0039/0061/0064, backend masterplan, bieżące kontrakty i odpowiadające im ścieżki implementacji |
| Granica przeglądu | Przekrojowa rewalidacja etapów i najważniejszych twierdzeń; nie pełny przegląd każdej linii solverów ani wszystkich 395 plików Markdown pod `final/` |

Na wejściu było sześć zmodyfikowanych plików śledzonych i jeden nieśledzony:

```text
apps/control-room/scripts/smoke-preparation-window.mjs
apps/control-room/src/design/styles/dialog-simulation-startup.css
apps/control-room/src/kernel/layout/SimulationStartupOverlay.tsx
apps/control-room/src/shared/ui/DraggablePanel.tsx
docs/audits/2026-10-20-simulation-preparation-ui.md
scripts/docker_volume_dev.py
scripts/docker_volume_capture_failure_reconcile.py  [untracked]
```

Nie przypisano tych zmian do odebranego mastera. Dla panelu przygotowania i jego zależności odczytano wersję `git show HEAD:<path>`. Audyt nie zmieniał tych plików, indeksu, HEAD, procesów aplikacji ani kontenerów. W czasie przechwytywania źródeł przez równoległe zadanie zachowano okno bez zapisów w checkoutcie.

## 3. Co pozostaje aktualne

- Rozdzielenie edytowanej definicji, przypiętego wykonania, trwałych wyników i stanu widoku.
- Jeden Python DSL, ProblemIR oraz wspólna semantyka, z osobnymi realizacjami FDM CPU/GPU i FEM CPU/GPU.
- Immutable RunSpec, identyfikatory projektu/runu, fencing i jawne requested/resolved execution.
- Jeden klient/resource layer oraz jeden workspace; ciężkie dane poza cienkim JSON control plane.
- Osobne dowody źródeł, runtime, browser/WebGL, nauki i wydania.
- Zachowanie danych, jawne unsupported i brak cichego fallbacku wymuszonego GPU.
- Kryteria CAE z dokumentu 04 jako wymagania odbioru. Ich obecność nie jest wynikiem testu.
- Niezależny produkt Windows z P8-C. Docker używany w development nie stanowi realizacji ani odwołania tego wymagania.

Plan 03 pozostaje użytecznym katalogiem rezultatów. Zależności etapów należy traktować jako bramki odbioru, nie dowód, że implementacja przebiegała liniowo: na masterze są już slice’y późniejszych etapów przy nadal otwartych wcześniejszych bramkach.

## 4. Ustalenia reaudytu

### D01 — wysoka: nieaktualna instrukcja wykonywania buildów

`03-plan-refaktoryzacji.md:49` kieruje pełne buildy do kolejki Fullmag_build_runner. README eksponuje również historyczny przyrostowy backend Windows (`README.md:3–15`). Obowiązujący AGENTS oraz ADR 0061/0064 rozdzielają obecnie codzienny Docker DEV od osobnych bramek release/CI/naukowych.

Potwierdzenie źródłowe: `justfile:27–37` udostępnia `docker-dev-toolchain` i `docker-dev`; `scripts/docker_dev.py:2436`, funkcja `up`, deleguje do `docker_dev_up.ensure_up`; `scripts/docker_dev_up.py:1231–1236` kieruje świeży start do `docker_volume_dev.start`. Istnieją też zarządzane ścieżki resume/recovery. To potwierdza implementację wejścia, nie pełną poprawność mountów, cache i runtime.

**Korekta:** zastąpić normatywny akapit o codziennym buildzie aktualnym kontraktem Compose. Zachować stare natywne/runnerowe receipty jako historię. Nie usuwać z planu niezależnej dystrybucji Windows i nie przedstawiać Docker DEV jako jej kwalifikacji.

### D02 — wysoka: F01–F06 są historyczną diagnozą, a nie bieżącą listą brakującego kodu

Audyt 01 sam zaznacza historyczność ustaleń, lecz czytelnik trafia następnie na tabelę krytycznych braków bez zwięzłej, aktualnej mapy ich zamknięcia.

| Dawne ustalenie | Potwierdzony stan źródłowy na HEAD | Pozostała granica |
|---|---|---|
| F01: niepełny graf i niejawny destrukcyjny GC | `store.rs::collect_live_refs:6853` używa wspólnego traversal i odrzuca niekompletny graf; `gc:6868` jest preview; `gc_apply:6893` sprawdza zakres i ponownie porównuje plan pod lease | Nie wykonywano GC ani nowej macierzy awarii |
| F02: capture bez materialnych referencji primary/aux | `capture.rs:105,130` zapisuje `TensorChunk` z object ref, długością i hashem dla obu grup pól | Nie dowodzi ExactResume wszystkich solverów |
| F03: ID manifestu może przejść do ścieżki bez walidacji | `fms.rs::preflight_fms:2098` przechodzi przez traversal dokumentów (`:2178`); `reachability.rs::validate_session:4899–4915` waliduje ID; `repository_path.rs::checked_path:101` stanowi granicę ścieżek | Nie deklarujemy odporności na każdy model ataku ani nowego testu importu |
| F04: manifest checkpointu przed stanem | `store.rs::commit_checkpoint:6413–6447`: walidacja tożsamości, stan, pełny graf, następnie marker checkpointu | Odbiór crash/power-loss pozostaje osobny |
| F05: wspólny `.part` i brak bariery zapisu | `durability.rs::atomic_write_impl:220–237`: UUID, `create_new`, `sync_all`, publikacja; osobna kontrola niepewnego wyniku | Sam fsync nie jest dowodem power-loss qualification |
| F06: lock oparty wyłącznie na PID | `writer.rs::WriteTransaction`, `:147–258`: natywny lock pliku, owner metadata i kontrola współdzielenia | Profile platform i fault/recovery wymagają właściwych dowodów |

Ścieżki w tabeli należą do `crates/fullmag-session/src/`. Ograniczone historyczne wyniki P0 pozostają w `p0/06-completion-audit.md`; nie powtarzano ich jako nowych wyników.

**Korekta:** zachować tabelę F01–F12 jako datowaną historię, dodać obok aktualny stan: przyczyna usunięta źródłowo / częściowo / otwarta bramka odbioru. Nie planować ponownie wykonanych napraw.

### D03 — wysoka: inventory i procent P3a mają nieaktualny mianownik

| Miara | Historyczny dokument | Odczyt 20.10.2026 |
|---|---:|---:|
| Unikalne ścieżki OpenAPI | 246 w audycie 01 | 307 |
| Ścieżki zawierające `sessions/current` | 239 w audycie 01 | 253 |
| Operacje path + method | 304 w zapisanym inventory P0 z 23.09 | 371 |
| Operacje zawierające `sessions/current` | Nie porównywano z dawną liczbą ścieżek | 308 |
| Handlery znalezione przez P0 checker | 304 w zapisanym inventory | 371 |
| Nierozpoznane handlery / konsumenci | 0 / 0 | 0 / 0 w heurystyce checkera |
| Router-only / OpenAPI-only | 2 / 0 | 2 / 0 |

`python -X utf8 -B scripts/audit_refactor_p0.py --check` zakończył się kodem 0, bez zapisu inventory. Wynik jest źródłowy i heurystyczny; nie dowodzi poprawności wszystkich konsumentów, identity fencing ani zgodności rzeczywiście uruchomionego API.

Dodatkowo `scripts/audit_refactor_p3a.py` czyta **zapisane** `p0/inventory.json` (`:12,238`), a `load_status_overrides:66` zachowuje wpisy review z wcześniejszego Markdown. Samo ponowne wygenerowanie tej tabeli nie jest świeżym review 371 operacji. Nie uruchamiano go z `--write`.

**Korekta:** odświeżyć inventory, porównać dodane/usunięte/zmienione operacje i przypisać ponownie ownera, klienta oraz dowód scope. Nie przenosić automatycznie `276 SOURCE PASS / 15 OPEN / 13 GLOBAL` ani 90% na nowy zakres.

### D04 — średnia: domknięcie P1 opisuje usunięty globalny modal

`07-domkniecie-etapow.md:9,56–58` nadal opisuje pełnoekranowy modal i `inert`. Na zatwierdzonym HEAD:

- `SimulationStartupOverlay.tsx::SimulationStartupOverlayView:118–130` montuje lokalne okno;
- `SimulationPreparationWindow:134–204` ma tryby open/minimized/closed, korzeń `aside` i `DraggablePanel` z `role="region"`;
- `WorkspaceShellClient.tsx::ActiveWorkspaceShell:219–238` renderuje layout i status osobno;
- w `WorkspaceDockLayout.tsx` nie znaleziono `inert` ani `WorkspaceStartupInteractionContext`.

Pliki UI są pod `apps/control-room/src/kernel/layout/`. Odczytano HEAD, ponieważ overlay i jego zależności mają obce lokalne zmiany. Nowszy checkpoint `p8/53cy-nonblocking-preparation-workspace.md` już opisuje usunięcie gate.

**Korekta:** oznaczyć opis 07 jako historyczny i podać aktualną granicę odbioru. Nie wnioskować z kodu o braku wszystkich bieżących błędów startupu lub o świeżym PASS przeglądarki.

### D05 — wysoka: lifecycle dokumentu i pełny authoring projektu to różne rezultaty

`crates/fullmag-application/src/application.rs::ProjectApplication:158` oraz `fullmag-api/src/router_v2/handlers/persistence/projects.rs:2319–2366` mają create/open i use cases dokumentu bez RuntimeSession. Test `fullmag-application/tests/project_lifecycle.rs:130` opisuje roundtrip bez runtime; nie uruchamiano go w tym audycie.

Jednak główny przepływ `apps/control-room/src/kernel/layout/NewProblemDialog.tsx:185–209` najpierw tworzy sesję, następnie projekt i wiąże jego authoring z tą sesją. `ProjectDocumentController.ts::save:441–458` przy aktywnym bindingu odczytuje scenę z sesji. ADR 0039 przewiduje dla projektu bez sesji Saved Results, readonly Inspector i placeholder viewportu.

**Wniosek:** istnieją runtime-free operacje dokumentu oraz odrębny flow edycji sceny związany z sesją. Nie wolno na tej podstawie deklarować całego niezależnego edytora projektu. Jednocześnie **utworzenie RuntimeSession nie jest dowodem uruchomienia solvera**; dokument 04 rozróżnia „bez solve” od innych operacji. To rozróżnienie musi pozostać w kryteriach, zamiast po cichu zaostrzać lub rozluźniać zakres P1/P2.

**Korekta:** osobno odbierać archiwum New/Open/Save, authoring pustej symulacji bez solve oraz docelową niezależność edytowanej definicji od wykonania. Pozostawić CAE-01/02/03 jako pełne scenariusze produktu.

### D06 — średnia: P6 nie jest już pozbawione publicznego odczytu datasetów

Wiersz P6 (`06-status-realizacji.md:1607`) mówi zbyt szeroko o braku publicznego dataset API. `crates/fullmag-api/src/router_v2/handlers/persistence/solutions.rs` ma `get_materialized_dataset:279` oraz `get_materialized_dataset_slice:320`, adresowane przez projekt/run/SolutionSet/revision/member/artifact. Konsumenci istnieją w `ControlRoomApi.ts:3241`, `solutionSetResources.ts:370` i `SavedResultsBrowser.tsx:43–184`.

**Korekta:** oznaczyć ten konkretny read path jako zaimplementowany źródłowo. Odrębnie rozliczać ogólną materializację i derived compute, projectory, plot/export recipes, skalę danych i runtime. Publiczny odczyt istniejącego artefaktu nie zamyka całego P6.

### D07 — średnia: P7 nie jest już wyłącznie planem

Potwierdzone źródła:

- `crates/fullmag-application/src/batch_expansion.rs::expand_independent_batch:568` — deterministyczne rozwijanie przypadków;
- `crates/fullmag-api/src/router_v2/handlers/persistence/projects.rs::submit_batch:542`, `list_batches:663`, `command_batch:858`, `list_batch_cases:1145`;
- `crates/fullmag-session/src/store.rs::commit_batch_intent:445–519` — trwały parent intent;
- `crates/fullmag-api/src/run_intent_persistence.rs:549,754` — przyjęcie batch i materializacja dzieci.

Expander jawnie odrzuca inne strategie niż `Independent` (`batch_expansion.rs:574–577`). Istnienie wartości enum `Continuation` i `DependencyGraph` nie dowodzi realizacji tych strategii. Nie oceniano tu pełnego multi-project, targetów ani raportów.

**Korekta:** zastąpić opis „0%, tylko zaplanowane” informacją o częściowej implementacji independent batches i osobnych pozostałych wymaganiach. Nie wyliczać nowego procentu z liczby endpointów.

### D08 — średnia: wpis B pomija kolejne ekstrakcje

`06-status-realizacji.md:1605` opisuje pierwsze wydzielenie energy/observables i 1%, a `:1614` oznacza ten sam strumień jako nieoszacowany.

`crates/fullmag-engine/src/fdm/cpu/fields.rs:19–40` podłącza już dziewięć modułów: direct_torques, exchange, anisotropy, dmi, magnetoelastic, zeeman, demag, energy, observables. FEM ma m.in. `backends/fem/core/fem_context_builder.cpp` i fasadę `backends/fem/src/context.cpp`.

**Korekta:** raportować ownerów i pozostałe granice B-CORE/B-FDM/B-FEM/B-DEMAG/B-WORKFLOW/B-STATE/B-ABI/B-OBS. Nie traktować liczby plików jako procentu architektury. FDM CPU nadal ma aktualną ścieżkę `FdmEngine::CpuReference`; nazwa katalogu native nie promuje nowego CPU backendu. Parity i fizyka pozostają osobne.

### D09 — wysoka: 99% P5 maskuje szeroki zakres pozostałej kwalifikacji

Źródła zawierają coordinator, fencing i adaptery accepted state. W szczególności `crates/fullmag-api/src/accepted_fem_state.rs::to_accepted_state_ref:209` oraz `accepted_fem_gpu_state.rs::to_accepted_state_ref:272` materializują referencje FEM; `accepted_fem_study_worker.rs::accepted_state_ref_from_attempt_snapshot:276` ma ścieżkę ich recovery. Nie należy więc opisywać całego accepted state FEM jako brakującego kodu.

Jednocześnie pozostała ścieżka legacy nie zniknęła: `crates/fullmag-cli/src/scratch_runtime.rs::run:664–677` nadal reaguje zakończeniem child na zmianę session/backend/scene revision. To nie dowodzi, że każdy accepted run zależy od mutable sceny; pokazuje, że nie można ogłosić globalnego cutoveru bez inwentarza konsumentów.

**Korekta:** osobne stany dla kodu adapterów, accepted-run process proof, checkpoint/ExactResume, steering, izolacji edycji i wycofania legacy. Zachować wymagane lane’y. Stare 99% nie jest oceną kosztu ani ryzyka reszty.

### D10 — wysoka: historyczny PASS nie kwalifikuje automatycznie obecnego HEAD

Status 06 nadal rozpoczyna się informacją o browser lifecycle „wynik jeszcze nieznany”. Bardziej szczegółowy P8-53DA zapisuje już pierwszą porażkę oraz ograniczone sukcesy New/Save/Open/Save/Close; nie jest to kompletna aktualizacja zbiorczego statusu.

Wpis o CI `c689caee2188a86e645e26aa03270e9212c1f7ca` dokumentuje 8537 PASS / 13 skip, ale między tym SHA a audytowanym HEAD zmieniło się 469 plików Control Room, 43 Python DSL, 18 fullmag-session i 23 workflow. Liczby oznaczają diff ścieżek, nie liczbę regresji.

Nie sprawdzano świeżo GitHub CI ani historycznych receiptów na dysku. **Nie stwierdzamy, że obecny master nie przechodzi testów; stwierdzamy, że wskazany stary run nie jest samodzielnym dowodem całego obecnego HEAD.** Nadal aktualne, niezmienione dowody można zachować po sprawdzeniu ich wejść i zakresu.

**Korekta:** każdy dowód musi mieć zakres, source SHA/hash, środowisko, końcowy wynik i pozostałą granicę. Wynik nieznany wymaga rozliczenia jako nieznany albo powiązania z terminalnym receiptem; nie dopisania PASS.

## 5. Zestawienie etapów po reaudytowaniu źródeł

Kolumna procentów cytuje historyczną tabelę. **Nie jest aktualizacją pomiaru i nie służy do wyliczenia procentu całości.** Ocena źródeł nie zamyka wymaganych testów.

| Etap | Dawny szacunek | Stan potwierdzony w tym audycie | Co trzeba rozliczyć do odbioru |
|---|---:|---|---|
| P0 | 85% | Główne zabezpieczenia storage obecne; świeże inventory 371 operacji | Aktualny baseline, profile durability/fault/recovery, kompletna mapa dowodów |
| P1 | 98% | Use cases i API dokumentu bez RuntimeSession; nowszy nieblokujący panel | Pełne CAE-01–04, recovery i wymagany desktop; nie mylić dokumentu z pełnym edytorem |
| P2 | 59% | Parametry/typed model, historia semantyczna i session-bound authoring | Kompletny roundtrip, wszystkie powierzchnie edycji i niezależność definicji |
| P3 | 94% | Typed study/catalog/RunSpec, durable Submit i koordynacja | Aktualne dowody execution, retry/recovery i wymaganych realizacji |
| P3a | 90% | Middleware scope oraz scoped cache istnieją; stary inventory nie obejmuje obecnego zakresu | Review 371 operacji, aktualne polityki aliasów, stale-scope A→B i decode/reconnect |
| P4 | 50% | PreparationReceipt/certyfikaty i osobna preparacja FEM | Pełny producer pipeline, zgodność źródeł/mesh/space, last-good, Live/browser i nauka |
| B | 1% / nieoszacowany | Kolejne moduły FDM i FEM; zachowane odrębne authority lane’ów | Własność pozostałych modułów, ABI/lifecycle, parity i kwalifikacja per lane |
| P5 | 99% | Coordinator i accepted-state adapters, również FEM; legacy scratch nadal istnieje | Izolacja, steering, checkpoint/recovery i cutover według adapterów/lane’ów |
| P6 | 52% | Trwałe katalogi, pinned materialized datasets i publiczne slice read API | Pozostały derived compute/projectory/plots/eksport, skala danych i runtime |
| P7 | 0% | Trwałe independent-batch plumbing w kodzie | Strategia continuation/graph oraz pozostałe P7 wymagają osobnego rozliczenia |
| P8 | 2% | Istotny przyrost infrastruktury DEV i historycznych bramek | Aktualna macierz CAE, clean install/upgrade/rollback, Windows release, wszystkie wymagane dowody |

Nie ma podstaw do świeżego „całość 49%” ani nowej arbitralnej liczby. Nawet wysoki odsetek kodu nie jest równoważny wysokiemu odsetkowi odebranych scenariuszy. Również stare 0%/1% nie oddaje obecności nowych implementacji.

## 6. Zalecana aktualizacja dokumentacji

To zalecenia po audycie; nie wykonano nimi przebudowy wcześniejszych dokumentów.

| Dokument | Działanie |
|---|---|
| README | Krótki bieżący punkt wejścia z SHA i odnośnikiem do reaudytu; dziennik checkpointów jako historia |
| 01 audyt | Zachować datę 20.09 i oryginalne F01–F12; dopisać mapę ich aktualnego rozstrzygnięcia |
| 02 architektura | Oznaczyć istniejące owner boundaries; usunąć „nowy” tam, gdzie biblioteka już istnieje; rozdzielić docelowe od wdrożonego |
| 03 plan | Zachować P0–P8/B i kryteria, poprawić normatywną ścieżkę DEV; nie wykreślać Windows release ani brakujących bramek |
| 04 kwalifikacja | Zachować CAE; dołączyć rejestr dowodów per scenariusz/lane/target, zamiast zastępować go jednym stanem etapu |
| 05 dowody/ADR | Zachować historyczne materiały; podłączyć późniejsze decyzje m.in. 0039, 0061 i 0064 oraz source identity |
| 06 status | Oddzielić krótką bieżącą tabelę od dziennika 3489 linii; odświeżyć opisy P6/P7/B, nie tylko liczby |
| 07 domknięcie | Zachować wymagania, wymienić historyczne blokery startupu i builda na aktualnie udowodnione braki |
| P0/P3a inventory | Zregenerować w kontrolowanym przyroście i wykonać review różnic; nie odziedziczyć automatycznie PASS |

Zalecany rekord zadania:

```text
id planu | kryterium odbioru | owner/symbol/konsumenci | source SHA
stan kodu | test źródeł | managed runtime | browser | nauka/release
receipt + wynik końcowy | otwarty brak | następna czynność
```

Jeżeli mają wrócić procenty, najpierw trzeba ustalić stały mianownik podzadań i ich wagi. Postęp implementacji i postęp kwalifikacji muszą mieć osobne wartości; brak wykonania nie jest PASS, a wymagania nie znikają po zmianie etapu.

## 7. Kolejność dalszych działań

1. Utrwalić rebaseline dokumentacji: obecny SHA, aktualne inventory i mapa wymagań do źródeł.
2. Odebrać jeden pionowy scenariusz M1: start, utworzenie niekompletnego modelu, edycja geometrii/regionów/materiału, zapis i ponowne otwarcie; osobno wykazać brak niejawnego solve i zachowanie szkiców.
3. Domknąć faktycznie brakujące bramki P3a/P5 na przypiętym pakiecie i kontekstach A→B; nie zaczynać od ponownej implementacji istniejącego koordynatora.
4. Zaktualizować backlog P6/P7 o istniejące read API i independent batches, następnie kwalifikować konkretne brakujące funkcje.
5. Prowadzić B i naukę per lane. Stabilny Docker DEV służy wykonaniu tej pracy, lecz nie zastępuje kwalifikacji solverów ani dystrybucji Windows.

## 8. Wykonane kontrole i źródłowe fingerprinty

| Kontrola | Wynik | Granica |
|---|---|---|
| Git branch/HEAD/status, relacja do bazy | PASS dla tożsamości wyżej | Bez fetch i bez zmian Git |
| `audit_refactor_p0.py --check` | Exit 0; 371/371, 0 unresolved, 2 router-only | Analiza źródeł; bez regeneracji plików |
| Zliczenie `paths` i metod w generated OpenAPI | 307 paths / 371 operations | Bez uruchamiania eksportera API |
| Lokalne linki Markdown w ośmiu głównych dokumentach | 476 odnośników, 0 brakujących ścieżek | Bez sprawdzenia anchorów i adresów sieciowych |
| Porównanie kontraktów ze źródłami | Ustalenia D01–D10 | Nie pełna analiza wszystkich ścieżek solverów |
| Build/test/browser/runtime/science | NOT RUN w tym audycie | Nie zmieniono statusu tych bramek na PASS |

SHA-256 przed dodaniem niniejszego raportu:

| Źródło | SHA-256 |
|---|---|
| `03-plan-refaktoryzacji.md` | `b330ff6144f4d87b9f7eb0907f6c5d265af40eb313cf2d269d0aaf909da54315` |
| `06-status-realizacji.md` | `4c1c57435be5914c6a5f7692bdb8884f6bced6749ed28d4cd74afd0a491894a3` |
| `07-domkniecie-etapow.md` | `1ea98cd66fbda882688518592c0814313263cf6508e6939e3a7e4b2f1fe98905` |
| `apps/control-room/src/kernel/api/generated/openapi-v2.json` | `2c9fa47e8d0e087e2ec2293ac5ff9a9f1cdee6a6c7fbd1d8bce835a8b568c7ad` |
| `scripts/audit_refactor_p0.py` | `797db7e092225ac9a6a0cb28f583e6378b0281f2d5187e3f637587925a715772` |
| `crates/fullmag-session/src/store.rs` | `98a55825f814cdd4ed11bf6b7bc1d2cb6b1fc4bfa5561fd3f24ad53eaf95012c` |
| `crates/fullmag-session/src/capture.rs` | `5687ef691a07fde79215502c6622a736ac122e2786617931a0d76a398806ebbd` |

Pełny HEAD identyfikuje pozostałe zatwierdzone pliki. Numery linii dotyczą tego HEAD; dla plików lokalnie zmienionych należy użyć `git show`, nie przesuwać dowodu na dirty wersję. Historyczne receipty zachowują własne SHA i nie zostały automatycznie przeniesione na audytowany master.

Kontrola końcowa: HEAD nie zmienił się; hashe planu 03, statusu 06 i OpenAPI
pozostały zgodne. Nowy raport przeszedł kontrolę UTF-8, parzystości bloków
kodu, dziesięciu identyfikatorów ustaleń, białych znaków i wybranych ścieżek
dowodowych. `git diff --check` zakończył się kodem 0.

Po zwolnieniu okna bez zapisów inne prace zmieniły dodatkowo
`compose.dev.yaml`, `docker/all-in-one/frontend_dev.py`,
`docs/guides/docker-volume-development.md` i
`scripts/test_docker_frontend_dev.py`. Nie włączono ich do oceny zatwierdzonego
HEAD. Jedynym plikiem dodanym przez ten audyt w repozytorium jest niniejszy
raport; nie wykonano commita ani zmiany indeksu.
