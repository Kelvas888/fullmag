# Dokończenie runtime i wizualizacji mastera — plan wykonania

**Cel:** zamknąć sześć punktów z podsumowania: dostęp Docker/WSL, wdrożenie
scalonego mastera, odtwarzanie siatki/pól, aktualna telemetria, optymalizacja
przygotowania oraz odbiór FDM i FEM.

**Architektura:** istniejący launcher i grupa `fullmag-master`; trwały accepted
store i jego zweryfikowane receipty pozostają źródłem prawdy. Odtworzenie
read-modelu korzysta z istniejących artefaktów i nie zwalnia Start ani nie
uruchamia solvera. UI używa wspólnych resource hooks i bieżącej tożsamości runu.

**Specyfikacja:** [aktualny odbiór CoFeB](../../audits/2026-10-29-cofeb-master-current-build.md),
[integracja mastera](../../audits/2026-10-29-master-sync.md),
[izolacja awarii](../../audits/2026-10-29-runtime-failure-isolation.md).

## Ograniczenia

- Główny checkout `/home/kkingstoun/git/fullmag/fullmag`, `master`, baza
  `89e25872cb94c85c8ca77371ecb0bd98780703cd`. Bez nowego worktree i testów
  jednostkowych. Build, statyczne kontrole i odbiór symulacji/przeglądarki
  wyłącznie przez zarządzaną grupę tego checkoutu.
- Zachować cudze zmiany instrukcji/dokumentacji i `external_solvers/3`, wyniki,
  cache przyrostowy, receipty i provenance. Bez reset/stash/globalnego prune.
- FEM/GPU/double/strict pozostaje wymuszone; FDM/GPU ma odrębny odbiór.
  Nie zmniejszać siatki, nie wyłączać walidacji pierwszego wejścia i nie
  zmieniać fizyki, aby poprawić czas.
- Kontrolowane wdrożenie obejmuje wyłącznie naszą grupę. Nie restartować
  Dockera, innych grup ani nie odtwarzać niejednoznacznych komend Solve.
- Kwalifikowana retencja zachowuje current + bezpośredni rollback i dane
  referencjonowane; brak obsługi stanu oznacza jawny `blocked` cleanup.

## Etapy i dowody odbioru

- [x] **1. Dostęp do silnika.** Bieżący `docker info` z WSL odpowiada;
  potwierdzono Docker Desktop 29.9.2, 40 CPU i około 196,6 GiB RAM.
  Oba dotychczasowe kontenery mastera są zatrzymane z exit255 po przerwie
  silnika; nie jest to zgoda na replay ich starego zadania.
- [ ] **2. Odtworzenie siatki i pól bez obliczeń.** Root odpowiada za
  `development_accepted_restore/terminal_observation.rs`,
  `live_accepted_projection.rs`, `live_scene_preparation.rs` i wymaganych
  konsumentów. Najpierw prześledzić odmowę publikacji terminalnej domeny.
  Wykorzystać istniejącą projekcję accepted output i zweryfikowaną siatkę;
  zachować run/task/attempt/epoch/plan/topology oraz stan terminalny.
  Dowód: po kontrolowanym odtworzeniu ten sam run i krok, dostępne domena,
  m/H_demag/H_eff, identyczne wartości, brak nowego admission/Start/Solve.
- [ ] **3. Telemetria.** Worker `footer_step_authority` zakończył swoją część;
  root integruje stopkę z brakującymi danymi backendu i generowanym kontraktem.
  Nie mieszać prepared scalar z późniejszym zaakceptowanym krokiem.
  Dowód: API i widoczna stopka pokazują ten sam krok i energię po ukończeniu
  i odświeżeniu; brak niepotrzebnego pollingu. Poprawić także potwierdzone
  błędne wartości uptime/nazwy algorytmu i etykietę settlementu, zachowując
  istniejący kształt kontraktu albo regenerując API zarządzaną receptą.
- [ ] **4. Czas przygotowania.** Worker `materialization_profile_map` tylko
  mapuje kod i pomiary; root wybiera i wdraża zmianę. Rozdzielić generację,
  certyfikację, encode/decode, native preparation i publikację. Usunąć
  wykazaną pracę powtarzaną przy reuse, zachowując walidację/piny wejścia.
  Dowód: porównanie tego samego workloadu, konfiguracji i fingerprintów
  topologii; podać czasy i faktycznie usuniętą pracę, bez utożsamiania różnych
  etapów pomiaru i bez zmniejszania domeny.
- [ ] **5. Wdrożenie scalonych źródeł.** Uzgodnić końcowy stan starego runu
  i ownera po przerwie silnika, zachować dane i użyć istniejącej recepty
  stop/recovery/resume. Zbudować w stałym backendzie, zachować 128 GiB/16 CPU.
  Dowód: źródła/SHA/snapshot, manifest, build receipt, API Ready, mounty,
  requested/resolved GPU/double oraz kwalifikowana retencja tej próby.
- [ ] **6. Odbiór obu rodzin.** CoFeB FEM/GPU/double: zgodny Universe i mesh,
  dokładnie 10 nowych zleconych iteracji, skończone m oraz niezerowe
  H_demag/H_eff w Airboxie. FDM/GPU i FDM multilayer: odrębne przypięte
  wejścia, 10 kroków, właściwe mapowanie pól i zakres Airbox.
  Dowód: binarne dane/provenance oraz widoczny canvas WebGL z niezagubionym
  kontekstem i niezerowym drawing buffer. Nie deklarować zbieżności naukowej
  ani kwalifikacji wszystkich backendów na podstawie tych krótkich prób.

## Checkpointy

Pierwotne obce zmiany zabezpieczono jako kopie i manifest w
`/tmp/fullmag-six-points-20261029`. Każdy etap zapisuje przyczynę, zmienione
pliki, weryfikację bez testów jednostkowych, pełny SHA commita i brakujące
dowody. Cel pozostaje aktywny, dopóki którykolwiek z sześciu odbiorów jest
niepełny. Raport końcowy oddziela źródła, build, runtime, render i fizykę.

### Checkpoint po przywróceniu dostępu Docker

- HEAD: `e6a58cc7b12bc92b96c271cacb4cd1e19118659e` — poprawiona kolejność
  pobierania brakującego helpera przed uwierzytelnieniem zachowanego namespace.
  Zwykły commit przeszedł lokalny hook; nie pomijano kontroli commitowania.
- Kolejne lokalne commity: `fcff58ce40ae8405db53284bb81d9f92bb6a0540`
  (odtwarzanie terminalnej domeny/pól i telemetryczny scope) oraz
  `b112a0d137aee132d545fa67c49c834d832bb8ba` (ponowne użycie dekodowania
  mixed-v2 i czasy faz). Nie są jeszcze dowodem wdrożenia aplikacji.
- `just docker-dev-toolchain` zakończył się powodzeniem w `fullmag-master`:
  próba `0ba636f2e89c4784a0ba8a77bed7dd6b`, obraz
  `sha256:efe1c5b5ef051387c4e6b32f960effd382a6e3cbc7de1627c15508be0ac96ebf`.
  Jest to dowód obrazu zależności. Nowa aplikacja backendowa nie została jeszcze
  skompilowana ani uruchomiona.
- W kodzie przygotowano odtworzenie terminalnej domeny i pól, przyjęcie
  końcowych skalarów oraz jawne powiązanie pojedynczego wiersza HTTP z runem
  i `request_scope_epoch`. Generowane API i odbiór UI nadal oczekują na
  działający nowy backend. Nie porównywać tego identyfikatora z publicznym
  `session_epoch` opartym na czasie rozpoczęcia sesji.
- Usunięto powtórny odczyt/dekodowanie tego samego archiwum mixed-v2 przy
  pełnym audycie cache. Dodano pomiary faz Python/native. Nie ma jeszcze
  nowego pomiaru tego samego workloadu: poprawa całkowitego czasu pozostaje
  **NOT VERIFIED**.
- Odtworzenie po przerwie silnika wykryło nieobsłużone przypadki inspekcji:
  pominięte opcjonalne `HostConfig.Mounts`, aliasy dysków Desktop oraz brakujące
  katalogi zatrzymanych historycznych grup Windows. Osobny dowód braku bindu
  wymaga rzeczywistego Win32/DrvFs, zwykłych katalogów nadrzędnych i dokładnie
  zatrzymanego kontenera. Nie wyłącza sprawdzania istniejących ani aktywnych
  konsumentów. Przelotna utrata krótkiego helpera powoduje najwyżej trzy pełne
  odczyty inventory; częściowy wynik nigdy nie jest przyjmowany.
- Potwierdzono odczytowo nietypowe `PATHEXT=.CPL` oraz odmowę `fsutil hardlink
  list` z kodem 50. Dostawca metadanych używa teraz uchwytu Win32
  `OPEN_EXISTING`, desired access `0`, bez czytania zawartości i zmian plików;
  wymóg jednej ścieżki nadal opiera się na natywnej liczbie dowiązań i tożsamości
  pliku. Niestandardowe `DataFolder` pozostają nieobsługiwane; dopuszczony jest
  jedynie zweryfikowany profil WSL z domyślnym ustawieniem legacy Hyper-V.
- Odczytowe preflighty korzystają z krótkich zarządzanych helperów. Nie
  opublikowano jeszcze autoryzacji recovery, nie usunięto ani nie uruchomiono
  stałych kontenerów aplikacji, nie zmieniono ownera i nie powtórzono Solve.
  Siedem plików obcych instrukcji/dokumentacji zachowuje
  hashe kopii początkowej; nie dołączać również obcego submodułu ani nowego
  równoległego audytu do naszych commitów.
- Kontrola składni obejmuje 22 zmienione pliki Rust/Python; `git diff --check`
  przechodzi. Bez testów jednostkowych. Odbiór nowej aplikacji, odtworzenia,
  renderu i nowych obliczeń FEM/FDM nadal pozostaje otwarty.
- Nowszy odczyt wykrył także junction canary starego profilu Windows:
  `.windows-folder-probe/host-junction` wskazuje na `junction-target` wewnątrz
  tego samego rootu. Wersja 2 dowodu/inventory rozróżnia względne LX symlinki
  i natywny directory junction; dla junctiona cel Windows musi odpowiadać
  dokładnie celowi DrvFs wewnątrz rootu. Nadal obowiązują budżety, sprawdzenie
  cykli, urządzenia, zwykłych katalogów nadrzędnych i końcowego katalogu.
  Dowiązania wychodzące poza root oraz nieznane tagi pozostają odrzucone.
- Canary `posix-link` okazał się natywnym Windows SymbolicLink z względnym
  celem `publication.bin`. Wariant `0xa000000c` dopuszcza wyłącznie względny
  cel natywny, zgodny z `readlink`, ograniczony do rootu i właściwego typu
  końcowego. Odczytowy pełny dowód `/state` historycznej grupy
  `awesome-mayer-5cef23-78db87f3557b6306` przeszedł z oboma canary.
  Niezależne review wariantów junction/symbolic zakończyło się PASS źródła.
- Nie tworzyć historycznego preflightu terminalnej sesji z samych pinów
  katalogu runów. Recovery po przerwaniu silnika zachowuje stare wyniki,
  lecz startuje API bez odtwarzania sesji. Odbiór odtwarzania zostanie wykonany
  po nowej, jawnie zleconej próbie CoFeB 10 kroków: rzeczywisty preflight,
  potwierdzony drain, istniejący terminal-observation proof i ponowny start
  obserwacji bez kolejnego Solve.
- Pełny odczytowy preflight przeszedł kontrolę obcych bindów bez zatrzymywania
  cudzych grup. Następna bramka wykryła pominięte referencje przygotowanych
  obserwacji: wszystkie 37 pinów spoza intentów i katalogu artefaktów należą do
  dwóch `task_prepared_observations`. Nie są dowodem utraty lub uszkodzenia
  danych. Wymagają walidacji typowanych rekordów i ich receiptów także w
  terminalnej ścieżce hosta i runtime. Suma 71 obiektów CAS wynosi 231 755 414 B,
  więc dotychczasowy łączny budżet odczytu 128 MiB jest niewystarczający;
  walidacja musi pozostać strumieniowa, ograniczona i sprawdzać wszystkie hashe.
