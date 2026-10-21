# Fullmag — plan refaktoryzacji i aktualny stan

Aktualizacja: **20.10.2026**. Baza kodu: lokalny
`master@42d92610312871d591db16a5b60a8f7a6d6339b5`.
Stan całego planu: **IN PROGRESS — pełny odbiór produktu niepotwierdzony**.
Równoległe niezacommitowane zmiany nie są częścią tej bazy.

## Od czego zacząć

| Dokument | Rola |
|---|---|
| [06 — aktualna tabela postępu](06-status-realizacji.md) | Osobno implementacja, wykonane historyczne kontrole i brakujący odbiór |
| [03 — plan wykonania](03-plan-refaktoryzacji.md) | Zachowany zakres P0–P8/B oraz kolejność dalszych przyrostów |
| [07 — najbliższe bramki](07-domkniecie-etapow.md) | Konkretne warunki zamknięcia, bez ponownego implementowania gotowych fragmentów |
| [08 — reaudyt mastera](08-reaudyt-master-2026-10-20.md) | Dziesięć rozbieżności dawnej dokumentacji z kodem, symbole i fingerprinty |
| [02 — architektura i kontrakty](02-architektura-i-kontrakty.md) | Docelowe granice i częściowo wdrożone elementy |
| [04 — kwalifikacja](04-kwalifikacja-i-scenariusze.md) | Normatywne scenariusze CAE i reguły zaliczania dowodów |
| [05 — dowody i ADR](05-dowody-i-adr.md) | Historyczne materiały wejściowe oraz późniejsze decyzje |
| [01 — audyt bazowy z mapą aktualizacji](01-finalny-audyt.md) | Ustalenia z 20.09; nie bieżąca lista brakującego kodu |
| [09 — kontrola aktualizacji](09-weryfikacja-aktualizacji.md) | Zachowanie zakresu, archiwów i materiałów oraz kontrola linków |

## Aktualny obraz

Główne zabezpieczenia storage, application use cases, durable Submit,
scoped API/cache i liczne adaptery są już w kodzie. P6 ma publiczny odczyt
materialized datasets, a P7 — trwałą obsługę independent batches.
Pełny authoring definicji niezależny od wykonania, wszystkie wymagane
scenariusze recovery/steering, kwalifikacja lane’ów i wydanie pozostają do
rozliczenia. Obecność implementacji nie zastępuje ich odbioru.

Dawne **49% całości** oraz procenty etapów są wycofane z bieżącego raportowania:
nie mają aktualnego, wspólnego mianownika. Nie zastąpiono ich nowymi ocenami
intuicyjnymi. Tabela 06 wskazuje zakres wdrożony i zakres dowodów; `NOT VERIFIED`
nie oznacza automatycznie braku kodu lub nieudanego testu.

Świeży odczyt źródeł: **307 ścieżek / 371 operacji OpenAPI**,
**371 rozpoznanych handlerów**, 0 nierozpoznanych handlerów/konsumentów
w heurystyce inventory. Historyczne 304 operacje nie pokrywają bieżącego API.
Nowy wykaz i granice review są w [P0](p0/07-current-api-inventory.md)
oraz [P3a](p3a/10-current-endpoint-review.md).

## Build i produkt

Codzienny DEV prowadzi przez przypisaną do checkoutu grupę Docker Compose:
`docker-dev-toolchain` i `docker-dev`, zgodnie z AGENTS i
[ADR 0061](../../../../adr/0061-docker-development-build-and-runtime-container.md).
Źródła, usługi, wolumeny i receipty muszą należeć do tej samej grupy.
Nie jest to polecenie restartu działającego środowiska.

**Niezależna dystrybucja Windows pozostaje wymaganiem P8-C.**
Docker DEV ani jego Linux runtime nie kwalifikują instalacji Windows bez
Docker/WSL. Osobne bramki CI/release/nauki zachowują właściwe zarządzane recepty.

## Historia i zasady utrzymania

- [Poprzedni punkt wejścia](README-historyczny-2026-10-20.md).
- [Dziennik checkpointów do 15.10](06-status-historyczny-do-2026-10-15.md).
- [Dawny plan domknięcia z 02.10](07-domkniecie-historyczne-2026-10-02.md).

Są to zachowane kopie historyczne. Ich określenia „aktualny”, porty, blokery,
procenty i polecenia obowiązują wyłącznie w kontekście opisanej daty.
Nowe aktualizacje trafiają do krótkiej tabeli 06 i właściwego checkpointu.
Każda deklaracja PASS musi określać źródło, zakres, target i końcowy wynik.
