# Simulation preparation — audyt i refaktoryzacja interfejsu

Data: 20.10.2026. Checkout: `C:\git\fullmag\fullmag`, branch `master`,
HEAD `88a9b68d29ec173a0b1f1b8750c126da022b0244`.

**Stan: zmiany lokalne zaimplementowane; końcowa weryfikacja przeglądarkowa
zablokowana przez usunięcie współdzielonych kontenerów podczas pracy.**
Raport nie stanowi kwalifikacji runtime, fizyki ani wydania.

## Zakres i ochrona istniejącej pracy

Użytkownik zlecił audyt i poprawę czytelności, wyglądu, przesuwania,
minimalizacji, powiększania, ukrywania, zamykania oraz obsługi logów.
Osobnym poleceniem wskazał pracę bezpośrednio na `masterze`.

Checkout był zmodyfikowany przed rozpoczęciem zadania, w tym
`SimulationStartupOverlay.tsx` i `simulationPreparationModel.ts`.
Zachowano istniejące rozszerzenia selektora tożsamości sesji i etykiet
aktywacji. Nie zmieniano modelu przygotowania, backendu, danych użytkownika
ani parametrów solvera. Nie wykonywano stagingu, commita, resetu ani operacji
Git na pozostałej pracy. W trakcie zadania pojawiały się kolejne niezależne
zmiany w checkoutcie.

Zwykłe `git status --short` nie mogło odczytać metadanych submodułu
`external_solvers/3`; inwentarz głównego checkoutu odczytano przez
`git status --short --ignore-submodules`. Nie zmieniano uprawnień submodułu.

## Ustalenia audytu

| Problem w stanie wejściowym | Dowód źródłowy | Wprowadzona korekta |
| --- | --- | --- |
| Panel nie miał obsługi przesuwania, zmiany rozmiaru ani przycisków okna | `SimulationStartupOverlayView`; pozycja `fixed`, `bottom` i `inset-inline-end` w `dialog-simulation-startup.css` | Wykorzystanie wspólnego `DraggablePanel`, sterowanie wskaźnikiem i klawiaturą |
| Użytkownik nie mógł usunąć panelu zasłaniającego workspace | Brak lokalnego stanu widoczności i zdarzenia zamknięcia | Minimalizacja do podsumowania, zamknięcie do małego przycisku przywracania, Escape |
| Rozwinięcie zmieniało szerokość panelu, ale użytkownik nie kontrolował jego geometrii | Reguła `:has(...data-state="open")`, zagnieżdżone limity wysokości | Jawne rozwinięcie, uchwyt rozmiaru, maksymalizacja i przywrócenie wcześniejszej geometrii |
| Treść logu konkurowała z trzema kolumnami metadanych | Stary grid `80px 52px 112px minmax(0, 1fr)`, mała czcionka | Metadane nad wiadomością, pełna szerokość tekstu, zachowane nowe linie i łamanie długich fragmentów |
| Brak wyszukiwania i eksportu zwykłego logu | Dostępny był tylko powrót do końca; kopiowanie diagnostyki dotyczyło błędu | Wyszukiwanie treści/etapu, All/Warnings/Errors, licznik, kopiowanie i plik TXT widocznych wpisów |
| Dane techniczne poprzedzały najważniejsze etapy i log | Kolejność JSX wewnątrz Accordion | Etapy i log na początku; wykonanie i provenance w osobnym rozwijanym szczególe |
| Czytelność szczegółu etapu ograniczało jednoliniowe obcinanie | `white-space: nowrap`, `text-overflow: ellipsis` | Zawijanie szczegółu etapu i responsywny układ zależny od szerokości okna |

## Zachowanie po zmianie

- Początkowo okno pokazuje krótki status. Rozwinięcie udostępnia etapy i log.
  Maksymalizacja otwiera również szczegóły.
- Pasek tytułu umożliwia przeciąganie. Przycisk uchwytu pozwala przesuwać
  okno strzałkami; Shift zwiększa krok z 10 do 40 px.
- Uchwyt w prawym dolnym rogu rozwiniętego okna zmienia jego rozmiar
  wskaźnikiem lub strzałkami. Geometria jest ograniczana do viewportu;
  ResizeObserver i zdarzenie resize korygują położenie.
- Minimalizacja pozostawia podsumowanie, zamknięcie — mały przycisk
  „Preparation”. Oba umożliwiają ponowne otwarcie. Escape działa tylko
  wewnątrz okna i respektuje obsłużone zdarzenia kontrolek potomnych.
- Ukrycie okna nie wysyła Stop, nie przerywa przygotowania i nie zmienia
  subskrypcji zasobu. Nie ma modalnego backdropu ani blokady workspace.
- Lokalny stan okna należy do konkretnego `preparation_id`. Aktualizacja
  revision, błąd lub reconnect tego samego przygotowania nie otwierają
  samoczynnie zamkniętego panelu. Nowe przygotowanie otwiera własne okno.
  Przejście z nieznanego przygotowania do pierwszego opublikowanego ID
  również rozpoczyna nowy lokalny stan.
- Ukryta zawartość pozostaje zamontowana, aby zachować filtr i wyszukiwanie.
  Fokus przechodzi do przycisku przywracania i wraca do kontrolki okna po
  jego ponownym otwarciu. Pierwsze pojawienie się panelu nie przejmuje fokusu.
- Błąd pozostaje widoczny w podsumowaniu/przycisku przywracania. Region
  ogłoszeń dostępności działa również po ukryciu zawartości.
- Log korzysta z istniejącego ograniczonego ogona zasobu, maksymalnie
  200 wpisów. Eksport dotyczy **widocznych, przefiltrowanych wpisów**,
  nie pełnego historycznego logu silnika.
- Jeden efekt widoku odpowiada za przewijanie do końca. Ręczne przewinięcie
  do starszych wpisów wyłącza śledzenie; przycisk powrotu je przywraca.
  Obserwacja rozmiaru viewportu obsługuje też otwarcie szczegółów bez nowej
  rewizji zasobu. Pobranie pliku zwalnia utworzony object URL.

Stan położenia, rozmiaru, rozwinięcia, widoczności i filtrów jest lokalnym
stanem UI. Zasoby serwera pozostają w dotychczasowych resource hooks.
Nie dodano endpointów, store zasobów ani trwałego zapisu stanu symulacji.

## Mapa zmian

Ścieżki poniżej są względem `apps/control-room/`.

| Plik | Odpowiedzialność |
| --- | --- |
| `src/shared/ui/DraggablePanel.tsx:46` | Wspólne przesuwanie, resize, maksymalizacja, przywracanie, Escape, opcjonalne zachowanie zamontowanej zawartości |
| `src/kernel/layout/SimulationStartupOverlay.tsx:118` | Widoczność per przygotowanie, sterowanie oknem, fokus, układ etapów i provenance |
| `src/kernel/layout/SimulationPreparationLog.tsx:69` | Filtrowanie i serializacja; obsługa logu od linii 139 |
| `src/design/styles/dialog-simulation-startup.css` | Geometria, hierarchia, responsywność i przycisk przywracania |
| `src/design/styles/simulation-preparation-log.css` | Osobny układ czytelnego logu |
| `src/design/styles/primitives.css` | Wspólny pasek i uchwyt okna |
| `app/globals.css` | Wyłącznie import nowego arkusza |
| `app/dev/simulation-preparation/page.tsx` | Podgląd komponentów dostępny tylko przy `NODE_ENV=development`; pozostałe tryby zwracają notFound |
| `scripts/fixtures/preparation-window-page.tsx` | Kontrolowane fazy i logi bez klienta API i bez mutacji symulacji |
| `scripts/smoke-preparation-window.mjs` | Wykonywalna regresja interakcji okna i logów |
| `src/kernel/layout/simulationPreparationTestDom.test-support.ts` | Wymiary viewportu w istniejącym pomocniku DOM |

Zmiana wspólnego `DraggablePanel` obejmuje także jego istniejącego konsumenta
`DataPreviewDialog`. Nowe resize, maksymalizacja i zachowanie zawartości
są opt-in; przesuwanie, ograniczanie położenia, dostępny uchwyt oraz Escape
dotyczą wspólnego prymitywu. Przegląd konsumenta wykonano źródłowo;
regresja jego działania w przeglądarce pozostaje `NOT VERIFIED`.

## Weryfikacja i granice dowodów

Wybrana grupa: `fullmag-master`. Przed kontrolami odczytano rzeczywiste mounty
`fullmag-master-frontend-1`: readonly źródła wybranego checkoutu, workspace i
cache w wolumenie `fullmag-dev-frontend-v1-32cabae4c4219a8a214b429b`.
Frontend był dostępny na loopback `3198`. Wolumen miał około 593 GiB wolnego
miejsca. Nie uruchomiono buildu backendu, nie instalowano zależności na hoście
i nie kompilowano testów jednostkowych.

| Kontrola | Wynik |
| --- | --- |
| `git diff --check` dla zmienionych źródeł | PASS, exit 0 |
| `node --check scripts/smoke-preparation-window.mjs` | PASS, exit 0; tylko składnia |
| Oględziny produkcyjnego workspace przez przeglądarkę | Potwierdzone pojawienie się nowego paska; **nie jest to dowód wszystkich interakcji ani końcowych źródeł** |
| `pnpm typecheck` w stałym frontendzie | FAIL poza zakresem: pięć diagnostyk poniżej; bez diagnostyk ówczesnych zmienionych komponentów |
| `pnpm lint` w stałym frontendzie | Przerwane wraz ze zniknięciem kontenera; brak terminalnego raportu lint |
| Końcowy typecheck, lint i React Doctor | NOT VERIFIED po końcowych poprawkach i dodaniu kontrolowanego podglądu |
| `smoke-preparation-window.mjs` | Zapisany; wykonanie NOT VERIFIED |
| Testy jednostkowe | Nie uruchomiono ani nie kompilowano — obowiązuje tymczasowy zakaz użytkownika |
| Runtime, fizyka, release | Poza zakresem kwalifikacji tego zadania |

Pierwsze wywołanie typecheck zostało prawidłowo odrzucone przez walidację
ścieżki `.fullmag-frontend`. Następne użyło rzeczywistego
`FULLMAG_FRONTEND_ROOT=/state/development/cache`. Wygenerowało typy tras,
a następnie zwróciło:

```text
primitiveSurfaceColor.ts(95,7): TS2322 string | undefined -> string
FieldMapModule.tsx(610,19): TS2304 Cannot find name 'evidenceStatus'
FieldMapModule.tsx(613,19): TS2304 Cannot find name 'evidenceStatus'
ObjectRegionMagneticParametersPanel.tsx(48,3): TS2440 materialFieldDraftKey
ObjectRegionMagneticParametersPanel.tsx(198,25): TS2554 Expected 2 arguments
```

W trakcie dalszej weryfikacji oba kontenery aplikacji zniknęły. Odczyt
`docker inspect fullmag-master-frontend-1` zwrócił `No such container`.
W grupie pozostał kontroler operacji `terminal-helper-retention`.
To zadanie nie usuwało ani nie zatrzymywało kontenerów. Nie uruchomiono
konkurencyjnego startu; skierowano do użytkownika pytanie o równoległą operację.

Logi uruchomionych kontroli skierowano do
`/state/development/preparation-ui-checks/` w wolumenie frontendu.
Nie usuwano cache, logów, wolumenów ani danych użytkownika. Ich ponowny
odczyt i kwalifikacja retencji wymagają powrotu uprawnionego konsumenta
właściwego wolumenu. Nie tworzono osobnego kontenera do odczytu ani buildu.

## Pozostały odbiór

Po zakończeniu równoległej operacji i przywróceniu grupy wybranego checkoutu:

1. Potwierdzić ID usług, mounty i port; ponownie uruchomić końcowy typecheck,
   lint i scoped React Doctor w stałym frontendzie.
2. Otworzyć `/dev/simulation-preparation` w tej samej grupie. Sprawdzić
   pointer/keyboard drag i resize, maximize/restore, Escape, minimalizację,
   zamknięcie, filtr, kopię i TXT, zachowanie scrolla po append oraz nowy ID.
3. Wykonać `smoke-preparation-window.mjs` w dozwolonej zarządzanej ścieżce
   przeglądarkowej, z `CONTROL_ROOM_URL` tej grupy i raportem w jej wolumenie.
   Sprawdzić również Data Preview, jasny motyw i małą wysokość viewportu.
4. Zaktualizować ten raport na podstawie exit codes i zrzutów końcowych źródeł.

Nie uznawać samej obecności scenariusza, zrzutu wcześniejszej wersji lub
częściowego typecheck za ukończenie odbioru.

## SHA-256 źródeł po refaktoryzacji

| Plik | SHA-256 |
| --- | --- |
| `SimulationStartupOverlay.tsx` | `0fb3aed56b5f6d8cba9c59819d520b4b09d6b22c9790f00579772cd3df65fd20` |
| `SimulationPreparationLog.tsx` | `25189f9ba15c3df3e8927c3c117c286b527665bc66ce6ea4dad48ab4c42e58fa` |
| `DraggablePanel.tsx` | `469403e0bee50a6e5d16e5f450e3f84733e7baaafbcc499da1a9b5703a3c5f44` |
| `dialog-simulation-startup.css` | `d5944303854bf6f8db4b82a0f800d0a6b436e71f5fa61671be082697b056d65e` |
| `simulation-preparation-log.css` | `d6d9195dd75d925f51fdcc1864f46624ba78fe91bb0821d9de84f1b10cddfebe` |
