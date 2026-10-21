# Najbliższe bramki domknięcia po reaudytowaniu mastera

Aktualizacja: **20.10.2026**, baza
`42d92610312871d591db16a5b60a8f7a6d6339b5`.
[Stan kodu i testów](06-status-realizacji.md), [plan zakresu](03-plan-refaktoryzacji.md).
[Dawny checkpoint 02.10](07-domkniecie-historyczne-2026-10-02.md) jest historyczny.
Nie obowiązują jego bieżące porty, stan runnera ani opis fullscreen/inert.

## 1. Kolejność odbioru

| Priorytet / pakiet | Co wykorzystujemy | Konkretne domknięcie | Dowód wymagany do zaliczenia |
|---|---|---|---|
| 1 — P0-A/P3a | Inventory i istniejące context fences | Przejrzeć różnicę starego 304-elementowego zakresu i obecnych 371 operacji; owner, request context, klient, cache/decode, publication i removal gate aliasu | Wiersze aktualnej macierzy mają przypięty source fingerprint i wynik review; odrębne stale-scope runtime A→B |
| 2 — M1/P1/P2 | ProjectApplication, persistence API, project controller i obecne panele | Start bez solve, niekompletna geometria/region/materiał, Save/Close/Open, zachowane dane i szkice; wyraźnie oddzielić dokument od flow tworzącego RuntimeSession | Powtarzalny realny browser/API receipt na przypiętym pakiecie; monitor niejawnych solve/mutacji; identity i byte/semantic roundtrip |
| 3 — P3/P5 | Accepted workers, coordinator, snapshoty i lease | Idempotentny Submit, utrata ACK, cancel/retry/restart, edycja draftu przy przypiętym runie, odrzucenie stale worker publication | Terminalny journal/receipt, identyczne wejścia runu, brak podwójnego solve, potwierdzony owner exit/release; per wymagany lane |
| 4 — P4 | Preparation receipts, native preparer, ostatni poprawny artefakt | Automatyczny producer flow, zmiana draftu podczas przygotowania, fail/retry, stale receipt rejection i zachowanie edytora | Pinned scene/run/mesh/space identity, quality, last-good i browser z żywym WebGL; mesh success nie zastępuje solve |
| 5 — P6 | Materialized dataset read/slice i pinned viewport | Rzeczywisty archive reopen, history/live A→B, integralność, ograniczony rozmiar odczytu i brak mutacji Live | Native/API/archive oraz browser receipt, budżet pamięci i exact source identity |
| 6 — P7 | Durable independent batches | Przyjęcie, materializacja dzieci, deterministyczne IDs/seedy, retry/cancel i backlog dla wspieranej strategii | Process E2E przypięty do batch/child RunIds; pozostałe strategie jawnie niezaliczone |
| Równolegle — B/P8 | Obecni właściciele kodu i grupy Compose | ABI/ownership/parity per lane; osobno clean install, upgrade i rollback produktu Windows oraz wspieranego Linux | Właściwe receipts runtime/science/release. Docker DEV nie zalicza samodzielnego Windows |

## 2. Precyzyjny zakres M1 i powiązanego authoringu

1. Zapisać source SHA, źródła pakietu, target, wersje i profil storage.
2. Uruchomić workspace i odróżnić dokument bez sesji od pustej symulacji.
3. Utworzyć niekompletny model; jawnie zapisać, czy flow utworzył RuntimeSession.
4. Dodać geometrię/region i dane materiałowe w zakresie dostępnego authoringu.
5. Pozostawić niepoprawny szkic; zweryfikować jego zachowanie bez publikacji złego IR.
6. Save/Close/Open: porównać tożsamość i semantykę modelu, nie tylko istnienie pliku.
7. Potwierdzić brak niejawnego solve. Utworzenie sesji samo w sobie nie oznacza solve.
8. Odrębnie odebrać failure/recovery i fizyczny desktop, jeśli wymagane przez target.

Projekt bez RuntimeSession ma obecnie zakres Saved Results/read-only według
ADR 0039. Brak edytora w tej ścieżce trzeba naprawić jako zadanie
authoringu, jeżeli jest wymagany przez odbierany scenariusz; nie zaliczać go
samym testem transportu archiwum i nie tworzyć ukrytej sesji dla obejścia testu.
Pakiety P1/P2 zachowują granice z planu 03; ta sekwencja łączy ich odbiór
użytkowy, a nie przenosi wszystkich zadań P2 do P1.

## 3. Zasady wykonania

W tej aktualizacji wykonano dokumentację, nie powyższe bramki. Nie uruchamiać
ich zbiorczo bez ustalenia źródeł, właściciela zasobów i zgodnej recepty.
Codzienny DEV korzysta z grupy Compose wybranego checkoutu; nie używać starego
runnera/natywnego launchera jako fallbacku. CI/release/nauka mają osobne
zarządzane trasy. Aktualne ograniczenia testów i udzielone wyjątki sprawdzić
w AGENTS i poleceniach użytkownika.

Wynik nieznany oznacza reconciliation zachowanego attemptu i receiptów,
nie ponowne Submit/Solve. Nie zatrzymywać obcego runtime, nie kasować cache,
sesji ani wyników jako sposobu przejścia bramki.
