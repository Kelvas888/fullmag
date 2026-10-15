# Bramka scheduler cancellation dla E2/E4

Data: 07.10.2026. Status: **NOT RUNNABLE — brak kompletnej, wspieranej ścieżki inicjalizacji i startu v2**.

Nie dodano harnessu uruchomieniowego. Poniższy odczyt poprzedzał implementację
inicjalizatora hosta; opisuje ustalony brak i wyprowadzony z niego następny
krok. Zarządzany `runtime_service_main` nadal odrzuca konfigurację host execution
v2. Uruchomienie samego schedulera poza service ownerem nie zamyka bramki
pełnego lifecycle usługi.

## Istniejąca ścieżka schedulera

`accepted_scheduler_main.rs` wczytuje opcjonalne `--host-service-config` i jego SHA-256, a następnie `HostRuntimeAdmission::for_scheduler` wiąże konfigurację z dokładnym store, pulą i limitem concurrency (`crates/fullmag-api/src/accepted_scheduler_main.rs:178-181,288-314`). `HostRuntimeAdmission::open` sprawdza v2 binding i otwiera wskazany ledger przez `HostResourceLedger::open`; nie tworzy go (`crates/fullmag-runtime-control/src/host_runtime.rs:515-547`).

Przy aktywnym host admission pętla schedulera wywołuje `reconcile_task_cancellations` (`crates/fullmag-api/src/accepted_scheduler_main.rs:392-402`). Ta ścieżka odczytuje trwałe intent, a dla taska `Accepted`/`Queued` deleguje projekcję do ledgeru (`crates/fullmag-runtime-control/src/host_runtime.rs:677-704`; `crates/fullmag-session/src/host_resource_ledger.rs:1190-1210`). To właściwy proces produkcyjny do sprawdzenia E2/E4: intent zarejestrowany przez API, następnie projekcja przez rzeczywisty scheduler, bez claimu i bez solvera.

`runtime_service_main` ma ścieżkę przekazania configu i jego digestu do dziecka schedulera (`crates/fullmag-api/src/runtime_service_main.rs:346-394`), lecz przed startem ownera bezwarunkowo odrzuca `host_execution` (`crates/fullmag-api/src/runtime_service_main.rs:646-658`). Komunikat wymaga ukończenia recovery, owner lifecycle, topology i enforcement gates. Ten guard pozostaje obowiązujący. Bezpośrednie uruchomienie binarium schedulera mogłoby ominąć właściciela usługi; nie spełniałoby wymogu uruchomienia przez wspieraną ścieżkę runtime service.

## Brakujący initializer

Istniejący verifier API wywołuje `fullmag.exe runtime initialize-scoped-accepted-store`, a później seeduje syntetyczny RunSpec, intent i katalog tasków (`scripts/windows/verify_compute_cancellation_api.py:137-168,282-396`). To inicjalizuje SessionStore dla testu HTTP, nie host ledger ani v2 service config.

`HostResourceLedger::initialize` jest dostępnym Rust API (`crates/fullmag-session/src/host_resource_ledger.rs:1637-1683`), ale odczytane wywołania znajdują się w `#[cfg(test)]` fixture. Produkcyjna ścieżka host admission używa `open` (`.../host_resource_ledger.rs:1685-1693`). Istniejący initializer konfiguracji aplikacji w `runtime_service_client.rs:184-210` korzysta z `application_service_config`; ten tworzy `runtime_service_config.v1` z `host_execution: None` (`crates/fullmag-runtime-control/src/local_resources.rs:14-48`). Nie znaleziono produkcyjnego CLI/managed recipe, który utworzyłby scoped host policy, ledger oraz przypięty do niego config v2.

## Minimalny następny krok

1. Dodać produkcyjny, zarządzany initializer scoped host execution, który przyjmuje jawne CPU-only policy/topology i placements, otwiera właściwy scoped store, tworzy ledger przez `HostResourceLedger::initialize` oraz zapisuje zwalidowany `runtime_service_config.v2` powiązany z tym store i ledgerem. Powtórzenie musi odczytywać i porównywać zapisany policy/config; nie może po cichu próbować ponownie próbkować zasobów ani odtwarzać brakującego stanu.
2. Udostępnić start v2 przez `runtime_service_main` dopiero po ukończeniu wskazanych przez guard bramek recovery, owner lifecycle, topology i enforcement. Accepted scheduler uruchamiany w tej bramce musi być dzieckiem tego service ownera.
3. Dodać verifier managed, który na tak utworzonym store zarejestruje cancellation przez istniejące API, obserwuje rzeczywistego schedulera i sprawdza terminalne `Cancelled` przy pustych polach claim/attempt/resource oraz zgodny ledger. Seedowane metadane fixture trzeba oznaczyć jako synthetic; to nie jest dowód Submit, fizyki ani kwalifikacji solvera.

Późniejszy managed component gate rzeczywiście uruchomił API, producenta puli
oraz accepted scheduler. Dowód nie uruchamia `runtime_service_main` v2 i nie
zamyka owner lifecycle całej usługi. Pełny service/recovery oraz fault-injection
gate pozostają **NOT VERIFIED**.

## Inkrement inicjalizacji w źródłach

Dodano wejście CLI `runtime initialize-host-application --config --config-sha256`
oraz inicjalizator przypiętej konfiguracji i ledgera. Kontrakt opisuje sekcja
13.29 specyfikacji, a status kontroli zapisuje implementation-checkpoint.
Nie oznacza to odblokowania v2 ani wykonanego testu schedulera. Następną
bramką pozostaje start przez runtime ownera z wymaganymi dowodami lifecycle,
recovery, topologii i egzekwowania zasobów.

Inicjalizator przeszedł następnie rzeczywistą bramkę natywną: 26 kontroli na
przypiętym pakiecie, bez uruchomienia usługi lub schedulera. Dowody i dokładny
zakres opisuje [host-initialization-check-20261007.md](host-initialization-check-20261007.md).
Pierwszy prerequisite ma odbiór inicjalizacji; standalone API→scheduler
projection również przeszło. Pozostają owner lifecycle, start usługi, jej
drain/recovery oraz egzekwowanie zasobów.

## Odbiór komponentu API → scheduler

Przypięty pakiet przeszedł managed build verification. Następnie bramka
`verify-compute-scheduler-cancellation` ukończyła 21 kontroli: dwa żądania
Accepted/Queued przez HTTP, natywną publikację puli, dwa procesy schedulera
z jawnym `stdin-v1` drain, terminalne Cancelled i idempotentny replay po
rewizji katalogu 5. Host ledger pozostał pusty, bez claimów i checkpointu.
Szczegóły, receipt i ograniczony zakres opisuje
[scheduler-cancellation-check-20261007.md](scheduler-cancellation-check-20261007.md).
