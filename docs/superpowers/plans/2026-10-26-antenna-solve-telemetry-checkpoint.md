# Stopka stacjonarnego obliczenia anteny — 26.10.2026

Status: poprawka źródeł interfejsu, nie zakończenie obliczenia ani odbiór pola.

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
