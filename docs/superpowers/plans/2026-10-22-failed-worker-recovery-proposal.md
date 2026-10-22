# Finalizacja znanego błędu zakończonego workera — propozycja do review

Status: przygotowany patch, bez kompilacji lokalnych unitów Rust i bez wykonania
recovery. Aktywacja wymaga nowego pakietu, CI, konkretnego requestu i decyzji operatora.

## Rzeczywisty stan i sprostowanie wcześniejszej hipotezy

Run `run-live-91ade96632da3c92902cd0143337a9496518ff29ea45ab0bc22313d44421eee4`,
task `task-66fae1a7f6c10925710e8005c7e5f13fbbf33637188579e901155328d41c2904`,
attempt `attempt-0c249de9f08745c2946dcb0f6d7017bc`, epoch1.
Worker4087 rzeczywiście wystartował i został reaped po błędzie certyfikatu Pioli,
exit1. Oryginalny receipt ma stop_requested=false i heartbeat18.
Owner `9270e44f-357c-4053-a3da-7416d8fb5096` ma Failed i terminalne dzieci.
Task pozostał Running/Reconciling, lease i host reservation są aktywne.

Dokładny trwały inbox ma **pending=null**. Prepare seq1, Start seq2 oraz heartbeat1–18
(seq3–20) są już applied. Commands journal ma jeden dodatkowy command21:
heartbeat19, bez wpisu inbox i bez ACK. Historical claim w started execution receipt
ma heartbeat0; nie wolno porównywać go na równość z final lease18 ani przepisywać.
Błąd final heartbeat zakończył supervisor przed terminalizacją i host release.

Wcześniejsza hipoteza o pending Start była błędna. Nie zastosowano na jej podstawie
żadnej operacji. Tryb recovery poniżej **odrzuca pending Start**. Istniejące durable
recovery supervisora może przy tym rzeczywistym pending=null ominąć wcześniejszy
błąd i terminalizować exit. Standalone supervisor CLI nie udostępnia jednak pełnych
owner/config/package pins ani host release; nie jest używany jako obejście lifecycle.
Wąski adapter operatora zachowuje deterministic Failed/DoNotRetry i pełne pins;
nie przenosi polityki spawnu/retry z supervisora. Nie refaktoryzuje jego normalnej pętli.

## Zakres i zgodność

Nowa jawna opcja istniejącego `fullmag-runtime-service --fail-reaped-worker`
finalizuje wskazany znany błąd jako Failed(retryable=false), bez retry.
Nie tworzy API, nowego proof ani schematu SessionStore. Nie zmienia no-spawn,
orphan teardown ani zwykłego Stop. Starsza binarka odmówi nieznanej opcji.
Nie potwierdza Start ani heartbeat, nie uruchamia solvera, nie zmienia exit receiptu,
nie usuwa częściowego Zarr, katalogu attemptu, logów, CAS ani wyników.

## Warunki i kolejność

1. CLI wymaga raw SHA bajtów requestu. Request przypina config, pełny Failed owner,
   aktualny installed package receipt i binarkę, build commit/source snapshot,
   exact store/run/task/attempt/epoch/resource/token, final lease, reservation,
   task katalogu, commands/events prefix, inbox i oba receipt: reaped exit i
   historyczny started execution. Źródła starego ownera pozostają przypięte
   osobno od źródeł nowego narzędzia recovery.
2. Blokady startup, launch i OWNER są utrzymane przez operację. Wymagane są
   terminalne compute/preparation oraz API exit z zachowanego process-tree.json,
   będącego kanonicznym sąsiadem configu. Boot ID, PID namespace i hostname muszą
   odpowiadać oryginalnemu kontenerowi. Zarządzana aktywacja przypnie także container ID.
   Brak procesu sam nie stanowi dowodu zakończenia.
3. Wymagany jest jeden Start, Started, inbox.pending=null i inbox.applied równy
   dokładnie commands prefix bez ostatniego command. Wszystkie wcześniejsze
   heartbeat mają ACK; final lease odpowiada ostatniemu ACK. Jedyny tail command
   to następny heartbeat, nieobecny w inbox/events. Completing, Completed,
   Stopped, Failed, Rejected, Stop i Release w dotychczasowym prefixie blokują tryb.
4. Katalog zawiera tylko dokładnie wskazany Running/Reconciling task, bez artifact IDs.
   Canonical artifact catalog musi być pusty lub nieobecny. W exact attempt nie
   może istnieć worker_execution_completed.v1.json — nawet malformed albo symlink.
   Właściciel accepted workera zapisuje ten receipt przed study output publication,
   więc sam brak artifact catalogu nie wystarcza. Started receipt musi zgadzać się
   z historycznym Start i tym samym, ewentualnie odnowionym final claimem.
5. Pod store writer publikowany jest deterministic Failed event związany z requestem
   i exit receipt digest. Następnie istniejący immutable FmsRetryDecision zapisuje
   ExplicitOperatorRequest/DoNotRetry. Replay dopuszcza wyłącznie ten event i decyzję,
   również po crashu między nimi. CLI raw request SHA i canonical_request_sha256
   dokumentu są rozróżnione w wynikach i journal reason.
6. Dopiero po trwałym Failed i DoNotRetry następuje release dokładnego final lease.
   Store writer zostaje zwolniony przed istniejącym release_worker_after_exit:
   zachowany zostaje lock order HOST→STORE oraz rzeczywisty receipt+Released proof.
   Nie są dodawane alternatywne powody release ani wyjątki od host ledger fence.
7. Immutable slot-owner ma raw SHA, exact PID i process-start token compute schedulera.
   Kanoniczny helper supervisora używa tego samego owner codec, nazwy resource slot
   i observera process_start_token co normalne stale-slot recovery. Dopiero po
   Failed, DoNotRetry, exact receipt, lokalnym Released i host proof przenosi cały
   slot do runtime-services/reaped-worker-recovery/<request-id>/supervisor-slot.
   Linux rename bez nadpisania zachowuje wszystkie bajty; replay potwierdza oba
   directory fsync. Dwa położenia, inny owner, dodatkowe pliki lub żywy proces blokują.

Nested writes tego samego SessionStore handle/thread są jawnie wspierane przez
crates/fullmag-session/src/writer.rs (depth). Regresja używa tego samego handle;
nie utrzymuje store writera przy wejściu w host ledger.

## Konkretny dowód odczytu

Wszystkie poniższe pliki znajdują się w wolumenie kontrolnym pod
`/opt/fullmag/control/verification/public-loop-solve-fixed-binding-20261022/`.

| Plik | SHA256 / ustalenie |
|---|---|
| reaped-worker-recovery-read-only-inventory.json | d0b4ce433fb867b54d9159dc379dc8455bd6bb12a34da7ce17526dc2f0823745 |
| reaped-worker-actual-inbox.json | 1ba3d8315c9920a6354d2bd1b5660048edaf3a45fab68f2790f11cdfc6e41ff8 |
| reaped-worker-recovery-observed-fields-only.json | 9dac5b9bf1a9b9bb6d9c39b6b18928d4f10827d5f3aab288d0b5788691e1430a |
| Started execution receipt | 7b0d6c942872cc9f32f333122459e7229afde67fe218fbe6cdbfd21c13640f69 |
| Supervisor slot owner | 1556112ac3c3af1d850125e1b9f25691d59ae2f91f6c21d29c914a74c7d8f89d |

Inwentarz obejmuje 11 wpisów częściowego Zarr i jeden plik exact attemptu.
Sprawdzono kanoniczne artifact_catalog.json (brak), run_catalog artifact_ids=[]
oraz exact completed execution receipt (brak). Wszystkie istniejące pliki wyników
mają zapisane ścieżki, rozmiary i hashes. Inbox.applied==commands[:-1] sprawdzono
na rzeczywistych zapisach, bez modyfikacji store. Wrapper observed-fields-only jest
celowo niezgodny z CLI request schema i nie zawiera przyszłych promoted tool pins.
Nie jest zgodą na wykonanie.

## Regresje i aktualne ograniczenia dowodów

Przygotowano sześć testów Rust: rzeczywisty kształt applied Start i różnica
HB0/ACK1/tail2; replay po samym Failed, DoNotRetry i lokalnym release; niezmienione
inbox/receipt/partial result; odmowa completed receipt bez artifact catalogu;
zmienione inbox/journal/started pins i niezgodne exit/success/Stop/timeout/epoch/
heartbeat; dokładna progresja reservation; slot archive replay; osobna odmowa
ambiguous pending Start bez mutacji. Testy używają tego samego kodu co runtime.
W bootstrap rust-contracts dopięto filtr do istniejącego explicit --bin harness.

Wykonano parse Rust przez rustfmt --emit stdout (bez kompilacji) i git diff --check.
Testów Rust NIE SKOMPILOWANO ani NIE WYKONANO lokalnie. Pełny pozytywny CLI,
rzeczywisty host release i archiwizacja są NOT VERIFIED. Odmowy niewymienione
w powyższych testach (np. pełne owner/package/namespace CLI refusal) pozostają
bramką konkretnego requestu, nie są przedstawiane jako wykonane regresje.

## Aktywacja i zgoda

Przygotowanie patcha/review jest autoryzowane. Konkretna aktywacja zmienia politykę
operatora względem istniejących komend: trwale finalizuje rozpoczęty failed attempt
i archiwizuje jego slot. Poprzednia zgoda no-spawn nie obejmuje Started. Wymagana
jest osobna decyzja dla konkretnego requestu i raw SHA po zbudowaniu/promocji
narzędzia, review i CI. Nie przygotowano pozornej zgody z placeholderami pakietu.

## Osobny zakres: zwykły błąd naukowy

Worker powinien publikować Failed(retryable=false) tylko dla rozpoznanego błędu
naukowego przed accepted output publication. Supervisor po durable Failed i
rzeczywistym reaped receipt mógłby zwolnić exact lease bez dopisywania applied Start
ani brakującego heartbeat. Nie każdy exit1 jest takim błędem: partial publication,
nieznany CAS i crash przed terminalnym eventem pozostają fail-closed.
Osobne testy muszą rozróżniać scientific failure, publication failure, crash,
sukces i opóźniony heartbeat. Tego zakresu obecny patch operatora nie implementuje.


## Korekta przeglądu requestu i kompilacji

Oryginalny wrapper observed-fields-only nie jest requestem CLI i zawierał
błędnie wybraną zwolnioną rezerwację preparation o tym samym run/task.
Nie zastosowano go. Dokładne dopasowanie musi obejmować solver owner,
attempt/epoch, compute resource i lease token; sam run/task nie wystarcza.
Poprawione obserwacje: reaped-worker-recovery-observed-solver-fields-only.json,
SHA256 6731c6a39c9bd5b8076657a17888a0ca6558e79ddcfc88d10549b04f5e235255.
Wskazują docker-all.compute.cpu, Active lease18 i Committed reservation;
canonical reservation SHA256 bc7ace1ac7178a4c173512201add9c7a0214c3e35c745d9f6ccae53c264b520b.
Oryginał pozostaje zachowany jako dowód korekty, bez zgody aktywacji.
Guard Request::validate odmawia preparation identity; nie poluzowano go.

CI oraz zarządzany build pakietu d423ef7fe5b0fcbab7c8c45457a7462f3c6ee60f
wykryły E0599: HostRuntimeAdmission::open zwraca Result<Option<Self>>.
Poprawka wymaga Some przez istniejące anyhow::Context i odmawia przy braku
host_execution, bez panic lub zmiany wspólnego API. Parser PASS;
recovery-optional-host-admission-fix.json zawiera dowód i rozważone rozwiązania.
Wymagany jest nowy udany build i wykonanie CI; nieudany kandydat nie będzie
promowany. Pełne runtime recovery nadal NOT VERIFIED i niewykonane.
