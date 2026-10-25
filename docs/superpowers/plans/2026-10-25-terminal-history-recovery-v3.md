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
