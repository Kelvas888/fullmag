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
