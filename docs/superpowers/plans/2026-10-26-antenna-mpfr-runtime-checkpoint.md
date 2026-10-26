# Kandydat MPFR dla pola anteny — checkpoint 26.10.2026

## Cel i klasyfikacja postępu

Poprzedni turn przyniósł postęp: poprawiono stany inspektora Universe/anteny,
23 kontrole renderowania/nawigacji oraz typecheck i lint przeszły. Nie był to
dowód pola na pełnym Universe. Pełny cel E0–E12 pozostaje otwarty.

Niniejszy etap usuwa przeszkodę wydajności operatora bez zmniejszania siatki,
zmiany źródła, tolerancji, limitu 1800 s ani pominięcia przejść kontrolnych.
Przygotowany kandydat MPFR128/160 jest FEM CPU, inspection-only. Nie jest
zakwalifikowaną bazą, realizacją GPU ani wynikiem pełnego Universe.

## Baza i przygotowanie źródeł

HEAD: 5bc05ae5880687b5fd27292931f4a60b868cab5c; istniejący dirty worktree
zachowano. Referencja native:
22c08a0585a5511d6737b9d429de180b9f22bdf4ed249382665ed7c42815c909.
Bundle: 6bacf94351693955f5b97ab7485613e5a23cc29e835ffaf02527cdb6389e0ca4.
Referencyjne 14 punktów wymagało 363,113 s operatora. Pełny przykład jest
osobnym zadaniem; nie zastępujemy go małym benchmarkiem.

Kandydat używa allocate_stack i et_off oraz nowej jawnej tożsamości
fem_oersted_rt0_surface.mpfr128_160_rndn_etoff.inspection.v1. Stare archiwa
pozostają czytelne pod dokładną starą tożsamością. Świeży native output wymaga
nowej. Wszystkie formuły, exact geometry, kolejność sumowania i odmowy
pozostają w kodzie. Dwa typy nie stanowią niezależnego oracle.

W tym turnie naprawiono mapę źródeł: jednoznaczne symbole właścicieli zamiast
nierozpoznawanych aliasów/kwalifikatorów i niejednoznacznego serialize.
CMake ma jeden wymagany moduł GMP/MPFR. Przypięty base Compose to Ubuntu22.04;
MPFR dev/runtime 4.1.0-3build3. Nie zmieniono base działającego API ani .env.
Prerejestracja i macierz realizacji pozostają w kanonicznej nocie 0950.

## Przygotowane dowody i procedura próby

Wolumen kontrolny grupy, verification/antenna-mpfr-20261026:

- toolchain-preflight.json: przypięta stara biblioteka, zdrowe API, wolne miejsce
  i decyzje retencji; około 133 GiB na D: oraz 220 GiB w WSL przed buildem;
- scene-before-image-change.json i status-before-image-change.json;
- runs-before-image-change.json: inwentarz historii przez publiczne API;
- preregistration-pins.json i baseline-source: wcześniejsze niezmienne piny;
- comparison-expectations-v1.json: wymagane 21 identycznych payloadów,
  dokładna zmiana reserved bytes +7126, wszystkie pozostałe liczniki zgodne;
- run-mpfr-candidate.py: jedna próba z nowym run ID i kontrolą braku wcześniejszego
  zlecenia, frozen request SHA i jawnie podanym SHA nowej biblioteki;
- compare-mpfr-candidate.py: porównanie 21 payloadów, źródła, polityki,
  tożsamości, diagnostyk, liczników i receiptu faz. Nie wykonano go na
  nieistniejącym wyniku kandydata.

Nie uruchomiono Solve MPFR. Skrypt próby nie ponawia automatycznie żądania;
observation timeout nie stanowi zakończenia workera. Sprawdzenie Pythona
hosta3.8 ujawniło brak removeprefix; walidator uruchamiany jest właściwym
Pythonem3.10 istniejącego backendu, bez zmieniania walidatora.

Zachowana scena jest dokładnie zgodna z istniejącym kanonicznym FMS:
c05d8176471e7de2e8ef439375f362223a22e0023a6e64c1a267bde861f9ed87.
Nie wykonano kolejnego odrzuconego compact export, nie zmieniono sceny
ani zapisanych wyników. Brak skilla fullmag-build-stage-cleanup; zastosowano
retencję governance: zachować aktywny cache, pakiet referencyjny, wyniki,
obrazy i staging, nie wykonywać żadnego prune/usuwania.

## Faktycznie aktywny build i następny krok

Z katalogu tego worktree uruchomiono just docker-dev-toolchain. Grupa:
fullmag-worktree-antenna-transport-e2e-20261011-5d5deadcd16e0fb1.
Nowy input tag: fullmag/fem-gpu-toolchain:inputs-8eda4c1644405bd9c8c303ea.
Handle terminala 33865 jest nadal żywy; ostatnia odczytana faza: MFEM
90/269, etap instalacji runtime zakończony. Efektywne parametry:
CUDA86-real/86-virtual, hypre86, MFEM jobs2, fast-compile0. Część zależności
była cached, MFEM i warstwa pakietów runtime są rzeczywiście przebudowywane.
To obraz zależności, nie osobny backend-build ani symulacja. Dotychczasowe
API/front pozostają uruchomione. Nie wolno wnioskować o nowym pakiecie lub
przyspieszeniu z samego postępu BuildKit.

Po zakończeniu tego samego handle sprawdzić terminal i imageID. Potem ponowić
kontrolę bieżącego API/runów oraz operacji control. Dla ukończonej sesji użyć
istniejącego managed restart-idle-volume z allow-prepared-session i stop-only,
nie fałszować saved-authoring checkpointu. Zachować dwa stare accepted runy;
nie nazywać ich manualnie wstrzymanymi bez dowodu i nie zwalniać ich blokad
ręcznie. Następnie just docker-dev-recreate-volume z canonical start
 aa0121dc39f84ebfa89b804f13881921 oraz config
5ae11c7ec51fbc05cebde982e3b7281f82e5318d23d6765ab136d45302b33fb6,
fresh_state=false, bez skryptu startowego/Solve. Kontroler musi sam dopuścić
stan i migrację konfiguracji po authenticated drain. Nowy obraz oznacza nowe
app-container IDs; zachowanie danych/cache nie oznacza tożsamości kontenerów.
Jeśli preflight odmówi, nie omijać bramki.

Dalsze bramki: aplikacyjny build w stałym backendzie, link/manifest MPFR,
ponowny odczyt starych wyników, jedna próba14, prerejestrowane porównanie,
szersza niezależna kwalifikacja i pełny Universe. Kontrole przeglądarki,
pełna baza/projekcja/LLG/FFT/BORIS i E12 nadal nie są zaliczone.


## Dokładne wejścia obecnego Universe — uzupełnienie

Następny turn przyniósł konkretny postęp przygotowania rzeczywistej pełnej
próby. Obecny manifest API ma 1162 nodes i 6548 Tet4, z czego 1726 conductor
oraz 4822 air. Historyczna próba ace433… miała 1154 nodes i źródło1862;
mały benchmark ma14 nodes i źródło1865. Nie są to te same siatki.
Aktualny FMS zawiera źródło677 nodes/1859Tet4 i Global1162/6548, zgodne
z zachowaną natywną preparation oraz bieżącą generacją
1068f1dda14706c4ebbb5f81c280ae0d8025f70d1cbf5a4aaa8d834b69a9097b.

Przygotowano pełny publiczny request w podkatalogu kontrolnym
full-universe-replay/frozen-submit-request.json. SHA256:
3dd66fe134bedbc66fb90fa40bfb510ac4aa2bbcb64953c2b5ce08620af7c6cb,
41 684 035 B. Archiwum projektu SHA256:
f8d8abafa021fb490c597692ccaa7b0a3c119aa143a2df51ebe336048b2bdbfc.
Kontrola replay-input-validation.json przeszła: identyczne bity wszystkich
punktów, connectivity/markery, generacja API, scena, ProblemIR, plan i katalog;
ponownie sprawdzono hashe wszystkich1973 assetów. Zmieniono tylko run ID
oraz metadata aktywacji samodzielnego runu. Nie wykonano remeshingu ani POST.
Projekt10909b… ma katalog runów HTTP200 i zachowany run2f2f…; bare GET projektu
nie jest kanoniczną trasą, więc jego404 nie dowodziło braku projektu.

Pełna próba obejmuje 2 160 158 par przy niezmienionym limicie4 mln/1800s.
run-full-universe-once.py wymaga najpierw wyniku21-payload parity z małego
MPFR i zgodnego SHA biblioteki. Sprawdzono dwie rzeczywiste odmowy preflightu:
mała próba nie startuje na starym pakiecie22c08…, pełna nie startuje bez
zaliczonego małego porównania. Obie zakończyły się przed submission-started;
żadnego Solve. Dowód trial-preflight-negative-checks.json.

Odrębny audyt dokładnej geometrii zachowano w future-geometry-reuse-proof.py
oraz JSON. 462 porównania Fraction wszystkich13 pól i sześciu permutacji
przeszły; jeden degenerujący po binary64 trójkąt jawnie pominięto. Dla obecnego
źródła jest7436 lokalnych ścian i4365 unikalnych trójkątów według bitów
współrzędnych. Potencjał ograniczenia powtórzeń geometry wynosi41,30% przed
narzutem. Nie zaimplementowano cache, nie współdzielono prądu/FacePass, nie
sprawdzono native guards/RSS i nie uznano tego modelu algebraicznego za
kwalifikację naukową. Najpierw osobny parytet MPFR; sam czas fazy exact z
małego benchmarku sugeruje, że MPFR-only może nie wystarczyć dla1800s, lecz
jest to ekstrapolacja, nie pomiar obecnego Universe.

Build33865 pozostaje aktywny, ostatnia obserwacja MFEM205/269. Właściwa trasa
DEV deleguje do build_volume_toolchain; końcowe piny znajdują się w
 toolchain/attempts/<attempt>/terminal.json i toolchain/current.json lub
verified.json. Stary toolchain/bootstrap-receipt.json nie jest producentem
tej trasy. Nowy obraz, aplikacyjny build, mała próba i pełna mapa są nadal
NOT VERIFIED. Źródła kernela pozostają wyłącznie kandydatem MPFR.


## Bramka tożsamości wykonania — przed pierwszą próbą MPFR

Niezależny przegląd wykrył lukę w przygotowanym comparatorze: porównywał
21 payloadów, lecz nie wiązał ich dostatecznie z publicznym katalogiem,
manifestem zakończonego zadania i biblioteką faktycznie załadowaną przez worker.
Naprawiono lokalne narzędzia w wolumenie kontrolnym przed jakimkolwiek nowym Solve.
Nie zmieniono fizycznych wejść, metod, tolerancji, limitów ani publicznego API.

Nowa kontrola wiąże project/run/task/attempt/epoch/step/case, codec, artifact IDs,
SHA256 obu obiektów CAS i rzeczywisty rozmiar bundle. Porównuje pełną identity
started/completed/profile w pamięci; raportuje wyłącznie jej digest i jawne
identyfikatory, bez wartości lease. Weryfikuje także zgodność żądania i konfiguracji
profilera. Runner przypina nagłówek inkarnacji API we wszystkich odpowiedziach.

W czasie rzeczywistej próby wymagany jest odczyt procesu dopasowanego po dokładnych
argumentach store/run/task: PID i start_ticks, executable oraz mapowania biblioteki
FEM muszą odpowiadać inode/device/hash przypiętych plików. Obserwacja wiąże również
receipt rozpoczęcia workera. Przed próbą, w obserwacji i po zakończeniu sprawdzane
są worker, biblioteka i hash receiptu pakietu. Jest to pojedyncza obserwacja procesu,
nie ciągła attestation. Brak obserwacji odmawia promocji, bez automatycznego Solve.

Zakres pinów pakietu jest jawny: dwa rzeczywiste pliki (worker i FEM library) oraz
receipt. Nie jest to ponowny audyt rzeczywistych bajtów wszystkich pozostałych plików
pakietu. Pełna próba wymaga tych samych pinów, pozytywnego małego porównania oraz
własnej obserwacji workera. Przypięty runner porównuje fizyczne wejście z frozen
request przed POST; comparator nie odtwarza samodzielnie całej tej transformacji.

Weryfikacja narzędzi: 80 kontroli interpretowanych PASS, w tym binding rzeczywistego
zachowanego wyniku i celowo podmienione identity, metadane i mapowania. Jawnie oznaczony
fixture całego verifiera nie jest obserwacją żywego procesu. Dwie odmowy preflight
PASS: stara biblioteka oraz brak pozytywnej małej próby. Po obu sprawdzono brak
submission-started. Nie kompilowano testów jednostkowych. Niezależny ponowny przegląd
nie znalazł blokera w zakresie exact worker/exact FEM; zachowano powyższe ograniczenia.

Dowody: verification/antenna-mpfr-20261026/ w kontrolnym wolumenie grupy:
trial_runtime_binding.py, check-trial-runtime-binding.py, runtime-binding-checks.json,
runtime-binding-preregistration-v1.json i trial-preflight-negative-checks-v2.json.
Klucz full_trial_requires_identical_package w prerejestracji oznacza porównanie
wskazanych dwóch plików oraz receiptu, a nie pełny actual-file audit.
SHA256 helpera: b1accf5776a22e54a953a8e9c186a074db81ee2101ba597b8c0f50862c6fc44e.
SHA256 małego runnera: 5fff8f2390f2ba66e99dff044b5d6c977e0127ec345b8828af57c576350360c3.
SHA256 comparatora: 661e1fc4ca431ca956f275dcb73763594a0e7be094d9e29c0cfd8f325d63c209.
SHA256 pełnego runnera: 8bb0dce027c472a7b28875b41abe5b3741b6736b594ccbd41996e37fdbdb2315.

Stan wykonania: aktywny toolchain attempt 899638a17d5e4f5389cbfebcf3f8af69,
uchwyt 33865; MFEM CUDA zakończony 269/269, hypre/PETSc/SLEPc CPU zbudowane,
trwa MFEM CPU. Stare API nadal działa. Nowy pakiet aplikacji, próba MPFR i pełny
Universe pozostają NOT VERIFIED. To kontynuacja aktywnego E0–E12, nie zakończenie zadania.
