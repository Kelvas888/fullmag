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
