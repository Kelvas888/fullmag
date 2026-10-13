# Odbiór natywnej inicjalizacji hosta

Data: 07.10.2026. Wynik: **PASS — inicjalizator konfiguracji i ledgera**.
Pełny E2/E3/E4 i cały E0–E7 pozostają w realizacji.

## Potwierdzone zachowanie

Zarządzana próba uruchomiła rzeczywiste komendy natywnego CLI w ośmiu
odrębnych magazynach utworzonych przez `initialize-scoped-accepted-store`.
Następnie użyła `initialize-host-application --config --config-sha256`.
Polityka CPU i digest topologii były jawnymi danymi syntetycznego fixture.
Rekordy ownera, launchera i admission fence były testowymi metadanymi;
nie stanowią dowodu działania ani zatrzymania prawdziwego ownera.

26 kontroli przeszło: 25 kontroli fixture i jedna kontrola kanonicznego
eksportera OpenAPI. Potwierdzono:

- publikację APPLICATION.json i pustego host ledgera oraz prawidłową
  tożsamość config/store/host/policy/epoch/topology;
- `execution_available=false`, bez deklarowania gotowego wykonania;
- dokładne ponowienie z identycznymi bajtami konfiguracji i ledgera;
- odrzucenie zmienionej konfiguracji i błędnego pinu;
- odrzucenie kandydata v1 oraz zachowanie wcześniej zapisanej konfiguracji v1;
- zachowanie częściowego ledgera i przypiętej konfiguracji także po retry;
- odmowę przy OWNER.lock, OWNER.json, LAUNCH.json i zamkniętej development
  admission, bez publikacji nowej konfiguracji lub ledgera.

Native guardy mogą tworzyć trwałe pliki mutexów. Kontrole odmowy porównują
stan aplikacji/ledgera i chronione rekordy, zamiast utożsamiać powstanie
prawidłowego mutexu z mutacją konfiguracji. Wrong-pin odrzucany przed otwarciem
store zachował całą jego strukturę. Ścieżka store była kanoniczna dla Windows;
pin odpowiadał typowanej reprezentacji serde, pomijającej puste pola polityki.

Wszystkie 20 zarejestrowanych procesów CLI mają potwierdzone wait/exit;
kontrola CIM po próbie nie znalazła żadnego z tych PID. Oczekiwane odmowy
zakończyły CLI kodem 1, a cała bramka zakończyła się kodem 0. Eksporter API
wykonał tylko `--print-openapi-v2`, bez uruchamiania serwera. Nie uruchamiano
usługi, schedulera, workerów ani solvera.

## Tożsamość źródeł i pakietu

HEAD: `1ee35b19e4a0e28da31ed5b9e52097d8b01919f8`, shared master/dirty.
CLI source gate `fdeda604052d433c81896a44661d6dbb` i sześciobinarny API/service
source gate `eb034451076148bc8a4bd1bae725337d` przeszły z exit0 i bez zmiany
źródeł podczas kontroli. Hashe zmienionych źródeł odpowiadają receipt oraz
faktycznie zbudowanemu snapshotowi. Testów Rust nie kompilowano ani nie uruchamiano.

Build `just windows-workspace-build dev dev 3197 auto` zakończył się exit0;
log `native-build-b417e9db3c904228852d66cfdab28998.log`. Pierwsze oczekiwanie
odmówiło przed startem; ponowienie nastąpiło dopiero po potwierdzonym zwolnieniu
blokady i zakończeniu jej procesu.

| Identyfikator | SHA-256 |
|---|---|
| Utrwalona fizyczna kopia źródeł | `f4198af9fbf1f9225d85a92aef3a12cdd5b7b55530a94e158851c67a8ad8ddf0` |
| Build/version source snapshot | `54a2e56d64b786f7bdb7f49f3f48a9099e8833db0d2763776ffcb4ac36bec8ce` |
| Backend ready fingerprint | `9c6bb771ba1612c17eaa446a4d7185ad92d5d0210f3893cd88e06837bb7017c6` |
| Manifest przypiętego pakietu | `0d5df1073bba5900909e577e5809d5b9f8124375490ee09ad645f7ef78fbb2cb` |
| Fixture verifier | `224b83303df5ce3f626daefbc29f2ef76bd78f6b9da7897537f26b7fdeb54ed6` |

Pełna wersja: `0.1.0-dev.20261007.g1ee35b19e4a0.dirty.s54a2e56d64b7+9776`.
Sam licznik 9776 nie identyfikuje pakietu; bramka przypina pełny manifest.

## Powtarzalna bramka i artefakty

```text
just verify-compute-host-initialization 0d5df1073bba5900909e577e5809d5b9f8124375490ee09ad645f7ef78fbb2cb
```

Receipt: `C:/git/fullmag/storage/builds/fullmag-0950f4dca4ffe38f/development-backend-api-checks/checks/6b7c3dfa0e1f4033a26e8b65e96e70c5/receipt.json`.
Ten sam katalog zawiera `compute-host-initialization-evidence.json`, logi CLI,
wejścia fixture i kanoniczny `openapi-v2.json`. Receipt wiąże wykonanie
z `verified_frozen_native_package`; nie przenosimy dowodu na późniejsze edycje.

## Otwarte bramki

Nie jest to dowód fizycznego NodeSnapshot, rzeczywistego owner lifecycle,
konkurencyjnego startu usługi, terminalnego scheduler cancellation/release,
CPU/GPU enforcement, Submit, równoległych sweeps, distributed solve ani
kwalifikacji naukowej. Startup guard konfiguracji v2 pozostaje aktywny.
Następny etap obejmuje podłączenie i odbiór owner lifecycle, topologii,
egzekwowania oraz recovery przed odblokowaniem usługi.
