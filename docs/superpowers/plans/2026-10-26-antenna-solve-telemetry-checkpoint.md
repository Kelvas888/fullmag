# Stopka stacjonarnego obliczenia anteny — 26.10.2026

Status 27.10.2026: odtworzony Failed oraz czas/powód etapu potwierdzone w działającym API i produkcyjnym modelu/SSR stopki. Pełna mapa H Universe nie powstała; browser/WebGL NOT VERIFIED.

Sekcje poniżej są chronologicznym rejestrem. Obowiązuje najnowszy checkpoint na końcu; wcześniejsze Running i brak sesji opisują wcześniejsze instancje.

## Problem i zmiana

Użytkownik widział stale STEP 0 przy rzeczywiście działającym solve anteny.
`apps/control-room/src/modules/footer/FooterTelemetry.tsx::buildFooterTelemetryModel`
wyświetlał liczniki integratora LLG również dla stacjonarnego etapu anteny.
Nowa gałąź wymaga jawnego `antenna_solve_stage_id` w istniejącym zasobie
StageExecution oraz zgodności session/run/session_epoch/request_scope_epoch.
Nie wnioskuje o fizyce z nazwy, koloru ani typu obiektu. Bez aktywnego indeksu
akceptuje wyłącznie jednoznaczny rekord jednoetapowego runu.

Stopka pokazuje Solve state, Stage elapsed, Progress i Results zamiast
nieadekwatnych liczników LLG. Running oznacza Awaiting result; Completed
odsyła do zapisanych wyników, lecz nie deklaruje ich dostępności ani weryfikacji.
Powód błędu/anulowania pozostaje widoczny, jeśli opublikował go backend.
Istniejące zasoby scalar-window, object-metrics i frequency są wyłączane dla
tej gałęzi, bez tworzenia drugiego ownera StageExecution lub nowych requestów.
Zachowano ścieżkę telemetrii LLG.

## Uczciwy czas i postęp

Bieżący rzeczywisty payload API nie zawiera czasu rozpoczęcia etapu ani
procentu postępu. Stopka pokazuje Not reported, bez wymyślonego procentu.
`status.run.started_at` oraz CurrentRun.started_at w aktualnym API pochodzą
z czasu utworzenia sesji; nie nadają się na zastępstwo początku solve.
Zegar lokalny powstaje tylko dla jawnego, poprawnego timestampu etapu w
Running; pierwszy render jest zgodny z SSR, a zmiana tożsamości, terminalny
stan i unmount sprzątają timer. Obecny payload nie tworzy timera.

Readonly audyt wskazał trwałe źródło przyszłego uzupełnienia projekcji:
`crates/fullmag-session/src/types.rs::FmsCoordinatorJournalEntry.created_at`
oraz `WorkerEvent::Started`, publikowany przez
`crates/fullmag-api/src/accepted_study_worker.rs` przed wykonaniem etapu.
To czas rozpoczęcia wykonania etapu przez worker, nie czas CPU ani dokładne
wejście do funkcji native. Obecny projector w
`crates/fullmag-api/src/live_accepted_projection.rs::build_stage_execution`
nie przekazuje go do istniejących pól API. Backend nie został w tym celu
zmieniony ani zrestartowany; przyszła zmiana wymaga fence task/attempt/epoch,
odczytu journalu i managed weryfikacji po terminalnym wyniku obecnego Solve.

## Dowody i granice

Interpretowana regresja `apps/control-room/scripts/check-antenna-solve-telemetry.mjs`
używa kodu produkcyjnego, rzeczywistego zachowanego payloadu HTTP, renderu SSR
oraz sterowanego lifecycle zegara. Dowód RED poprzedniej stopki i wyniki GREEN
są w wolumenie kontrolnym grupy, katalog
`verification/antenna-solve-telemetry-20261026/`.
Regresja obejmuje stany terminalne bez active_stage_index, obce tożsamości,
brak/niepoprawny czas i procent, zachowanie LLG, pojedynczych ownerów,
wyłączenie nieadekwatnych requestów oraz cleanup bez API polling.
Nie kompilowano testów Rust ani testów jednostkowych aplikacji.
Nie wykonano buildu lub restartu solvera, nowego Solve ani zmiany budżetu.
Browser/WebGL i rzeczywisty wygląd poprawionej stopki pozostają niezweryfikowane
z powodu wcześniej zablokowanego dostępu narzędzia do strony.

Ostatni rzeczywisty pomiar przed tym zapisem: Unix ms 1793054325882,
run-live-62d110763485b10e2512922267a1aed284996710852d4fd27cb3f4ad71a1e496,
PID 5124, stan R, CPU ticks 1121976 → 1122288 w 2 s,
czas procesu około 9027 s, API Running, revision artefaktów 0.
To dowód wykonywania pracy, nie procent wykonania ani gwarancja zakończenia.
Pełny wynik V/J/H oraz obraz H w Universe nadal nie są potwierdzone.

## Brak aktywnej telemetrii po restarcie — 27.10.2026

Nowszy odczyt API potwierdził `health.status=ok`, `active_session=false`
i pustą listę sesji. Historyczny pełny Solve zakończył się Failed z powodu
`surface RT0 wall-time exhausted`; nie powstała mapa H całego Universe.
Poprzednie datowane obserwacje Running są historią, nie stanem aktualnym.

Dodatkowa regresja odtworzyła błąd: bez statusu bieżącej sesji stopka nadal
budowała Step 0, a zachowany event starej sesji mógł dać nawet Step 42.
`FooterTelemetry.tsx::buildFooterTelemetryModel` kończy teraz tę gałąź przed
odczytem scalarów/metryk: pokazuje `No live telemetry` i nie publikuje liczników.
Nie deklaruje ani uruchomionego solve, ani braku wszystkich historycznych wyników.
Jawna gałąź anteny oraz rzeczywiste liczniki LLG pozostają bez zmian.

RED: interpretowana regresja przed poprawką zakończyła się exit 1 na
`Absent session telemetry must not publish zero or stale LLG counters`.
GREEN: osiem grup modelu produkcyjnego/SSR/lifecycle przeszło exit 0.
Sprawdzono także wyłączenie zależnych requestów przy braku statusu.
Pełne `tsc --noEmit --incremental false` oraz lint trzech zmienionych plików
z `--max-warnings=0` zakończyły się exit 0 w istniejącym kontenerze frontendu.
Nie kompilowano ani nie uruchamiano suite jednostkowej aplikacji/Rust.

Dowody: frontend volume `/state/development/verification/footer-missing-session-20261027/`:
`result.json`, `green.stdout.log`, `green.stderr.log`, `typecheck.*.log`, `lint.*.log`.
To korekta renderowania przy braku danych, nie odtworzenie historycznej sesji,
nowy wynik solvera ani odbiór wizualny przeglądarki. Browser/WebGL nadal NOT VERIFIED.

## Próba odtworzenia Failed po wymianie usług — 27.10.2026

Pełny run `run-live-62d110763485b10e2512922267a1aed284996710852d4fd27cb3f4ad71a1e496`
zakończył się Failed po 3 h 1 min 27,431 s; artefaktów tego runu jest zero.
Nie jest to obliczenie LLG: licznik Step nie jest miarą wykonania statycznego
solve przewodzenia i pola. Nie ponowiono pełnego Solve.

Źródła odtwarzania obserwacji Failed dodają prywatny, przypięty dowód oryginalnej
sesji i zakończenia native, bez tworzenia ACK, zmiany Start lub ponawiania runu.
Producent to `scripts/docker_volume_terminal_observation.py::build_proof`,
transport PID1 to `docker/all-in-one/runtime_service.py::terminal_observation_preflight`,
a instalacja stanu API jest w `crates/fullmag-api/src/development_accepted_restore/terminal_observation.rs`.
To nadal zmiana w weryfikacji, nie potwierdzony efekt w UI.

Zarządzane `docker-dev-images` przygotowało obrazy, zachowując cache toolchaina.
Stop-idle `3846ff5c5a9e4eaa9c45fefc469ee016` i wymiana usług
`904a15f685884ac3a5f8cf71a0b42f69` zakończyły się poprawnie.
Start `37062974a42f4ad4aec3976df9dfafe6` zakończył się failed-confirmed na
kompilacji API: zapis czasu ma typ u64, a stan sesji wymaga u128.
Źródła poprawiono przez jawną konwersję zachowującą timestamp. Późniejszy
managed resume `f7bd1d394eab4343a6fe27e792362c76` zbudował pakiet i odtworzył
Failed, ale StageExecution nadal zwracał 204. Końcowy wynik kolejnej poprawki
opisano w najnowszym checkpointcie poniżej.

Wykryte problemy hosta poprawiono bez obchodzenia przepisów: zgodność typów
Python 3.8, przekazanie pary pinów przez bramkę just oraz porównanie mountów
niezależne od kolejności listy, z zachowaniem porównania pełnej zawartości.
45 interpretowanych regresji protokołu/dispatch oraz 13 istniejących regresji
cache/admission przeszło. Nie jest to kwalifikacja natywna ani browser/WebGL.
RunIntent, run_catalog i start_release pełnej nieudanej próby zachowały hashe.
Wyniki i trzy poprzednie pakiety są zachowane; nie wykonano sprzątania.

Osobna diagnostyka ma zachować cały source 677/1856 i Global 1145/6428,
obserwować cztery jawne punkty i zaostrzyć autorski budżet operatora do 180 s.
Przygotowanie źródła poprzedza pierwszy target, więc samo ograniczenie liczby
punktów nie ogranicza oczekiwania. Budżet operatora jest kooperacyjny i nie
obejmuje wcześniejszego solve transportu ani całego jobu. Publiczne authoring,
admission i zapis profilu błędu wymagają rzeczywistego wykonania; nie zgłoszono
wyniku ani porównania OFF/ON. Stare przygotowanie OFF 10800 s nie jest parą
nowej próby 180 s. Pełna mapa Universe, profil faz i widok UI nadal NOT VERIFIED.

## Odtworzony etap i rzeczywisty render stopki — 27.10.2026

Managed `just docker-dev-restart-idle` zakończył się succeeded:
`7320487f4e8d4265acd4d2b16a2b185e`, Compose config
`66401b85878924fb0ca043cad95c27b219264e52e78461de7535f014d947ca9c`.
Kompilacja aplikacji w tym samym backendzie trwała 358155 ms, exit 0;
nie kompilowano testów jednostkowych Rust. Zachowano oba container ID:
backend `cc32cb682ae597e3f6c5e52c5e4372fbfa85a8ec1219bf830e3391b94a43bd1b`,
frontend `0dacc07deb1e3f8e8d0cc7f029fbba00c32532884f80a2083d2c079a9c0edd45`.
Źródła: HEAD `7e6b98e686810674d60668b0f302b123564d8e5e` + WIP,
snapshot `95cf7cc2df21ba0b1217342216e5d105f26e0f6fdb60be7bfc97be4cc56d3bd2`.
Nie uruchomiono nowego Solve.

Przyczyną StageExecution 204 był brak hydratacji zakończonego etapu;
normalny projector prawidłowo odmawiał publikacji z powodu
`accepted_execution_input_mismatch`. Tego guardu nie osłabiono.
Prywatna ścieżka terminal observation buduje istniejący StageExecution z
przypiętego zaakceptowanego katalogu i journalu pod istniejącym writer fence.
Czysty `build_terminal_observation_stage_execution` nie pobiera kolejnego
read locka, nie tworzy progresu, wyników, ACK, tasków ani rezerwacji.
Hydratacja używa istniejącego `replace_current_live_stage_execution`.

Rzeczywisty odczyt po restarcie: API `897c21ed-442a-4a42-82fb-41dcdffe03e9`,
health 200, CurrentRun 200 Failed, StageExecution 200 zamiast 204.
Etap `inspect_loop`: Failed, Started 1793045302463 ms, Failed 1793056189895 ms,
czas 10887432 ms; powód `surface RT0 wall-time exhausted`.
Nie użyto czasu utworzenia sesji jako czasu rozpoczęcia workera.
Scena jest identyczna przed i po restarcie; SHA surowego payloadu
`29aaf160a79afc317cf46b529f0d54b8281212c948883b083c7a01a726d09c8e`.
Rzeczywisty native install receipt ma SHA
`db19d5463b0172c404a66761569a1d7feffa8c038cecc067c4d4aec727768ff3`;
przypina tę samą terminal evidence
`84476f129ce02c821c6adfeeb147ea3232b84529fbfeac454d421b8403f78afc`.

52 interpretowane regresje protokołu, lifecycle i dispatch przeszły.
Produkcyjny model i SSR stopki sprawdzono osobno z rzeczywistymi payloadami
Status/StageExecution: `Solve state = Failed`, `Stage elapsed = 03h 01m 27s`,
`Progress = Not reported`, `Results = Not completed`; brak liczników Step/LLG.
To nie jest kontrola rzeczywistego DOM ani dowód wyglądu w przeglądarce.

Dowody w control:
`verification/terminal-observation-stage-hydration-20261027/actual-after-managed-restart/`
(HTTP, receipt instalacji, tożsamości binariów, retencja),
`verification/terminal-observation-idle-restart-20261027/applied-repository-regressions.json`.
Dowody SSR w wolumenie frontendu:
`/state/development/verification/terminal-observation-stage-hydration-20261027/actual-failed-footer-result.json`
oraz zapisane stdout/stderr, skrypt i payload HTTP; fixture SHA
`c26ee9bb25a070a7dfbbe9a72cf35e0b38d71934cd2412c64be14c3e6fde8fc8`.
Zachowano bieżący pakiet i pięć backupów; candidates/retired puste.
Nie wykonano sprzątania ani nie zadeklarowano kwalifikacji retencji.

Próba diagnostyczna 180 s / cztery targety NIE wystartowała. Publiczne
preview i RunIntent zwróciły 200, lecz rzeczywisty v4 Submit zwrócił 400:
`invalid_run_submission: v4 Submit requires captured compiler source`.
Nie wysłano materializacji, nie powstał run ani worker/rezerwacja tej próby.
Nie obchodzimy bramki źródła. Następny krok: poprawny publiczny skrypt z
jawnymi wejściowymi siatkami źródła, Global i czterech targetów, prawdziwy
source capture, dopiero potem ograniczona diagnostyka kosztu operatora.
Pełny profil faz, mapa H Universe i browser/WebGL pozostają NOT VERIFIED.


## Udana diagnostyka V/J/H na czterech punktach — 27.10.2026

Pełny historyczny Universe pozostaje Failed. Nowa, odrębna próba diagnostyczna
zakończyła się Succeeded i została odczytana przez publiczne API. Nie jest
pełną mapą Universe ani kwalifikowaną bazą do LLG/FFT lub reprodukcją publikacji.
Bieżąca scena UI nadal odpowiada historycznej próbie, a nie nowemu headless runowi.

### Naprawione przyczyny przygotowania

- Jawny `MeshData` NPZ przypisany do istniejącego ownera zachowuje surową
  siatkę przewodnika obok Global i osobnego niemagnetycznego sampling.
  Import obejmuje P1/Tet4; nie zmienia ścieżek bez source ani mixed topology.
  Regresja częściowej mapy object IDs dała RED, potem 8 PASS w Pythonie.
- Dispatch CLI rozpoznaje `prepare-run-json` i `run-script-accepted`.
  `--prepare-only` używa tego samego capture, kompilatora i pełnego limitu
  transportu co Submit; sam nie wysyła Submit/Solve. Wspólna walidacja
  RunIntent obejmuje również ten tryb. Rzeczywiste help/parser checks: 5 PASS.
  Rzeczywisty prepare-only odrzucił też pusty idempotency_key: exit 1, brak
  requestu na stdout i brak HTTP/Solve; receipt invalid-idempotency-key-regression.json.
- Kompilator dopuszcza jawne snapshoty `antenna_field_solve` tylko przy dokładnej
  zgodności authored ID, definicji i portu. Wykorzystuje wspólny parser selektora;
  kompletność, kolejność, enabled i późniejszy planner pozostają obowiązkowe.
- Producent zachowuje rzeczywistą intencję skryptu przez kanoniczne adaptery
  `for_problem`, `migrate_legacy_live_execution` i `bind_declared_execution`.
  Typowane profile/warstwy pozostają chronione; heterogeniczne snapshoty są
  odrzucane przed wspólnym bindingiem accepted v4.

Pozostaje ogólny problem Auto/null: binding usuwa `cpu_threads:null` z preimage v2.
Nie zmieniono tego podpisu ani jego walidatora. Nowy skrypt jawnie autoruje
`study.threads(1)` i `CpuResources(threads=1)` przed przygotowaniem źródła.
Native/BLAS/affinity pozostają Auto. Jawna polityka native/BLAS wymaga adaptera
przydziału i została odrzucona w osobnym probe, nie wyłączono tej kontroli.

### Build i pochodzenie wejść

Trzy kolejne managed iteracje w tych samych backend/frontend przeszły:
`50251e80681f43a98cadd96c8e3f5b3f` (Make 304233 ms),
`faaeaabb66b444e1a7c406bab942d5d2` (233862 ms),
`c234b558b01a4a298650e155b2f35f6f` (152194 ms).
Najnowszy pakiet ma snapshot
`37a1c2e90c97b54743af6f5ff52c9d07889c23058860d24a5b04ef1a61d38c0d`,
HEAD przy buildzie `a3f8498a9ab9b32ef08112a0085febd65ddf50a5` + WIP.
Przy pierwszej próbie ostatniej iteracji omyłkowo podano pin iteracji zamiast
wdrożenia; odmowa nastąpiła przed zmianą usług. Prawidłowy pin recepty
`docker-dev-restart-idle` pochodzi z `development/attempts/`, nie `iteration/`.

Scenariusz wejściowy został następnie zmieniony wyłącznie o jawne authoring CPU
i poprawny manifest. Jest osobnym wejściem istniejącego pakietu, nie przebudową
solvera. Skrypt `examples/antenna_universe/rt0_profile_180s/fem_antenna_rt0_four_target_180s.py`
ma SHA256 `7213dcfe8a70714c88bb9e3b9e19ed4269cc34b499dc13efe149f73327363bdb`;
manifest `6cf677ce949c62e90077d3b3ad6be8b36cef1e1d9ace8ab86d9298299f7f990a`.
Trzy assety pozostają bajtowo identyczne z wejściami referencyjnymi.
Raw przewodnik: 664/1856; po cięciu: 677/1856; Global: 1145/6428;
sampling: 4/1, dokładnie prerejestrowane wierzchołki komórki Global 1726.
Nie dodano magnetów ani energii LLG.

Prawdziwy capture i kompilacja z worktree: exit 0, 35.429 s;
request 44172062 B, SHA256
`74fd68ff51da3407c4418f0e3bd8f2efc0e53b1380e1603d67040def6cf97b07`.
Profilera dodano przez istniejący publiczny producer RunIntent, exit 0, 4.185 s.
Nie edytowano ręcznie fingerprintu ani zaakceptowanego stanu.
Przy Submit klient przekroczył 30 s, lecz run był zapisany. Odczyt GET i ponowny
czysty producer potwierdziły identyczny RunIntent/fingerprint; Submit nie ponowiono.
Materialization wysłano raz: HTTP 200. API kolejno preparing → running → succeeded.

### Trwała tożsamość i wynik

- project: `project-1f48487cf16342ca9524e0795d39597b`
- run: `run-9e08498d8f5bf1dbbac665ff3e261fd2c89ad689f7037199f77f6b712a982db6`
- fingerprint: `2813bc4191c2310416213e33e058762f0d4bbdea2e2587f734c8dcbfa4fa9614`
- task: `task-a6d400f350e83896790c9d83988e8e85e52c806addb41cf43ddf1730cd482c84`
- attempt: `attempt-e33d397928a34e298444afa3f49b5a8f`, epoch 1
- pakiet CAS: `9fa75fc1002b976d172fd151baed14551dda7e0a6bee7042f9ae611699135c76`

API: katalog i przypięty zasób accepted inspection HTTP 200; zasób sprawdził
`full_cold_bundle`. Binarne payloady V, J, H oraz pozycje pobrano przez publiczny
endpoint z pinami attempt/epoch/package. SHA256 i długości odpowiadają manifestowi;
wszystkie wartości są skończone, a cztery pozycje równe prerejestracji.
V ma 677 wartości [V], J 1856 wektorów w centrach komórek [A/m²], H cztery
wektory [A/m]. Potencjał źródła 0.25 V, prąd 0.14283655988114702 A,
charge relative residual 8.271607187684167e-13. To rozwiązanie charge/Oersted,
nie pola demag ani dynamiki magnetyzacji.

### Zmierzony profil i jego ograniczenia

Operacja `antenna.closed_loop.inspect` zakończona poprawnie: 94.288 s.
Natywny operator pola: 26.717 s. To nie czas całego runu z publikacją.

| Faza | Czas [s] |
|---|---:|
| Przygotowanie źródła | 1.159 |
| Dokładna geometria | 7.899 |
| Binary64 | 1.071 |
| 80 cyfr | 6.622 |
| 120 cyfr | 7.870 |
| Kontrole zgodności | 2.044 |
| Redukcja i serializacja | 0.006 |
| Czas operacji nieprzypisany tym fazom | 67.617 |

`accounting_issue=false`. Nie wolno automatycznie przypisać ostatniego czasu
samemu solverowi prądu. Przygotowanie źródła nie dominuje w tym przypadku;
w kosztach pola duże są geometria i obie ścieżki wysokiej precyzji.
Cztery punkty nie uzasadniają ekstrapolacji czasu ani deklaracji przyspieszenia
pełnego Universe. Następny krok to optymalizacja oparta o ten profil i osobna
walidacja całego Global; nie ślepe ponowienie ani podniesienie timeoutu.

Worker PID 5668 zakończony; jego lease został normalnie zwolniony
2026-10-27T04:06:54.993011851Z. Minimum zasobów w RunIntent jest filtrem oferty,
nie limitem pamięci na 1 bajt. Faktyczna oferta lease wynosiła 3000 millicpu,
5637144576 B RAM i 7516192768 B storage; authoring solvera ma jeden wątek CPU.
Nie zmieniono limitów kontenera ani polityki hosta.

Dowody: control volume `verification/rt0-public-capture-20261027/`, w tym
`wt-capture-receipt.json`, `wt-pre-submit-review.json`,
`wt-submit-confirmed-fingerprint.json`, `wt-materialization.http.json`,
`wt-inspection-catalog.http.json`, `wt-inspection-pinned-resource.http.json`,
`wt-public-vjh-verification.json`, `wt-worker-operation-profile.v1.json`,
`wt-resource-lease-records.json` i receipty managed buildów.
Profil SHA256 `71cb1ca89b00297caba8a65db8667562fdab1f57ca7786acb4ec231d50bbcef1`.

Kwalifikacja pozostaje `inspection_only` / `NOT VERIFIED`; API odmawia
per-ampere basis, source FFT i LLG drive. Pełna mapa H Universe oraz widok
przeglądarki/WebGL nadal NOT VERIFIED. Rust unit tests nie kompilowano.
Retencja: bieżący pakiet i osiem backupów zachowane, bez kasowania cache,
wyników i wolumenów; pełna kwalifikacja retencji nadal NOT VERIFIED.


## Pomiar całego wywołania native — 27.10.2026

Nie zmieniono metody, precyzji, tolerancji, siatek ani punktów próbkowania.
Dodano opcjonalny native_call_wall_ns: czas całego profilowanego wywołania ABI,
zawierający operator pola. To pomiar zagnieżdżony, nie dziesiąta faza do sumowania.
Dziewięć dotychczasowych faz zachowuje identyfikatory i znaczenie.
Stare raporty bez pola pozostają czytelne; wyłączony profiler nie odczytuje
dodatkowego zegara. Producer i walidator sprawdzają operator <= call <= total,
zachowując oznaczenie anomalii zegara i pomiar po kontrolowanym błędzie native.

Właściciele: crates/fullmag-runner/src/native_fem/steady_transport.rs::solve_rt0_common,
crates/fullmag-runner/src/antenna_field_solution/closed_loop_execution.rs::execute_antenna_closed_loop_inspection_profiled_typed,
crates/fullmag-runner/src/solver_profile.rs::SolverProfileOperationSample::validate,
crates/fullmag-api/src/schemas/diagnostics.rs::SolverProfileOperationResource.

Zarządzana iteracja 54271fb73a40410db92124c665001de0: sukces, Make 548536 ms,
pakowanie 4393 ms, weryfikacja pakietu 3456 ms.
Snapshot 24e18593ff4171f3619e0bb427e7f4c0b86e0b7ee4b576e86c5a63ec0b8c9344,
bazowy commit d3cc5a5800bd463c5af99741b99825c86dba2e3d z jawnym dirty.
API instance f0996610-45cc-4f9d-ba4d-92e77f6f1e63; HTTP OpenAPI potwierdził pole
opcjonalne. Nie kompilowano testów jednostkowych Rust; źródła regresji dodano,
ale nie zgłoszono ich wykonania.

Oddzielny run run-c83f5ac8dfdb61c79eb80802915786b6c5cb40a59b16688a050e71aa71e0f310,
task task-966b29c29240483138e1c651705747c3c816404e9c2792c71efb06560f93367d,
attempt attempt-1848fa78c683425c802ed60a0d8f6620, epoch 1:
**Succeeded**, katalog rewizja 98. Zamrożone archiwum, katalog Study, asset_paths
i immutable_assets są identyczne z poprzednią próbą; nowy RunIntent utworzył
publiczny producer. Submit wykonano jeden raz. Po timeout klienta początkowy
GET zwracał 404, późniejszy GET potwierdził trwałe przyjęcie. Nie potraktowano
timeout/404 jako dowodu zakończenia żądania. Fingerprint
92d7d3484608cab3e098a8e5eb7fb175d7a74a22871f0faa5f251cb1d4a8df38
porównano z producerem przed jednorazową materializacją.

| Zmierzony zakres | Czas [s] |
|---|---:|
| Cała operacja runnera | 95.924504469 |
| Całe wywołanie native ABI | 85.573669145 |
| Operator pola | 26.591040381 |
| Native poza operatorem pola | 58.982628764 |
| Runner poza wywołaniem native | 10.350835324 |

To rozdziela poprzednie „unattributed”, ale nie identyfikuje konkretnego etapu
native. Nie wolno przypisać 58.98 s samemu solve potencjału ani projekcji RT0
bez kolejnego pomiaru. Różnica czasu względem poprzedniej próby nie jest
deklaracją przyspieszenia. Historyczne 3 godziny nie są baseline'em aktualnego
kernela bez potwierdzenia identycznego pakietu/operatora.

Publiczny odczyt przypiętego pakietu i v_raw, j_center_raw, h_raw, sample_xyz:
HTTP 200; wszystkie bajty mają te same SHA256 co poprzednia próba.
Worker PID 4669 zakończony; lease lease-cac02fd40e5c4a918fea16f7860cb6da
normalnie Released o 2026-10-27T04:45:04.013756390Z.
Nadal inspection_only: display/current_density dostępne,
per_ampere_basis/source_fft/llg_drive zablokowane.
Pełna mapa Universe, kwalifikacja naukowa i browser/WebGL nadal NOT VERIFIED.

Dowody w wolumenie kontrolnym: verification/native-call-timing-20261027/.
Profil SHA256 1bb4c366d59812fe652d53c6c5c18b340a7c9942479a8598f2aaffb4221e86ff;
timing-breakdown.json, public-vjh-comparison.json, pinned-resource.json,
run-terminal.json, submit-fingerprint-confirmed.json,
openapi-field-verification.json, build-receipt.json.
Pozostawiono 9 generacji rollback; brak usuwania. Skill fullmag-build-stage-cleanup
nadal nieobecny; retencja nie jest zakwalifikowana.

### Napotkana blokada generowania typów API

docker-dev-codegen używał starego development/verified.json mimo bieżących usług
z powiązanej udanej iteracji. Poprawka 36cbcb40f6dd006b28aba3c507c288c75c72f101
w scripts/docker_dev_codegen.py::_validate_admitted_source_mount używa aktualnego
terminala i istniejącego scripts/docker_volume_activate.py::_linked_runtime_terminals.
Zachowuje kontrolę obu kontenerów, obrazu, konfiguracji, mountów i wyścigu receiptów.
26 interpretowanych regresji przeszło, RED odtworzył starą odmowę, rzeczywisty wybór
obu usług przeszedł. TMPDIR=/build był potrzebny wykonywalnemu interpreterowi
fixture, ponieważ kontenerowe /tmp jest noexec.

Po poprawce codegen przeszedł bramkę usług, ale prawidłowo odmówił przez stale-source
gate: zmieniony skrypt należy do snapshotu runtime. Nie osłabiono _source_matches
ani nie zmieniono receiptów. Pozostają zarządzany build z aktualnymi źródłami
i regeneracja klienta/typów; nie zgłoszono ich jako zakończonych. Następny krok
wydajności: pomiar etapów native i osobno poprawka operatora pola, z kontrolą
identycznych wyników.


### Zamknięcie synchronizacji typów — 27.10.2026

Poprzednia blokada stale-source została usunięta przez rzeczywisty zarządzany
build, bez osłabienia bramki. Iteracja dd1fd019a11c4a29b2545ce36f1b1c4c:
sukces, Make 254713 ms, pakowanie 8802 ms, weryfikacja 3559 ms.
Commit wejściowy 891918ab18fbef6c7bf35328b5aee6254aad626a,
snapshot baef683051ad8031277a7347e88983cb278a07f00c06c11c8281dca12098f577.
Receipt SHA256 3bd6bcda27927a285243c2c45ce55d26c3c1c663afa40641b3ca6d0f53ee8758;
kopia build-dd1fd019-receipt.json w dotychczasowym wolumenie dowodów.
API health HTTP 200. Zachowano te same kontenery i wszystkie dane; pozostawiono
10 generacji rollback bez usuwania.

Rzeczywisty docker-dev-codegen zakończył się sukcesem: exit 0, 68733 ms,
receipt backend/codegen/openapi-v2/a28c6d671a2de47e7b0f1d2a71b1b300edcdb1ddd1e7715585252a7c11aa7654.json.
Wygenerowano cztery artefakty; diff obejmuje tylko openapi-v2.json
i openapi-v2-types.ts: opcjonalne native_call_wall_ns. Nie zmieniono endpointów.
Przypięty backend, frontend, źródła, build identity i wolumeny zostały sprawdzone
przed generacją oraz po niej; staging usunięto przez istniejącą procedurę.

Zarządzana kontrola frontend-antenna: sukces. Typecheck, testy dwóch wskazanych
plików Vitest i ESLint zakończyły się kodem 0; receipt
verification/frontend-antenna-checks/receipt.json. To kontrola typów i kontraktów,
nie dowód wizualny przeglądarki ani naukowa kwalifikacja anteny.


### Diagnostyka geometrii 20 punktów i pełna próba Universe — 27.10.2026

Audyt tylko do odczytu rozdzielił nośnik źródła (raw 664 węzły / 1856 Tet4,
po przecięciu źródła 677 / 1856) od nośnika pola Global (1145 / 6428).
Zgodność geometrii elementów źródła nie wymaga zgodności numeracji węzłów
niezależnego Global. Samo istnienie 46 wspólnych węzłów nie jest błędem siatki.
Dowód: verification/native-call-timing-20261027/geometry-readonly-audit.json,
SHA256 628aa18d64471935fc36fa78ac9cf6005ec82541911c75bb0e56bd2caf1039f6.
Klasyfikacja obejmuje przypadki dokładnie na granicy, wewnętrzne i bliskie
granicy; bardzo małe odległości dotyczą dokładnej reprezentacji binary64,
nie deklarowanej dokładności fizycznej.

Nowy publiczny skrypt rt0_geometry_180s/fem_antenna_rt0_geometry_180s.py
zachowuje 20 istniejących węzłów i pięć Tet4 Global wraz z ich ordinalami.
Nie przemieszcza węzłów, nie upraszcza przewodnika ani tolerancji.
Wybór i hashe zapisano w input-manifest.json. Nie obejmuje 15 przypadków
kontaktów wewnętrznych źródła; pełna próba je zachowuje.
Pierwszy capture odmówił dostępu do assetów poza katalogiem skryptu.
Naprawiono pakiet wejścia przez identyczne lokalne kopie assetów;
nie zmieniono bramki ani katalogu uprawnień.

Run run-bb36bd56d49ba6da9201623cd8d5566f141e292f0c7d474e4c9f897c0cebb6a1,
task task-1c5af8116c42e519552172b6e5a7a2873c30cded42dfe28f9ade2fb6f2a5356a,
attempt attempt-51e01e436bfd43ca941ad03d8062db0d, epoch 1:
**Succeeded**. Capture, kanoniczny producer RunIntent, pojedyncze Submit
i materializacja, worker native, archiwum oraz publiczny odczyt V/J/H
przeszły rzeczywistą ścieżkę aplikacji.

| Zmierzony zakres diagnostyki 20 punktów | Czas [s] |
|---|---:|
| Cała operacja runnera | 211.171287713 |
| Całe wywołanie native ABI | 199.361945707 |
| Operator pola | 142.854900841 |
| Native poza operatorem pola | 56.507044866 |
| Runner poza wywołaniem native | 11.809342006 |

Profil nie zgłasza accounting_issue. Wszystkie 20 wektorów H są skończone.
Publiczne v_raw, j_center_raw, h_raw i sample_xyz zwróciły HTTP 200
i zgodność hashy z przypiętym pakietem. V/J są bitowo identyczne z baseline4,
a cztery wspólne próbki H również pozostają bitowo identyczne.
Worker PID 7399 zakończony; lease-a83dc91282a24c0babd5168ea37f73ea
Released 2026-10-27T05:20:36.030104473Z.
Dowody: verification/rt0-geometry-cases-20261027/public-vjh-comparison.json,
worker-operation-profile.v1.json, timing-breakdown.json, run-terminal.json
i resource-lease-records.json. To nadal inspection_only, nie kwalifikacja
bazy per A, FFT, LLG ani odtworzenie publikacji.

Pełny skrypt rt0_full_universe_frozen/fem_antenna_rt0_full_universe_frozen.py
usuwa diagnostyczny obiekt sampling i wybiera Global. Zachowuje wszystkie
1145 węzłów / 6428 Tet4, ten sam przewodnik i 2 125 120 par źródło–target.
Rzeczywisty capture potwierdził przygotowane źródło 677 / 1856,
identyczne z anteną diagnostyki 20. Wszystkie tolerancje i limity są identyczne,
poza przywróceniem dotychczasowego limitu pełnego pola 10800 s;
90 s/target pozostaje. Nie podniesiono dotychczasowej polityki pełnej próby.
Niezależny przegląd obu skryptów i manifestów: brak Required.
Przegląd źródeł nie stanowi dowodu ukończenia pełnego Solve.

Próba pełna run-5654db21201dd6c660f7ecae78baf8588477fe2a7d90480d9d64b30e4d050080
została przyjęta HTTP 201; fingerprint
9475dbcad624061ae17274f275355b3aaea03429df46b4b1fcdeb4e7179c1f87
zgodny z kanonicznym producerem. Materializacja raz, HTTP 200.
Task task-5d7919a0c304d49459b92343dca688a7f370108c918308340259d02ae7694bc0,
attempt attempt-61282a3f0a5b4db8a9a8add68d705645, epoch 1,
stan odczytany przez API: running, rewizja 23. PID 9549 rzeczywiście pracuje.
Jego załadowana biblioteka ma SHA256
9d53bd2519a8c814f4272137712a1b48ba5a277c63aba84380855361f3dc4eea,
identyczny z diagnostyką 20 punktów. Stan ten nie dowodzi wyniku pełnej mapy.
Dowody w verification/rt0-full-universe-20261027/, w tym
compiled-carrier-shape.json, pre-submit-review.json, submit-response.json,
materialization-response.json i loaded-worker-native-binding.json.
Prepared request SHA256 c8c2cb73b1e5767f0f3f504a65d209c1a3696e28de596b5c4cf90bc2a8dc816a.
Commit źródeł przed próbą: 3ddfd9b4c680255f7b142e3b277d7079cf8feefa;
pakiet pozostaje z udanej iteracji dd1fd019a11c4a29b2545ce36f1b1c4c.

W UI licznik step opisuje dynamikę LLG, więc statyczne V/J/H nie zwiększa go.
Aktywny accepted run i scena authoring to odrębne zasoby; sam widok sceny
nie potwierdza przypięcia ani wyrenderowania wyniku accepted.
Pełna mapa, jej wyświetlenie w Universe i browser/WebGL: nadal NOT VERIFIED
w chwili tego checkpointu. Odczytu przeglądarki nie ponawiano po blokadzie.


### Odczyt zapisanego wyniku i stan wybranego runa w UI — 27.10.2026

Kontynuacja poprzedniego etapu oznacza rzeczywisty postęp: zakończona diagnostyka
20 punktów i uruchomiony pełny run pozostają zachowane. Ponownie sprawdzono
żywy PID 9549 i ten sam starttime; CPU procesu rośnie, API potwierdza running.
Pełny wynik 1145 punktów nie został jeszcze opublikowany w tym checkpointcie.

Aktualny /v2/sessions/current/status nadal wskazuje stary, nieudany
run-live-62d110763485b10e2512922267a1aed284996710852d4fd27cb3f4ad71a1e496
z solver_steps=0. Ten licznik nie jest postępem nowego accepted runa.
FooterTelemetry::resolveFooterAntennaStage prawidłowo wymaga tej samej
tożsamości session/epoch/run; nie zmieniono tej ochrony.

Wynik 20 punktów przeszedł istniejący kontroler
scripts/validate_accepted_antenna_closed_loop_http.py::validate:
33 rzeczywiste kontrole, exit 0, cold scope full_cold_bundle.
Statusy: 13 × 200, 3 × 206, 5 × 304, 3 × 400, 6 × 409, 3 × 416.
Sprawdzono V, lokalne J i H, ich jednostki, hashe, długości i wartości skończone;
obce attempt/epoch/package odrzucono jako antenna_source_conflict.
Odczyt nie zmienił authoring session, sceny ani poleceń i nie uruchomił Solve.
Dowód: verification/rt0-geometry-cases-20261027/closed-loop-http-integrity-gate.json,
SHA256 6111f5e8948078e51c47f9809bf0f7887ed7093f00c01d9f6cf2e6efc7e6fb12.
Pierwszy wybrany smoke_accepted_antenna_inspection.py poprawnie odmówił innej
rodziny metadanych: dotyczy truncated external lead, a nie closed_loop.
Nie osłabiono jego walidacji; użyto istniejącego właściwego kontrolera.

Niezależny audyt potwierdził rzeczywisty SolutionSet wyniku 20 punktów:
solution-8741cfadb0b34bbb7d16f9c7bee755cc7c0645ed1a268f44ac7330b878a1448e,
rewizja 2, succeeded. H:
materialized-dataset-d863f1f9fa5c8b6af2876affe0f7851953be6666c0c8959a2729a3666697dacc,
H_ant, A/m, 20 × 3 f64, integrity=verified.
V i J również mają materialized datasets; J zachowuje tet4_cell_local_nodes.
Zapisana geometria H 20 / 5, topology i support odczytane HTTP 200,
zgodne z deskryptorami. To dane diagnostyczne, nie pełna mapa Universe.

Istniejąca ścieżka jest wystarczająca:
SavedResultsBrowser::inspectSelected →
PinnedMaterializedDatasetSelectionRef →
ObjectVisualizationController::setSavedFieldPresentation →
useSavedFieldViewportResources →
buildSavedFieldViewportSceneModel.
Nie dodano alternatywnego ownera, pinów, endpointów ani fałszywego live result.
Otwarty projekt jest stanem klienta ProjectDocumentController: odczyt API
nie potwierdza, że przeglądarka ma otwarty project-1f48487cf16342ca9524e0795d39597b.
Przyszły odbiór UI musi sprawdzić zgodność projektu i wybrany saved dataset.

Poprawka apps/control-room/src/modules/results-navigator/SavedResultsBrowser.tsx:
SavedProjectResults otrzymał Refresh runs; SavedRunResults korzysta z istniejącego
useProjectRunResource i pokazuje lifecycle/readiness tylko jawnie wybranego runa.
Refresh run and results odświeża jego zasób i odkrywanie SolutionSet.
Błędy refresh nie ukrywają poprzednich danych, ale jawnie oznaczają starszą listę.
Wybór SolutionSet/datasetu i prezentacja pozostają bez zmian; nie ma pollingu,
Compute, automatycznego attach ani zmiany bieżącej sesji.

Nowa regresja SavedResultsBrowser.execution.test.tsx sprawdza kliknięcia Refresh,
właściwą tożsamość project/run, zachowanie tożsamości panelu przy refreshError
oraz brak Inspect, gdy succeeded nie ma SolutionSet. Poprzednie testy integralności
przypięcia datasetu pozostają osobnym dowodem. Końcowe cztery testy po uzupełnieniu ostrzeżeń refresh przeszły, exit 0.
Niezależny review minimalnego diffu: brak Required; uwagę o refreshError
uwzględniono w źródłach i regresji.

Browser/WebGL i wizualny odbiór poprawki pozostają NOT VERIFIED;
nie ponawiano zablokowanego dostępu. Nie deklarujemy pełnego Universe,
kwalifikowanej bazy, FFT, LLG ani odtworzenia publikacji.


Końcowe kontrole źródeł tej poprawki:
- istniejący zarządzany just docker-dev-control-checks z zakresem
  frontend-visualization: succeeded, 19 poleceń exit 0, w tym typecheck,
  wskazane 15 kontroli ESLint, architecture i api-hygiene. Receipt
  verification/frontend-visualization-checks/receipt.json,
  SHA256 b485705378ccb208d4867029d893b860ee5fd4e42b64c5efe3ac9c47b8d9dac0.
  Kontrola ESLint useViewport3DSceneModel trwała 150263 ms, ale zakończyła się 0;
  nie potraktowano dłuższej obserwacji jako awarii ani nie przerwano procesu.
- po końcowej zmianie refreshError: w stałym frontendzie 0dacc07deb1e, pod istniejącą
  blokadą .fullmag-frontend-import-checks.lock, pnpm exec vitest run wskazanych
  SavedResultsBrowser.execution/integrity: 4 testy pass; pnpm run typecheck:
  exit 0; pnpm exec eslint obu zmienionych plików --max-warnings=0: exit 0.
  Obserwacja poleceń i pełne wyjścia:
  verification/saved-results-execution-20261027/focused-checks.json.
  To kontrole źródeł JS/TS, nie native build ani dowód wizualny.
- source-view.json w tym samym katalogu potwierdza zgodność plików worktree
  i rzeczywiście testowanego cienia frontendu.
  SavedResultsBrowser.tsx SHA256
  995ba6f699eed343703b9b78ed1857f76f9104b8243e5460cd0c178376b05ba0;
  SavedResultsBrowser.execution.test.tsx SHA256
  f22150464e51ee191a73967c0543d26858a944b309eafa61ac5355ca808c6c56.

Nie zmieniono schematu API, wygenerowanych typów, native operatora ani źródeł
pracującego solvera. Nie restartowano backendu. Nowa stopka nie udaje obserwacji
innego runa: stan nowej próby należy czytać po jej jawnym wyborze w Saved Results.
Nie wykonywano nowych kompilacji testów Rust ani ponownego Solve diagnostyki.


### Zgodność Saved V/J/H i przygotowanie naprawy Auto — 27.10.2026

Poprzednia kontynuacja jest postępem: zapisano poprawkę Saved Results
c8774e112f2dd746c88110dcf537c243a209d858. W tej kontynuacji ponownie sprawdzono
żywy worker 9549 i API pełnego runa; stan running, bez opublikowanych artefaktów.
Nie rozpoczęto drugiego Solve ani buildu/restartu.

Istniejący scripts/smoke_saved_antenna_fields.py::verify wykonano na rzeczywistym
SolutionSet 20 punktów, rewizja 2. PASS: metadane, FMDS, geometria FMMT, maski FMSP,
hashe, jednostki, producer i przypięcie do SolutionSet/member/manifest/tensor.
Sprawdzono też odmowę obcego geometry_object_ref.
Zapis: verification/rt0-geometry-cases-20261027/saved-vjh-http-gate.json.
Osobne accepted-to-saved-value-comparison.json porównuje z wcześniej odczytanym
pakietem accepted; wszystkie wartości są bitowo identyczne:

| Quantity dla UI | Payload zaakceptowanego wyniku | Próbki × składowe | SI |
|---|---|---:|---|
| V_electric | v_raw | 677 × 1 | V |
| J_charge | j_local_raw | 7424 × 3 | A/m² |
| H_ant | h_raw | 20 × 3 | A/m |

J pozostaje lokalne w czterech węzłach każdego Tet4, nie jest wygładzane do
wspólnego nodalnego J. Zgodność ta nie kwalifikuje fizyki ani renderera.
browser_qualified=false, physics_qualified=false, cold_reopen_qualified=false:
nie wykonano restartu/reopen, bo pełna próba nadal pracuje.

Rzeczywisty zasób /simulation/stages/execution istnieje i ma zgodne session,
epoch, request_scope_epoch oraz run_id ze statusem starej sesji. Publikuje failed
z powodem surface RT0 wall-time exhausted, a nie postęp nowego accepted runa.
Kod FooterTelemetry.tsx w worktree i cieniu frontendu jest zgodny
(SHA256 3d4b87cd1d40434eff82c408850fa03aa92d0c6f3dfbde9ace7e61b96dfa5596).
Nie potwierdzono przez przeglądarkę, co faktycznie wyrenderował klient użytkownika.

Audyt nierozwiązanego Auto/null:
Python RuntimeSelection.to_runtime_metadata autoruje cpu_threads:null;
antenna_coincident_materialization::materialize_antenna_coincident_loops
włącza runtime_selection do przygotowanego preimage.
Publiczny CLI binduje już przygotowaną geometrię przez
script_pipeline_acceptance::compile_accepted_closed_loop_pipeline.
execution_profile_binding::bind_materialized_execution usuwał null mimo
niezmienionego typowanego Auto. Walidator planera prawidłowo odrzucał zmieniony
digest. compute_resources::ComputeResourcesIR::validate_legacy_selection
już dopuszcza null; nie jest potrzebna zmiana preimage ani walidatora.

Nowy wariant w rt0_profile_180s/fem_antenna_rt0_auto_180s.py i
auto-input-manifest.json zachowuje fizyczny AST, wszystkie trzy assety
i politykę bazowego scenariusza czterech punktów. Usuwa tylko jawne CPU1
i zachowuje domyślne Auto. Składnia Python, AST i hashe: PASS.
SHA256 skryptu 1ee2b0001e1506e670f4d155e886c9942b9d23a149d29132999e7cac43191153.

Rzeczywisty RED na aktualnym pakiecie:
fullmag-bin run-script-accepted z tym skryptem, dotychczasowym base.fms,
profile.json, resources.json, idempotency-key rt0-auto-four-preparation-20261027-01
oraz --prepare-only: exit 1 po 40.639554970 s. Błąd:
prepared source authored input digest does not bind actual geometry, closure,
carrier, materials and intent. Stdout pusty; brak Submit/Solve.
Pakiet 0.1.0-dev.20261027.g891918ab18fb.dirty.sbaef683051ad+9796.
Dowody: verification/antenna-auto-identity-20261027/before-receipt.json,
before-stderr.log i source-input-check.json.

Poprawka źródeł w crates/fullmag-application/src/execution_profile_binding.rs:
Auto zachowuje istniejące null i brak klucza; nadal usuwa kolidującą nienullową
wartość legacy. Jawna liczba wątków działa jak dotychczas. To zachowuje replay
starszych zaakceptowanych katalogów z pominiętym kluczem.
Nowa regresja w tests/execution_profile_binding.rs porównuje cały ProblemIR
i powtórny bind obu wariantów. Istniejące testy tego pliku już obejmują
liczbę4, usuwanie legacy8 przy Auto oraz odrzucenie zmodyfikowanego requestu;
nie dodano ich duplikatów. Test API script.rs oczekuje teraz zachowanego null,
lecz nadal odrzuca rzeczywistą zmianę device:auto→cpu po przygotowaniu geometrii.
Niezależny review implementacji: brak Required.

Status: SOURCE ONLY; GREEN publicznego prepare-only nadal NOT VERIFIED.
Nie kompilowano ani nie uruchamiano testów Rust. Zarządzany build i GREEN
przygotowania muszą nastąpić po terminalu pełnego workera, nigdy przez przerwanie
jego obliczeń. Zmiana prawdziwego profilu po materializacji nadal wymaga
bind-before-geometry jak w istniejącym flow UI; ta poprawka nie obiecuje jej obsługi
w CLI i nie pomija walidatora. Pełny cel E0–E12 pozostaje nieukończony.

### Archiwalny przewodnik przy zapisanym H — 27.10.2026

Kontynuacja jest postępem implementacyjnym oraz zweryfikowanym oczekiwaniem na
konkretny żywy worker. Pełny run 5654db21… nadal ma lifecycle running; potwierdzono
PID 9549 i niezmieniony starttime, rosnący CPU oraz brak opublikowanego katalogu.
Nie restartowano backendu, nie anulowano próby i nie wykonano kolejnego Solve.

Audyt wykazał brak kontekstu przewodnika w trybie Saved H: dotychczasowy adapter
tworzy tylko zapisany sampling carrier, a zasoby live są prawidłowo wyłączone.
Nowa poprawka używa istniejącego pinned SolutionSet/member oraz istniejących
materializedDataset, savedFieldGeometry i savedFieldTopology w typowanym kliencie.
Nie tworzy endpointu, pina, drugiego view­portu ani zastępczego modelu fizycznego.

Mapa źródeł:
- kernel/resources/savedAntennaSourceContextResources.ts::
  resolveSavedAntennaSourceDataset i loadSavedAntennaSourceContext wiążą H_ant
  z dokładnie jednym V_electric sibling; hook useSavedAntennaSourceContextResources
  odcina stary kontekst synchronicznie po zmianie wyboru.
- modules/viewport-3d/model/savedAntennaSourceModel.ts::
  buildSavedAntennaSourceModel buduje wyłącznie powierzchnię źródłową bez pola.
- modules/viewport-3d/layers/SavedAntennaSourceLayer.tsx::
  SavedAntennaSourceLayer renderuje złoty materiał z dotychczasową subtelną fakturą
  i jawnie zwalnia geometrię, materiał oraz obie tekstury.
- hooks/useViewport3DSceneModel.ts oraz layers/Viewport3DScene.tsx dołączają
  oddzielną warstwę i uwzględniają jej bounds w dopasowaniu kamery.

Powiązanie wymaga zgodności project/run/SolutionSet, containing i owner revision,
member, run_spec_digest, item_id pakietu i producenta closed-loop-inspection v2.
Brak lub duplikat zgodnego V daje jawny brak kontekstu, bez live fallbacku.
Discovery jest ograniczone do dziesięciu stron po 100 metadanych, a geometria
przechodzi dotychczasowe ograniczenia, kontrolę manifestu/hashu i dekodowanie.
Nie pobiera się wartości V ani nie przypisuje H do węzłów przewodnika.
H zachowuje własną siatkę, maskę wsparcia, wartości i jednostki A/m.

Rzeczywisty nowy loader wykonano w stałym frontendzie przez ControlRoomApi
na istniejącym wyniku diagnostyki 20 punktów. PASS: siedem GET HTTP 200,
H pozostaje 20 próbek; archived source ma 677 węzłów, 1856 Tet4 i 1322 trójkąty
powierzchniowe, ten sam bundle. Brak odczytu slice V, live API i mutacji.
To rzeczywista weryfikacja danych/integracji klienta, nie dowód obrazu WebGL.

Kontrole:
- 24/24 focused Vitest: identity i unikalność, paginacja/manifest drift,
  stare zaznaczenie, brak wartości/live fallbacku, geometra SI, lifecycle zasobów
  oraz istniejąca walidacja pól Saved.
- pnpm run typecheck: exit 0; ESLint siedmiu zmienionych plików: exit 0,
  --max-warnings=0; architecture hygiene: exit 0.
- check-saved-field-presentation.mjs: PASS przy wymaganym
  node --experimental-vm-modules. Pierwsza próba bez flagi nie mogła utworzyć
  vm.SourceTextModule; nie zmieniono kontrolera ani aplikacji w celu jej obejścia.
- istniejące regresje sceny/modelu: pierwotnie 216 pass / 4 fail. Cztery błędy
  są dawnymi asercjami tekstowymi Airbox, niezgodnymi również z blokiem w HEAD
  47557600a400a8f038987c1f7d1b5937b58dee41. Sprawdzały historyczną bramkę FEM,
  choć wspólny target już stosuje renderingState dla obu ścieżek FDM/FEM.
  Uaktualniono sześć asercji do istniejącego kontraktu, dodając kontrolę braku
  dawnej bramki. Bez zmiany runtime: 166/166 testów modelu pass;
  54/54 testów sceny pozostało pass. Łącznie 244 testy wskazanych plików pass.
- Niezależny review nowego delta: brak Required dla identity, integracji i lifecycle.
  Zgodność źródeł worktree z cieniem frontendu potwierdzona hashami.
  Obcy ArtifactInspectionSource.tsx i jego staged blob pozostają bez zmian.

Dowody w wolumenie kontrolnym:
verification/saved-antenna-source-context-20261027/:
before-source.json, actual-typed-api.json, focused-tests.json, typecheck.json,
lint.json, architecture-hygiene.json, saved-presentation-contract.json,
existing-viewport-tests.json, preexisting-airbox-test-drift.json,
scene-model-tests-final.json, scene-model-test-lint.json i source-view.json.
Pełne logi nieudanych prób zachowano; status zbiorczy dotyczy końcowych kontroli.

Status: implementacja i kontrole źródeł/klienta API zweryfikowane w opisanym zakresie.
Browser/WebGL, obraz pełnego Universe i cold reopen nadal NOT VERIFIED.
Nie ponawiano zablokowanego dostępu do przeglądarki. Baza per A, LLG, FFT,
kwalifikacja naukowa i odtworzenie publikacji nie wynikają z tej poprawki.
