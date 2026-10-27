# Terminalna sesja: odzyskanie po błędzie OCI przed PID1

## Cel i zakres

Próba c037af6df84448b1ba6576157b822914 zatrzymała się w hooku NVIDIA
przed nowym PID1. Zachowała terminal-session-preflight.json i backend-drain.json,
ale nie checkpoint saved-authoring. Bazowy development attempt
37062974a42f4ad4aec3976df9dfafe6 jest failed-confirmed; nie wolno przepisywać
jego historii. Autentyczny succeeded publication witness to iteration
94ca9bf8ff37455a939d416150c3b10a, wskazywany również przez iteration/verified.json.

Nowy wariant obejmuje terminalny current run, obecnie Failed
run-live-62d110763485b10e2512922267a1aed284996710852d4fd27cb3f4ad71a1e496,
i zachowanie dwóch accepted runów z ręcznym, niezwolnionym startem.
Nie obsługuje prepared current run, nie odtwarza authoring i nie uruchamia Solve.
Stary saved-authoring v1 pozostaje osobną ścieżką ze swoim prawdziwym checkpointem.

## Kontrakt i mapowanie źródeł

Nowy moduł scripts/docker_volume_terminal_prestart_recovery.py definiuje
zamknięty schemat fullmag.docker-terminal-prestart-reconciliation.v1.
Request zachowuje wspólne piny source/config/controller/trzech kontenerów
z docker_volume_reconcile.validate_request. Dodaje prestart_helper_sha256,
failure, prior_publication, history_baseline i observation.

failure wiąże raw SHA drain, preflight i pierwotnego development terminal receipt,
kanoniczne SHA stanów backend/frontend oraz raw SHA dokładnego błędu NVIDIA.
prior_publication wiąże attempt i raw SHA immutable successful iteration terminal;
musi on być bajtowo równy iteration/verified.json i odnosić się do dokładnego
base/config/source/image/kontenerów/StartedAt oraz sealed package receipt.
Nie przyjmuje dowolnej starszej udanej próby resume.

history_baseline ma kontrolną ścieżkę JSON, raw SHA i ID zapisanego runu.
Rzeczywisty operator baseline jest w
verification/master-runtime-62f222-20261027/state-before.json:
43 katalogi, 1391 plików zapisanego runu i 2 pliki odzyskanej solution.
To dowód operatorski tych konkretnych plików, nie natywne poświadczenie
wszystkich historycznych journals. Publiczne run.revision jest wersją stanu API,
nie rewizją run_catalog. Świeży recovery_store_sha256 ustanawia osobny baseline.

## Bramki wykonania

validate_failure wymaga unchanged StartedAt/fingerprint z kontrolera,
backend exited/Pid0/exit128 z dokładnym hookiem NVIDIA, frontend exit0,
braku nowego backend_started_at, publikacji builda/provenance operacji
i checkpointu authoring. Istniejący _read_terminal_process_receipt uwierzytelnia
drain wobec persisted ownera. service_owner i terminal_service_owner muszą
wskazywać tego samego ownera i dzieci.

build_observation używa krótkiej usługi diagnostycznej we własnej grupie Compose.
Aktualny sealed package, control/runtime-control i wybrany source są readonly.
Nie ma candidate overlay, publikacji provenance, /build, /user-data, GPU,
sieci ani socketu Dockera. State i ledger mają zapis wyłącznie dla istniejących
natywnych writer guards; ich dowody nie są zmieniane. Zachowuje się dokładne
mounty i podkatalogi wolumenów. Ponieważ probe pomija normalny entrypoint,
wywołuje wyłącznie image-owned _configure_device_access w trybie CPU,
zachowując istniejącą trasę biblioteki /usr/local/cuda/compat bez hardware
preflight, stubów lub host driver bind. Obecność tej trasy nie dowodzi,
że prawdziwy native proof już zadziałał. Reuse _released_snapshot jawnie odmawia,
gdy state/ledger mają nieobsługiwany volume-subpath.

Istniejące runtime service-inspect-terminal-run jest jedynym źródłem natywnego
terminal digest, retry i preparation/resource evidence. Python nie dekoduje
wyników naukowych. Sprawdza raw hashes, rzeczywiste specification.parameters
run_intent, accepted_run_start_policy.v1/manual i brak start_release.json.
Zbiór held IDs musi dokładnie odpowiadać kolejce z przypiętego preflight.
_released_snapshot zachowuje shared-lock host-before-store i durable release proofs.

Sealed receipt/provenance muszą zgadzać się w schema/state, raw receipt SHA,
obrazie, commit/source/native snapshot, toolchain i pełnym binary inventory.
Przed i po inspector pliki naukowe są identyczne. Rootowy WRITER.owner.json
jest zmiennym advisory, ale wymaga pełnego rozpoznanego schematu, canonical
UUID, PID/host/timestamp i released=true. Inventory ma limit 32768 plików/1 GiB
i hashuje strumieniowo.

## Reconcile, retry i completion

Nowy reconcile jest wyłącznie failure-only: nie publikuje iteration/verified.json.
Preview sprawdza dowody bez przejęcia pierwotnej blokady. Apply ponawia je
pod istniejącym observer protocol. continuation zwraca jawny terminal_history;
nie tworzy zmyślonego authoring checkpointu. Pod resume lease ponownie
sprawdzane są stare package/config/provenance oraz cała observation.

Po zarządzanym starcie może legalnie powstać nowy pakiet aktualnych źródeł.
Istniejący _finish kwalifikuje receipt/source/image/storage/process/readiness.
Osobny terminal_completion_gate otrzymuje ponownie przypięte raw SHA jego
bieżącej publikacji, native config i StartedAt. Nowe runtime piny muszą
dokładnie odpowiadać tej kwalifikacji; obcy lub niekwalifikowany pakiet
jest odrzucany. Native terminal digest, history, held intents i released
resource snapshot muszą pozostać identyczne. Dopiero potem kończy się lease.
Udany restart nie oznacza automatycznego przywrócenia sceny do bieżącej sesji.

## Weryfikacja i granice dowodu

Dedykowane testy scripts/test_docker_terminal_prestart_recovery.py sprawdzają
schematy, mounty, rzeczywistą Python PROBE na małym store z atrapą native CLI,
manual admission, zmiany podczas odczytu, malformed writer/provenance,
publication/continuation CAS oraz kwalifikowaną nową generację.
Stare testy v1 uruchamia się osobno tą samą receptą offline.

Na etapie przygotowania nie wykonano prawdziwego native proof, reconcile,
restartu ani Solve. Runtime proof i preview pozostają NOT VERIFIED do
niezależnego review i osobnego zarządzanego uruchomienia. Testy Rust nie są
kompilowane. Recepta just docker-dev-offline-check używa zatrzymanej własnej
grupy, sourceRO/controlRW, bez danych użytkownika i GPU.
