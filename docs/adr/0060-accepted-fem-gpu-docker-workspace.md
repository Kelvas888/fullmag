# ADR 0060 — accepted FEM GPU w developerskim Workspace Docker

Status: przyjęte do implementacji; kwalifikacja runtime **NOT VERIFIED**.
Data: 2026-10-15.

## Kontekst

Obraz z CUDA i działający managed CLI nie wystarczają do wykonania zadania GPU
przez formularz Workspace. Wersja profilu Docker v1 publikuje wyłącznie CPU,
a adapter accepted FEM z ADR 0045 obsługuje tylko CPU. Użytkownik wymaga obu
usług developerskich i rzeczywistego GPU z jednego publicznego Workspace.
Sesje i wyniki mają pozostać bezpośrednio w storage Windows.

## Decyzja

Rozszerzamy istniejący accepted FEM adapter o GPU; wspólny worker zachowuje
Start/Prepare, heartbeat, Stop, durable completion i publication. Numeryka
pozostaje w natywnym backendzie `backends/fem`; adapter wywołuje kanonicznego
runnera z niezmiennym planem i `StageFemMeshIdentity`. Jeden Python DSL,
ProblemIR, planner i API v2 nadal obsługują FDM/FEM oraz CPU/GPU.

Requested `cpu` lub `gpu` musi zgadzać się z rzeczywistym lease. `auto` pozostaje
w authored intent; jawny override managed launchera wskazuje przydzielony
resolved device. Brak zgodnego lease, natywnego runtime lub dowodu urządzenia
kończy preflight przed solver side effect i `started receipt`. GPU nie może
spaść do CPU. Pierwszy adapter GPU obejmuje H1/P1, double, strict, time evolution
i LLG-overdamped relaxation z istniejącej capability map. Inne minimizery,
nieobsługiwane outputs oraz niezakwalifikowane kombinacje pozostają odrzucone.
Nie promujemy przy tym statusu naukowej walidacji żadnej fizyki.

GPU worker wymaga aktywnego host launch binding zweryfikowanego przez wspólny
`HostResourceLedger`, dokładnego lease i jednego fizycznego UUID. Supervisor
ogranicza widoczność do tego UUID, a runner używa ordinału 0 w ograniczonym
środowisku. Nazwa zasobu ani sam plan nie są dowodem urządzenia. Readiness GPU
wymaga rzeczywistego natywnego probe; polityka hosta wiąże kanoniczną topologię,
aktualny inventory i budżety. Brak lub utrata tych dowodów zamyka admission,
zachowując istniejące rezerwacje i obowiązek kontrolowanego recovery.

Stan GPU ma osobny wersjonowany envelope
`fullmag.fem.gpu.accepted-state-snapshot.v1`. Cztery primary carriers wiążą
natywne wartości, mapę lokalnych węzłów, indexed geometry oraz typed native
execution receipt wraz z przydzielonym UUID. Receipt musi dowodzić strict
`device_resident`: zgodnych masek required/resolved/executed, pustych masek
host/unknown, zera fallbacków i transferów compute w hot loop. Pozytywny krok
i zegar pochodzą z natywnego snapshotu. Recovery odczytuje bounded immutable
`m_final.json`, ponownie dekoduje receipt i porównuje odtworzony envelope;
nie uruchamia solvera ponownie. CPU zachowuje własny schema v1 i carriers.

Wspólny ledger hosta używa oddzielnego profilu `host-ledger-v1`: ext4 backing
pod kanonicznym `storage/build-volumes`, zarządzany mount i bind `/host-ledger`
wyłącznie w backendzie. Nie rozszerzamy sesyjnego grantu `windows-folder-v1`
na globalny ledger ani nie tworzymy ukrytego named volume. Jednorazowy helper
montowania jest narzędziem utrzymania; frontend i backend pozostają dwiema
usługami aplikacji. Frontend nie otrzymuje ledgeru, GPU ani accepted store.

## Migracja poleceń live w Dockerze

Backend Docker nie ma konsumenta starszej kolejki live. Dlatego w tej trasie
zarówno CPU, GPU, jak i `auto` przechodzą przez istniejący accepted pipeline.
Natywny launcher zachowuje dotychczasową trasę legacy; rozpoznanie trasy należy
do granicy API, a nie do czystego helpera aplikacyjnego.

Dla sceny bez zadeklarowanego profilu adapter używa kanonicznego, pustego
`ExecutionProfileIR::default()` (`exec:default@1`). Wybory autora trafiają do
jawnej warstwy `Study` lub `Script`, łącznie z `auto` i pełnym
`ComputeResourcesIR`. Profil nie może ukrywać domyślnego CPU ani nadpisywać
zasobów. API jawnie publikuje lub odczytuje niezmienny profil w katalogu;
niezgodny istniejący hash lub konflikt rewizji kończy admission. Efektywna
kopia sceny użyta do materializacji nie zmienia po cichu sceny autora.

Helper migracyjny nie czyta hosta, nie zapisuje storage i nie tworzy UUID GPU.
Starszy ordinal nie staje się tożsamością fizycznego urządzenia: pojedynczy
ordinal 0 oznacza wyłącznie dopuszczalny indeks po ograniczeniu widoczności
przez przydział hosta. Żądanie wielu GPU lub innego ordinału jest odrzucane.
`MeshBuild` i `FdmGridRefresh` pozostają przygotowaniem modelu, bez Solve;
Run/Relax wymagają osobnego accepted admission oraz publikacji do istniejącego
live read model. Sam helper migracyjny nie potwierdza wykonania tych etapów.

## Granica aktualnej implementacji UI

Durable accepted task i bieżący journal komend live Workspace są odrębnymi
ścieżkami. Ten etap dodaje GPU do workera accepted; nie podłącza automatycznie
komend formularza `mesh/run/relax/solve` do tego workera. Backend Docker
uruchamia obecnie API i runtime service, bez owned konsumenta live command
queue. Wpięcie formularza wymaga kanonicznej materializacji task/lease oraz
committed host allocation przed uruchomieniem solvera; ta część jest nadal
**NOT IMPLEMENTED**. Samo dodanie attached CLI ominęłoby wspólny ledger CPU/GPU
i nie jest dopuszczonym rozwiązaniem. Uruchomienie skryptu z aktywnym modelem
oraz `wait_for_solve` pozostaje osobnym niezakończonym etapem. Nie należy
przedstawiać obecnego Docker Workspace jako gotowego do Compute z formularza.

## Kontrakty i konsumenci

Zmiana korzysta z istniejących typed study outputs, accepted-state reference,
resource pools, compute profiles i wspólnego runtime status. Nie dodaje
oddzielnego endpointu FEM GPU, transportu komponentowego ani drugiego viewportu.
OpenAPI i wygenerowane klienty zmieniają się tylko w razie rzeczywistej zmiany
publicznego schematu; sam nowy producer nie uzasadnia ich ręcznej edycji.
FDM GPU korzysta z istniejącego workera i tego samego host allocation boundary;
jego pełna ścieżka formularz → GPU → wynik wymaga osobnego dowodu.

Właściciele implementacji:

- `accepted_fem_study_worker` — przygotowanie i wykonanie accepted FEM;
- `accepted_fem_gpu_state::FemGpuAcceptedStateSnapshotV1` — identity/recovery;
- `FemGpuExecutionReceipt::validate_strict_device` — istniejące native reguły;
- runtime service, compute-node probe i host ledger — admission i lifecycle;
- launcher Docker, wersjonowane Compose i resolver — mounty i provenance.

## Migracja i rollback

ADR 0045 nadal określa CPU. Ten ADR rozszerza wyłącznie accepted GPU i host
execution scope, którego ADR 0059 nie kwalifikował. Profil CPU v1 pozostaje
kompatybilny; jawny profil hosta v2 wymaga nowych bramek. Nie przejmujemy
istniejącego ownera, częściowego ledgeru ani sesji o innej konfiguracji.
Rollback zamyka admission nowego profilu i zachowuje backing, sesje, logi oraz
receipty. Nie zastępuje GPU ofertą CPU i nie restartuje działającej symulacji.

## Weryfikacja

Wymagane są regresje request/lease/auto, UUID i launch binding, niepełnych lub
hybrydowych native receipts, topology/freshness, recovery oraz zgodności CPU.
Kompilacja unit tests odbywa się wyłącznie w CI tego zadania, zgodnie z wyjątkiem
użytkownika. Do odbioru potrzebny jest końcowy managed build frontendu i backendu,
realne zadanie FEM GPU przez API, FDM GPU z formularza, terminal release,
browser/HMR/WebGL oraz FMS save/reopen/restart z odczytem plików Windows.
Source checks, wykrycie GPU ani build obrazu nie zastępują tych dowodów.
