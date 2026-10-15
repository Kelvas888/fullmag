# Docker Windows — FEM GPU w Workspace/API

Data: 15.10.2026. Status: W TRAKCIE / runtime NOT VERIFIED.

## Cel i decyzje użytkownika

Dokończyć dwa kontenery developerskie: frontend HMR z głównego checkoutu lub
zarejestrowanego worktree oraz backend budowany na żądanie. Sesje i wyniki
pozostają bezpośrednio w rzeczywistym storage Windows. Tylko frontend publikuje
port hosta; backend komunikuje się po prywatnej sieci Compose. Użytkownik
rozszerzył zakres o rzeczywiste FEM GPU w Workspace/API, obok istniejącego CLI.

Zachowujemy jeden Python DSL, ProblemIR, planner, API v2 i workspace. Nie
zmieniamy fizyki ani natywnych operatorów: obowiązują noty 0410 i 0960, backend
golden masterplan oraz aktualne ograniczenia capability matrix. Pierwszy
accepted producer GPU respektuje ograniczenia H1/P1, double, strict i
final_state/total_energy istniejącego adaptera; unsupported workloads pozostają
jawnie odrzucone. Jawne GPU nie może wykonać CPU. Requested auto pozostaje
zapisane, a resolved device wynika z legalnego planu i faktycznie przydzielonego
zasobu. CPU zachowuje własny istniejący kontrakt i recovery.

## Etapy i kryteria odbioru

1. Naprawić prywatnego wykonawcę CI: pinned Buildx, kontrola przed JIT i
   rzeczywisty reproducer COPY --chmod. Następnie wykonać niezmienioną
   managed FEM qualification z CUDA 12.6.3 i fizycznym NVIDIA GPU. Zachować
   pobrane warstwy, compiler cache, backing ext4 i logi nieudanych prób.
2. Po przeglądzie kontraktów zapisać ADR 0060 dla accepted FEM GPU. Powiązać
   pojedyncze fizyczne GPU i rzeczywisty VRAM z ofertą, lease, host ledger,
   workerem i execution identity. Nie publikować zasobów wymyślonych ani
   podwójnie wydawać tego samego CPU/RAM/GPU. Runtime service pozostaje
   właścicielem lifecycle i publikacji zasobów.
3. Rozszerzyć accepted FEM adapter i snapshot/recovery: immutable request,
   preparation i plan, preflight przed started receipt, natywny GPU runner,
   rzeczywisty native execution receipt, osobna tożsamość GPU state i ten sam
   wspólny Start/heartbeat/Stop/completion protocol. CPU snapshot v1 oraz
   publiczne kodeki zachowują kompatybilność. Nie konstruować GPU evidence z
   samego planu, CUDA visibility lub nazwy silnika.
4. Sprawdzić capability/transport i konsumentów. Wykorzystać istniejące zasoby
   v2 i typed outputs; zmieniać OpenAPI oraz generowane typy tylko przy
   rzeczywistej zmianie schematu. W jednym workspace wykazać GPU allocation,
   accepted run, końcowe native provenance i odczyt opublikowanego wyniku.
5. Zbudować końcowy backend i frontend przez istniejącą kolejkę na jednym
   commit/snapshot. Uruchomić oba kontenery, wykazać HMR po zapisie pliku
   Windows, poprawny WebGL, połączenie API, GPU execution oraz zachowanie
   zapisanego FMS i jego hashy po normalnym stop/start. Wymagane CI/review,
   commit/push/PR/merge, bezpieczny fast-forward głównego checkoutu i qualified
   cleanup własnego worktree kończą cykl.

## Uruchomienie skryptu w Dockerze — doprecyzowanie użytkownika

Polecenie wskazujące skrypt ma zachować istniejący kontrakt Fullmaga:
Workspace od razu przedstawia załadowany, aktywny model. Przygotowanie modelu
oraz siatki poprzedza Solve. Symulacja uruchamia się automatycznie według
skryptu, chyba że interaktywny skrypt ma `wait_for_solve=True`; wówczas
przygotowany model czeka na Compute. Nie wolno bezwarunkowo wymuszać headless,
zmieniać authored auto na CPU ani omijać wspólnego ledgeru GPU.

Launcher ma tłumaczyć ścieżkę Windows względem wybranego readonly checkoutu.
`docker compose run fullmag <ścieżka>` nie jest obecnie działającym
interfejsem: usługi aplikacji to frontend/backend, a ich entrypoint uruchamia
Workspace. Implementacja i dowód startupu skryptowego są osobnym wymaganym
etapem. Skrypt `tests/vlad/4.5GHz_fem.py` zawiera `device=auto`, wiele etapów
BB/PG-BB i długą symulację anteny; prosty bounded LLG proof nie kwalifikuje
jego całej sekwencji.

## Weryfikacja i granice

Lokalnie nie kompilujemy testów jednostkowych. Wyjątek użytkownika obejmuje
wyłącznie CI tego zadania. Regresje obejmą niewłaściwy lease/GPU binding,
CPU fallback, brak lub mismatch native receipt, zachowanie requested auto,
CPU compatibility oraz recovery bez ponownego solver side effect. Interpretowane
kontrole Python, parsery, formatowanie i przegląd nie zastępują wykonania GPU.
Managed runtime i browser proof są osobnymi bramkami. Udane wykonanie bounded
workload nie jest ogólną kwalifikacją fizyki FEM GPU.

Historyczne blokery przed rozpoczęciem tego rozszerzenia: bootstrap CI ma jeden
nieudany test batcha (1101 PASS), a tymczasowy runner nie zawierał Buildx.
Diagnoza i naprawa tych przyczyn są częścią tego samego zadania. Cudzy dirty
master, procesy, cache i wyniki pozostają zachowane.


## Stan bramek i dowody odbioru

| Obszar | Obecny dowód | Wymagane do odbioru |
| --- | --- | --- |
| Konfigurator nowego hosta | PR #174 scalony do mastera `f9179caf`; skrypt istnieje lokalnie i na GitHub | Pełny bootstrap toolchaina/runnera na czystym hoście pozostaje osobnym etapem |
| Compose i storage | Wersjonowane definicje, kontrole parsera, host ledger i regresje interpretowane | Realny start dwóch usług, odczyt plików Windows i restart |
| Toolchain FEM/CUDA | Naprawione CPU SLEPc/PETSC_ARCH, prywatna etykieta wykonawcy CI | Udana managed FEM qualification na poprawionym obrazie |
| Zgodność źródeł i CI | `eigensolve-method-contracts` i `dispersion-artifact-consumers` przeszły dla `ea2a659` | Wymagane kontrole dla końcowego commita |
| Polecenia live CPU/auto/GPU | Powstaje adapter accepted i czysta migracja legacy z pełnymi zasobami | Kompilacja w CI, admission, lifecycle i wynik w tym samym Workspace |
| FEM przygotowanie / wait_for_solve | Trwa podłączenie kanonicznego przygotowania live | Widoczny aktywny model i siatka przed Compute, bez solver side effect |
| Uruchomienie skryptu | Kontrakt i ograniczenia opisane powyżej | Ścieżka Windows, aktywacja, auto-run oraz wariant wait_for_solve |
| Frontend HMR i WebGL | Definicja source bind i przygotowane procedury dowodowe | Zapis pliku w Windows widoczny w przeglądarce, zachowanie stanu i żywy WebGL |
| FDM/FEM GPU | Source admission, worker i receipt nie stanowią runtime proof | Formularz → fizyczny GPU → terminalny wynik, native receipt i zwolnienie lease |
| Integracja | Pozostałe zmiany w PR #175, master zachowany z cudzym dirty submodule | Review/CI, merge, lokalny fast-forward i qualified cleanup |

Aktualizując tę tabelę, zachowujemy rozdział konfiguracji, kompilacji, runtime,
przeglądarki i walidacji naukowej. Stan jednej bramki nie promuje pozostałych.
