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
