# Start SP4 FDM GPU single

Cel: uruchomić wskazany PG-BB w `fullmag-master`, zachować single/strict, próg torque 1e-6 T, limit 100000 kroków, tabelę co 10 kroków i końcową magnetyzację.

1. Związać SaveState z typowanym, zaakceptowanym stanem poprzedniego etapu. Zachować nazwę, format i dataset. Zapis nie uruchamia solvera i ma trwały receipt umożliwiający bezpieczne odtworzenie wyniku.
2. Udostępnić istniejący CUDA FDM PG-BB single przez accepted worker. Sprawdzić lease GPU, precyzję planu i rzeczywistą precyzję runtime. Relaksacja używa kanonicznego resolvera czasu oraz własnych kryteriów zatrzymania.
3. Dodać regresje i wykonać build aplikacji w grupie worktree. Zakaz kompilacji testów jednostkowych pozostaje w mocy. Zintegrować lokalnie, przebudować master i uruchomić niezmieniony model przez launcher.
4. Potwierdzić accepted run, GPU/single oraz rzeczywisty postęp. Zapisać wynik i diagnostykę pod `~/git/simulations/fullmag`. Mumax3 czeka na wynik Fullmaga.

Kontrole: brak Solve w SaveState; brak cichego fallbacku CPU; niepoprawne źródło stanu/format/precision odrzucone; zachowane CAS, claims, receipty, cache i dane użytkownika. Build i obecność źródeł nie są kwalifikacją fizyki.

Podstawa naukowa: `docs/physics/0580-canonical-relaxation-equilibrium-contract.md` i `0500-fdm-relaxation-algorithms.md`. Nie zmieniamy równań, algorytmu ani kryteriów zbieżności.
