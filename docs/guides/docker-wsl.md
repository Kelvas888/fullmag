# Fullmag w Docker z Linux i WSL

Ten sam `setup_docker.py` obsługuje Windows, Linux i WSL. Na natywnym Linux
oraz w WSL wybiera trasę `linux-native-v1`, opisaną w tym przewodniku.
Dla natywnego Windows używaj [przewodnika Windows](docker-new-windows-host.md).
Używa istniejących recept Docker i natywnego writera Linux. Pełny cold-start,
HMR w przeglądarce, zapis/ponowne otwarcie sesji oraz wykonanie solvera GPU na
obu wariantach hosta pozostają **NOT VERIFIED**. Zapis konfiguracji ani widoczność GPU
nie są dowodem tych zachowań.

## Wymagania

Uruchamiaj polecenia w powłoce Linux lub WSL, z checkoutu Git na lokalnym systemie plików
Linux. Checkout, storage i wybrany worktree muszą używać ext4, XFS albo Btrfs.
Katalogi pod `/mnt/c`, DrvFS/9p, CIFS/SMB, NFS, symlinki w ścieżce oraz storage
należący do innego projektu nie spełniają tego kontraktu. Ścieżka `~/git` jest
ścieżką WSL; nie przekazuj jej jako ścieżki natywnego Windows.

Potrzebne są Python co najmniej 3.10, Git, `just`, `findmnt`, działający Docker
z silnikiem Linux, plugin Compose i dostęp do NVIDIA. Na natywnym Linux wymagany jest dostępny Docker Engine. Przy Docker Desktop
w Windows włącz integrację używanej dystrybucji WSL. Z tej samej powłoki sprawdź:

```bash
python3 --version
git --version
just --version
findmnt -T . -n -o FSTYPE
docker version
docker compose version
docker info --format '{{.OSType}}'
nvidia-smi
```

`docker info` musi zwrócić `linux`. Brak `just` blokuje recepty; kreator nie
instaluje narzędzi. Dostępność `nvidia-smi` nie potwierdza dostępu solvera do GPU.

## Kreator i storage

Z katalogu głównego checkoutu:

```bash
python3 -B scripts/setup_docker.py
python3 -B scripts/setup_docker.py --check
```

Wskaż własną bezwzględną ścieżkę storage poza checkoutem. Kreator
zapisuje `FULLMAG_PROJECT_STORAGE_ROOT` w lokalnym `.env` głównego checkoutu
oraz wybór checkoutu i portu w `index/docker-host-settings.json` storage.
Zachowuje inne ustawienia i sekrety; pokazuje plan przed zapisem i nie przejmuje
obcego ani niepustego niezarejestrowanego storage. Worktree korzystają ze wspólnej
konfiguracji przez resolver, bez kopiowania `.env`.

`--check` niczego nie zapisuje. Kod `0` oznacza pozytywną kontrolę konfiguracji
i wymaganych narzędzi. Kod błędu wymaga usunięcia wskazanej przyczyny; nie jest
sygnałem do ręcznego omijania preflight. Kreator nie buduje obrazów, nie
inicjalizuje koordynatora i nie uruchamia aplikacji.

## Build i start dwóch usług

Nowy Docker Engine nie dziedziczy obrazów, cache ani konfiguracji runnera z
Windows lub innego hosta. Przed buildem wymagany jest istniejący, zdrowy
`Fullmag_build_runner` z aktywnym `fem-gpu-release` i lokalnym zweryfikowanym
obrazem workera/toolchaina. Kontrakt i konfigurację opisuje
[lokalny runner kontenerowy](local-container-runner.md). Nie uruchamiaj drugiego
koordynatora dla worktree ani ciężkiego buildu poza kolejką. Recepty budowania
obrazów koordynatora/workera wskazują kontekst `desktop-linux`; sam kreator
nie przygotowuje tego kontekstu ani nie bootstrapuje nowego hosta. Na natywnym
Linux również wymagają świadomie przygotowanej konfiguracji koordynatora;
przewodnik nie zakłada obecności Docker Desktop. Jeżeli runner nie jest jeszcze
przygotowany, zapis storage przez kreator nie odblokowuje poleceń build/start
poniżej.

Uruchom z checkoutu zawierającego implementację WSL:

```text
just runner-container-status
just docker-all-dev-backend-build
just runner-wait <job_id> 30
just docker-all-dev-image <job_id> <commit> <source_digest> <native_snapshot_sha256>
just docker-all-dev <assembly_receipt> 3197
```

Wstaw tożsamości zwrócone przez zgłoszenie; `assembly_receipt` jest ścieżką
receiptu składania obrazu. Do składania przejdź po terminalnym `succeeded`.
Kod 124 z `runner-wait` kończy obserwację; dalej sprawdzaj ten sam job.
Pusty argument `source_root` wybiera główny checkout. Dla zarejestrowanego
worktree przekaż tę samą bezwzględną ścieżkę jako argument `source_root` we
wszystkich trzech receptach developerskich. Checkout i port zapisane przez
kreator przekazuj jawnie, jeśli różnią się od domyślnych.

Launcher używa `compose.dev.yaml`: frontend publikuje port na `127.0.0.1`,
backend jest dostępny tylko w prywatnej sieci Compose. Otwórz
`http://localhost:3197/workspace`; dostęp z przeglądarki Windows zależy również
od przekazywania localhost przez używaną konfigurację WSL/Docker Desktop.
Źródła są montowane readonly, HMR obserwuje frontend, a backend pobiera
zweryfikowany pakiet. Build nie restartuje działającej symulacji.

Storage jest bezpośrednim bindem do `/state`. Hostowy preflight sprawdza lokalny
system plików Linux, a kontener potwierdza typ swojego montowania; eksport
Windows/9p jest odrzucany. Trasa nie używa certyfikatu `windows-folder-v1`,
Windows native readback ani zastępczego named volume. Receipty, logi, provenance
i sesje pozostają w kanonicznym storage. Zatrzymuj własny projekt wskazany w
receipcie; nie stosuj globalnego prune ani kasowania cache.

## Granice dowodów

Health API i terminalny build nie dowodzą wykonania GPU, działania WebGL ani
poprawności naukowej. `just docker-all-verify` nadal sprawdza specyficzny kontrakt
Windows-folder/9p i nie jest bramką kwalifikacji `linux-native-v1`. WSL wymaga
osobnych dowodów rzeczywistego runtime, przeglądarki, zapisu i restartu sesji oraz
solverów. Odporność na utratę zasilania i restart całej VM pozostaje
**NOT VERIFIED**. Decyzję o rozdzieleniu tras opisuje
[ADR 0060](../adr/0060-docker-linux-native-session-storage.md).
