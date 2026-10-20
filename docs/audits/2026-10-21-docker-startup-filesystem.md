# Start Docker DEV — koszt filesystemu Windows/9P

Stan na 21.10.2026. Audyt dotyczy grupy
`fullmag-worktree-docker-volume-only-implementatio-670653a9f4702651`,
źródeł `7c16297b1d100c7c95b2d839f774bf8fb79e3709` oraz poprawki statusu
Git opisanej poniżej. Nie stanowi kwalifikacji runtime ani fizyki.

## Potwierdzony problem

Próba development `b0aa3b4d1975403d8c4e7a13241cec07` utworzyła dwie usługi.
Backend `124a4f50062a…` zakończył się kodem 2 podczas capture źródeł:
`status-runtime` przekroczył 300 s; cały pierwszy capture trwał 437 s.
Make, pakietowanie, API i rotacja konfiguracji native nie zostały osiągnięte.
Frontend `11900ad149d2…` pozostał uruchomiony na porcie 32871, lecz żądanie
`/workspace` przekroczyło 180 s podczas kompilacji. Stan procesu `healthy`
nie dowodzi gotowości HTML ani połączenia z API.

Natywny Windows Git odczytał drzewo w 0,297 s i status w 0,187 s.
Probe kontenerowy z limitem 2 CPU odczytał identyczne drzewo w 19,655 s
(SHA256 `18fd282dc5bf36b16ee2c7a51f0ffaa45ad99176222ef1306931cba8015cb11e`).
Status z ignorowaniem submodułów i bez tej opcji przekroczył po 45 s.
To nie jest dowód, że poprawiona kwerenda przekroczy pełny budżet 300 s.

Trace2 oraz próbki własnych procesów potomnych wskazały odświeżanie indeksu
Git i wywołania filesystemu czekające w `p9_client_rpc`. Wyłączenie samego
`core.preloadIndex` nie zmieściło kwerendy w 45 s. Pierwszy probe z limitem
0,25 CPU nie nadaje się do porównania z backendem mającym 4 CPU.

Próbki własnych wątków Node przez wewnętrzny inspector wykazały
`statx → p9_client_rpc`. Stabilny odczyt pathname dla 15 wywołań wskazał
rzeczywiste pliki `apps/control-room/src`, również pliki testowe. Nie były
to ścieżki cache ani `node_modules`. Same otwarte pliki `.pack.gz_` nie
dowodzą, że kompresja cache jest przyczyną zawieszenia.

Pomiar maszyny Docker i cgroup frontendu wykluczył aktywne swapowanie oraz
presję pamięci: PSI memory/IO bliskie zeru, brak OOM, bez przyrostu swap I/O.
Brak dowodu, że samo zwiększenie RAM lub usunięcie cache rozwiąże problem.

Dowody w grupowym control volume:

- `verification/source-git-probes/86a5b9f11bfa4246959053420bb26825.json`;
- `verification/source-git-probes/218922a1b1a14980935c74b01a0d578a.json`;
- `verification/vm-pressure/5d596f1ecb44465ba74a7b5b73287713.json`.

## Poprawka o sprawdzonym zakresie

Backendowy live capture i oba tryby kanonicznego helpera źródeł przekazują
`--ignore-submodules=all` do statusu Git. Wnętrza gitlinków są wyłączone
z wejść aplikacji i native dirty identity; ich skanowanie było zbędne.
Backendowy manifest nadal wiąże przypięte commity gitlinków z HEAD/index
w polu `excluded`.

Regresja używa rzeczywistego `external_solvers/3`: zmiana plików wewnątrz
nie zmienia digestu aplikacji, natomiast zmiana przypiętego commita w indeksie
zmienia manifest. Sprawdza też rzeczywisty capture kanonicznego helpera
w obu trybach. Baseline: 13 testów, 1 oczekiwany błąd braku flagi; po poprawce:
13/13 zaliczonych. Źródła readonly i stabilne, dane testowe wyłącznie
w control volume; bez kompilacji testów Rust.

Receipty regresji:

- `verification/interpreted-attempts/ece6ac564cae47f1aec83ea6828f00f7.json`;
- `verification/interpreted-attempts/9859ede07f754bdb9e13dc6d35045304.json`.

## Wynik dalszego odczytu na tym checkoutcie

Poprawiona kwerenda ze źródeł, z limitem 4 CPU jak backend, zakończyła się
poprawnie w 195,296 s; drzewo odczytano w 14,071 s. Receipt:
`verification/source-git-probes/6ec560053ea746bfaf4ba90bf5138b52.json`.
Dowodzi to zakończenia tej kwerendy w budżecie 300 s, lecz nie pełnego capture,
buildu ani gotowości API.

Osobny probe `fs.watch` na bindzie Windows zobaczył nowy własny plik wejściowy,
ale przez 12 s nie dostał żadnego zdarzenia. Po kontroli bajtów usunięto
wyłącznie ten plik. Receipt:
`verification/native-watch/b5376eebebef4b8f8405fa5aeb00868e.json`.
Samo wyłączenie globalnego pollingu mogłoby więc zgubić wykrywanie nowych tras.
Nie zostało zastosowane jako rzekoma naprawa HMR.

## Granice i dalszy odbiór

Poprawka submodułów nie jest dowodem naprawy kosztu wszystkich plików
śledzonych. Wymagane pozostają: pełny capture na checkoutcie Windows,
start API/native, odpowiedź Home, HMR, restart z cache i wykonanie skryptu.
Zmiana obrazu wrappera wymaga właściwej zarządzanej ścieżki odtworzenia;
sam restart starego obrazu nie wdroży zmienionego `backend_source.py`.

Zachowano wolumeny, cache, konfigurację ownera i held run `run-live-9f453e3a…`.
Nie ponawiano Solve, nie zwalniano zasobów bez dowodu ani nie przenoszono
źródeł do archiwum. Optymalizacja musi zachować live bind, pełne hashe
wejść i wykrywanie zmian HEAD, indeksu oraz bajtów plików.


## Kontynuacja po błędzie capture

Nowy validator zachowuje istniejący pending binding po błędzie capture przed
Make. Przypina kanoniczne current/terminal, zapisany Compose, failure log,
źródła, accepted-run oraz historyczny owner/process/config. Bieżący kontener
przechodzi odrębny pre-admission proof; historyczne metadata nie są wiązane
ponownie z jego inkarnacją. Zachowano zwykłą ścieżkę natywną i jawny fresh-state.
Kontrakt: ADR 0066, moduł `docker_volume_pending_continuation.py`.

Odczytowy preflight rzeczywistej próby `b0aa3b4d1975403d8c4e7a13241cec07`
przeszedł bez operacji lifecycle. Potwierdził `restart_verified=false`,
niezużyty binding, zachowane accepted-run i nieobecność historycznych kontenerów.
Właściwy pin Compose to SHA kanonicznego dokumentu
`1a27bcdfd85dd17de22d7523239befe84a23e3984ae0d4f412b88695b3546f64`.
SHA surowego pliku z końcowym LF (`670b398c…`) jest innym pinem. Hash konfiguracji
natywnej pozostał `7555da771595cf28af13bbe618e24dc67ea34d92ef1213da57403245a4df78a8`.

Regresje źródeł i callera, z readonly bindem i stabilnymi wejściami:

- `verification/interpreted-attempts/0c860ca80fc54121801c83e07e456165.json`;
- `verification/interpreted-attempts/61e106a7d4f84d4ba06df27d134bcc1b.json`.

Końcowe regresje błędnych receiptów i wznowienia:
`verification/interpreted-attempts/2744f7b78d474014b1c4a124f644021e.json`.

Oddzielnie 87 testów publikacji backendu przeszło po dostosowaniu istniejącej
regresji do retencji odłożonej poza startup:
`verification/interpreted-attempts/8a6ff1e7d4a147cbb44e053b7e1a97bf.json`.

Odczyt debuggera pokazał zakończone kompilacje trzech compilerów Next, bez
błędów i aktywnego przebiegu `Watching`. Kolejny GET `/workspace` zwrócił HTTP
200 po 0,235 s i pierwszy 1 KiB HTML po 0,25 s. Nie jest to dowód wyrenderowanego
Home ani pełnego UI; browser QA nadal wymaga zdrowego backendu. Backend tej
próby pozostaje zakończony kodem 2 do właściwej operacji odtworzenia i nowego
pełnego capture/build/start.
