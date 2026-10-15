# Fullmag w całości w Docker Desktop

Ten tryb składa jeden obraz uruchomieniowy zawierający backend API, statyczny
Control Room, publiczny Python DSL, rozszerzenie PyO3 oraz biblioteki FEM/CUDA.
Windows udostępnia przeglądarkę i Docker Desktop. UI i API używają tego samego
portu: `http://localhost:3197/workspace`. Kontener nie potrzebuje checkoutu,
socketu Dockera ani hostowego Pythona podczas uruchomienia.

## Budowanie

Pełną kompilację wykonuje istniejący `Fullmag_build_runner`. Nie uruchamiaj
równoległego ciężkiego buildu przez `docker build` ani hostowy Cargo.
Przed zgłoszeniem sprawdź zdrowie runnera i konfigurację `fem-gpu-release`.
Worktree musi być wcześniej zarejestrowany przez `fullmag_storage.py register`
w ramach cyklu zadania. Źródłem jest pełny SHA commita właściwego checkoutu:

```text
just runner-container-status
just docker-all-build <pelny-sha>
just runner-wait <job-id> 30
just docker-all-image <job-id> <pelny-sha>
```

Zgłoszenie używa obsługiwanej niezależnej kopii niezmiennej kapsuły źródeł,
bez hardlinków do współdzielonego source CAS. Nie modyfikuje ani nie naprawia
obiektów CAS odrzuconych przez kontrolę niezmienności. Job nadal wykonuje
jeden istniejący koordynator, z profilem `fem-gpu-release`. Receipt
`state=submitted` oznacza przyjęcie do kolejki, nie rozpoczęcie ani sukces buildu.
Pole `queue_state_at_submission` dotyczy chwili zgłoszenia; aktualny stan
sprawdzaj przez `runner-status` i `runner-wait`. `build_claimed_at_submission`
sygnalizuje przejęcie joba przez koordynatora, nie uruchomienie kompilatora.
Kod 124 z `runner-wait` oznacza
koniec czasu obserwacji, a nie anulowanie joba.
Przed POST do kolejki zapisuje `submission.json` z `capture_id`, `request_key`
i ścieżką kapsuły. Po timeoutcie stan `submission_unconfirmed` wymaga sprawdzenia
kolejki według `request_key`; nie zgłaszaj ponownie nowego capture, dopóki nie
ustalisz, czy koordynator przyjął poprzedni job.

Ostatnie polecenie nie kompiluje kodu. Sprawdza terminalny receipt, profil GPU,
hashy artefaktów, tożsamość commita i kapsułę źródeł. Następnie składa obraz
offline z przypiętego obrazu toolchaina, całego pakietu release i źródeł DSL.
Wynik zawiera `image_id` oraz ścieżkę `receipt.json` pod resolverowym
`storage/runtimes/<worktree-id>/docker-all-images/<id>`.
Kontekst składania pozostaje pod profilem `storage/builds/<worktree-id>/docker-all-gpu`.
Obraz zawiera pełny toolchain i może być duży; nie jest wersją slim.

## CI: routowanie managed FEM

Workflow `.github/workflows/frontend-3d-managed-fem.yml` zachowuje ten sam
job, środowisko i rzeczywistą bramkę kwalifikacji. Używa dokładnie czterech
etykiet runnera:

```text
self-hosted, linux, x64, ${{ vars.FULLMAG_FEM_RUNNER_LABEL || 'fem-managed' }}
```

Operator może skierować nowy run do lokalnego, ephemeral runnera przez zmienną
repozytorium `FULLMAG_FEM_RUNNER_LABEL=fem-managed-docker`. Taki runner musi
mieć wyłącznie etykiety `self-hosted`, `linux`, `x64` i `fem-managed-docker`;
nie wolno dodawać mu generycznej `fem-managed`, ponieważ przejąłby starsze,
już oczekujące joby. Po wyłączeniu zmiennej workflow wraca do dotychczasowego
`fem-managed`; jest to ścieżka rollbacku i nie wymaga anulowania cudzych jobów.

`fem-managed-docker` zachowuje istniejący kontrakt `linux-ext4-loop-v1`
realizowany w Docker Desktop Linux. Zmienna tylko kieruje job do kolejki;
przed rejestracją i uruchomieniem runnera operator musi potwierdzić dokładny zestaw etykiet, profil Docker, ext4 z `findmnt` i
proweniencją loop/backing, `nsenter`, dostępność NVIDIA oraz wszystkie
prerequisites rzeczywistej bramki CPU/GPU. Sama etykieta ani sonda GPU nie
świadczą o gotowości runnera. Bramka
`run_frontend3d_required_gate.sh managed-fem-qualification` musi przejść w
całości; nie zmieniamy jej warunków, fallbacków, kodów wyjścia ani required
check. Ten routing nie kwalifikuje Windows-folder storage używanego przez
sesje FMS.

## Uruchomienie

```text
just docker-all-start <absolutna-sciezka-do-assembly-receipt.json> 3197
```

Port hosta jest konfigurowalny. W kontenerze zawsze używany jest port `8081`;
publikacja następuje wyłącznie na `127.0.0.1` Windows. Statyczny frontend
korzysta z tego samego originu dla API i WebSocket; nie ma osobnego serwera Node.
Docker Desktop musi używać silnika Linux i udostępniać GPU NVIDIA. Brak drivera
CUDA lub GPU kończy start przed uruchomieniem API. Dostępne urządzenie nie
nadpisuje wyboru CPU/GPU/auto w kanonicznym modelu. Jawne żądanie GPU nie ma
cichego fallbacku CPU; dostępność konkretnych zadań nadal określa capability map
bieżącego Fullmaga.

Kontener uruchamia również kanoniczny runtime service, scheduler i publikatory
puli zasobów. Health wymaga gotowego API oraz runtime service. Budżet kontenera
wynosi 4 CPU i 8 GiB RAM; konfiguracja dzieli go na compute (3 CPU, 6 GiB)
i przygotowanie (1 CPU, 1 GiB), pozostawiając 1 GiB dla API. Nie deklaruje
niezmierzonych zasobów GPU w puli. Bieżąca ścieżka accepted runs obsługuje CPU;
FEM GPU pozostaje dostępny przez istniejącą ścieżkę CLI w tym samym obrazie.
Obecność CUDA nie rozszerza capability map workspace.

Pierwszy start tworzy nowy accepted store. Kolejne starty otwierają kompletny
store; częściowy katalog, obcy owner lub niezgodna konfiguracja wymagają
kontrolowanego recovery. Nie są automatycznie zastępowane.

Start zapisuje Compose i receipt z nazwą projektu, ID kontenera, ścieżką stanu
oraz URL. Stan sesji jest osobnym montowaniem `/state`. Zatrzymanie kontenera
nie usuwa danych. Dla konkretnego projektu z receiptu:

```text
docker compose -f <compose.json> --project-name <compose-project> stop
docker compose -f <compose.json> --project-name <compose-project> start
```

Zatrzymanie najpierw zamyka admission API, następnie żąda drain od dokładnie
tego ownera runtime service i sprawdza terminalne receipty obu dzieci.
Compose daje 60 sekund na tę procedurę. Timeout lub utrata potwierdzenia
pozostawia stan nieznany i dowody do recovery. Nieudany start lub nadzór
zamyka API, zachowuje możliwie działający service i utrzymuje niezdrowy kontener
do jawnego zatrzymania przez operatora; nie wykonuje automatycznego takeover.

## Tryb deweloperski: dwa kontenery

```text
just docker-all-dev <absolutna-sciezka-do-assembly-receipt.json> 3197
```

Compose uruchamia `frontend` (Next.js dev z HMR) oraz `fullmag` (API, Python,
FEM/GPU i runtime service). Oba korzystają z tego samego przypiętego obrazu;
role mają osobne procesy, montowania i budżety. Frontend ma 2 CPU i 4 GiB RAM,
backend 4 CPU i 8 GiB RAM. GPU udostępniane jest wyłącznie backendowi.

Adres przeglądarki pozostaje `http://localhost:3197/workspace`. Port 8080
frontendu publikowany jest na loopback Windows. Backend słucha na 8081
wewnątrz sieci Compose; frontend przekazuje do niego API. Nie wymaga CORS
ani osobnego adresu API w przeglądarce.

Launcher ustala główny checkout przez Git. Jego katalogi Control Room
`app`, `src`, `public` i `scripts` są montowane readonly do frontendu.
pnpm 10.8.1 jest przygotowany offline w obrazie, z narzędzia już obecnego
w przypiętym builderze. Pierwszy start pobiera tylko zależności workspace.
Zapis źródeł w głównym checkoutcie jest wykrywany przez polling Watchpack
(500 ms); Next aktualizuje stronę przez HMR i kompiluje ją przy pierwszym wejściu.
Cold-start ma limit 35 minut, obejmujący instalację zależności z limitem 30 minut
oraz przygotowanie API/Next; zwykły restart używa zachowanych
zależności. Cache, logi i `node_modules` pozostają w osobnym
podkatalogu `state/development` kanonicznego storage Windows. Nie używamy
hostowych `node_modules`, `.env` ani katalogu Git w kontenerze.

Pliki konfiguracji i manifesty zależności są utrwalane przy przygotowaniu
workspace. Ich zmiana wymaga przygotowania nowego workspace; HMR obejmuje
katalogi źródeł. Frontend nie ma montowania accepted store ani certyfikatu
zapisu sesji. Sesje i wyniki zapisuje backend bezpośrednio w swoim `/state`,
mapowanym do rzeczywistego storage Windows.

Zmiana kodu backendu nie wywołuje automatycznej kompilacji ani restartu
symulacji. Jawne żądanie utrwala snapshot głównego checkoutu i zgłasza istniejącą
kolejkę managed GPU release:

```text
just docker-all-dev-backend-build
just runner-wait <job-id> 30
just docker-all-dev-image <job-id> <commit> <source-digest> <native-snapshot-sha256>
```

Wartości tożsamości pochodzą z receiptu zgłoszenia. Edycja podczas capture
powoduje odmowę, późniejsze zmiany nie odrzucają przyjętego snapshotu ani nie
uruchamiają kolejnego buildu. Niezarejestrowane nowe pliki wymagane przez runtime
powodują odmowę zamiast cichego pominięcia; dodaj je do Git przed capture.
Ciężki build jest serializowany z działającymi kontenerami Fullmaga. Przy aktywnym
workspace zgłoszenie pozostaje w kolejce jako `queued`, z przyczyną
`waiting_for_existing_fullmag_container` w stanie koordynatora. Przed wykonaniem
buildu operator musi bezpiecznie zatrzymać własny workspace, gdy jego zadania się
zakończą. Launcher nie zatrzymuje ani nie restartuje runtime'u automatycznie.
Jeżeli runtime pojawi się podczas admission, job może otrzymać `blocked`;
sprawdź jego stan przed kolejną operacją. `docker-all-dev-image` wymaga
terminalnego `succeeded` oraz zweryfikowanych artefaktów.
Nowy obraz nie zastępuje działającego backendu. Zastosowanie wymaga kontrolowanego
uruchomienia. Ten tryb nie deklaruje automatycznego odtworzenia niezapisanego
workspace po zmianie obrazu backendu.

## Storage i granice weryfikacji

Launcher rozwiązuje storage przez `fullmag_storage.py`, przed pierwszym zapisem.
Kontekst składania, logi, provenance, receipty i pliki Compose pozostają w storage
projektu. Nie kopiuje hostowego `.env` ani Git do obrazu. Nie wykonuje prune ani
automatycznego kasowania kontekstu, obrazów lub sesji.

Sesje pozostają bezpośrednio w nowym folderze kanonicznego storage Windows,
montowanym do `/state`. Launcher działa natywnie w Windows i sprawdza lokalny
NTFS/ReFS, wolumen fixed oraz brak reparse points w przodkach. Nie używa wolumenu
nazwanego ani zastępczego katalogu kontenera. Utworzony namespace należy do
Dockera; bieżący natywny writer Windows odrzuca jego marker właściciela.
Do przenoszenia sesji między runtime’ami używaj eksportu `.fms`.

Dla bind mountu 9p (`0x1021997`) wymagany jest jawny `windows-folder-v1`.
Przed API launcher uruchamia i restartuje własny kontener próbny, weryfikuje
native readback oraz dziewięć kontroli: fsync pliku i katalogu, atomic replace,
publikację katalogu, blokadę między procesami, no-follow symlink/junction,
transakcje SQLite i odczyt po restarcie. Certyfikat hosta jest montowany readonly;
grant startowy wiąże go z obrazem, źródłem, binariami i bieżącym mount namespace.
Domyślna odmowa 9p pozostaje w mocy poza tym konkretnym profilem i folderem.

Te kontrole dopuszczają operacyjne użycie folderu. Nie dowodzą odporności na
utratę zasilania ani restart całej VM Docker Desktop. Power-loss pozostaje
`NOT VERIFIED`, zgodnie z istniejącym kontraktem trwałości Fullmaga.

Zielony receipt składania obrazu oznacza tylko złożenie sprawdzonych artefaktów.
Health API nie dowodzi działania canvas/WebGL, symulacji FEM GPU ani poprawności
naukowej. Te bramki wymagają osobnych dowodów. Lokalny zakaz kompilowania testów
jednostkowych pozostaje w mocy; użytkownik dopuścił wyjątek wyłącznie dla CI
tego zadania.
