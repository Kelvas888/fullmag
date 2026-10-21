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
2. **Wykonane:** dodano `stop-idle-volume` z kontrolą pierwotnego stanu
   frontendu; testy interpretowane przechodzą. Master zatrzymany przez managed drain; worktree ma zgodną konfigurację.
   Nie uruchamiać starego master po migracji bez zgodnego profilu delegacji.
3. **Kod przygotowany:** wąska metoda migracji, jawny argument starej generacji
   i protokół request/claim/result w launcherze. Managed build Rust przeszedł
   w próbie `1cca36cf2e874d3a86f5d372b9da0e36`; hashe obu plików Rust
   zgodne ze zbudowanymi kopiami. Protokół Python sprawdzony testami;
   nowy helper wdrożony w obrazie worktree, hash pliku zgodny ze źródłem.
   Próba `e0e48ebf417540dcb2344ad43b1d9325`: pakiet 24 pliki zweryfikowany,
   storage i cgroup PASS, zwykły start odrzuca stary profil. Migracja została następnie zweryfikowana w kroku 5.
4. **Wykonane:** testy Python: 9 runtime, 8 host, 7 istniejących testów
   inicjalizacji oraz regresje kolejności/drain przechodzą. Natywny test Rust obejmujący 18 przypadków odmów, przerwania, powtórzenia
   i zachowania danych przeszedł w stałym backendzie worktree (exit 0).
   Użytkownik zezwolił na testy tej poprawki w zarządzanej grupie worktree.
5. **Wykonane:** obaj konsumenci zatrzymani; spójna kopia `ledger.tar`
   i receipt zachowane w `host-readiness-migration-backups/worker-cpu-quota-973c2f42-30b2-47bc-9941-769bcc5dde4b`
   pod runtime storage. SHA256 archiwum:
   `e2b12517d3eaae06bc12f9ec7045dcaaa631329384608bc58749c80fab5583de`.
   Jawna migracja request `73b09c34-c2a5-4d8a-b198-b8534bc52192`,
   próba `4d0e2f9cbf9a4e68be5329f1e950d724`: exit 0, succeeded.
   Zachowano policy, node_policy i rezerwacje. Jedyna zmiana enforcement:
   `cpu_quota: unavailable -> supported`.
6. **Częściowo:** API health i nowa generacja potwierdzone; managed restart
   bez zmian `f9f6051a8b41468e9584c21ed79946be` przeszedł z cache hit.
   Test API: 4 dozwolone kombinacje przyjęte, 6 niedozwolonych odrzuconych,
   bez fallbacku i bez Solve. Limit realnego workera oraz obliczenia GPU
   pozostają NOT VERIFIED. Generator OpenAPI zakończył się poprawnie po przebudowie pakietu.
   Restart wymagał jawnego wskazania naszej pustej sesji probe
   `session-18e08614dd42eff9000000c6`. Dodano `--empty-scratch-session-id`
   do `restart-idle-volume`: eksport przed stop, ponowna kontrola niezmienionej
   sesji, odmowa zmian modelu i przyjętych obliczeń. To nie jest odtworzenie
   sesji po restarcie. Próba `866c86b3ad3f4ea989409b85dc1fcc5c` przeszła; eksport zachowany,
   API zdrowe, `active_session=false`. Codegen receipt:
   `backend/codegen/openapi-v2/e279e77feded30dede68089dee488a606cdec4a5789aaa95a6fd346c2a710903.json`
   w wolumenie kontroli. Schematy i typy zawierają `gpu` oraz `single`.
   Master pozostaje zatrzymany do integracji i zgodnego buildu.

Generacja przed migracją:
`ddc5f0dfe4c684828cddb8f31215bb583e5cffd19896c67ac378d162ea3acf42`.
Generacja po migracji:
`db34cb25611db7b5ee09f511b8789fc92e089c2c39bd7b9042fa61049650227c`.

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
Wykonanie migracji i zachowanie danych potwierdzono w kroku 5.

## Pozostała weryfikacja

Testy jednostkowe API i Vitest pozostają NOT VERIFIED: brak podłączonej
zarządzanej recepty dla tych testów w stałych usługach. Live probe sprawdza
admission; nie zastępuje wykonania GPU. Integracja PR wymaga działającego
uwierzytelnienia GitHub i zachowania cudzych zmian w main.
