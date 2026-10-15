# Architektura developerska Fullmaga w Docker Compose

Uzgodnienie użytkownika: 16.10.2026. Status: kontrakt docelowy; bezpośredni
build/start obu usług jest w implementacji, runtime NOT VERIFIED.
Ten dokument określa nowy tryb developerski. Wcześniejsza procedura budowania
przez Fullmag_build_runner nie jest warunkiem tej ścieżki.

## Źródła i usługi

Projekt Compose nazywa się `fullmag` i zawiera dwie usługi aplikacji:
`backend` oraz `frontend`. Jedna wartość `FULLMAG_SOURCE_ROOT` wybiera główny
checkout albo konkretne worktree. Obie usługi otrzymują bind mount tego samego
checkoutu; źródła pozostają na hoście, edytowane zwykłym edytorem Windows.
Checkout ma być montowany readonly dla procesów aplikacji. Zależności oraz
wyniki kompilacji nie mają zaśmiecać źródeł.

| Element | Odpowiedzialność |
| --- | --- |
| `frontend` | Instalacja przypiętych zależności JS wewnątrz kontenera, Next.js dev, HMR i proxy do backendu |
| `backend` | Budowa pełnego Fullmaga wewnątrz kontenera, API, Python DSL i procesy wykonawcze |
| Toolchain | CUDA i pozostałe narzędzia oraz biblioteki natywne; budowane przez Docker, współdzielone warstwy/cache |
| Prywatna sieć Compose | Frontend łączy się z `backend:8081`; backend nie publikuje portu hosta |
| Port frontendu | Jeden konfigurowalny port loopback hosta; przeglądarka korzysta z UI i API pod jednym adresem |

Backend zawiera FDM CPU, FDM GPU, FEM CPU oraz FEM GPU. Rodzinę solvera oraz
urządzenie wybiera dopiero konfiguracja symulacji i planner. Nazwa istniejącego
Dockerfile `docker/fem-gpu/Dockerfile` opisuje toolchain, nie ograniczenie całej
aplikacji do FEM. Wymuszone GPU nie może przejść niejawnie na CPU. Obecność
wszystkich wariantów w buildzie nie potwierdza obsługi dowolnej kombinacji
fizyki ani poprawności jej wykonania.

## Cykl edycji i przebudowy

Pierwszy start przygotowuje obrazy narzędziowe, kompiluje backend oraz instaluje
zależności i uruchamia frontend. Kompilatory i instalatory działają wewnątrz
odpowiednich kontenerów, bez starej kolejki runnera.

Zmiana pliku frontendu na hoście jest od razu widoczna przez bind mount.
Next.js wykrywa zapis i uruchamia HMR. W Docker Desktop wykrywanie zmian wymaga
właściwej konfiguracji watchera, w razie potrzeby pollingu; rzeczywisty zapis
pliku Windows musi to potwierdzić.

Zmiana backendu nie uruchamia kompilacji ani restartu automatycznie. Użytkownik
jawnie zleca przebudowę backendu. Ta operacja pobiera aktualny stan wybranego
checkoutu i kompiluje go w kontenerze z zachowaniem cache Cargo i kompilacji
natywnej. Build używa zamrożonych wejść danego żądania, aby edycje podczas
kompilacji nie mieszały wersji. Checkout nadal pozostaje zamontowany na żywo.
Pomyślny build nie może sam zatrzymać aktywnej symulacji; zastosowanie nowego
pakietu wymaga kontrolowanego restartu.

Obraz narzędziowy i pakiet aplikacji są osobnymi warstwami. Zmiana kodu Rust
nie powinna wymuszać ponownego budowania CUDA, hypre, MFEM czy libCEED.
Zwykły restart kontenera nie usuwa cache. Zmiany zależności lub flag mogą
wymagać szerszej kompilacji; cache nie gwarantuje pominięcia każdego kroku.
Dokładne polecenia będą opisane po uruchomieniu bezpośredniej ścieżki; starsze
polecenia oparte na job ID i assembly receipt nie stanowią jej instrukcji.

## Skrypt symulacji jako parametr startu

Start przyjmuje opcjonalny parametr `--script`, wskazujący plik Python wewnątrz
wybranego checkoutu. Ścieżka względna jest rozwiązywana względem
`FULLMAG_SOURCE_ROOT`; ścieżka absolutna musi wskazywać plik w tym samym drzewie.
Hostowa ścieżka Windows jest mapowana na zamontowane źródła kontenera.
Ścieżka względna, zawartość i hash skryptu należą do provenance uruchomienia.

Po starcie przeglądarka pokazuje Workspace z modelem tego skryptu jako aktywnym.
Wykonanie zachowuje semantykę autora: zwykły skrypt uruchamia symulację,
a interaktywny `wait_for_solve` przygotowuje model i siatkę oraz czeka na Compute.
Sam serwer HTTP lub wczytany tekst skryptu nie dowodzi aktywacji modelu.
Start bez skryptu otwiera Home; nie wybiera sam przypadkowej sesji.

## Dane i wersje

Sesje, modele, wyniki oraz logi pozostają w rzeczywistym storage Windows,
wybranym w lokalnym `.env` przez `FULLMAG_PROJECT_STORAGE_ROOT` i bind mount.
Nie zastępujemy tego storage ukrytym wolumenem Docker Desktop. Zachowujemy
walidację dostępu i trwałości zapisu Windows.

Cache zależności i buildów jest trwały, oddzielony od wyników i jawnie
zdefiniowany w konfiguracji. Może używać natywnego systemu plików Linux dla
wydajności; nie przenosi to sesji ani wyników z Windows. Ten sam cache nie
może być równolegle modyfikowany przez nieskoordynowane buildy.

Deklaracje wersji bibliotek natywnych pozostają w kanonicznym
`docker/fem-gpu/Dockerfile`; obraz publikuje rzeczywiste wersje i commity w
`/opt/fullmag-deps/share/fullmag/dependency-versions.json`. Frontend korzysta z
przypiętych wersji narzędzi i lockfile. Nowy tryb nie tworzy drugiej,
niezależnej listy wersji.

## Warunki odbioru

1. Bezpośredni start dwóch usług w projekcie `fullmag`, bez zgłoszenia joba runnera.
2. Pełny backend zbudowany w swoim kontenerze, frontend uruchomiony w swoim.
3. Home widoczny w przeglądarce oraz działające połączenie z API pod tym samym adresem.
4. Zapis źródła Windows powoduje HMR; jawna kolejna przebudowa backendu używa cache.
5. Sesje i wyniki są widoczne w wybranym rzeczywistym storage Windows po restarcie.
6. Start ze skryptem aktywuje właściwy model i respektuje interaktywny `wait_for_solve`.
7. Osobne dowody wykonania CPU/GPU; sam build, wykrycie GPU i HTTP 200 nie są takim dowodem.

## Kolejność wdrożenia — stałe numery zadań

1. Zapisać uzgodnioną architekturę.
2. Zdefiniować w Compose dwa serwisy, źródła, storage, sieć i port.
3. Przygotować obraz narzędziowy.
4. Podłączyć wybór checkoutu/worktree i przygotowanie źródeł backendu.
5. Uruchomić trwały cache kompilacji backendu.
6. Zbudować pełny backend: FDM/FEM, CPU/GPU.
7. Uruchomić frontend Next.js z montowanych źródeł.
8. Uruchomić oba kontenery w grupie `fullmag`.
9. Sprawdzić widoczny Home i komunikację UI–API.
10. Potwierdzić HMR po edycji pliku w Windows.
11. Potwierdzić przyrostową przebudowę backendu bez utraty cache.
12. Sprawdzić parametr skryptu, aktywację modelu, wykonanie GPU i zapis wyników w Windows.
13. Uzupełnić instrukcję, przeprowadzić wymagane CI/review i scalić na `master`.

Aktualizacje postępu używają formatu „Zadanie X/13”. Numery oznaczają stałe
etapy, nie deklarację ich ukończenia; dowody i bieżący stan trafiają do
checkpointu zadania w rozwiązanym storage.
