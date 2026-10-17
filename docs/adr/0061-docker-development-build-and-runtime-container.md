# ADR 0061 — budowanie i uruchamianie developerskiego backendu w jednym kontenerze

Status: decyzja użytkownika przyjęta; implementacja i runtime **NOT VERIFIED**.
Data: 2026-10-17.

## Kontekst

Development ma być widoczny w Docker Desktop jako jedna grupa wybranego
checkoutu z usługami `frontend` oraz `backend`. Dotychczasowy launcher buduje
backend w jednorazowym kontenerze, publikuje pakiet w storage Windows, a potem
uruchamia osobny kontener runtime. Rozdziela to logi i wydłuża iteracje przez
kopiowanie dużych artefaktów. Użytkownik wymaga jednego stałego kontenera
backendu, który buduje kod i następnie uruchamia aplikację.

## Decyzja

W trybie dev dokładnie dwie stałe usługi aplikacji należą do projektu
`fullmag-master` lub `fullmag-worktree-<worktree_id>`:

- `frontend` uruchamia Next.js dev i HMR z wybranego checkoutu Windows;
- `backend` przy starcie wykonuje zweryfikowany, przyrostowy build, a następnie
  w tym samym kontenerze uruchamia API i nadzorowany native runtime.

Docker Desktop i `docker logs` pokazują pełen przebieg backendu: przygotowanie
źródeł, kompilację, publikację wyniku i uruchomienie usług. Tryb dev nie tworzy
osobnego `backend-build` i nie przenosi dużego pakietu między kontenerami przez
storage Windows. Toolchain pozostaje przypiętym obrazem Docker; jawne buildy
release i kwalifikacja CI zachowują odrębne procedury.

Źródła są montowane readonly. Kompilator pracuje na zweryfikowanym cieniu ext4
z utrwalonym cache Cargo/CMake/CUDA. Backend obejmuje FDM CPU, FDM GPU, FEM CPU
i FEM GPU; wybór realizacji pozostaje w authored intent i plannerze. Wymuszone
GPU nie ma fallbacku CPU. Zmiana mechaniki budowania nie poszerza kwalifikacji
fizyki ani wspieranych kombinacji modelu.

Restart developerskiego backendu jest jawną operacją zarządzanego launchera:
sprawdza wybraną grupę i bezczynność, uzyskuje potwierdzony native drain,
przygotowuje nowe wejście źródeł i ponownie uruchamia ten sam kontener, gdy
konfiguracja obrazu i mountów się nie zmieniła. Zmiana obrazu lub mountów może
wymagać jawnego odtworzenia usługi. Frontend pozostaje uruchomiony. Nie wolno
zastępować kontenera na podstawie samego timeoutu ani uznawać utraty obserwacji
za potwierdzenie zatrzymania. Niepotwierdzony owner wymaga kanonicznego recovery.

Budowanie odbywa się przed startem API; nie podmienia plików wykonywanych przez
aktywną symulację. Nieudany build zachowuje logi i receipt, pozostawia backend
niegotowy i nie uruchamia API z częściowo opublikowanym pakietem. Zachowujemy
ostatni zweryfikowany pakiet, cache i dowody; brak automatycznego resetu stanu.

Sesje i wyniki nadal leżą w fizycznym storage Windows. Ustawienia i historia
pozostają w osobnej bazie grupy. Backend nie publikuje portu hosta; frontend
łączy się z `backend:8081` przez prywatną sieć grupy i udostępnia jeden wybrany
port loopback. Home może działać podczas budowania lub niedostępności API.

Opcjonalny plik `.py` pozostaje wejściem startowym tego samego launchera:
publikuje aktywny model i zachowuje automatyczne Solve albo trwałe oczekiwanie
`wait_for_solve`. Restart backendu nie jest nowym, niejawnym poleceniem Solve.

## Wdrożenie i weryfikacja

1. Dodać typowane `build-then-serve` w `backend_dev.py`: istniejący lock, Make,
   hash artefaktów, receipt i walidowany handoff do `entrypoint.py`.
2. Przenieść cache, manifest i wejścia Git do stałej usługi `backend`;
   zachować hardening, osobne sieci, frontend HMR oraz storage Windows.
3. Usunąć jednorazowy build z developerskiego `up`; dodać kontrolowany restart
   z odświeżeniem manifestu i zachowaniem container ID, gdy konfiguracja zgodna.
   Uaktualnić README, AGENTS i przewodnik; rozdzielić opis dev od release.
4. Wykonać adekwatne regresje Pythona i rzeczywisty start dwóch usług. Sprawdzić
   log kompilacji w `backend`, API/UI, ponowne użycie cache po restarcie, trwałe
   dane oraz start pliku `.py`. Dowód wykonania GPU pozostaje osobną bramką.

Nie kompilujemy lokalnie testów Rust w czasie obowiązywania zakazu użytkownika.
Udany build nie zastępuje dowodu browser/runtime ani wymaganych kontroli PR.
Wycofanie wymaga potwierdzonego zatrzymania własnej grupy i jawnego wskazania
zachowanego, zweryfikowanego pakietu; nie kasuje cache, sesji ani wyników.
