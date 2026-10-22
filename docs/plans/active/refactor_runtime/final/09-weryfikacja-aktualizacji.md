# Weryfikacja aktualizacji dokumentacji — 20.10.2026

Zakres: dokumentacja w `docs/plans/active/refactor_runtime/final`.
Baza opisu implementacji: lokalny `master`,
`42d92610312871d591db16a5b60a8f7a6d6339b5`.
Nie wykonywano fetch, aktualizacji mastera ani weryfikacji bieżącego GitHub CI.
Równoległe dirty zmiany aplikacji, launcherów i infrastruktury nie należą do
opisywanej bazy. Nie zmieniono ich w ramach tego zadania.

## Wynik i zachowany zakres

Zaktualizowano punkt wejścia, audyt bazowy, architekturę, plan wykonania,
reguły kwalifikacji, rejestr dowodów, tabelę postępu i kolejność domknięcia.
P0/P3a mają osobne aktualne inventory API i rejestr review; stare inventory
oraz jego historyczne wyniki pozostają zachowane.

| Kontrola | Wynik | Metoda i granica |
|---|---|---|
| Pakiety planu 03 | **PASS — 48/48**, ta sama kolejność identyfikatorów | Porównanie identyfikatorów wierszy P0–P8/B z `git show HEAD`; nie wykonanie pakietów |
| Scenariusze kwalifikacji 04 | **PASS — 88/88**, ta sama kolejność identyfikatorów | Porównanie wierszy CAE/FINAL z HEAD; nie wyniki tych scenariuszy |
| Referencje kontraktów 02 | **PASS — bez utraty identyfikatorów** | Porównanie zbioru jawnych odwołań Kxx z HEAD; pełny normatywny zakres K01–K18 pozostaje wskazany |
| Materiały wejściowe audytu | **PASS — 18/18 hashy zgodnych** | SHA-256 bieżących bajtów oryginalnych materiałów względem niezmienionego manifestu w 05 |
| Kopie historyczne | **PASS — dokładne bajty sprzed zastąpienia** | Hashe poniżej; zachowano wspólny katalog, więc względne linki mają tę samą bazę |
| Odwołania do dawnych nagłówków 06/07 | **PASS — brak takich odwołań w Markdown `docs/`** | Wyszukanie linków `06-status-realizacji.md#…` i `07-domkniecie-etapow.md#…`; nie ogólny walidator wszystkich kotwic |
| Diff whitespace | **PASS** | `git diff --check -- docs/plans/active/refactor_runtime/final`, exit 0; bez zmian aplikacji |
| Lokalne odsyłacze Markdown | **PASS — 793 odsyłacze w 24 plikach, 0 brakujących celów** | Zmienione i nowe Markdown pakietu, łącznie z archiwami; kontrola istnienia ścieżki, bez ogólnej walidacji kotwic i URL zewnętrznych |
| Struktura tabel bieżących dokumentów | **PASS — 58 tabel, 0 rozbieżności kolumn** | Archiwa zachowane bajtowo są wyłączone z korekt formatowania; uwaga poniżej |
| JSON i macierz API | **PASS — 371 unikalnych operacji w obu formatach** | Odczyt JSON, porównanie metoda/ścieżka z właściwą tabelą Markdown i hash schematu; dodatkowe 2 router-only są osobną tabelą |
| Zakres zmian API względem historycznego inventory | **304 zachowane + 67 dodanych, 0 usuniętych** | Porównanie po metodzie i znormalizowanej ścieżce; nie dowodzi niezmienionej semantyki 304 zachowanych operacji |

Nowe inventory używa `operation_mapping(root, {})` z istniejącego
`scripts/audit_refactor_p0.py`. Źródła routera i OpenAPI sprawdzono względem
HEAD; konsumentów ze współdzielonego dirty checkoutu celowo nie kwalifikowano.
Wszystkie 371 operacji mają `REVIEW REQUIRED` w nowym rejestrze P3a.
Nie oznacza to 371 znalezionych błędów ani unieważnienia całej wcześniejszej
implementacji — oznacza brak przypiętego aktualnego review semantyki.

Pierwsza szeroka kontrola tabel wskazała dwa nieescapowane znaki `|`
w zachowanym starym statusie (linie 1757 i 1761); pozostawiono dokładną
kopię archiwalną. Licznik endpointów rozdzielono na właściwe 371 operacji
OpenAPI i osobne 2 router-only. Po tym doprecyzowaniu zakresu kontrola
bieżących tabel oraz zgodności JSON/Markdown zakończyła się PASS.
Nie są to testy aplikacji.

## Archiwa

| Plik | SHA-256 zachowanej kopii |
|---|---|
| [Dawny README](README-historyczny-2026-10-20.md) | `907016ad829d9bd76ab94fa59f9101e56485ba92e39340180094fd1993515062` |
| [Dawny status](06-status-historyczny-do-2026-10-15.md) | `4c1c57435be5914c6a5f7692bdb8884f6bced6749ed28d4cd74afd0a491894a3` |
| [Dawny plan domknięcia](07-domkniecie-historyczne-2026-10-02.md) | `1ea98cd66fbda882688518592c0814313263cf6508e6939e3a7e4b2f1fe98905` |

Nie przepisano historii testów na nowy HEAD. [Tabela postępu](06-status-realizacji.md)
rozdziela obecność kodu, wykonania zapisane w checkpointach, świeże kontrole
źródłowe i brakujące dowody. Dawne procenty pozostają w archiwach.

## Granice

- Nowe testy jednostkowe/integracyjne aplikacji: **NOT RUN**.
- Nowy build, restart lub próba managed runtime: **NOT RUN**.
- Nowy browser/WebGL smoke: **NOT RUN**.
- Nowa kwalifikacja naukowa lub wydania: **NOT RUN**.
- Ponowny odczyt wszystkich historycznych receiptów i aktualnego CI: **NOT VERIFIED**.

Aktualizacja dokumentacji nie zamyka bramek produktu i nie zmienia physics,
API, normatywnej treści ADR, konfiguracji storage ani uprawnień do wykonania.
Nie wykonywano stagingu, commita, push, migracji ani usuwania danych.
