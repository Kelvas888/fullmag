# Przegląd audytu Docker DEV — uproszczenie ścieżki uruchamiania

Data: 21.10.2026. Aktualizacja: 02:00 CEST. Stan źródeł: master
`8729dd0700b5992dac35b22f57f46d257d57cd9a`; ostatni wykonany build pochodzi
z `6c5a9792f6046bfb7b7cff85dbea7252760c3ea2`.
Przeczytano cały `2026-10-21-docker-dev-workflow-audit.md` i zweryfikowano
bezpośrednio niżej wymienione mechanizmy. Bez testów. Nie powtarzano pełnego
zliczania LOC, historii commitów ani inspekcji obcych grup Docker.

## Wniosek i schemat kontenerów

Główny wniosek audytu jest uzasadniony: codzienny start ma zbyt wiele zależności
od recovery i identyfikacji buildu. Istotny problem leży w orkiestracji oraz
sprzężeniu stanu buildu ze stanem symulacji. Dodawanie kolejnych stałych usług
nie usuwa tego sprzężenia.

Docelowo zachować dwie stałe usługi tej samej grupy checkoutu:

- **backend**: trwały cache i cień źródeł w named volumes, przyrostowy build
  aplikacji, następnie API/native runtime; jeden właściciel procesu i jeden
  koordynator start/stop;
- **frontend**: ten sam readonly checkout, Next/HMR, osobne named volumes
  zależności i `.next`, połączenie z prywatnym `backend:8081`.

Obraz przypiętych zależności nadal przygotowuje BuildKit. Nie dodawać osobnej
usługi `backend-build`. Sesje, wyniki i projekty zachować na skonfigurowanym
storage użytkownika. Kwalifikacja/release może korzystać z pełnej zamrożonej
ścieżki dowodowej; codzienny DEV powinien mieć prostszy cykl bez ręcznych pinów.
To rekomendacja architektury, nie deklaracja wdrożonej migracji.

## Co potwierdzono i co wymaga korekty w audycie

| Wniosek | Ocena na bieżących źródłach |
|---|---|
| Capture dwukrotnie odczytuje checkout i kończy start przy różnicy | Potwierdzone: `backend_source.py::capture_live_source_manifest`, linie 1664–1667. To bezpośrednia przyczyna ostatniego exit 2 |
| Readonly Git z `autocrlf=true` i `GIT_OPTIONAL_LOCKS=0` | Potwierdzone: `backend_source.py::_live_git_command` i `_live_run_git`. Czasy statusu pochodzą z wcześniejszych logów, nie z nowego benchmarku |
| Snapshot jest wejściem kompilacji | Potwierdzone m.in. przez `fullmag-build-info/build.rs:12` oraz przekazanie tożsamości do CMake FEM. Koszt relinkowania należy mierzyć po zmianie, nie zakładać stałej liczby sekund |
| Kandydat po przerwanym buildzie blokuje start | Potwierdzone: `backend_dev.py` odrzuca niepustego kandydata o stanie innym niż ready (okolice linii 3444) |
| Globalny limit 64 prób na fazę | Warunek jest w `docker_build_control.py:508`. Przycinania nie potwierdzono; to problem projektu retencji, nie uzasadnienie skasowania historii |
| Nadzór ma 30 s tolerancji | Potwierdzone: `runtime_service.py:89`. Sam timeout obserwacji nie dowodzi śmierci API ani solvera |
| Commit 72cd5efcd ustawia Cargo tylko na 4 | Wymaga doprecyzowania: 4 jest bazą Compose dla quota 4 CPU; `apply_saved_budget` ustawia w tej grupie **16**, zgodnie z profilem 128 GiB / 16 CPU. Odczyt środowiska działającego Cargo potwierdził 16; nowy Make zakończył się exit 0 |
| Usunięcie retencji z krytycznej ścieżki nie jest wykonane | Usunięcie synchronicznego wywołania było już w commicie 01cb8ed1; stary uruchomiony obraz go nie zawierał. Źródło i obraz trzeba odróżniać |
| Status pięciu grup oraz liczba wolumenów | To snapshot z czasu audytu; nie traktować go jako stale aktualnego stanu hosta |
| Zyski 1,5–2×, 3–4× i pętla poniżej 2 minut | Hipotezy do pomiaru, nie wyniki. Czas buildu może dominować I/O, nvcc, linkowanie albo zależności sekwencyjne |

Pierwsza próba `recreate-volume` z `72cd5efcd` skończyła się przed zmianą usług:
`pre-admission recreation cannot replace native recovery authority`.
Przyczyną jest skierowanie już uwierzytelnionego `PreApiContext` do wzajemnie
wykluczającej się ścieżki wymagającej pustego native recovery context.
Poprawka dotyczy istniejącego wyboru gałęzi, bez nowego modułu recovery,
resetu ownera ani ponownego Solve.
Po poprawce gałęzi recreate zakończyło się powodzeniem; późniejszy build
przeszedł. Nadal nie ma dowodu gotowości API ani meshu.

## Rekomendacje, których nie wdrażać dosłownie

1. **R0.4 — nie kontynuować po niespójnym capture z fałszywym manifestem.**
   Uprościć kopiowanie: zmaterializować wejście w ext4 i identyfikować rzeczywiste
   bajty użyte do kompilacji. Zmiana live checkoutu po przygotowaniu tej kopii
   nie powinna unieważniać rozpoczętego buildu; następny build obejmie nowe
   zmiany. Samo usunięcie porównania dwóch manifestów nie zapewnia tego kontraktu.
2. **R0.3 — przenieść tożsamość do runtime jako spójną migrację.**
   Usunięcie `rerun-if-env-changed` przy pozostawieniu wartości wbudowanej
   w binaria może raportować stary commit dla nowych bibliotek. Trzeba
   równocześnie zmienić producenta i konsumentów, w tym API↔CLI, i oddzielić
   tożsamość artefaktu od tożsamości bieżącej sesji.
3. **R0.9/R2.8 — kwarantanna niedokończonego kandydata zamiast kasowania.**
   Zachować ostatni opublikowany pakiet, log błędu i wymagane dane rollback.
   Automatyczne usunięcie kandydata lub wszystkich starych backupów nie wynika
   z obecnej zgody i nie dowodzi ich zbędności.
4. **R2.3/R2.5 — martwy PID albo kontener nie wystarcza do wyczyszczenia
   globalnego ledgera lub unknown activation.** Zwolnienie musi dotyczyć
   dokładnie jego runu/lease i nie może naruszać obcej grupy. Jedna przyjazna
   komenda może automatycznie odkrywać te dane; operator nie powinien ręcznie
   przepisywać UUID/SHA. Nie musi to oznaczać resetowania ownerów.
5. **R1.6 — współdzielić pobrania, zachować rozdział niezgodnych natywnych
   artefaktów.** Cargo registry i pnpm store są dobrymi kandydatami na wspólne
   named volumes. Usunięcie toolchainu z klucza natywnego CMake/target bez
   zastępczej walidacji ABI i zależności MFEM/CUDA może użyć starej biblioteki.
6. **R1.3 — zakaz testów nadal obowiązuje.** Audyt nie jest jego odwołaniem.
   Również reset danych, przeniesienie checkoutu do WSL i usunięcie starych
   tras nie zostały wykonane na podstawie tego przeglądu.
7. **R2.10 — limit CPU kontenera nie zastępuje delegacji workerów w obecnym
   runtime.** `accepted_fem_preparation_supervisor.rs:233` oraz
   `accepted_study_supervisor.rs:614` wywołują
   `LinuxWorkerCgroup::prepare(allocated_cpu_millis)` przed startem procesu.
   `worker_cgroup.rs:52` wymaga delegowanego rootu, a następnie egzekwuje budżet
   konkretnego workera. Samo usunięcie helpera/bramki ponownie zablokuje launch.
   Uproszczenie wymaga zmiany także tych konsumentów i zachowania limitów,
   identyfikacji oraz zakończenia całego drzewa workera.
8. **R1.1 — przebudowa w działającym backendzie potrzebuje bezpiecznej
   publikacji.** Supervisor może przełączać API na nowy pakiet dopiero po
   zakończeniu lub jawnym przerwaniu aktywnego runu. Nie nadpisywać bibliotek
   pod procesem solvera. Komenda użytkownika może ukrywać szczegóły; jeden
   właściciel procesu i zachowanie starego pakietu pozostają potrzebne.

## Kolejność zmian

1. Domknąć obecny start bez zmiany sesji: poprawny dispatch, log rzeczywistej
   fazy i Cargo 16, API ready, materializacja i mesh dla held04.
2. Usprawnić DEV capture/cache: jeden rzeczywisty zestaw wejść ext4, klucz
   backendu obejmujący jego wejścia; docs i frontend nie uruchamiają backend
   package pipeline. Osobno rozwiązać cache-hit i ujawnienie nowych plików.
3. Zrobić jeden publiczny interfejs lifecycle: up/status/logs/down/rebuild.
   Przerwanie obserwacji oddzielić od przerwania buildu. Wykryte przerwanie
   symulacji pokazać jako interrupted/held, bez automatycznego Solve.
4. Uporządkować aktualizację konfiguracji i zależności frontendu w zachowanym
   wolumenie; HMR skrócić po pomiarze kosztu pollingu na NTFS.
5. Dopiero po rzeczywistym cyklu edit→build→run usunąć zastąpione moduły oraz
   ujednolicić dokumentację. Ustalić jedną oficjalną drogę DEV, zachowując
   osobne wymagania kwalifikacji/release.

Miara powodzenia to czas edycja→API oraz skuteczny restart z zachowanymi
wynikami i cache, nie sama redukcja liczby linii. Ostatni build przeszedł;
API/mesh/Solve pozostają **NOT VERIFIED**. Nie wykonano testów,
resetu danych, globalnego prune ani migracji storage.


## Pomiar po przeglądzie i granice diagnozy

Nowy backend wystartował 23:14:06 UTC. Odczyt działającego Cargo potwierdził
16 jobów; Docker 128 GiB / 16 CPU. Capture 295448 ms, sync 17199 ms,
9183 pliki. Git status zajmował 109175 i 91096 ms.
Przerwa zapisów została zwolniona dopiero po przygotowaniu kopii ext4.

Wynik nowej próby: Make exit0 / 218431 ms, pakiet i gates PASS. Następnie
`runtime initialize-docker-accepted-store` przekroczył 180 s przed startem API.
Backend exited1/non-OOM, frontend healthy3198. Development
`8bad15a80b074dc1ac771433000bfb3b` jest failed-confirmed. Nie ponowiono bootstrapu,
aktywacji ani Solve. Porównanie Make 218431 ms z poprzednim 217249 ms nie jest
benchmarkiem jobów: źródła i warunki cache były różne.

### Diagnostyka przed main, bez otwierania SessionStore

W zarządzanych helperach tej samej grupy użyto tego samego obrazu i pakietu,
z GPU-all jak backend, readonly pakietem oraz bez mountów sesji/wyników.
Nie uruchamiano testów ani solvera. Stan `succeeded` receiptów oznacza zebranie
diagnostyki; wynik samego procesu jest podany osobno.

| Operacja | Dowód |
|---|---|
| `adc1c0bf4bce464797a91538ef54513d` | `fullmag-bin --version`, LD_DEBUG=libs: timeout 20 s, brak pierwszego build stamp; ostatni komunikat loadera to init `libcublasLt.so.12` |
| `2207c2dcf5a1409091adc313318dfd05` | Przerwany tylko własny proces metadata pod cuda-gdb: stos w `libnvJitLink.so.12`, dalej `libcublas.so.12` i loader. Nie ustalono funkcji wewnętrznej ani nieskończonej pętli |
| `3d9a7d86cc7447c19512c78af22416ba` | Oddzielne `ctypes.CDLL`: nvJitLink 20 ms, cublas 88 ms; później **ten sam fullmag-bin --version exit 0 w 4500 ms** |

MD5 plików zgadza się z właściwymi metadanymi CUDA 12.6:
`libcublasLt.so.12.6.4.1` = `f1ce6109fc6ff651c83d49bd29bd9bfc`,
`libnvJitLink.so.12.6.85` = `994fd941fd171d06cc1153fc04e59e4c`.
Wcześniejszy odczyt szukał metadanych 12.4 i dostał expected=null — to nie był
dowód uszkodzenia biblioteki. Nie wykonano jej reinstalacji.

Wniosek: zaobserwowano opóźnienie przed `main`, a później poprawne wykonanie
komendy metadata. Trwała awaria CUDA ani konkretna przyczyna timeoutu bootstrapu
nie są potwierdzone. Ciepły cache/I/O to hipoteza, nie wynik pomiaru porównawczego.
Nie należy z samego timeoutu wnioskować o konflikcie writera SessionStore ani
automatycznie zwiększać limitu 180 s. Odbiór API i meshu nadal wymaga rzeczywistego
startu przez istniejący launcher z zachowaniem pending continuation i held04.
