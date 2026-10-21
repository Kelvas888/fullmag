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

Poniższa lista opisuje stan po pierwszej, przerwanej sesji. Wyniki wznowienia
odbioru na bieżącym `masterze` znajdują się na końcu dokumentu.

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

## Wznowienie odbioru na masterze — 20.10.2026

Baza: `42d92610312871d591db16a5b60a8f7a6d6339b5`, checkout
`C:\git\fullmag\fullmag`, branch `master`. Wcześniejsza refaktoryzacja jest
już w tej bazie. Zachowano niezwiązane zmiany
`scripts/docker_volume_dev.py` i
`scripts/docker_volume_capture_failure_reconcile.py`; nie wykonywano stagingu,
commita ani operacji integracji.

Kontener frontendu:
`da708d4161677eb7e3b11a0bbf9a9e07e90a84b2753d34d4840a789a206a550f`,
grupa `fullmag-master`, port `3198`, źródła readonly z tego checkoutu.
Kontener backendu był zatrzymany (`Exited (2)`). Sprawdzenia UI przeprowadzono
na `/dev/simulation-preparation`: produkcyjne komponenty, kontrolowane dane,
bez wywołania solvera. Nie jest to dowód działania żywej sesji ani backendu.

### Dodatkowe znalezione usterki i poprawki

1. **Ref przy przycisku przywracania:** pełny typecheck wykazał TS2322,
   ponieważ wspólny `ButtonProps` nie zawiera `ref`. Zamiast rozszerzać API
   wszystkich przycisków, okno wyszukuje swój przycisk przez
   `hostRef` i `data-preparation-restore`. Browser potwierdził fokus po
   minimalizacji, zamknięciu i Escape oraz powrót fokusu do uchwytu okna.
2. **Pozycja po maksymalizacji:** browser wykazał zmianę zapisanej pozycji
   na `(8, 8)` po przywróceniu, mimo zachowania rozmiaru. Dodano oddzielny
   zapis pozycji sprzed maksymalizacji oraz zabezpieczenie ograniczania
   pozycji przed wymiarami zmaksymalizowanego panelu. Pomiary granic są
   przechwytywane przed aktualizatorem stanu; obsługa geometrii korzysta
   z efektu layoutu. Końcowe sprawdzenie na świeżo uruchomionym frontendzie
   ujawniło dodatkowo wariant bez ręcznej zmiany rozmiaru. Globalna reguła
   `prefers-reduced-motion` nadawała wszystkim elementom przejście 1 ms,
   przez co pomiar widział jeszcze zmaksymalizowane wymiary. Panel otrzymał
   `transitionProperty: "none"`: geometria zmienia się synchronicznie.
   Scenariusz regresji obejmuje teraz osobno rozmiar CSS i rozmiar ręczny.
3. **Za mały log w wąskim układzie:** przy szerokości 390 px kontrolki
   pozostawiały około 36 px treści logu. Minimalna wysokość sekcji logu
   wzrosła do 360 px, a stosu etapów i logu do 540 px. Browser potwierdził
   156 px przewijanego logu. Całe szczegóły można przewijać wewnątrz okna.

Scenariusz `scripts/smoke-preparation-window.mjs` uzupełniono o:
kontrolę fokusu, rzeczywistą treść schowka i zgodność TXT z kopią,
minimalną czytelną wysokość logu, niski viewport oraz zrzut przy błędzie.
Nie kompilowano ani nie uruchamiano testów jednostkowych.

### Wyniki sprawdzeń przy wznowieniu

| Kontrola | Wynik i zakres |
| --- | --- |
| Pełny `pnpm typecheck` po poprawce przycisku | PASS, exit 0 |
| `pnpm lint` dla całego Control Room | FAIL środowiskowy: sterta Node około 2 GiB, `JavaScript heap out of memory`, exit 134 wewnętrznego procesu |
| ESLint sześciu plików okna i podglądu | PASS, exit 0 |
| Końcowy pełny typecheck, składnia smoke i ESLint DraggablePanel/smoke | PASS, exit 0 po poprawce przejścia geometrii i rozszerzeniu regresji |
| React Doctor, zakres plików zmienionych względem HEAD | 0 błędów; 6 ostrzeżeń `only-export-components` w istniejących eksportach `SimulationStartupOverlay.tsx`; bez zmiany publicznych eksportów |
| Przenoszenie klawiaturą i myszą | PASS: `(96,144)` → `(106,144)` → `(166,174)` |
| Zmiana rozmiaru klawiaturą i myszą | PASS: `960×680` → `950×680` → `890×640` |
| Przywrócenie pozycji po końcowej poprawce | PASS: rozmiar CSS `(96,32), 960×680` i ręczny `(106,32), 950×680` pozostają identyczne przed i po maximize/restore; brak błędów konsoli |
| Filtr tekstowy i poziom błędów | PASS: `Entry 14:` daje jeden wpis; Errors daje 5 wpisów, bez innych poziomów |
| Kopia do schowka | PASS: odczytano pełny wpis 14 z metadanymi i zachowaną drugą linią, bez sąsiednich wpisów |
| Pusty wynik filtra | PASS: zero wpisów, kopiowanie wyłączone |
| Eksport TXT | PASS: pomimo timeoutu narzędzia download plik rzeczywiście trafił do Downloads; odczyt UTF-8 i porównanie z zaobserwowaną treścią schowka dały dokładną zgodność |
| Czytanie starszych wpisów i dopisanie nowego | PASS: `scrollTop=1586` przed i po dopisaniu 61. wpisu, także przez ukrycie/przywrócenie |
| Powrót do końca logu | PASS: odstęp od końca 0 px |
| Minimize/close/Escape oraz fokus | PASS; aktualizacja failed/stale nie otwiera ukrytego okna |
| Nowe preparation ID i formularz w tle | PASS: okno otwiera się, tekst roboczy pozostaje niezmieniony |
| Zakończenie (`ready`) | PASS: panel i przycisk przywracania znikają; nowe przygotowanie otwiera panel ponownie |
| Viewport 390×844 i 1280×500 | PASS dla granic okna i dostępności zamknięcia; 156 px treści logu w poprawionym układzie wąskim |
| Pełny skrypt smoke i żywa sesja backendu | NOT VERIFIED; powyższe dowody pochodzą z interakcji CUA z produkcyjnym komponentem w podglądzie |

Pierwszy React Doctor w cieniu źródeł nie wykrył kontekstu Git i rozpoczął
pełny skan; zatrzymano wyłącznie własny proces. Wąski skan wykonano z
readonly źródeł `/opt/fullmag/source/apps/control-room`, używając
zainstalowanego narzędzia w wolumenie frontendu, `--scope files --base HEAD`,
bez telemetrii, bez supply-chain i bez instalacji zależności.

### Pamięć i artefakty

`compose.dev.yaml:246` ustawia frontendowi `mem_limit: 6g`; `cpus: 2`
jest w linii 245. Docker inspect potwierdził 6 442 450 944 bajtów
i 2 000 000 000 NanoCPUs. Pomiar cgroup wyniósł 6 263 447 552 bajtów,
a RSS procesu Next 5 431 536 KiB. To mały zapas dla równoległych kontroli.
Nie zmieniano limitów. OOM procesu lint i limit całego kontenera to
odrębne ograniczenia; podniesienie jednego nie dowodzi usunięcia drugiego.

Logi kontroli: `/state/development/preparation-ui-verification/`
w istniejącym wolumenie frontendu. Zachowano logi i cache; nie usuwano
kontenerów, wolumenów ani danych użytkownika. Zrzuty odbiorowe są w katalogu
wizualizacji bieżącego zadania. Pozostają materiałem UI, nie receiptami
runtime ani kwalifikacją fizyki.

Pobrany plik `C:\Users\Mateusz\Downloads\simulation-preparation-log.txt`
ma 182 bajty i SHA-256
`856c3b1cb918e335873d589f85f84b7ddd102fc687b7dbd70b0cb8368f86e337`.
Nie zawiera wpisów sąsiednich ani obcięcia diagnostyki.
Zrzut wąskiego układu:
`C:\Users\Mateusz\.codex\visualizations\2026\10\20\01a1598d-f866-7f41-b21a-f79aa0e7eb0f\preparation-narrow.png`.

Podczas ostatniego powtórzenia kontroli grupa `fullmag-master` ponownie
zniknęła (`No such container`; pusty odczyt kontenerów z etykietą projektu).
Odczyt statusu czatu „Przywróć wizualizacje FEM i FDM” potwierdził trwające
zarządzane odtworzenie usług i obrazu po recovery. Nie uruchomiono
konkurencyjnej operacji. Po odtworzeniu frontend
`084b594d7f1cf36aadb95b627cdac257b349673ac26725d65a5ba57a885358dc`
udostępnił ten sam checkout na porcie 3198. Końcowy typecheck, lint poprawionych
plików, składnia smoke, stan ready i oba warianty maximize/restore zakończyły
się sukcesem. Pełny samodzielny smoke, żywa sesja backendu, jasny motyw oraz
browser regression Data Preview pozostają NOT VERIFIED. Konsument Data Preview
został przejrzany źródłowo; nie włącza opcji resize/maximize.
Niezależne review poprzedzające końcową poprawkę przejścia nie wykazało regresji;
końcową poprawkę sprawdzono źródłowo, typecheckiem, lintem i w przeglądarce.

Końcowy zrzut desktopowy:
`C:\Users\Mateusz\.codex\visualizations\2026\10\20\01a1598d-f866-7f41-b21a-f79aa0e7eb0f\preparation-desktop.png`.

### SHA-256 źródeł po dodatkowych poprawkach

| Plik | SHA-256 |
| --- | --- |
| `SimulationStartupOverlay.tsx` | `9d05abaf152dc14a8b3f35ac2a03cdc6c995eb3891b8daf5a4776d73143f157d` |
| `DraggablePanel.tsx` | `6a7a3c179fc8b231419f5441c9735799b10452a91044f802a8d767688fabe326` |
| `dialog-simulation-startup.css` | `622efa7b8caa74fe09826196b08bc930bcf5a94232d9e6280d614089185a0e5a` |
| `smoke-preparation-window.mjs` | `3ca64cfe93932ec86ee82c4b643ef4c7a32a54730cc262de91c257227f594597` |

## Korekta limitów frontendu — wdrożenie zweryfikowane

Na polecenie użytkownika ustawiono w źródłach `mastera` limit frontendu
16 GiB RAM, 4 CPU oraz `--max-old-space-size=6144` dla narzędzi Node i
sanityzowanego środowiska launchera Next. Receipt frontendu zapisuje
`node_max_old_space_size_mib: 6144`. Zmiana nie obejmuje limitów backendu.

Odczyt Compose potwierdził nowe wartości; parser Python i kontrola diff
zakończyły się poprawnie, review statyczny nie wykazał regresji.
Testy helpera nie zostały uruchomione: automatyczna kontrola uprawnień
odrzuciła je jako objęte tymczasowym zakazem testów jednostkowych.

Odczyt przed wdrożeniem wykazał nadal `memory.max=6442450944` i
`cpu.max=200000 100000`. Proces `next-server` miał
`NODE_OPTIONS=--max-old-space-size=100642 --enable-source-maps --inspect=127.0.0.1:0`.
Zainstalowany `next/dist/cli/next-dev.js:274` sprawdza jawny limit i przy
jego braku przyjmuje połowę `os.totalmem()`. To wyjaśnia niezgodność sterty
około 98 GiB z limitem kontenera 6 GiB. Jawne 6144 MiB zapobiega temu
automatycznemu doborowi; sam zapis źródeł nie zmienia działającego procesu.

Po uzgodnionym zarządzanym odtworzeniu grupy wdrożenie limitów ma **PASS**:
nowy działający frontend
`a977d68e3b74c60df5dcc5cadd0f4e7791a6bb1eed65bf1672d7c6ab07abc69e`
używa obrazu
`sha256:dffb31c9ea100873e08271843cc5ecc00cb101feb59a0fcb7a01483f2e7ac495`.
Docker inspect: `Memory=17179869184`, `NanoCpus=4000000000`.
Cgroup: `memory.max=17179869184`, `cpu.max=400000 100000`.
Proces Next PID 27 ma `--max-old-space-size=6144`, a rzeczywisty
`next-server` PID 43:
`--max-old-space-size=6144 --enable-source-maps --inspect=127.0.0.1:0`.
6144 MiB jest limitem old space; nie oznacza równego mu całkowitego RSS.
Dowód limitów nie zastępuje gotowości API ani weryfikacji recovery,
opisanej w `2026-10-20-preparation-recovery.md`. Nie utworzono
automatyzacji okresowego wznowienia — jej próbę odrzuciła kontrola uprawnień.

Po kolejnej rekreacji wynik limitów ponownie **PASS**: frontend
`e1a04f452f84c610135ea6b43c1bf641af118eaa48dfcd2fd902c4ad588d2fff`,
obraz `sha256:e30f3cf928e9b970f4963b41b51faad1a6fe2776832c5bebc102f6fd18dd08f3`.
W inspect, cgroup i środowisku działających procesów Next PID 27/43
potwierdzono te same wartości 16 GiB / 4 CPU / 6144 MiB old space.
