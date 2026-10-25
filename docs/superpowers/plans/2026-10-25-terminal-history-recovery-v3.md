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
