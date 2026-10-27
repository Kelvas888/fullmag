# Antena i Universe: integracja mastera oraz PR #247 — 27.10.2026

Status: master zintegrowany; build, kontrakty i odczyt Saved sprawdzone. Odbiór PR, CI oraz rzeczywisty browser/WebGL pozostają osobnymi bramkami.
To checkpoint przyrostu implementacji, nie zamknięcie E0–E12.

## Zakres i baza

Istniejący worktree `/home/kking/git/fullmag/worktrees/antenna-transport-e2e-20261011`,
branch `codex/antenna-transport-e2e-20261011`,
[PR #247](https://github.com/MateuszZelent/fullmag/pull/247) do `master`.
Pobrany i zintegrowany `origin/master`:
`38ffb49bf4f8dabfdf2b4921903c88183bb9f84e`.
Commit integracji: `a11a5cba11035d2d54abca649782d10fcebb1b7d`.
Zachowano lokalne zmiany anteny oraz oryginalny artefakt FMS poza indeksem.
Pełne kopie źródeł, indeksu i diffów pozostają w control volume, w
`verification/master-pr-integration-20261027/`; zachowany stash:
`02f01f18537ce9b06e461ab548c90655e06e9b8b`.

## Zachowanie aplikacji

- `schemas/runtime.rs::StageExecutionRecordResource` udostępnia opcjonalne
  `antenna_inspection`: `retained`, `absent` albo `unknown` z reason code.
  `antenna_inspection.rs::inspection_discovery_metadata` sprawdza rejestr lub
  istniejący rekord; nie kwalifikuje payloadów numerycznych. Handler
  `simulation/runtime.rs::get_stage_execution` zachowuje fence sesji i rewizji.
- `artifactInspectionAvailability.ts::artifactInspectionAvailability` wymaga
  zgodnych session/epoch/request scope/run/runtime stage/authored stage.
  Inspector oraz `useArtifactFieldOverlay` odczytują katalog pól dopiero dla
  potwierdzonego właściciela `retained`. Brak wyniku nie staje się pustym
  katalogiem ani fallbackiem do pola innej sesji.
- `ArtifactInspectionSource.tsx` pokazuje stan wykonania i dostępność wyniku
  osobno. `LayoutController.ts::openSavedResults` atomowo otwiera Results → Saved.
  `ResultsNavigatorModule.tsx` korzysta z tego samego stanu layoutu, także przed
  pierwszym zamontowaniem panelu. Zmiana wyboru nie uruchamia Solve.
- Nośniki V/J przewodnika i H otoczenia pozostają osobne. Wybór Universe nie
  zmienia zapisanej domeny wyniku na Global. Zapisany H używa własnej topologii,
  a zgodna jawna publikacja live zachowuje pierwszeństwo.
- Integracja zachowuje masterowe poprawki Inspectorów, ograniczone cache,
  metadane przygotowania i read-only retry dowodów. Naprawiono brakujący import
  `quantityCatalogEntrySupportsAirbox`; zaktualizowano regresje komponentów.

## Build i kontrakt wygenerowany

Jedyna grupa DEV:
`fullmag-worktree-antenna-transport-e2e-20261011-5d5deadcd16e0fb1`, port 3203.
Build odbył się w tym samym backendzie `cc32cb682ae5`, z zachowaniem frontendu
`0dacc07deb1e`, obrazu, mountów i cache. Nie użyto hostowego Cargo/CMake ani
oddzielnego kontenera budującego.

Recepta z wybranego worktree:
`FULLMAG_SCRIPT_OUTPUT_DIRECTORY=examples just docker-dev-restart-idle 37062974a42f4ad4aec3976df9dfafe6 66401b85878924fb0ca043cad95c27b219264e52e78461de7535f014d947ca9c <worktree> 3203 true`.
Zmienna procesu zachowuje wcześniejszą zgodę na zapis wyników w `examples`;
nie zmieniono wspólnego `.env`.

Attempt `94ca9bf8ff37455a939d416150c3b10a`: succeeded, exit 0.
Źródło: commit integracji + WIP, snapshot
`cc9916130a4b98f0b3c35915de4a9ef930dcfc7090c9264e9aa04d509e61e649`.
Wersja `0.1.0-dev.20261027.ga11a5cba1103.dirty.scc9916130a4b+9796`.
Make 1479984 ms; bramki `linux-native-v1` i `worker-cgroup` PASS, API gotowe.
Receipty: `iteration/attempts/94ca9bf8ff37455a939d416150c3b10a/` w control volume.

Następnie `just docker-dev-codegen <worktree>` zakończył się succeeded.
Kanoniczny receipt:
`backend/codegen/openapi-v2/dc38a50cfd8760689f7bf4ebe01313ee9d58db3ecad7b2f5a3af1b6af2d64b3e.json`.
OpenAPI SHA256: `f2469c172e1d009a3b12b32bf6faa40d1ca5594b01a98424c7b14ac785f265d5`.
Zmiany wygenerowanych typów TS i Python odpowiadają wyłącznie discovery.
Późniejszy import frontendu i korekty jego testów działają przez HMR; nie
przypisujemy im źródłowego snapshotu wcześniejszej kompilacji backendu.

## Zachowanie danych i rzeczywisty odczyt

Po buildzie GET `/v2/sessions/current/simulation/stages/execution` zwrócił 200.
Ta sama próba `run-live-62d110763485b10e2512922267a1aed284996710852d4fd27cb3f4ad71a1e496`
pozostała Failed, a jej etap `script-execution-2df97d99b6b88a3c58d0b135696e390a819e720b84d6311f4f6d0a62a8969bec`
ma `antenna_inspection={state:absent, reason_code:no_retained_inspection}`.
Nie podstawiono pod nią starszego zapisanego wyniku.

Porównanie before/after potwierdziło identyczne scene oraz logiczną sesję,
wszystkie 1391 plików pełnego zapisanego runu, 43 katalogi runów i oba pliki
odzyskanego rozwiązania. Zero dodanych, usuniętych lub zmienionych plików;
zero aktywnych zadań. Dowód:
`verification/inspection-availability-20261027/runtime-preservation-review.json`,
SHA256 `f83740001b3647842bb9b6c97a20ca14bda5989ab39c3345cd4dc903de1cdb39`.

## Weryfikacja frontendu po integracji

Na rzeczywistych źródłach po codegen i poprawce importu przeszło 330/330
wybranych testów Vitest w 23 plikach. Trzy interpretowane kontrole:
Universe Inspector 27/27, selekcja pola 68/68, powierzchnia 39/39.
Pełny typecheck, lint 27 plików i kontrola architektury PASS (exit 0).
`summary.json` SHA256: `483ba0452159e345c65d8801746a180e481cc1268cc0b6d89d0104ab3936307a`.
Dokładne polecenia i logi pozostają w wolumenie
frontendu: `verification/final-antenna-frontend-20261027/commands.json`.

Odczytowy harness rzeczywistych komponentów i API:
`node /state/development/verification/final-antenna-frontend-20261027/verify.mjs --expect-absent --saved-flow`.
Wynik: `retained_absence_gate=passed`, `saved_flow=passed`, 16 GET / wszystkie
200, zero błędów, zero mutacji API, zero dodatkowych requestów i renderów
w oknie idle. Przejście Airbox → Browse saved results → Saved → run5654 →
odzyskane rozwiązanie rev1 → H_ant → Inspect ustawiło zapisany H w prezentacji
Airbox. Wiersz przed Inspect pokazał H, A/m i 1145×3. Nie wysłano błędnego
katalogu stage dla bieżącej próby Failed; nie uruchomiono kolejnego Solve.
Dowód: `verification/final-antenna-frontend-20261027/report.json`.
SHA256 raportu: `b39f646d86ef2e8ced703fa406858ab93619d8fe1a40bb1e07254398c9a2d34f`.
To test TestDom + prawdziwy HTTP, bez kwalifikacji rzeczywistej przeglądarki.
Trzech nowych regresji Rust discovery nie kompilowano lokalnie; dodano ich
wykonanie do istniejącego workflow bootstrap CI. Wynik CI wymaga osobnej
oceny dla HEAD wypchniętego PR.

## Granice odbioru i retencja

Odzyskany wynik `run-5654db21201dd6c660f7ecae78baf8588477fe2a7d90480d9d64b30e4d050080`
ma surowe V/J/H; H zawiera 1145 wektorów A/m na siatce 6428 Tet4.
Lifecycle tego runu nadal Failed; odzyskanie danych nie czyni wykonania
Succeeded ani bazy pola zakwalifikowanej do LLG. Wcześniejsza kontrola
zamrożonych wejść i wspólnych próbek H wykazała zgodność bajtową; nie jest
niezależnym dowodem poprawności fizyki, zbieżności ani odtworzenia publikacji.

Przeglądarka/WebGL nadal NOT VERIFIED: automatyczna kontrola URL zablokowała
odczyt starej karty będącej stroną błędu z niedozwolonym protokołem. Nie
obchodzono tej odmowy inną kartą, powierzchnią przeglądarki lub CDP.
TestDom i HTTP nie zastępują screenshotu, kontroli canvas ani WebGL.
Przekrój poprzeczny w UI, kwalifikowana baza → DC Relax/AC Run,
spin-wave response oraz pełne porównanie BORIS pozostają otwarte.

Retencja zarządzanego buildu: deferred (`outside-startup`). Zachowano bieżący
pakiet, rollback, aktywny cache, wyniki, logi i receipty. Nie usuwano kontenerów,
wolumenów ani danych użytkownika. Po buildzie dostępne logicznie w Dockerze
321285468160 B; nie jest to gwarantowana niezależna pula od hosta.
Skill `fullmag-build-stage-cleanup` nie jest dostępny; zastosowano reguły
retencji governance. Ponowna ocena dopiero po wykazaniu zbędności i referencji
rollback. Worktree i grupa pozostają do dalszej pracy oraz review PR.


## Pierwszy CI i korekty kontraktów po integracji

Dla HEAD `d4255dad0034ea785316ccfe4191f781948b6510` zakończyły się 32 kontrole:
14 success, 8 failure i 10 skipped. Nie uznano początkowych lokalnych 330
przypadków za dowód przejścia całego CI. Przejrzano pełne logi nieudanych jobów.
Wszystkie poniższe poprawki dotyczą testów, fixture, audytu i selektora smoke;
produkcja solvera, API, bramki providera, tolerancje i runtime pozostają bez zmian.

| Rodzina nieudanych kontroli | Potwierdzona przyczyna i poprawka | Weryfikacja lokalna |
|---|---|---|
| source-contracts | Test klasyfikacji tworzył komunikat przez `invalid`, który dodaje prefiks, a oczekiwał dosłownego tekstu bez prefiksu. Fixture używa jawnego `RunError`; dokładne asercje i obsługa nieznanych statusów zachowane. | Parser Rust PASS; wykonanie Rust oczekuje na CI. Pierwszy CI miał 1820 PASS i tę jedną awarię. |
| rust-contracts, checkpoint-windows-contracts | Jeden test `quantities.rs` podawał `Value` zamiast nowego `SharedJson`. Dodano `.into()` wyłącznie w fixture. | Parser Rust i diff PASS; testów Rust lokalnie nie kompilowano. |
| terminal-artifact-attestation Ubuntu, python-contracts | Trzy stare konteksty testowe nie implementowały terminal-observation preflight i nowego context managera. Uzupełniono mocki i dokładne asercje wywołań. | 296 przypadków Python: 293 PASS, 3 oczekiwane skips; przed poprawką odtworzono dwie awarie. |
| modal-observables, control-room-contracts | Fixture nie uwzględniały jawnego admission podglądu, jednego właściciela statusu stopki, atomowej kolejki kolory+macierze oraz rozstrzygniętego providera i projekcji tensora. Zachowano odmowy, dodano sześć negatywnych regresji. | Rodziny skupione 37 + 109 + 96 PASS; pełny typecheck, lint 12 zmienionych plików i architecture PASS. |
| browser-fixture-smoke | Kontrola geometrii szukała starego natywnego selecta zamiast wspólnego comboboxa z aktualną etykietą. | Parser i odczytowy SSR/AST kontrakt selektora PASS; rzeczywisty smoke przeglądarkowy oczekuje na nowy CI. |

Jeden pełny przebieg Vitest na zamrożonych źródłach zakończył się: 873/874
pliki oraz 9127/9128 testów PASS, exit 1, 438,88 s. Jedyny błąd tego przebiegu
nie dotyczył kodu produktu: cross-app test próbował otworzyć
`apps/web/dev-server.mjs` w cieniu zawierającym tylko Control Room.
Istniejący test obsługuje `FULLMAG_TEST_SOURCE_ROOT`; przy jawnym pinie do
readonly `/opt/fullmag/source` cała ta rodzina przeszła 12/12 (exit 0).
Nie zmieniono testu ani launchera, nie wyłączono przypadku i nie powtarzano
873 niezmienionych zielonych plików. Osobno finalny SHA fixture jednostki
`A/m^2` sprawdzono w 56/56 przypadkach capabilities. Nie przedstawiamy tych
przebiegów jako jednego pełnego wykonania z exit 0.

Dokładne logi/komendy/SHA są w wolumenie frontendu pod
`verification/pr247-ci-20261027/`: `full-frontend-tests.log`,
`post-full-focused.json`, `root-final-checks/summary.json`,
`provider-tensor-planar-review.json` oraz `selector-contract.json`.
Pełne logi i raporty backendu są w control volume pod tą samą ścieżką:
`terminal-artifact-fixture-review.json` SHA256
`22b3aba3c525a3f43435d4754ed4b8d6adb75be4e8eef89c6d534dde59f08f50`,
`rust-checkpoint-fixture-review.json` SHA256
`8acae5052788d5a93c03eb62c3abc6f8ced788a0cbc3fbcd366fdfbedf833819`.

Następna bramka: nowy push i ponowny CI dla jego dokładnego HEAD. Nie zmieniono
wyników ani nie uruchomiono Solve lub nowego buildu produkcji wyłącznie dla
fixture. Odbiór rzeczywistego Saved viewportu i pełny E0–E12 pozostają otwarte.

Niezależnie ponownie przejrzano przyszły przekrój Saved. Plan oraz przegląd
ponownego użycia istniejącego FMVP z obowiązkową maską są w control volume
`verification/antenna-saved-planar-design-current-20261027/`. To wyłącznie
projekt: brak próbki musi pozostać brakiem, norma następuje po interpolacji
wektora, cztery piny właściciela i maska muszą być spójne przed prezentacją.
Nie wdrożono w tym przyroście nowego endpointu, codec ani przekroju UI.


## Drugi CI i kolejne korekty fixture

Dla wypchniętego HEAD `c76eaf2e0bf782c8e5b0c0807be7e38e77e275f0`
potwierdzono w pełnych logach CI: source-contracts 1821 PASS, 0 FAIL,
1 ignored; Control Room 873 pliki PASS, 1 skipped, 9117 testów PASS,
13 skipped oraz osobne 3 microbench PASS. Przeszły także generated API,
browser-fixture-smoke i inspector-actions-browser-smoke. To dowody CI dla
wskazanego commita, a nie kwalifikacja rzeczywistego Saved viewportu.
Ostatni dostępny odczyt całego zestawu: 19 success, 2 failure,
10 skipped, 1 in progress; nie przedstawiamy go jako wyniku końcowego.

Pozostałe zakończone błędy dotyczyły fixture Python i testu start-policy Rust.
W tej korekcie nie zmieniono produkcyjnego runtime, parserów, bramki Compute,
solverów ani tolerancji:

- testy retained recreation uwzględniają opcjonalny odczyt rejestru cancelled
  activation i sprawdzają dokładne wywołanie;
- frontend resume odtwarza aktualny przypadek OOM, zachowuje backend/package/
  process/incarnation fences, odrzuca non-OOM i sprawdza brak buildu oraz
  zmiany generacji; prawdziwy helper resume pozostaje wykonywany;
- test shell uznaje zwykłe `--stop-only`, które już generuje justfile;
  niekompletne piny i shell injection pozostają odrzucane;
- test źródła siatki odrzuca nie-NPZ, zgodnie z istniejącym owner-bound API,
  zamiast twierdzić, że wszystkie importy siatki są niedostępne;
- test inspekcji akceptuje oba kanoniczne tryby `manual`/`automatic`, a jako
  błędne sprawdza null, obcy schemat, nieznany tryb i dodatkowe pole.
  Durable exact Compute release i produkcyjny kod workera są niezmienione.

Lokalne dowody: cztery rodziny Python 64 + 14 + 5 + 15 = 98 PASS,
0 FAIL, 0 SKIP; pojedynczy test nie-NPZ 1 PASS. Parser Python i parser Rust
(rustfmt emit stdout) PASS. Testów Rust nie kompilowano i nie uruchamiano
lokalnie. Niezależny przegląd polityki startu: 0 Required/Blocker.
Dowody w control volume pod `verification/pr247-ci-c76e-20261027/`:
`frozen-four-fixtures-final-review.json` SHA256
`c36b9021a8693db9945d0fbd1c815878eade0447ea2dbc0492642efbec6f373e`,
`start-policy-review.json`, `start-policy-source-check.json`,
`non-npz-source-focused.json` oraz pełne logi.

Szerszy lokalny przegląd Python ujawnił ograniczenia środowiska (brak montażu
wspólnej `.git`, różnice UID/cache oraz timeouty cięższych fixture).
Nie zmieniono produkcji ani nie podmieniono metadanych Git w celu ich ukrycia.
Pełny nowy CI jest nadal wymagany. Windows gh zwrócił HTTP 401; ważności
logowania nie zakładamy. Odczyt `git ls-remote` potwierdził branch PR na c76e
oraz nowszy master `cc91b2550767e73f3b059ff94fdff466a77e46ef`.
Wyniki, FMS, cache, grupa 3203 i pełny zakres E0–E12 pozostają zachowane.


## Zapis fragmentu i druga aktualizacja mastera

Poprawki powyższych fixture zapisano w
`bb0afabe56c4d451b4ed666899bf3dff72c5a07a`.
Master `cc91b2550767e73f3b059ff94fdff466a77e46ef` scalono bez konfliktów
w `226ec9f7e5afd50d18b7c65cb73b251f4a61cfa8` i wypchnięto do gałęzi PR.
Systemowy odczyt GitHub CLI potwierdził ważne logowanie keyring; wcześniejszy
HTTP 401 wystąpił w ograniczonym środowisku polecenia i nie dowodził wygaśnięcia
systemowego logowania. Nie było potrzeby resetowania danych uwierzytelnienia.

Podczas tej operacji master przesunął się do
`0e5d179d42e70d7f94662f1e8f40ceb93f140f7a` (m.in. prepared FEM observations,
compute-fields evaluation, dokumentacja lokalna i shared build storage).
Integracja wymagała pięciu rozstrzygnięć konfliktów: zachowanie obu recept
justfile, obu akcji CLI, sumy list testów z zachowaniem scope/oracle,
spójnych subpath mountów cache oraz regresji Next config z obu gałęzi.
Wąska regresja launchera: 56/56 PASS, parser justfile i Python PASS;
Next config 21/21 PASS i ESLint PASS. Logi w control volume:
`verification/pr247-master0e5d-20261027/`, frontend:
`verification/master-merge-0e5d179d-20261027/`.
Zintegrowane źródła nie oznaczają uruchomienia nowej polityki cache ani nowego
pakietu runtime. Nie wykonano cleanup, migracji storage, restartu ani Solve.
Testy i przegląd nie zastępują wymaganego nowego CI oraz buildu runtime.

Test cache po scaleniu: 21/21 PASS oraz macierz subpath 10/10 PASS;
wszystkie regresje obu rodziców zachowane. Niezależny przegląd launchera:
0 Required/Blocker, 68 modułów stanowi sumę obu list. Raporty:
`verification/pr247-master0e5d-20261027/backend-cache-conflict-review.json`
(SHA256 `11c2d37913430efaa96927e937dcf7b9d45aa787e312aa7647aa3060f7fb8e10`)
oraz `verification/master-merge-0e5d179d-20261027/launcher-merge-review.json`.


## CI po integracji 62f222 oraz próba runtime

HEAD `62f222f732bd6c44056673ad0320ff8ab9134c2e` jest wypchnięty i PR #247
ma stan MERGEABLE. Ostatni odczyt CI: 20 success, 1 failure, 10 skipped,
1 in progress. Poprawione rodziny Rust i Python przeszły. Jedyny zakończony
błąd source-contracts to losowy fixture
`mixed_domain_plan_digest_survives_permuted_full_request_roundtrip`:
MeshIR serializuje mapę jakości w kolejności BTreeMap, a test szukał fragmentu
HashMap o losowej kolejności. Awaria następowała przed kontrolą digestu.
Korekta porządkuje tylko mapę wzorca testowego; oba kierunki permutacji,
zgodność planu/digestu i odmowa zmienionego wejścia pozostają. Parser rustfmt
i diff check PASS; testów Rust lokalnie nie kompilowano ani nie uruchamiano.
Pełny log: `verification/pr247-ci-62f222-20261027/source-contracts-122368971209.log`
w control volume. SHA256 poprawionego pliku:
`bbf5115d3b675d24a1f9f526b822ee24fe9eed12ff03d231db905bbb0c660f79`.

Zarządzany restart własnej grupy nie uruchomił buildu: po poprawnym drainie
Docker odmówił nowego PID 1 z NVIDIA prestart `ldconfig terminated with signal 9`.
Attempt `c037af6df84448b1ba6576157b822914`, wynik
`outcome-unknown-resources-retained`. Backend jest stopped/PID 0/exit128,
frontend stopped/exit0; kontenery, pakiet, cache i wyniki zachowane.
Dowód `backend-drain.json`: state drained, process receipt SHA256
`34949a31456d06d5b5238b74b777ebd4bc0522e597367a0f792bf5989f9d5f38`.
Stan przed próbą: 1391 plików wynikowych, 43 katalogi runów, 2 pliki
odzyskanego rozwiązania, zero aktywnych zadań. Snapshot i checker:
`verification/master-runtime-62f222-20261027/`.

Nie zastosowano ręcznego startu ani zastępczego checkpointu. Niezależny audyt
wykazał, że dotychczasowy prestart recovery wymaga saved-authoring checkpoint;
ta próba prawidłowo użyła terminal-session-preflight i drain. Dla niej brakuje
obsługi tego wariantu dowodów. Potrzebne są osobny proof, exact config/container/
history CAS, kontrola braku nowej publikacji, preview i przypięta kontynuacja.
Nie przedstawiamy nieudanego restartu jako buildu ani działającego API.
