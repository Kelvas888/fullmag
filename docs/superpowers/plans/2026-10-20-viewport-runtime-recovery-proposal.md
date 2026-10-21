# Viewport R7 — propozycja odzyskania własnej grupy Docker

Status: do decyzji operatora; brak zgody oznacza brak mutacji recovery. To nie jest dowód wykonania ani ukończenia R7.

## Przypięty zakres

- Checkout `C:\git\fullmag\worktrees\viewport-visual-quality-20261020`, branch `codex/viewport-visual-quality-20261020`, HEAD obserwacji `53971ed8705bfcf4af8084d0ab0b8585286eb33a` plus jawny diff baselines/audytu i checkpointu.
- Compose `fullmag-worktree-viewport-visual-quality-20261020-781a03fef79664b6`, port3218.
- Backend `bc2c9636ddadf53604d655f072274146323f15faee55e608969733f249d85a33`, image `sha256:2bfcc5155dd6d8f152a2a0c279f27d62e107921d4edfa2f382b7ab3a236ed001`.
- Frontend `3afd4865666f4f5a9eb2e6738da5e08d415b9d93c7247ae4b8bf781349c4d38c` pozostaje healthy; nie stanowi dowodu gotowości backendu.
- Process receipt `/opt/fullmag/runtime-control/runtime-service/process-tree.json`, raw SHA256 `eedfb3d64c4856f87355b7d25b18c8763cf6f12758c03df45bf986825aac30c0`.
- Owner `/opt/fullmag/runtime-control/runtime-services/OWNER.json`, raw SHA256 `b1908cbaf9c9472f2cafa85b16d805b054d14215c06222ed804ad40a6ff0999a`. Nie publikujemy tokenów ownera.

## Dowód awarii i ograniczenia

Process receipt ma state=failed_outcome_retained, api_shutdown=unknown, bez api_exit_code. Powód: `runtime observation stayed degraded for 31s: API identity probe failed during supervision: API loopback probe failed for /v2/platform/openapi.json: timed out`. Docker OOMKilled=false, restart count0. W namespace pozostał supervisor; procesu API nie ma. Owner state=unknown, pid21631 nie istnieje; dzieci compute21640 i preparation21641 mają zapisane exited_success i nie istnieją w /proc. Sam brak PID nie jest trwałym dowodem kodu zakończenia API ani zwolnienia lease.

Browser launcher odmówił przed startem nowej przeglądarki: `Development recovery does not identify exactly one live group`. Nie ma nowego screenshotu potwierdzającego szerokość baselines. Ostatni zdrowy runtime dowodzi wcześniejszej implementacji.

`docker_volume_stop_failed.py` wymaga trwałego api_exit_code oraz terminalnego Failed ownera; obecny przypadek tego nie spełnia. `docker_volume_container_recovery.py` wymaga jawnej autoryzacji operatora i przypiętego zatrzymanego namespace. Nie wolno zamieniać unknown w drained, wpisywać domniemanego exit code ani stosować zwykłego docker restart jako obejścia.

## Proponowane wykonanie po zgodzie

1. Ponownie zweryfikować dokładne kontenery/obrazy/mounty, raw hashe receipt/OWNER, namespace PID/start-token, manifest konfiguracji, journal runów, rezerwacje i lease. Zmiana pinów wymaga ponownego odczytu; aktywna albo nieznana praca zatrzymuje mutację.
2. Przygotować brakującą obsługę tego wariantu w istniejącym zarządzanym launcherze/recovery, z autentykowanym dowodem odrębnego zakończenia namespace i zachowaniem starego unknown oraz pierwotnego błędu. Nie uznawać nieobserwowanego zakończenia API za zaobserwowany kod exit.
3. Wykonać regresje tej ścieżki w grupie wybranego worktree: odrzucenie niezgodnych hashy/kontenerów/ownerów, żywych PID, lease/rezerwacji oraz niepełnego dowodu; ponowienie wyłącznie tej samej przypiętej transakcji. Bez uruchamiania testów solvera ani zmiany fizyki.
4. Opublikować dokładną autoryzację i receipty w technicznym named volume. Przeprowadzić kontrolowane zamknięcie wyłącznie przypiętego backendu oraz zgodne odtworzenie usług w tej samej grupie przez launcher. Wymiana frontendu tylko jeśli wymaga tego zweryfikowana konfiguracja grupy.
5. Zachować źródła, cache, sesje, wyniki, oryginalne logi i wszystkie stare receipty. Brak fresh-state, zmiany ownera bez dowodu, globalnego prune i ponownego Solve/RunIntent.
6. Potwierdzić backend ready/API/native, admission dokładnej grupy, stan istniejącego anulowanego runu, następnie ponowić browser QA nowych baselines. Historyczny problem cancelled/missing artifact_catalog może wymagać odrębnej integracji poprawki; sam restart nie jest dowodem jego rozwiązania.

Master3198 i obce worktree pozostają poza zakresem. Zgoda na tę propozycję nie jest zgodą na maskowanie błędów404/422 ani skrócenie macierzy odbioru R7.
