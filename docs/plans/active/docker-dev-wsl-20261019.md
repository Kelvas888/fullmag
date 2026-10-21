# Docker DEV z Linux/WSL — plan i checkpoint

Cel: cała codzienna trasa buildera i launchera działa z WSL, z zachowaniem
grupy Compose, wolumenowego cache, źródeł readonly i trwałego storage sesji.
Użytkownik nakazał pracę bez worktree, bezpośrednio na `master`.
Baza: `b48b2934df60b074d00fce7b01ea040180505ad4`.

## Kolejność i kryteria

1. Konfigurator i wspólny klient Docker: Windows context zachowany, Linux/WSL
   używa bieżącego endpointu. Dowód: regresje konfiguratora i buildera.
2. Osobny certyfikat Linux oraz host/guest/Rust admission, UID/ACL i stabilny
   accepted store. Dowód: operacyjne testy publikacji, lock, SQLite, no-follow,
   cert bind oraz kompilacja aplikacji w stałym backendzie.
3. Zweryfikowane mapowanie ścieżek host ledger i przypięcie mountów dla
   restart/resume/recreate. Dowód: realny probe WSL i inspect usług.
4. Toolchain, obrazy helperów, backend/frontend i restart przez `just` wybranej
   grupy. Dowód: końcowe receipty w wolumenie, API i ponowne użycie cache.
5. Review pełnego diffu, instrukcja i raport z rozróżnieniem kompilacji,
   runtime oraz nieobjętej tym zadaniem kwalifikacji naukowej.

## Bieżące dowody

- Na polecenie użytkownika pobrano `origin/master` i wykonano fast-forward
  z `b48b2934df60b074d00fce7b01ea040180505ad4` do
  `6d3fcc08285e075cab0019cb235f21c7a2a9841f` (57 commitów). Lokalne poprawki
  zabezpieczono w stashu `91cc46ab5aa03ab62415ab87f3adc7a50bfe7ba6`, następnie
  odtworzono i rozwiązano sześć konfliktów. Stash pozostaje kopią bezpieczeństwa.
  Nowe ścieżki discovery/activation/recovery uwzględniają adapter Linux i piny
  daemon bindów; zachowane nowe guardy autora. Numer naszego ADR zmieniono na
  0064, ponieważ upstream dodał już ADR 0063 o recovery kontenerów.
- Po integracji wykonano spójny zestaw 436 interpretowanych regresji: OK,
  3 istniejące skip. Obejmuje setup, oba adaptery, ACL, realny parser Compose,
  retained state, discovery/activation, stop/recovery, guest gate i runtime.
  Niezależne review nowych ścieżek hostowych: brak Blocker/Required.
  Nie kompilowano testów jednostkowych. Runtime i kompilacja aplikacji nadal
  wymagają dowodu z nowego HEAD.
- Parser Rust zaakceptował oba zmienione pliki sesji po integracji; receipt
  `verification/rust-parse-6d3fcc082.json` ma zakres wyłącznie składniowy, bez
  kompilacji. Rzeczywisty `setup_docker.py --check` na nowej bazie: exit 0.
  Render Compose zachowuje CUDA 12.9.1, architekturę 120 i projekt
  `fullmag-master`. README i przewodnik architektury wskazują obie trasy hosta.
- Rzeczywisty konfigurator `--check` na WSL: exit 0; Docker Linux i RTX 5050
  dostępne. Pierwotna blokada platformy odtworzona przez regresję przed poprawką.
- Rzeczywisty probe natywnego storage WSL w grupie `fullmag-master`, jako UID
  65532, przeszedł wszystkie siedem kontroli host/guest oraz wiązanie końcowego
  certyfikatu. Receipt:
  `verification/wsl-native-storage/87eb3d89f68744e3b2b652cb5aebce92/receipt.json`
  w tym samym wolumenie kontroli. Dokładny helper
  `667a68a2f091a6f93c2c6b44584e4b6c23c90edcf9f389d7024ac386b28208a3`
  zatrzymano i usunięto po ponownej weryfikacji tożsamości i zapisaniu terminal
  inspect. To dowód storage, nie uruchomienia API ani solvera GPU.
- Testy host/guest wykonują rzeczywiste fsync, rename, lock i SQLite na fixture.
  Systemowe ACL wymagają uruchomienia testu poza sandboxem (wewnątrz EINVAL).
- Kod buildera używa adaptera klienta na całej trasie volume DEV. Historyczny
  enrollment runnera nie jest ścieżką zastępczą.
- `just docker-dev-toolchain` z WSL faktycznie uruchamia BuildKit w grupie
  `fullmag-master`; wszystkie jego logi/receipty są w
  `fullmag-build-control-fullmag-master-a7f7e9b9a4026499`.
- Próby `3dbf60145f4a4a9e9d0daceca87157df` i
  `fa2bedfc0ab345b2b06891aa1890c645` zakończone potwierdzonym exit 130
  (`failed-confirmed`). Pierwszy audyt ujawnił domyślne moduły testowe CPython,
  które BuildKit wykonał równolegle; poprawiona recepta je pomija. Drugi ujawnił
  ignorowanie architektury PETSc z `.env`; poprawiono przekazanie argumentu.
- Trzecia próba używała tagu wejść
  `fullmag/fem-gpu-toolchain:inputs-6466b4fae1ef14f8e1a9bff4` i obsługuje
  skonfigurowaną CUDA 12.9.1 / architekturę 120. Próba: `3e3f5b828529417db96ef0433adbbdce`;
  BuildKit: `default/default/vl6wf9ym13c8cmcuwaal11iby`; dawny uchwyt `16410`
  jest już terminalny. Użytkownik jawnie wybrał szybszą kompilację CUDA DEV.
  Pojedynczy SIGINT przez pidfd zweryfikowanego Compose PID 1688081 zakończył
  próbę: Compose exit 130, launcher exit 2, `failed-confirmed`. BuildKit
  potwierdził `Canceled` po 111 min 19 s, a observer brak CICC/NVCC/Ninja.
  Stary helper wycofał się normalnie, bez ręcznego usuwania zasobów.
  Odczyt BuildKit potwierdził Running; readonly observer potwierdził wzrost
  CPU ticks procesu `cicc` kompilującego `bilininteg_convection_ea.cpp` dla
  `compute_120` (60804 → 60904 w sekundę), przy około 1.5 GiB RSS.
  Brak nowej linii Ninja nie dowodzi zatrzymania tej kosztownej kompilacji.
  Próba została uruchomiona przed pobraniem nowego mastera i nie kwalifikuje
  checkoutu po aktualizacji. Kolejny zarządzany build ma użyć cache BuildKit
  i bieżących wejść. W bieżącym `.env` są już
  `FULLMAG_MFEM_CUDA_FAST_COMPILE=mid` i `FULLMAG_MFEM_BUILD_JOBS=1`;
  dotychczasowy builder nie przekazywał pierwszego ustawienia. Wdrożono jawny
  argument Compose/Dockerfile oraz metadane manifestu, z domyślnym `0`.
  Wyłącznie kompilacja MFEM GPU otrzymuje `--Ofast-compile`; poziomy aktywne
  wymagają potwierdzonej obsługi NVCC. 54 adekwatne testy interpretowane PASS,
  w tym wykonywany bash z atrapami narzędzi i rzeczywisty parser Compose.
  Render rzeczywistego hosta potwierdził `mid`, jobs `1`, architekturę 120
  i projekt `fullmag-master`. Nowy test włączono do kontroli w backendzie.
  Użytkownik zatwierdził koszt mniejszej optymalizacji runtime dla tego DEV.
  `.env` pozostaje bez zmian; zachowujemy istniejące jawne ustawienia.
  Stan i odnośnik Desktop odczytuje
  `docker buildx history inspect vl6wf9ym13c8cmcuwaal11iby` (CLI przyjmuje Build ID).
- Czwarta próba z `mid` zakończyła się sukcesem (exit 0): dawny uchwyt `7874`, attempt
  `f3adcbc5c35943d4947218fc573ef032`, Build ID `zn72u8oyeu06iaibcpjombrvv`,
  helper `9f55fa97ce05`, tag
  `fullmag/fem-gpu-toolchain:inputs-10574860b39fa95467265486`.
  Realny observer potwierdził `--Ofast-compile mid` w NVCC i
  `--Ofast-compile=mid` w CICC, z `compute_120`. BuildKit odzyskał wcześniejsze
  warstwy zależności z cache. MFEM GPU zlinkował się po około 39 minutach,
  a osobne HYPRE/libCEED/PETSc/SLEPc/MFEM CPU również zostały zbudowane.
  Terminalny receipt potwierdza `succeeded`, HEAD `6d3fcc08285e075cab0019cb235f21c7a2a9841f`,
  obraz `sha256:4fbed5ddce6edb091c0f3b62000277be7f8b40cb11ffd54da54114c334c59a26`.
  Odczyt manifestu `toolchain/dependency-versions.json` potwierdził
  `declared.mfem.cuda_fast_compile=mid` oraz fazę `runtime`.
  Wolne miejsce VM po buildzie: 943395438592 bajtów; cache zachowano.
- Pierwszy zarządzany start aplikacji: dawny uchwyt `21463`, attempt
  `338ee05be72a4106a0d3c89738486b68`, `failed-confirmed`, exit 2.
  Toolchain został użyty z cache (attempt `28db1347bcda487bb6fff71ee3cbc6f2`),
  obrazy dev (`010ea16969ad4a03bb325c5626397033`) i backend
  (`d1ff458ec83f41e3b97d14e66dee3a20`) zbudowane pomyślnie.
  Walidator `docker_development_inputs.seed` nadal wymagał Windows i zatrzymał
  start przed utworzeniem usług aplikacji. Poprawiono hostowy seed, Linux
  no-follow reader, provenance i odbiornik POSIX w frontendzie, łącznie
  z guest fallback. 103 testy, 1 skip; pozostałe PASS. Nowy moduł regresji
  jest w zarządzanych kontrolach backendu.
- Drugi start aplikacji: dawny uchwyt `5536`, attempt
  `09e8be39a6554589819b7139ed06a22b`, config SHA
  `bad9d563a1c02e56b5a11dde75a97dc70b2dc0caf3137ed69f33cebf6039c4e1`.
  Backend `18e6c53fb8bd`, frontend `4f870a8996b4`; obraz
  `sha256:055c62d5a19e857a65f8112979eab6e7e5cee4f1a5768cdd8cef8771a3c93d3d`.
  Pierwsza rzeczywista kompilacja aplikacji `make install-cli-dev` zakończyła
  się exit 0 po 854144 ms. CLI/API/workery: 11 min 07 s, potem moduł Python.
  Pakiet 24 plików zweryfikowany; bramka `linux-native-v1` PASS.
  Frontend zdrowy, HTTP 200 na `http://127.0.0.1:3197/workspace`.
  Start nie jest jeszcze sukcesem runtime: hostowy walidator ledgeru odrzucił
  alias WSL, a backend wyszedł przy tworzeniu `WRITER.lock` (Permission denied).
  Docker utworzył rodziców zagnieżdżonego mountu runtime-services jako
  UID/GID 65534, mode 750, bez zapisu dla backendu UID 65532.
  Poprawiono walidację ledgeru na dokładny pin z zachowanego Compose,
  z oddzielną walidacją kanonicznego receiptu: 18 PASS, 2 istniejące skip.
  W toku: przygotowanie stałych katalogów sesji i ACL przed Compose.
  Stary stan należy zachować; wznowienie przez managed recreate z fresh_state,
  bez ręcznego usuwania katalogów, resetu ownera ani kasowania cache.
- Przygotowanie katalogów Linux zostało poprawione i niezależnie przejrzane:
  tylko cztery nowe stałe katalogi, przypięte fd/O_NOFOLLOW, operator i UID
  65532 przez ACL, odmowa istniejącego drzewa przed zmianami. Testy ACL i
  receiptów PASS. Recreate zachowuje poprzedni `gpu_access_requested`.
  Wrapper just poprawiony dla odstępu po pustym opcjonalnym recovery.
  Odtworzenie `6d1a8412828d4d16ab7be4063b1890f4` zakończyło się sukcesem,
  zachowując stary stan i wszystkie wolumeny cache.
- Kolejny start `1a17ca2a29c647f28bdabacc5a948f56`, config SHA
  `a59437b5a0e514f9d49d08ac719a332801676fae7bcaaad2053ea35bc7f384aa`,
  jest terminalny (`failed-confirmed`); dawny uchwyt `72865` zamknięty.
  Pakiet przebudował się przyrostowo, accepted store przeszedł poprzednią
  blokadę ACL. Błąd wystąpił przy ledgerze: client bind i następnie local
  bind-volume widziały pusty katalog /dev/sdc zamiast mountu ext4 loop.
  Obecne zachowane usługi: backend `64f550726153` zatrzymany, frontend
  `36459a5876eb` działa; do kolejnego startu użyć managed recreate-volume
  przypiętego do powyższego attempt/config, z fresh_state=true.
- Szerszy uprzywilejowany probe host PID/mount namespace został odrzucony
  przez automatyczną kontrolę uprawnień i nie wykonał się. Nie obchodzono
  odmowy. Ograniczone nieuprzywilejowane próby tylko do odczytu wykazały
  poprawny dostęp do istniejącego ledgeru przez /dev/disk/by-uuid/UUID.
  UUID `c5878a7f-7d72-4698-8340-8da982553bef`, backing i aktualne /dev/loop2
  zgodne z receiptem i pojedynczym odczytem sysfs. Nie używamy surowego numeru
  loop jako trwałego device; nie tworzono nowego filesystemu.
  Nowy descriptor V2 i próba przed startem aplikacji są już w launcherze.
  Operacyjna kontrola tej właściwej recepty PASS:
  `verification-ledger/attempts/768d79d36c1441c09c3849a4ed699098/terminal.json`.
  Testy źródłowe ledger/orkiestracja/recovery: 53 przypadki, 2 stare skip,
  pozostałe PASS. Recovery używa tego samego readonly probe i CAS descriptor.
  Stary osobny orphan adapter pozostaje NOT VERIFIED dla volume DEV, zgodnie
  z wcześniejszą dokumentacją; nie poszerzano jego protokołu host receipt.
- Pierwszy realny probe WSL wykazał, że inspect Source `/home/...` nie dowodzi
  dostępności w mount namespace demona. Resolver jest poprawiany na podstawie
  mountinfo, z potwierdzeniem device/inode/hash markera, bez skanowania hosta.
  Poprawiony realny probe przeszedł: `verification/wsl-bind/ac02e00c45b14136aa2222a370350391`.
  Właściwy host-ledger również przeszedł: `verification/wsl-ledger/bc51ce6e268e41309b0c339e7cd4c9ff`.
- Niezależne review całego nowego admission/runtime: brak otwartych Blocker/Required.
  Wykryty NameError po udanym ledger ensure został poprawiony i odtworzony
  w realnej próbie. 207 regresji builder/runtime przeszło (3 istniejące skip),
  operacyjne host/guest/ACL oraz testy wznowienia przeszły. Dwa testy rzeczywistego
  parsera Compose potwierdziły przekazanie ustawień GPU/PETSc/MFEM z dotenv.
- Odczyt fizycznego dysku Docker Desktop: ponad 500 GiB wolnego miejsca na
  wolumenie Windows w chwili kontroli. Pomiar VM i storage pozostaje w receiptach.
  To obserwacja, nie quota ani gwarancja rozmiaru zimnej kompilacji.

## Retencja

Skill `fullmag-build-stage-cleanup` jest niedostępny w katalogu skilli sesji;
stosujemy build-storage governance. Nie usuwano cache, obrazów, wolumenów ani
wyników. Cache z potwierdzonych przerwanych prób pozostaje potrzebny do
przyrostowej kontynuacji. Logi, receipty i nieudany probe stanowią dowód diagnozy.
Trzy zakończone własne helpery diagnostyczne wycofano po zachowaniu ich
logów i pełnych ID: `verification/wsl-probe-retirement/4f71931a220443e0857117be38b81c08.json`.
Nie usunięto żadnego wolumenu ani backing ledgeru.
Mała fixture kwalifikacji storage pozostaje w
`runtimes/fullmag-218e710fcdeaec49/storage-qualification/87eb3d89f68744e3b2b652cb5aebce92`
pod skonfigurowanym storage jako dowód host/guest. Ponowna ocena po końcowej
weryfikacji runtime; nie zawiera cache ani wyników użytkownika.
Ponowna ocena cache dopiero po zweryfikowanym toolchainie i runtime; sam nowszy hash
wejść nie dowodzi zbędności cache. Pomiary miejsca są w receiptach operacji.
Zakończone własne probe kontenery ledgeru wycofano po zachowaniu logów i
tożsamości. Nowe deskryptory wolumenów diagnostycznych zachowano bez prune;
nie zawierają niezależnych filesystemów ani wyników. Nie wznawiać diagnostycznego
deskryptora z surowym loop po restarcie VM. Ponowna ocena wyłącznie jako
nieużywane metadane konkretnej próby, z kontrolą refs i osobną zgodą na cleanup.

## Końcowy build i restart WSL

- Zarządzane odtworzenie usług `8b0c057dd06a437394963748cd47a53a`
  zachowało stare stany i cache. Toolchain, development-base i backend image:
  cache-hit. Nie wykonano nowego ciężkiego buildu zależności.
- Start `development/attempts/c57cfe60ea454d6ea296064cc3ca7b4a` zakończył się
  `succeeded`, exit 0. Config SHA:
  `697851b75a0f51cd43b6fcfb9c74363523546531c20caa47176b1f69a24d4625`.
  Profil `linux-native-v1` przeszedł admission; API/runtime ready.
  Frontend: `http://127.0.0.1:3197`, health obu usług healthy.
- Przyrostowy build aplikacji w tym samym backendzie: make 53652 ms, package
  24 pliki. Cargo raportował build-info, fem-sys, runner, runtime-control,
  CLI, API i py-core; etapy Cargo 41.89 s oraz 7.87 s. To pomiar realnych
  poprawionych wejść, bez obietnicy stałego czasu ani pojedynczego crate.
- Zarządzane `docker-dev-control-checks`: exit 0, 729 przypadków w 7.981 s,
  23 skip (m.in. niedostępne hostowe narzędzia w kontenerze). Receipt:
  `verification/interpreted-checks.json`. Nie kompilowano testów natywnych.
- Kontrolowany idle restart `iteration/attempts/026f5aed2625439c9009fe7e16cca2d2`:
  `succeeded`, exit 0, `backend_package_cache_hit=true`, ten sam config SHA,
  brak kompilacji i nowego pakietu. Admission Linux ponownie PASS.
  Backend zachował pełny ID
  `3aee6529428c88080973ccc95b0602d28fcc8fa687391836eb82cdff84c5dba1`,
  frontend `2420b8d3041d28a69b4ecf4dcc1766487be3a1d07b161d9d146308c476b64cef`.
  Obie usługi ponownie healthy; restart nie uruchamiał Solve.
- Rzeczywisty inspect potwierdza dokładnie dwie stałe usługi aplikacji:
  build/package/control i frontend cache są named volumes, źródła readonly,
  userdata/state pozostają bind mountami hosta. Ledger korzysta z przypiętego
  ext4 volume V2. Stare failed state, backup stash oraz cache pozostawiono.
  Automatyczna retencja backendu zgłosiła files=1; nie wykonywano prune.
- Receipty i logi pozostają w
  `fullmag-build-control-fullmag-master-a7f7e9b9a4026499`.
  `git diff --check` i staged diff check przeszły.

- Natywny Chrome Windows headless: exit 0, poprawnie wyrenderowany ekran
  startowy, tytuł `Workspace | Fullmag Control Room`, compute Connected,
  No active session, RTX 5050 i telemetry available. Screenshot 1440×1000
  obejrzany; bez error overlay. Artefakty przeglądarki (odrębny TEMP profile):
  `/mnt/c/Users/kelvas/AppData/Local/Temp/fullmag-wsl-browser-ebd572219a774ad091a102e7ac19b59b/`
  (`workspace.png`, `workspace.html`, `chrome.log`). Chrome używał disable-gpu;
  ekran startowy nie ma canvas i nie dowodzi WebGL ani wykonania symulacji.

Status: build, API, frontend HTTP, ekran startowy w przeglądarce oraz restart
z cache zweryfikowane. HMR bez reloadu dokumentu, solver GPU,
parytet fizyki, release oraz starszy orphan adapter volume DEV pozostają
NOT VERIFIED. Nie wyciągać tych wniosków z dostępności GPU lub healthchecku.

## Wznowienie po restarcie komputera — 20.10.2026

HEAD użytkownika: `b686c7aa84fbc296d0752e64bbfdc2342ad2189a`.
Obca zmiana `AGENTS.md` pozostaje poza zakresem poprawki.

- Odtworzono brak UUID device i wygasły alias storage Docker Desktop.
  `resume` przywraca wyłącznie istniejący obraz z zapisanym UUID. Alias może
  zostać odtworzony tylko dla zweryfikowanego markera i istniejącego obrazu;
  obcy mount, niepusty katalog lub niezgodny UUID blokuje operację.
- Rzeczywista próba `resume/attempts/b80c401db87241f19da7a44a5af36e75`
  przywróciła ledger oraz przebudowała aplikację z cache. UUID i dane zachowane.
  Start ujawnił pozostałe blokady po niepotwierdzonym wyłączeniu:
  frontend miał stary receipt procesu, a natywny OWNER pozostał Ready.
- Frontend odzyskano kontrolowaną operacją
  `frontend-restart/attempts/665a37ecf4b54b7c92f57954bc98d990`.
  Oryginalny receipt i jego SHA zachowano przed publikacją stopped.
  Sprawdzono zatrzymany private PID namespace, brak konsumentów wolumenu,
  runtime flock i CAS. Cache, źródła i dane sesji nie zostały usunięte.
- Backend odmówił attach do starego builda przed uruchomieniem native.
  API zakończyło się kodem -15, runtime nie został uruchomiony.
  Zarządzane stop-failed zakończyło dokładnie przypięty supervisor. Dowód:
  `verification/stop-failed-3aee6529428c88080973ccc95b0602d28fcc8fa687391836eb82cdff84c5dba1.json`.
  Poprawiono odczyt kanonicznej ścieżki i stderr oraz dodano wąską allowlistę
  dokładnego błędu build mismatch; pozostałe nieznane błędy nadal blokują stop.
- Zachowany pin Ready i OWNER mają zgodne tokeny, PID 165, host oraz stary
  commit/snapshot. Pin: `runtime-control/runtime-services/`
  `docker-client-dc79acbb-57a9-4fba-abf8-70dc4b6a1f93.json`.
  LAUNCH.pid=165. Nie zmieniono OWNER ręcznie ani nie dopisano draina.
  Jawne odzyskanie użyło istniejącego natywnego kontraktu i osobnego dowodu
  hosta według ADR 0066, bez fabrykowania dawnego stop journal.
- Autoryzacja `cold-recovery-authorization/attempts/7257f445219b4e37aa785f7c3d04ea4c`
  przypięła autentyczny pin Ready, historyczny verified receipt, managed stop,
  dokładne zatrzymane przestrzenie PID, pusty accepted store i zwolniony ledger.
  Request ID: `53d07762-6414-43d4-b18e-993d673655e9`.
  Native outcome: `empty_namespace_recovered`. Archiwum oryginalnego ownera:
  `runtime-control/runtime-services/container-recovery/4eeb59dbc3e17601f2a622732af67085da16d6dc1a1f79af00fc48b77f8c0ca4/archive/manifest.json`.
  Start `development/attempts/3c17a8ffb1ec43f48b555de02af45d72` przeszedł.
- Próba restartu ujawniła porównywanie nowego LAUNCH i generacji zasobów
  z archiwum poprzedniego ownera. Poprawiono replay po autentycznym drainie:
  owner wymaga aktualnego SHA, LAUNCH pasującego PID, a dwa rekordy zasobów
  dokładnej nowej generacji i niezmienionych ofert. Typy JSON pozostają ścisłe.
  Archiwum, stare logi, locki i checkpointy nadal są sprawdzane bez wyjątków.
  Rzeczywisty readonly probe na stanie Drained przeszedł:
  `recovery-replay-probe/attempts/e38afd67bdd14096acf2a9268bd66944`.
- Własna operacja `image-update-stop/1179d037fd3e469ea861becbeb355547`
  zakończyła usługi prawdziwym drainem, ale host nie domknął jej receiptu.
  Automatyczna kontrola odrzuciła ręczne oznaczenie sukcesu. Po jawnej zgodzie
  użytkownika zamknięto wyłącznie tę operację jako `failed-confirmed`,
  zachowując oryginalny receipt i dowody. Nie zmieniono native OWNER.
- Końcowy start `development/attempts/0351d3f6f8a044dbb68f22d427967330`:
  `succeeded`, exit 0. Config SHA:
  `a870930bea656f9579ebd834f7ff6a3c5f0210315b5756d7f948961079832f5f`.
  Obraz: `sha256:e876400b1af62a98664788873e8ddaad4da4116ea609639fca0b23954630b2c9`.
  Profil `linux-native-v1` przeszedł admission, native owner Ready i API ready.
  Nowe usługi nie zawierają jednorazowej autoryzacji recovery.
- Końcowy idle restart `iteration/attempts/554e031322854324a62dae066a1cfe9e`:
  `succeeded`, exit 0, `backend_package_cache_hit=true`, bez zmiany ID usług.
  Backend: `b1674bb964022a4af490b63f903276f8281bd63374aeb43feab5cd7435caaf9d`.
  Frontend: `9677dd8191b7c3bdc13375e1b5ffd8041cf298ada8bbcac8f36c76fb63930509`.
  Obie usługi healthy; prywatne API `status=ok`, `active_session=false`.
  URL: `http://127.0.0.1:3197`.
- Zarządzane interpretowane regresje: 756 przypadków, exit 0, 23 skip,
  10.076 s. Wąski zestaw hostowy: 85 przypadków, 2 skip. Payload helpera,
  `bash -n` i `git diff --check` PASS. Nie kompilowano testów natywnych.
  Receipt: `verification/interpreted-checks.json`; końcowe obserwacje:
  `verification/reboot-resume-summary.json` w dotychczasowym control volume.

Retencja: cache, obrazy, wolumeny, stare stany, sesje, wyniki i logi zachowano.
Wycofano tylko dokładnie zidentyfikowane własne helpery po zachowaniu dowodów;
nieudany helper ledgeru ma archiwum
`verification/failed-ledger-helper-681949c25d1747d2a08ab200a9afe2ed.json`.
Nie wykonano globalnego prune. Wolne miejsce VM: 923058319360 bajtów;
ponowna ocena cache dopiero po wykazaniu zbędności konkretnych generacji.
Skill `fullmag-build-stage-cleanup` nadal niedostępny; stosowano governance.

Status: odzyskanie tego zimnego wznowienia, build, API oraz zwykły restart z cache
zweryfikowane. Nie oznacza to automatycznego recovery dowolnego przerwanego runa
lub nieznanego ownera. Solver GPU, fizyka, WebGL i release pozostają NOT VERIFIED.
Zmiany są lokalne na `master`; bez nowego commita ani push.

## Synchronizacja mastera — 20.10.2026

- Na polecenie użytkownika pobrano `origin/master` (fork Kelvas888) oraz
  `upstream/master` (MateuszZelent). Oba wskazały
  `a63b50ca0c0c4b457f440b0ac276b483d282c555`.
  Lokalny `master` zaktualizowano fast-forward o 89 commitów; wczorajszy
  `b686c7aa84fbc296d0752e64bbfdc2342ad2189a` pozostaje jego przodkiem.
- Pełna kopia 21 lokalnych plików sprzed aktualizacji pozostaje w stashu
  `58c25d36b7e7fe10c498ed1cb2b1d143cf58d342`.
  Użyto `stash apply`, bez usuwania kopii. Starszy stash także zachowano.
  `.env` i obca zmiana `AGENTS.md` mają identyczne SHA jak przed aktualizacją.
- Rozwiązano konflikty runtime, stop-failed i listy regresji, zachowując
  nowe guardy upstream oraz obsługę zimnego wznowienia WSL. Replay korzysta
  teraz z pełniejszej implementacji successor upstream z zachowaniem ścisłych
  typów JSON i SHA bieżącego ownera. Legacy frontend dopuszczono wyłącznie
  do kontrolowanego odtworzenia; nowy ephemeral owner nie wymaga zmiany
  trwałej diagnostyki. Lokalną decyzję recovery przenumerowano na ADR 0066,
  zachowując nowy upstream ADR 0065.
- Przywrócono także lokalne testy stop-failed, których nazwa kolidowała z
  nowym plikiem upstream. Dostosowano nieaktualne fixture namespace, mountów,
  środowiska i komunikatu wycofanej trasy. Naprawiono pobrany błędny import
  `docker_text` w `docker_worker_cgroup.py` przez adapter centralnego capture.
- Wąskie sprawdzenie integracji: 108 testów PASS. Końcowe zarządzane
  `docker-dev-control-checks`: 840 przypadków, 23 skip, 11.345 s, exit 0.
  Receipt: `verification/interpreted-checks.json` w dotychczasowym control volume.
  Brak nierozwiązanych konfliktów; indeks Git pusty. Nowe zmiany pozostają
  lokalne, bez commita i push.

Nie budowano obrazów ani nie restartowano aplikacji podczas synchronizacji.
Działający backend nadal używa poprzedniego obrazu i buildu; start całego
nowego mastera pozostaje NOT VERIFIED. Nie przenosić wcześniejszych dowodów
runtime na nowe źródła. Dane użytkownika, wolumeny i cache zachowano.
