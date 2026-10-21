# Migracja profilu limitów CPU workerów

Cel: odblokować start FDM GPU single bez resetu rejestru, utraty danych ani
osłabienia admission. Worktree: `scratch-gpu-single`, branch `codex/scratch-gpu-single`.

## Kroki i dowody

1. **Potwierdzone:** oba wolumeny ledger wskazują filesystem UUID
   `c5878a7f-7d72-4698-8340-8da982553bef`. Konsumenci: `fullmag-master`
   i grupa worktree. Diagnostyczny managed build przeszedł; initializer nadal
   poprawnie odrzuca niezgodność. Policy i inventory są identyczne. Zmiana
   wyłącznie `cpu_quota: unavailable -> supported` odtwarza nowy hash capabilities.
   Dowód diagnostyczny: `/tmp/host-readiness-comparison.json`; surowe dane:
   `/tmp/host-readiness-before-migration.json`, `/tmp/host-readiness-candidate.log`.
2. **Częściowo:** dodano `stop-idle-volume` z kontrolą pierwotnego stanu
   frontendu; testy interpretowane przechodzą. Przygotować zgodną konfigurację konsumentów.
   Nie uruchamiać starego master po migracji bez zgodnego profilu delegacji.
3. **Kod przygotowany:** wąska metoda migracji, jawny argument starej generacji
   i protokół request/claim/result w launcherze. Managed build Rust przeszedł
   w próbie `1cca36cf2e874d3a86f5d372b9da0e36`; hashe obu plików Rust
   zgodne ze zbudowanymi kopiami. Protokół Python sprawdzony testami;
   nowy helper wdrożony w obrazie worktree, hash pliku zgodny ze źródłem.
   Próba `e0e48ebf417540dcb2344ad43b1d9325`: pakiet 24 pliki zweryfikowany,
   storage i cgroup PASS, zwykły start odrzuca stary profil. Migracja NOT VERIFIED.
4. **Częściowo:** testy Python: 9 runtime, 8 host, 7 istniejących testów
   inicjalizacji oraz regresje kolejności/drain przechodzą. Natywny test Rust obejmujący 18 przypadków odmów, przerwania, powtórzenia
   i zachowania danych przeszedł w stałym backendzie worktree (exit 0).
   Użytkownik zezwolił na testy tej poprawki w zarządzanej grupie worktree.
5. **Do wykonania:** dopiero po weryfikacji drain konsumentów, spójna kopia
   rejestru/CAS, jawna migracja i start zgodnych backendów. Bez ręcznej edycji JSON.
6. **Do wykonania:** API health, świeża generacja i snapshot, limit realnego
   workera, restart bez migracji, kontrola zachowania policy i danych. Następnie
   weryfikacja FDM GPU single i generacja OpenAPI.

## Warunki przerwania

Dodatkowa różnica profilu, aktywne rezerwacje lub owner, nieznany wynik operacji,
zmiana oczekiwanej generacji albo brak dowodu delegacji wymagają diagnostyki.
Nie resetować rejestru. Nie zastępować wymuszonego GPU przez CPU.

## Integracja i retencja

Zachować cudze zmiany main. Zachować rejestr, stare i nowe CAS, dowody migracji,
logi oraz receipty. Nie usuwać worktree, dopóki korzystają z niego kontenery.
Kod gotowy nie oznacza wykonanej migracji ani kwalifikacji solvera.

## Przerwanie operacji

Nieznany wynik blokuje ponowienie i zachowuje request/claim/result. Nie obiecujemy
automatycznego odzyskania. Osobne polecenie uzgodnienia wyniku pozostaje poza
obecnym zakresem; przed migracją wymagany jest dowód bezpieczeństwa przerwań.

## Weryfikacja natywna

Użytkownik zezwolił na testy tej poprawki. Jawna trasa
`verify-worker-cpu-quota-volume` działa w stałym backendzie przed API.
Próba `39fe357092354a8384a1f0a13105ff1d`, request
`973c2f42-30b2-47bc-9941-769bcc5dde4b`: 1 test / 18 przypadków PASS,
exit 0. Log i receipt pozostają w wolumenie kontroli. Pierwsza próba wykryła
brak launch binding w fixture Released; poprawiono wyłącznie fixture.
Testy Python nowej recepty i startu: 9 PASS. Drain zatrzymanego legacy
frontendu oraz zachowanie pozostałych kontroli: 2 testy PASS.
Rejestr runtime pozostaje bez migracji; następny etap to drain i spójna kopia.
