# Odbiór anulowania przez scheduler

Data: 07.10.2026. Wynik: **PASS — komponent API i accepted scheduler**.
To nie kwalifikuje startu `runtime_service` v2 ani pełnego E0–E7.

## Przebieg

Zarządzana recepta `verify-compute-scheduler-cancellation` uruchomiła pakiet
o pełnym manifest SHA-256
`7d87e9c8bdeaf1ad95c9aa8884db6758e4e657f4bb852e90c5995b54a44dd74e`.
W niepowtarzalnym accepted store production CLI utworzył SessionStore,
przypiął konfigurację v2 i zainicjalizował host ledger. Następnie produkcyjne
API przyjęło osobne żądania anulowania dla jednego Accepted i jednego Queued
taska. Oba odpowiedziały 202; przed schedulerem taski pozostały niezmienione
i bez claimu.

Ofertę `native-local.compute.cpu` opublikował rzeczywisty CLI puli zasobów
(generacja 1). Dwa procesy accepted schedulera otworzyły przypięty host config,
odczytały tę pulę i otrzymały jawne drain tokeny przez istniejący
`stdin-v1` owner-control. Każdy zakończył się kodem 0 ze stanem `drained`,
`scheduled_count=0`, pustym `executed`, jednym rozpoznanym zasobem i bez
checkpointu. Każdy wyemitował jedno zdarzenie ready i drained, bez owner tokena.

## Stan potwierdzony po schedulerze

- Run: `run-scheduler-cancellation-fixture`; początkowe metadane są seedowanym
  fixture, nie wynikiem Submit.
- Katalog końcowy ma rewizję 5. Taski `task-scheduler-cancel-accepted` oraz
  `task-scheduler-cancel-queued` są `cancelled`, bez attempt, ownership epoch,
  resource ani coordinator genesis.
- Host ledger ma zero rezerwacji. Katalog checkpointu scheduler pool nie
  powstał; oferta i jej bajty pozostały niezmienione po drugim uruchomieniu.
- Oryginalne żądania API można powtórzyć po zakończeniu: oba zwróciły 200,
  zachowały swój cancellation ID i zwróciły aktualną rewizję 5. GET terminalnego
  runa po replay działa.
- Bramka zakończyła się kodem 0 z **21 kontroli**. Sześć zarejestrowanych
  procesów CLI/API/scheduler zakończyło się i zostało odebranych. API fixture
  verifier zatrzymał po stanie idle; jego kod wyjścia 1 nie jest dowodem
  graceful service drain. Oba schedulery zakończyły się przez jawny drain.

## Źródła i granice dowodu

Build log: `native-build-774c99aba27347cda7e1bbb169cf449e.log`. Build CLI, API
i desktop `backend-dev` zakończył się sukcesem, następnie managed `build_snapshot
verify` zweryfikował zapisany source capsule. Snapshot SHA-256:
`303581c8dd9fca2cd7dc2b4efc3f8ce2a5186875f93f99bc01346498f3006d5d`;
build/version source snapshot:
`4f987a46d5b83ef08d5b378f14aa0b2c7b25e5709f97474a0e5bab793b021a8f`.
Pliki scheduler, host runtime, API schedulera i cancellation handler w snapshot
odpowiadają źródłom użytym przez tę bramkę. Źródłowy test recovery z SessionStore
pozostaje NOT COMPILED/NOT RUN zgodnie z zakazem kompilacji testów Rust.

Receipt i pełne logi znajdują się pod:
`C:/git/fullmag/storage/builds/fullmag-0950f4dca4ffe38f/development-backend-api-checks/checks/37460841eaf544f4908258148e2efe84/`.

Host policy, topology digest oraz run/task catalog były jawnymi danymi
syntetycznego fixture. Owner token, prawdziwy owner lifecycle, fizyczny
NodeSnapshot, Submit, worker, solver ani zasoby sprzętowe nie były częścią
testu. `runtime_service_main` v2 guard pozostał aktywny. Nie wynika z tego
egzekwowanie CPU/GPU, release po pracy solvera, kwalifikacja fizyki,
równoległe sweeps ani distributed solve. Następne etapy E2/E3/E4 i E5–E7
pozostają otwarte.
