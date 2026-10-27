# Odzyskanie terminalnej sesji po błędzie NVIDIA przed PID 1

Status: projekt kontraktu i plan wykonania; kod oraz rzeczywisty preview nie są
jeszcze dowodem wdrożenia. Dotyczy własnej grupy anteny na porcie 3203.
Nie zmienia modelu fizycznego ani wyniku obliczenia.

## Potwierdzony przypadek

- Gałąź `codex/antenna-transport-e2e-20261011`, poprawka CI
  `7ae277614211434ad850702e85e9c4d9df2b2ccb`.
- Zachowany start `37062974a42f4ad4aec3976df9dfafe6`, Compose SHA256
  `66401b85878924fb0ca043cad95c27b219264e52e78461de7535f014d947ca9c`.
- Nieudana iteracja `c037af6df84448b1ba6576157b822914`, stan
  `outcome-unknown-resources-retained`.
- Backend `cc32cb682ae597e3f6c5e52c5e4372fbfa85a8ec1219bf830e3391b94a43bd1b`
  stopped, PID 0, exit128, bez nowego StartedAt. Frontend
  `0dacc07deb1e3f8e8d0cc7f029fbba00c32532884f80a2083d2c079a9c0edd45`
  stopped, exit0. Przed błędem zapisano autentykowany native drain.
- OCI prestart NVIDIA odmówił wejścia do nowego PID 1: `ldconfig` zakończony
  sygnałem9. Make i nowy Fullmag nie wystartowały.
- Bieżący run62d jest Failed; dwa inne zaakceptowane runy 36bd i6a1 są nadal
  wstrzymane. Nie wolno ich zwolnić ani automatycznie wykonać.

Źródłowy audyt potwierdził lukę: `docker_volume_prestart_recovery.py`
waliduje wyłącznie saved-authoring checkpoint. Restart terminalnej sesji
zapisuje zamiast niego `terminal-session-preflight.json` i `backend-drain.json`.
Tworzenie checkpointu authoring wstecznie nie jest poprawnym recovery.

## Minimalny zakres poprawki

Dodać odrębny request
`fullmag.docker-terminal-prestart-reconciliation.v1`. Zachować dotychczasowy
saved-authoring v1 i jego wszystkie odmowy. Nowy wariant obejmuje terminalny
current run oraz zachowane held runs; nie rozszerzać go na dowolny aktywny
lub niejednoznaczny run ani przygotowaną bieżącą sesję bez osobnego dowodu.

Request przypina oryginalny receipt, kontroler i helper, źródło, konfigurację,
obrazy, ID/fingerprint/StartedAt i pełne stany obu kontenerów, błąd NVIDIA,
preflight i drain oraz rzeczywisty operator baseline. Brak nowego PID 1 i
publikacji musi wynikać z exact Docker/provenance/receipt CAS, nie z samego
braku healthchecku. Zmiana dowolnego pinu oznacza odmowę.

## Dowód bieżącej historii

Wykorzystać istniejący natywny CLI
`runtime service-inspect-terminal-run` dla terminalnego run62d.
Mapa źródeł: `crates/fullmag-cli/src/args.rs` — wariant service inspect;
`crates/fullmag-runtime-control/src/runtime_service_client.rs` — klient;
`crates/fullmag-session/src/runtime_service.rs` —
`RuntimeServiceConfig::inspect_terminal_run_evidence`;
`crates/fullmag-session/src/host_resource_ledger.rs` —
`HostResourceLedger::with_terminal_run_evidence_fence`.
Polecenie bierze blokady host→store, sprawdza katalog, lease, admission i exit
receipts oraz zwraca `mutations_applied:false`, `solve_replayed:false`.

Natywny dowód pojedynczego runu nie zastępuje:

1. aktualnego grupowego no-active/released snapshot;
2. dokładnego zbioru held runs, identycznych raw intent SHA, jawnego manual
   start policy i braku `start_release`;
3. porównania rzeczywistych 43 katalogów, 1391 plików wyniku oraz 2 plików
   odzyskanego rozwiązania z operator baseline sprzed stopu;
4. nowego, jawnego baseline recovery, porównywanego przy preview, apply,
   bezpośrednio przed retry i po nim.

Baseline przed stopem znajduje się w control volume:
`verification/master-runtime-62f222-20261027/state-before.json`.
To rzeczywisty zapis operatora, ale nie natywny snapshot całych journals;
nie rozszerzać jego znaczenia. Nowy snapshot musi mieć jawne granice liczby
plików/bajtów, bez symlinków i niepewnych ścieżek. Zmiany advisory
`WRITER.owner.json` są dopuszczalne wyłącznie po rozpoznaniu dokładnego,
zwolnionego rekordu; pozostałe zmiany historyczne są odmową.

Krótki zarządzany helper należy do tej samej grupy, nie ma sieci, GPU,
`/build`, candidate overlay ani API. Używa dokładnego aktualnego pakietu,
readonly źródeł i poprawnie odwzorowanych mountów runtime-control. Zapisy
ogranicza do istniejących blokad/advisory i dowodów; nie wykonuje Solve,
materializacji, naprawy danych, usuwania ani migracji.

## Zastosowanie i kontynuacja

1. Wykonywalne regresje source/contracts w kanonicznym helperze offline.
   Stare saved-authoring przypadki i odmowy muszą pozostać zielone.
2. Niezależne review: exact piny, brak nowego start grant, poprawne locki,
   niezmieniony status Failed i zachowanie held runs.
3. Rzeczywisty native proof i pełny preview bez zmiany ownera.
4. Failure-only reconcile tylko iteracji c037 przez tego samego ownera;
   zachowanie pierwotnych receiptów, logów, wolumenów i wyników.
5. Jedna przypięta zarządzana kontynuacja pierwotnego startu. Nowy wariant
   nie wywołuje saved-authoring restore ani Solve; utrzymuje lease do
   końcowej kontroli historii i API.
6. Po gotowości porównać wynikowe V/J/H, stan sceny, run62d i dwa held runs.
   Zmiana request-scope po restarcie jest oczekiwana i musi unieważnić stare
   requesty frontendu; nie zmienia to właściciela naukowego wyniku.

Powtórzenie błędu NVIDIA nie uzasadnia pętli startów. Zachować nowy receipt
oraz zasoby i zmienić hipotezę na podstawie diagnostyki. Zmiana sterownika,
restart wspólnego Docker/WSL lub inny profil GPU wymaga odrębnego zakresu
operatorskiego, nie ukrytego fallbacku.

## Kryterium zaliczenia i granice

Kryterium: zaakceptowany proof, preview i failure-only reconcile, jeden
prawidłowy managed restart, działające API oraz odczyt niezmienionych wyników.
Sukces testów nie jest tym dowodem. Wciąż osobno wymagane są kwalifikacja
naukowa, Saved viewport/WebGL i pozostały zakres E0–E12.
