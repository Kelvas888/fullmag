# Recovery namespace z zachowaną historią terminalną — kontrakt v3

## Problem

Owner `0c242b7c-66cf-4d66-b442-50555419d423` pozostaje Unknown, chociaż
odczyt procesów nie wykazuje jego ani schedulerów, a rezerwacje hosta są
zwolnione. Historia obejmuje rzeczywiście wykonane i nieudane zadania.
V1 wymaga pustego magazynu, V2 zachowuje wyłącznie cancelled-before-claim.
Nie wolno przerabiać ukończonych runów na cancelled ani usuwać ich historii.

## Zmiana kontraktu i granice

Istniejący `RuntimeServiceContainerRecoveryRequest` otrzymuje jawny
`runtime_service_container_recovery_request.v3`. Nowe pole
`retained_terminal_runs` zawiera kompletny spis runów. Każdy wpis ma:

| Pole | Typ | Obowiązek |
|---|---|---|
| run_id | istniejący stable ID | jednoznaczny i bez duplikatów |
| run_intent_sha256 | lowercase SHA256 | dokładne bajty intentu |
| run_catalog_sha256 | lowercase SHA256 | dokładne bajty katalogu |
| terminal_evidence_sha256 | lowercase SHA256 | kanoniczny digest dowodów store + host ledger |

Maksymalnie 128 runów i 4096 zadań; zachowane limity wejść/CAS walidatora.
V1/V2 nie akceptują nowego pola, V3 nie miesza go z cancelled-only.
V3 zachowuje istniejący dowód zakończenia kontenerów Docker. Nie rozszerza
wariantu authoritative-absence, który nadal należy wyłącznie do V2.

Natywny core pod istniejącymi blokadami startup/launch/owner oraz writerami
host -> SessionStore ponownie sprawdza dokładny inventory, intent/catalog,
niezmienione CAS oraz terminalne dowody każdego runu. Dotychczasowy
`terminal_run_evidence_value_locked` pozostaje właścicielem kontroli claims,
admissions, exit receipts, leases i uzasadnień no-spawn. Wspólny hostowy
walidator sprawdza prawdziwe release proofs; sama etykieta Failed/Succeeded
nie wystarcza. Stan aktywny lub zmiana dowodu ma skutkować odmową.

Nie ma usuwania wyników, rekoncyliacji lease, ponowienia Solve ani syntetycznego
drain. Wynik skutecznego recovery to istniejący kanoniczny Failed z pustą listą
dzieci, bo teardown kontenera nie dowodzi natywnych exit statusów. Nowy outcome
receiptu: `retained_terminal_runs_recovered`; schemat receiptu pozostaje v1.

## Właściciele kodu

| Odpowiedzialność | Ścieżka + symbol |
|---|---|
| V3 i blokowana operacja | `crates/fullmag-session/src/runtime_service.rs` + `RuntimeServiceContainerRecoveryRequest::validate`, `recover_container_proof_locked` |
| Jawne piny i porównanie dowodu | `crates/fullmag-session/src/runtime_service/retained_terminal_runs.rs` + `validate_retained_terminal_runs` |
| Wspólne intent/catalog/CAS i leases | `crates/fullmag-session/src/runtime_service/retained_cancelled_runs.rs` + `validate_retained_run_inputs` |
| Kanoniczny host/store evidence | `crates/fullmag-session/src/host_resource_ledger.rs` + `terminal_run_evidence_sha256_locked`, `with_terminal_run_evidence_fence` |
| Odczytowy producent pinu | `crates/fullmag-session/src/runtime_service.rs` + `RuntimeServiceConfig::inspect_terminal_run_evidence` |
| Klient z przypiętą konfiguracją | `crates/fullmag-runtime-control/src/runtime_service_client.rs` + `inspect_terminal_run_evidence` |
| Prywatna komenda CLI | `crates/fullmag-cli/src/args.rs` + `RuntimeCommand::ServiceInspectTerminalRun` |

Odczytowa komenda `runtime service-inspect-terminal-run` wymaga surowego SHA
konfiguracji i run_id. Zwraca digest; nie startuje API/runtime i nie zmienia
runu, ownera lub rezerwacji. Służy przygotowaniu pinu, który core recovery
musi później sprawdzić ponownie pod pełnymi blokadami.

## Weryfikacja i stan

Kontrola składni Rust przeszła bez kompilacji testów jednostkowych.
Dodano źródłowe regresje wersji v1/v2/v3, mieszania kontraktów, pustych i
powielonych pinów oraz złych digestów. Testów Rust nie skompilowano ani nie
wykonano. Wymagane są jeszcze build aplikacji, rzeczywisty odczyt dowodów,
negatywne przypadki wejść, integracja launchera i kontrolowane recovery.
Nie zastosowano migracji ownera. Nowe V/J/H i Universe nadal NOT VERIFIED.

## Build i pierwsza rzeczywista diagnostyka

Managed recovery-build `9d5c8a6f61164d299f621a50a9cde42e` zakończył się
succeeded/exit0. Make: 636733 ms; pakowanie: 3599 ms / 24 pliki.
Źródło: `ea1cb3ed807b37c7f21cc13149538d2100bf3317`, snapshot
`30f655a6462697e0086291f4da34b98b0d413d84abc07fd134a326b8673a6b70`.
Kandydat: `.backend-package-candidate-gvcf71no`, receipt SHA256
`be2ef899c8a62cb8594ab02aa1cf26130df21499be2350e72eaf871451366b52`.
Starszy kandydat `.backend-package-candidate-sexe5b82` jest zachowany w
quarantine; bieżącego pakietu nie promowano i nie startowano runtime.

W wolumenie kontrolnym, katalog
`verification/terminal-history-recovery-v3-20261025/`, zachowano odtwarzalny
`inspect-native-history.py`, `native-history-progress.json` i
`native-history-diagnostics.json`. Nowy CLI rzeczywiście uruchomiono, lecz
14/14 odczytów zatrzymała bramka `compiled source commit differs from runtime
provenance`. Obecny backend prawidłowo poświadcza stary pakiet c0f3dc7e;
nieopublikowany klient ea1cb3ed nie może udawać tego pakietu.
Nie uzyskano jeszcze żadnego terminal_evidence_sha256 ani gotowych pinów recovery.
Sprawdzono niezmienność 33 chronionych plików: config/owner/process/provenance,
ledger oraz intent/catalog dla każdego z 14 runów.

Negatywny raw config SHA i niebezpieczny run_id odmówiono we właściwych
bramkach. Przypadek brakującego runu nie dotarł do kontroli istnienia, ponieważ
wcześniej odmówiło provenance; nie jest zaliczonym testem tej gałęzi.
Źródłowych testów Rust nadal nie kompilowano.

Inventory obejmuje 14 terminalnych katalogów. 2027 pinów CAS odpowiada dokładnie
2027 referencjom inputów z zachowanych intentów, o łącznym rozmiarze obiektów
107196388 bajtów. To odczytowy pomiar, nie wykonanie pełnego natywnego walidatora
CAS ani dowód zakończenia procesów. Limitów walidatora nie zmieniono.

## Następna droga weryfikacji

Odrzucono zmianę globalnego provenance działającego API oraz osłabienie bramki
storage. Potrzebny jest osobny kanoniczny widok zbudowanego kandydata dla
odczytowej diagnostyki: ten sam obraz i grupa, kandydat widoczny jako
`/opt/fullmag/package`, jego zgodne provenance wyłącznie w technicznym
podkatalogu kontrolnym, bez kompilacji/API/Solve. Dane hosta pozostają te same;
natywne blokady i kontrola niezmienności są obowiązkowe. Taki helper musi zostać
zintegrowany z zarządzaną receptą i przetestowany przed użyciem; sama ta propozycja
nie jest działającą trasą ani zgodą na zmianę provenance starego API.

Docker dokumentuje `volume-subpath` dla montowania istniejącego podkatalogu
wolumenu: [Volumes](https://docs.docker.com/engine/storage/volumes/#mount-a-volume-subdirectory).
Obsługę wprowadzono w Engine 26.0; wersję rzeczywistego silnika trzeba sprawdzić
przed wdrożeniem helpera. Pakiet kandydata można odczytywać, zachowując globalny
mount i provenance dotychczasowego backendu bez zmian.

Odczyt silnika na tym hoście: Docker Engine `29.7.2`, API `1.55`.
Wersja nie jest blokadą `volume-subpath`; sama nowa recepta nadal NOT VERIFIED.

## Zarządzany widok diagnostyczny kandydata

Przygotowano `just docker-dev-candidate-history` oraz kontroler
`scripts/docker_candidate_history.py`. Recepta wymaga pełnych pinów źródła,
backendu, obrazu, zakończonego recovery-build i receiptu kandydata. Nie buduje,
nie promuje pakietu i nie uruchamia API ani Solve.

Kontroler sprawdza terminalną authority builda, marker Ready i pełny inventory
kandydata oraz diagnostyczny stan donora. BuildControl serializuje operację
`candidate-history`. Techniczny helper tej samej grupy otrzymuje:

- readonly subpath istniejącego package volume pod `/opt/fullmag/package`;
- readonly główny control volume oraz osobny zapisywalny subpath operacji jako
  `/opt/fullmag/control/backend`, aby kanoniczny producent wystawił provenance
  tego kandydata bez zmiany globalnego provenance donora;
- oryginalne dane i grant Linux, bez zmiany owner tokenów, markerów lub `.env`;
- RW SessionStore i host ledger wyłącznie dla wymaganych natywnych blokad.
  Bajty całego naukowego SessionStore (bez technicznego aliasu runtime-services)
  są porównywane przed odczytami i po nich; owner/process/config/provenance i
  ledger donora również muszą pozostać identyczne;
- brak `/build`, socketu Docker i sieci; root filesystem readonly. Sterownik
  CUDA jest dostępny do załadowania zależności CLI. W WSL dopuszczony jest
  most `/dev/dxg`; raport zapisuje faktyczną topologię, bez twierdzenia o izolacji GPU.

Package/provenance w helperze przechodzą dotychczasową bramkę storage bez
zmiany walidatora Rust. Natywna komenda pozostaje odczytowa. Wynik przechowuje
rozróżnienie sukcesu diagnostyki i dowodu każdego runu; brakujący lub niespójny
run nie tworzy częściowej listy gotowej do recovery. Trzy negatywne przypadki
muszą dotrzeć do oczekiwanych bramek, nie tylko zwrócić dowolny błąd.

Audyt writerów: host nie kopiuje źródeł/pakietów ani nie zapisuje artefaktów
buildu do storage. Scope, logi, prywatne provenance i wynik pozostają w control
volume. Pakiet jest RO. Kontroler nie ma operacji usuwania, rotacji, promocji,
admission ani zmiany stanu ownera. Helper jest efemeryczną diagnostyką, a nie
alternatywnym builderem lub runtime aplikacji. Timeout zachowuje nieznany wynik
operacji BuildControl; nie powoduje automatycznego ponowienia.

Interpretowane regresje nowej topologii i stałego argv oraz dotychczasowego
recovery: 30 PASS (`candidate-view-tests.json` w katalogu verification v3).
Nie kompilowano testów native. Rzeczywisty wynik nowej recepty wymaga jeszcze
odczytu terminalnego receiptu; nie utożsamiamy testów topologii z działającym
preflightem danych ani z recovery.

## Diagnoza środowiska sterownika WSL

Pierwsza próba ujawniła brak zachowania VolumeOptions.Subpath; poprawiono
kopiowanie aliasów i dodano regresję. Kolejna zachowała 5737 plików store,
lecz 14 komend zatrzymało ładowanie libcuda.so.1, zanim weszły do CLI.
Runtime NVIDIA z NVIDIA_VISIBLE_DEVICES=none dostarczył bibliotekę, lecz
WSL udostępnia /dev/dxg również w tej konfiguracji. To nie dowodzi braku
dostępu do GPU. Kontroler zapisuje kernel i urządzenia, dopuszcza wyłącznie
pustą listę albo dxg na kernelu Microsoft, i nadal uruchamia tylko stałą
komendę odczytową. Nie uruchamia API, workera ani Solve.

## Wynik rzeczywistej próby i checkpoint

Próba `d6be2a86e8824ed9a232d6087b36bc6d` zakończyła się
`failed-confirmed`, bez promocji, recovery, API i Solve. Sterownik załadowano;
raport potwierdza kernel Microsoft WSL2 i wyłącznie most `dxg`.
`native-observations.json`, `store-before.json` i `store-after.json` pozostają
w `candidate-history/attempts/d6be2a86e8824ed9a232d6087b36bc6d` wolumenu
kontrolnego grupy.

Porównanie wszystkich plików wykazało dokładnie jedną zmianę:
`WRITER.owner.json` w korzeniu SessionStore. To doradczy zapis blokady
technicznej, tworzony przez kanoniczny writer przy wejściu i wyjściu.
Pozostałe 5736 plików, w tym wyniki naukowe, zachowały identyczne SHA256.
Nie osłabiono kontroli inventory: helper nadal odmawia przy tej zmianie.
Dodatkowa kontrola donora potwierdziła niezmienione przypięte bajty
owner/process/config/provenance i ledgera (`donor-retention.json`).

Każdy z 14 runów odmówił w bramce `Linux native probe is not bound to this
owner/mount/namespace`. Dowód `.linux-native-probe.json` został rzeczywiście
wystawiony dla namespace backendu; nowy namespace nie może go dziedziczyć.
Nie zmieniono tego dowodu, nie sfałszowano namespace ani wyników testów probe.
Negatywne przypadki złego config SHA i niebezpiecznego run_id trafiły we
właściwe bramki; brakujący run pozostaje niezweryfikowany z powodu wcześniejszej
odmowy namespace. Nie ma gotowych pinów recovery (0/14).

Ta recepta jest narzędziem diagnostycznym z zachowaną odmową, a nie
zakwalifikowaną trasą odczytu historii. Dalsza poprawka wymaga kanonicznego,
izolowanego producenta probe dla namespace diagnostyki bez nadpisania dowodu
działającego backendu oraz rozdzielenia kontroli technicznych metadanych writera
od niezmienności naukowych plików. Nie ponawiać tej samej trasy bez takiej zmiany.

W tym checkpointcie: 5 interpretowanych regresji topologii/argv PASS, parser
Python PASS, `git diff --check` PASS. Nie kompilowano testów Rust.
Fetch `origin/master` wskazał `f08fc7755acdf742c5fdcbcb6ce5bec7c40abe48`,
który jest już przodkiem brancha zadania: brak nowych commitów do scalenia.
Build aplikacji pozostaje wcześniejszym dowodem; nie jest dowodem recovery
ani udanego Solve Universe.

## Izolowany prawdziwy probe — wynik poprawki

Dotychczasowy producent `docker/all-in-one/linux_native_probe.py` otrzymał
opcjonalny `evidence_path`, wymagający zweryfikowanego restart readback.
Zwykłe wywołania zachowują dotychczasową atomową publikację. Diagnostyka
zapisuje dowód do jednego istniejącego pliku operacji w control volume,
bez zmiany inode. Ten sam plik jest zamontowany jako readonly file subpath
pod kanonicznym `/state/.linux-native-probe.json` wyłącznie w helperze.
Nie skopiowano starego wyniku checks ani namespace: producent ponownie
wykonał rzeczywiste fsync, atomic replace, process lock, no-follow, SQLite
i restart readback na rzeczywistym `/state`. Natywny walidator nie zmienił się.
Źródło producenta i runtime kontrolera są przypięte przez SHA256 w receipcie.

Operacja `4d63e56a4948445984f7a1150a1aa59e` zakończyła się succeeded,
wynik diagnostyki passed: 14/14 runów i 3/3 negatywne bramki.
Gotowe piny są w `candidate-history/attempts/4d63e56a4948445984f7a1150a1aa59e/result.json`
w wolumenie kontrolnym grupy. Nie są uprawnieniem do pominięcia ponownej
walidacji pod blokadami w core recovery.

5736 plików zachowało identyczne SHA256. Jedyną zmianą store jest
korzeniowy `WRITER.owner.json`, sprawdzony osobno jako `fullmag.writer.v1`
z `released=true`; zmiana dowolnej innej ścieżki, także podobnie nazwanego
pliku w runie, nadal powoduje odmowę. Runtime owner, config, process receipt,
ledger, globalne provenance i domyślny probe backendu pozostały identyczne.

19 interpretowanych regresji producenta i diagnostyki PASS. Potwierdzono
70 plików starego wyniku V/J/H, 2 archiwa i 6 chronionych plików błędnej
próby oraz niezmieniony FMS użytkownika. Dowód retencji:
`verification/terminal-history-recovery-v3-20261025/retention-after-private-probe.json`.
Nie kompilowano testów Rust, nie promowano pakietu i nie wykonano nowego Solve.
Następny krok: integracja konsumenta v3 z kontrolowanym zatrzymaniem
diagnostycznego API, świeżym dowodem teardown i ponowną natywną kontrolą
całej terminalnej historii. Backend i Universe nadal nie są przywrócone.

## Konsumenci v3 i odczytowy preview stopu Unknown

Istniejący `scripts/docker_volume_container_recovery.py` rozpoznaje jawny
request v3, waliduje pełne piny terminalne i przekazuje je do istniejącego
producenta requestu oraz odczytowego snapshotu store/ledgera. Snapshot sprawdza
dokładny inventory i bajty intent/catalog; nie zastępuje natywnej walidacji
`terminal_evidence_sha256` pod blokadami. V1/V2 nie przyjmują pinów v3,
V3 nie miesza pinów cancelled-only, a absence attestation pozostaje V2-only.

Kod image-owned `docker/all-in-one/runtime_service.py` rozpoznaje ten sam
outcome `retained_terminal_runs_recovered` i zachowuje wymaganie rzeczywistego
teardown. Jest to zmiana źródeł obrazu, jeszcze niewdrożona do obecnego
kontenera; wymaga zarządzanego buildu i weryfikacji przed użyciem recovery.

Stop-probe w `scripts/docker_volume_stop_diagnostic.py` ponownie używa
istniejącej walidacji dokładnej tożsamości Unknown vs zachowany Ready pin.
To wyłącznie kontrola tożsamości: oddzielnie nadal wymagane są zgodny fence
API i incarnation, zdegradowana odpowiedź HTTP, pełny census /proc oraz
nieobecność ownera, schedulerów i workerów. Stop nie publikuje Failed ani
Drained i nie zwalnia rezerwacji; legacy pole `failed_owner` zawiera
niezmieniony dokument z rzeczywistym `state=unknown`.

Odczytowy rzeczywisty preview PASS: API PID 3274, health degraded, owner
3282 oraz dzieci 3285/3286 nieobecne. Nie wysłano sygnału stop. Dowód:
`verification/terminal-history-recovery-v3-20261025/unknown-diagnostic-stop-preview.json`
w wolumenie kontrolnym grupy. SHA256 serializowanego probe:
`4392d452080f0613b1eebc300e94bc77ead46066d531e3dc7e05a97a388d73ce`.

104 testy interpretowane PASS: diagnostyczny stop, dotychczasowy stop failed,
recovery-build i host/runtime recovery. Wykryto i naprawiono nieaktualny
fixture starego stopu: brak inicjalizacji `_active_operation` i przypięcia
helpera, wymaganych przez bieżący BuildControl. Nie zmieniono oczekiwanej
semantyki zatrzymania ani zachowania nieznanego wyniku.

Nie skompilowano testów Rust, nie przebudowano obrazu, nie wykonano stopu,
promocji, recovery ani Solve. Pozostała integracja istniejącego operator
authorization/prior-stop journal z diagnostycznym stopem i pełnymi pinami v3,
a następnie pełny preview przed zatrzymaniem naszego backendu. Sama obsługa
wersji w klientach nie dowodzi gotowej procedury odtworzenia instancji.

## Integracja operatora z terminalną historią

Dodano jawny `fullmag.docker-container-recovery-operator-authorization.v2`
z kompletnymi pinami `retained_terminal_runs`. Stary operator v1 zachowuje
ścisły zestaw pól. V2 wiąże dokładne SHA256 diagnostycznego journalu,
konfiguracji Compose/runtime, ownera i końcowego process receipt. Wymaga
`stopped-execution-unknown`, `unknown-preserved`, nietkniętych leases i
zachowanego Ready pina; nie przyjmuje fikcyjnego Drained. Poprawiono też
etykietę receiptu stopu, aby dla Unknown nie twierdziła failed-preserved.

Główna istniejąca procedura `recover` przekazuje piny v3 do obu snapshotów
store/ledgera i do natywnego requestu. Dla nowej autoryzacji może początkowo
obejrzeć działający frontend tej samej grupy, lecz backend nadal musi być
zatrzymany. Dopiero po przygotowaniu obrazów i pełnej ponownej walidacji
pod lifecycle lease zatrzymuje dokładnie przypięty frontend. Sprawdza
fingerprint, StartedAt, image/ID i faktyczny exited/PID0/FinishedAt, zapisuje
dowód oraz ponawia pełny preflight. Nieznany wynik stopu zachowuje guard.
Stara ścieżka nadal wymaga obu kontenerów zatrzymanych przed wejściem.

108 interpretowanych testów PASS. Nowe regresje obejmują rozdzielenie
autoryzacji v1/v2, dryft pinów journalu, odrzucenie zmiany inkarnacji
frontendu oraz zachowanie lease przy nieznanym wyniku stopu.
Nie uruchomiono jeszcze stopu, odtwarzania kontenera, recovery ani Solve.
Pełny rzeczywisty preview całej procedury oraz zarządzany build obrazu
pozostają wymagane przed wykonaniem mutacji.

Stan naukowy bez zmian: pełna mapa H wokół anteny na siatce Universe
i jej wizualizacja w UI nie zostały uzyskane. Stare zaakceptowane V/J/H
na małym zbiorze punktów nie są dowodem realizacji tego wymagania.

Dodatkowo oba preflighty porównują dokładną inkarnację backendu z journalem:
ID/obraz, StartedAt, FinishedAt, exit code, exited/PID0 i brak OOM.
Zmiana tych danych blokuje przejście, nawet przy zachowanym container ID.

## Rzeczywiste przygotowanie i kontrolowany stop

`just docker-dev-images` PASS: toolchain cache hit, próba
`cc59b8d4184a4a6da7badd974d396a5d`. Nowy backend image:
`sha256:b3eb4e5bf434b46acd633e4339962bffbcb9b6ccaac59ce5ebf444c4023cc10c`,
image-backend `cec67e6f38c84a8587891636ae4a304a`. To przygotowanie obrazu,
nie build aplikacji ani start solvera.

Dodano brakującą receptę `just docker-dev-stop-diagnostic` ze ścisłym
stałym argv i domyślnym `preview=true`. Preview ma własną fazę i blokadę
BuildControl, odmawia abortowania pending activation i nie wykonuje
rekoncyliacji nieznanego stopu. 6 testów interpretowanych PASS, w tym
komendy złożone, dopisane flagi i zamiana fazy lease.

Pełny rzeczywisty preview `1cbf8ee1c3d046019c0ecd52355b28cb` PASS.
Świeży odczyt historii `9de2d65ff97240bb8cbc386c7c455d9b` PASS 14/14.
Stop `242dc6e0c13340e394a20609ff811525` succeeded: API exit -15, backend
exit 1, execution unknown i owner unknown-preserved. Wynik 1 pochodzi
z zachowanej nieudanej obserwacji runtime; nie jest udanym native drain.
Terminal process receipt SHA256:
`60dbf4b3043e8f430bd6549eef4b99de28bc99e5736aead19b42c391a22dc40c`.

Pełny post-stop preflight `1075dafa520a48a08b51244f9e2ca4df` PASS:
zgodny backend/journal/config/owner i snapshot wszystkich 14 wejść.
Autoryzacja v2 w wolumenie kontrolnym:
`runtime-services/container-recovery/06e99e63-da04-4190-897e-d30cb8404a6a/operator.json`,
SHA256 `3cf7b4c118249f4a25f1d966f61215b24c9a6e3f26ad9b4ce8e778cbae960a9a`.
Frontend pozostaje uruchomiony do ponownej walidacji pod lifecycle lease.
Recovery, uruchomienie nowego pakietu oraz Solve Universe nadal wymagają wykonania.

## Rzeczywiste recovery v3 i nowa próba naukowa

Managed recovery przez `just docker-dev-recover-container` succeeded.
Development attempt `2c5c5be072564f54a656df0073f42b25`, konfiguracja
`9c648952a1fa638b5f85a75c90c596de6206c18c8cb39d3834aaab43957666ad`.
Nowy backend `597e3116dda99f957d23bfc081c5464a111cdc17629122f98c5ad3af693bb8bf`,
obraz `sha256:b3eb4e5bf434b46acd633e4339962bffbcb9b6ccaac59ce5ebf444c4023cc10c`.
Build aplikacji i walidacja 24 plików pakietu PASS. Źródło:
`2357399e3b337e682bb96dc845202262346e7da4`, snapshot
`1c26e58627276dc9229b1838bf1c70f2bdc72f71d6351ea3a7ebc43b4b1faeb4`.
Cache zależności wykorzystano bez przebudowy CUDA/MFEM.

Natywny receipt requestu
`3ccca87d0dd46c0538b99af9202c36abf319889997104ea38bcafa9631b75a94`
potwierdza `retained_terminal_runs_recovered`. SHA256 receiptu:
`cde2a62b0a0620159a0714d719675be6018d10bfdbe1abc2ce41176e5d59aa5a`.
Owner ready (PID 3526, dzieci 3529/3530), process-tree ready, API health
200/ok. API nie miało aktywnej sesji, więc sam start nie przywrócił
sceny do UI i nie jest dowodem wizualizacji.

Retencja po recovery PASS: 70 plików starego V/J/H, dwa archiwa, sześć
chronionych plików nieudanej próby Universe i niezmieniony FMS użytkownika.
Dowód: `verification/terminal-history-recovery-v3-20261025/retention-after-native-recovery.json`.
Przejściowy błąd połączenia `Wsl/Service/WSAETIMEDOUT` nie był błędem
buildu: Docker Desktop potwierdził brak restartu i gotowość kontenera;
łączność Ubuntu później wróciła. Nie restartowano Dockera/WSL ani buildu.

Jawny publiczny POST retry poprzedniej małej próby został zaakceptowany
202 z catalog revision 347 -> 348. Retry ID:
`surface-rt0-after-recovery-20261025-01`, run
`run-live-255fa587f4084d187d7e690f4d75076a4889fcf685a044ee02e4e8486a06b2da`,
task `task-575d7ffbb1951afb4119ac548f4f51ae6f13682d01e522ccc9e4dea6abcc4e2c`.
Nowy attempt `attempt-37daccd7aa964bc88f6143ad9613ba06`, epoch 2,
worker PID 4333, start_ticks 14316498. Potwierdzono running i rosnący
czas CPU (utime 16304 -> 27426 ticków), nie tylko zapis katalogu.
Przydział: 3000 cpu_millis, 5637144576 B RAM, 7516192768 B storage.

Request/ACK zachowano jako `after-recovery-retry-request.json` oraz
`after-recovery-retry-response.json` w `verification/surface-rt0-performance-20261025`.
Retry używa dokładnie zamrożonych wejść, w tym tych samych SHA siatek:
1865 Tet4 przewodnika i 14 punktów pola, 26110 par. Nie odtwarzano siatki
Gmsh ani nie ponawiano żądania po timeout. Na checkpointcie brak accepted H
i brak artefaktów tego attemptu. Oczekiwanie dotyczy tego konkretnego
żywego procesu; nie uruchamiać kolejnego retry bez rozpoznania jego wyniku.
Pełne Universe i wizualizacja w UI pozostają niezrealizowane.


## Zaakceptowany benchmark i przygotowanie źródła — 25.10.2026

Poprzedni attempt-37daccd7aa964bc88f6143ad9613ba06 zakończył się Succeeded.
Bundle CAS 145824512f55385f015038172929619e6115f27a3ccf3db80e0ce944c810f9ee:
22 payloady sprawdzone; V/J/H skończone, niezerowe i spójne; 14 punktów H,
1865 Tet4. Osiem kontroli publicznego HTTP PASS (jednostki, SHA, ETag 304,
odmowa starego attemptu 409). Raporty w control volume:
verification/surface-rt0-performance-20261025/after-recovery-accepted-vjh-analysis.json
oraz after-recovery-accepted-http.json. Native czas 487.287556356 s.
Universe/UI i kwalifikacja LLG nadal NIEUKOŃCZONE, wynik inspection_only.

Rzeczywisty build FEM to CMake Release, CXX -O3 -DNDEBUG. Załadowana
biblioteka oraz artefakt cache FEM mają ten sam SHA256
f31e500602891ceaff5d0fad61d8aea0601de1361e0fd72e4d8d80ba900814ef.
Nieoptymalizowany cache pod FDM nie jest biblioteką używaną przez runtime.

Optymalizacja surface_rt0.cpp przygotowuje dokładne wejścia, wyznacznik,
outward winding, normalne i krawędzie raz na wywołanie. Kolejność sum,
trzy precyzje i tolerancje pozostają. Walidator noty 0950 PASS; 41 testów
interpretowanych kontraktu PASS. Managed build cf10673f01d04be788d8632db2346048
PASS, API wróciło. Snapshot:
b449e3aac9d713268355bf964d3734cd27620f609eb893912ebdc2fb0efbbe54.
Zgodność wyniku i przyspieszenie po poprawce pozostają NOT VERIFIED.

Nowe zlecenia zachowują te same definition/study/catalog CAS i 1973 assety.
Run run-surface-prepared-source-20261025-01 ma historyczną manualną bramkę
UI, nie jest zmaterializowany i nie wykonał Solve. Publiczne Submit oraz
materialization run-surface-prepared-source-20261025-02 przeszły. Attempt
attempt-56642ebad7874adfa9c9367a8945e319 zakończył się Failed PRZED solverem:
worker odrzuca jawne automatic, dopuszczone przez wspólny start gate.
Zachowano terminalny receipt i historię, nie ponowiono próby bez poprawki.

Poprawka współdzieli ścisły decoder start gate między schedulerem i workerem.
Wersja, zamknięte manual/automatic i kontrola trwałego grantu manual pozostają.
Przygotowano regresję Rust obu trybów i odmów; nie kompilowano testów.
Dalsze kroki: managed build, publiczne retry dokładnie próby 02, ścisłe
porównanie 21 payloadów oraz pełnych diagnostyk trzech precyzji i pomiar czasu.
Skrypt porównania: control volume, ten sam katalog verification,
compare-prepared-source-results.py. Bez zmiany limitów, precyzji lub jakości.

Retencja: wszystkie bieżące pakiety, cache i dowody są potrzebne do
porównania lub rollbacku; nie wykazano zbędnego zasobu do usunięcia.
Nie wykonano prune. Skill fullmag-build-stage-cleanup nie występuje w tym
worktree; zastosowano regułę zachowania danych z build-storage governance.


### Wykonanie po poprawce Start oraz porównanie — 25.10.2026

Managed restart z development attempt 2c5c5be072564f54a656df0073f42b25
zakończył iterację d3b549111d8c4fd29cb99a0f75184f72 kodem 0. Snapshot pakietu:
90ed459db0e923935db35350f334b05bb6fdf72d0775a48a1e6bfabd6f8ce052.
Błędne wcześniejsze użycie identyfikatora iteracji cf106... jako development
attempt odmówiło odczytu przed zmianą usług; właściwy development pin
zachowano. Nie ponawiano buildu po timeout obserwacji.

Publiczne retry z catalog_revision 11 przyjęto 202: run
run-surface-prepared-source-20261025-02, task
task-6376539a6a15f6adad185839fded07d6df010f9fccd615f7e691721072b2f5a8,
attempt-33df698e66944c87b9409baf0200c887, epoch 2. Potwierdzono żywy PID 3453,
start_ticks 14639461 i rosnący czas CPU; następnie Completed i Succeeded.
Nowy pakiet CAS cb8231675d3151513c17047dad6b0c6cf857e473bf1805d8c4ce0a70f7a00fc4.
Poprawkę wspólnego parsera Start zapisano osobno:
f5c9400ea1cc4a0456e4248a0cf8c04e61761f43.

Ścisłe porównanie PASS: wszystkie 21 payloadów poza raportem powierzchniowym
są identyczne bajtowo, w tym V/J/H raw i per-A; pełne dane diagnostyczne
trzech precyzji, limity i tolerancje także identyczne. Operacje wymierne
31 062 533 → 20 491 713, całkowite 585 607 487 → 395 876 894.
Czas operatora 487.287556356 → 418.612782124 s: spadek o 14.0933%, speedup
1.16405. Peak RSS 538046464 → 548306944 B. Nie obniżono precyzji ani jakości.
Jeden pomiar nie stanowi statystycznej kwalifikacji wydajności.
Raport prepared-source-result-comparison.json SHA256:
8e9bd221bf36d4c5fa083cb20e71f564b641136be654560fc1c2a706270fc6c6.
CPP w worktree jest identyczne z cieniem użytym do kompilacji; SHA256:
e548646e81c7963f9bd9cd451e9bc74ed546bc19a95735cf059e1cee69751c50.

Po potwierdzonym wyjściu workera uruchomiono niezależne całkowanie objętościowe
Biota–Savarta zachowanego cell-local J. Rzędy 4/8/12/16/24 i tolerancję
1e-9 A/m + 1e-5 normy H przypięto PRZED wykonaniem. Wynik PASS, exit 0;
wszystkie 14 targetów poza source cells. Maksymalna różnica dla rzędu 24:
5.147751632094446e-11 A/m. Czas 118.00734812399605 s. Weryfikacja nie
przeprowadza ponownie transportu i nie dowodzi inside-source, całego Universe
ani rygorystycznego certyfikatu błędu. Raport independent-volume-quadrature.json
SHA256 247f57869e37d7aae761c4dac9a5246d5024135fd54079865864944e2208a3d0.
Oba raporty i skrypty są zachowane w control volume, pod
verification/surface-rt0-performance-20261025/.

Pełne Universe, wizualizacja i kwalifikacja bazy LLG nadal nieukończone.
Przy aktualnym koszcie nie powtarzać ślepo pełnej próby 1154 targetów z limitem
1800 s. Starszy direct Universe miał odmowę regularnej kwadratury na głębokości
6; nie traktować próby tej samej metody jako nowej naprawy. Następny krok to
optymalizacja arytmetyki/operatora z zachowaniem kontroli błędu, nie zwiększanie
limitów i nie zmniejszanie domeny. Wyniki, historie i cache pozostają.


### Dokładne tożsamości liczników — wykonanie 25.10.2026

Zastąpiono ponowne dokładne iloczyny mieszane w geometry równoważnymi
h*d/S i h. Bez zmiany fizyki, trzech precyzji, formuł i tolerancji.
Regresja Fraction: 540 konfiguracji, 2160 równości, PASS. Walidacja noty
0950 i git diff --check PASS. Managed build iteracji
762850b9674b4e8cb49007b4101ad2be PASS; nie kompilowano testów native/Rust.
Publiczne submit 201 i materialization 200, run
run-surface-exact-identities-20261025-01, task
task-24e0507a41937d7288a6b1e94671da91a47eaa6deb617f0567df6b0705746785,
attempt-3263891a38d64727b56b199e121ec7a4, epoch 1: Succeeded.
Worker PID 3635, start token linux-starttime-14822938, receipt exit 0.
Nowy bundle CAS:
453bb352b0e4ed9458942bfbf13bd5b2a331ba01286c782451227b9e69300a6d.
Output manifest CAS:
271b311068ea27c8965aae5f48fed2076a0a53c77525fee943e544dcd231640d.

Ścisłe porównanie PASS: 21 payloadów identycznych bajtowo, identyczne
pełne diagnostyki precyzji, polityka i tolerancje. Czas operatora
418.612782124 -> 371.592043076 s, speedup 1.1265386057752131;
łącznie o 23.7427596% mniej niż 487.287556356 s przed obiema optymalizacjami.
Operacje wymierne 20 491 713 -> 14 851 953, całkowite
395 876 894 -> 297 494 414. Peak RSS 545902592 B.
Raport control-volume verification/surface-rt0-performance-20261025/
exact-identities-result-comparison.json, SHA256
1a54515b223fc2eb63e25a28708b4003574b5f56faef59a1ccf83c16078fdb9e.
Niezależna objętościowa referencja H pozostaje adekwatna, ponieważ H jest
identyczne bajtowo. Nie powtarzano niezmienionej referencji.
To pojedynczy pomiar 14 targetów, NIE pełne Universe ani wizualizacja UI.
Wszystkie wyniki, receipty, cache i niezacommitowany plik użytkownika
zachowano. Brak wykazanej zbędności danych: bez prune/usuwania.
Następny krok: dalsze obniżenie kosztu dokładnego operatora przed ponowną
pełną próbą; nie zwiększać limitów ani nie redukować domeny/jakości.


### Cache centrowanego prądu — próba w toku 25.10.2026

Poprzedni etap to commit 8cacaa6ad0a117dd3c0d3bbb93e08ca4e3d79c22.
Nowy WIP przygotowuje C=sum(c_i) i M=sum(c_i*(v_i-v_0)) raz na komórkę;
J(t)=[C*(t-v_0)-M]/abs(det). Zachowuje niezerowe C, znaki i wszystkie
instrumentowane operacje. Fraction: 4608 konfiguracji PASS, oba zwroty,
permutacje, skale, translacje, zera i cancellation. Skrajne konfiguracje
Fraction dowodzą tożsamości, nie reprezentowalności wejścia binary64.
Niezależny read-only review: bez błędu kodu; status istniejącego source-map
zmieniono na not_verified do potwierdzenia nowej próby native.

Managed restart tej samej grupy, iteration fa4e4651a4cf49cf84edcd78150e0681,
zakończył się succeeded/exit0. Native make 197342 ms, cache i kontener
zachowane. Nie kompilowano testów jednostkowych native/Rust. Preflight:
465477775360 B wolnych w /build, brak aktywnego workera, zdrowe puste API.
Pierwsza diagnostyka użyła nieistniejącego /health i otrzymała 404; właściwy
odczyt /v2/platform/health potwierdził status ok. Nie zmieniano routingu.

Jedna nowa publiczna próba, submit201/materialization200:
run-surface-centered-current-20261025-01,
task-2e5265a3b7dac09f2d7944374f02d873adb15f53f78f65a39d3fb0e2c3714bf3,
attempt-c2aba7f2916145578846173e3e6d9eb0, epoch1.
Potwierdzono lifecycle running i żywy PID3701, start_ticks15017135,
użytkownik2994 ticks/system334 ticks w chwili obserwacji. Request SHA256:
67ef7e07216a77cc1b3e260e0c7fb766ff1877abac6027cdcc21f00fba2b03c1.
Archiwum, study/catalog i fizyka identyczne z poprzednią próbą; zmieniono
wyłącznie run_id i idempotency_key. Comparator przygotowany PRZED wynikiem:
compare-centered-current-results.py, baseline453bb352b0e4ed9458942bfbf13bd5b2a331ba01286c782451227b9e69300a6d.
Pliki w control-volume verification/surface-rt0-performance-20261025/.
Stan wyniku/przyspieszenia do porównania pozostaje NOT VERIFIED.

Odrębny read-only przegląd kosztu HTTP wykazał minimum trzy wywołania
pełnego walidatora pakietu w jednym GET: study.rs completion,
study_inspection_integrity.rs read_saved_inspection i runner decode.
Metadata17.15s/h_raw336B17.28s/30417.33s vs katalog1.10s i stale4091.34s
pochodzą z zachowanego raportu, nie nowego profilu. Udział funkcji w czasie
jest hipotezą, redundancja jest potwierdzona źródłami. Pierwsza poprawka
powinna współdzielić zweryfikowany wynik w JEDNYM żądaniu, bez publicznego
skip_validation, bez osłabienia completion, CAS hashing i pre/post fence.
Nie zmieniano loaderów, polityki, cache/admission ani API w tym etapie.

Retencja: bieżące/porównawcze pakiety, cache, receipty i historie są potrzebne;
nie wykazano zasobów zbędnych. Bez prune/usuwania. Skill cleanup nadal brak.
Pełne Universe i widok UI pozostają nieukończone.


### Rozstrzygnięcie cache prądu — brak mierzalnego przyspieszenia

Ta sama próba zakończyła się Succeeded; exit workera0, wszystkie21
payloady i pełne diagnostyki numeryczne identyczne. Nowy bundle:
e8e735f33a7a283e05453a29c8fa7477221fa5fbb113ae49d4c52c4b5dde8d0a.
Czas operatora 373.749115756 s wobec 371.592043076 s baseline,
speedup0.9942285544257763. Różnica około0.58% nie dowodzi trwałej regresji,
ale NIE spełnia przypiętej bramki przyspieszenia. Comparator zakończył exit1
na assert no measured acceleration; pozostałe bramki były spełnione.
Nie poluzowano testu ani tolerancji. Zapisano oddzielny raport odrzucenia:
centered-current-result-comparison.json, SHA256
15aac0aebe8e50411289f7fc975d228c1baaaa5338ca934586e3f5063492b79a.
Operacje wymierne14 851 953 ->14 221 583, całkowite297 494 414 ->285 327 154;
redukcja liczby operacji nie przełożyła się na potwierdzony czas.

Zachowano patch tej próby w control volume jako
verification/surface-rt0-performance-20261025/centered-current-rejected-candidate.patch.
Wycofano wyłącznie cztery własne zmiany CPP/noty/source-map/regresji
z bieżącego worktree do HEAD8cacaa6ad0a117dd3c0d3bbb93e08ca4e3d79c22.
Użytkownikowy FMS, wszystkie wyniki i cache pozostają. Pakiet uruchomiony
po próbie nadal zawiera równoważny numerycznie wariant testowy; kolejnym
krokiem jest managed restart przy idle do przywróconego źródła, bez Solve.
Nie traktować tej próby jako kolejnego przyspieszenia lub pełnego Universe.
Potwierdzono rzeczywiste Release/-O3, zgodność CPP ze zbudowanym cieniem
SHA256 b04fddd522b93fd445ec05c332cb959e5efc2e6053bf1b232e8c41e5e3c31046
i mapowanie workera na /opt/fullmag/package/lib/libfullmag_fem.so.0.
MemAvailable około13GB i load2.41 podczas końcowej kontroli nie wskazywały
na brak RAM jako wyjaśnienie kosztu operatora. Nie zmieniano limitów hosta.
Następny istotny kierunek to dokładna arytmetyka/GMP i funkcje wysokiej
precyzji/MPFR, osobno mierzone i jawnie opisane; nie domniemany zysk z
liczników i nie ponawianie pełnego Universe bez rozwiązania kosztu.

Patch eksperymentu SHA256: d7cb7032954f315a45c1efeea83930347fbae450efd47f1a4530d29aa0d88ce7.
