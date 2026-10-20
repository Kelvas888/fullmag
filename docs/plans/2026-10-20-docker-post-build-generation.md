# Dokończenie startu Docker DEV po opublikowaniu pakietu

Cel: uruchomić API/native runtime zachowując oczekujący run, historię, Windows
storage i named volumes po potwierdzonej awarii przed nowym ownerem.

Potwierdzone: build i oba gates przeszły; preflight accepted został naprawiony;
rotacja generacji odmawia z powodu brakującego kontekstu kontrolowanego odtworzenia.
Kontrakt: [ADR 0066](../adr/0066-docker-post-build-generation-continuation.md).

1. Hostowy helper i `docker_volume_dev.py`: osobny zamknięty rekord wiążący
   historyczny stop/accepted proof z niezmienionym Failed ownerem oraz osobno
   rzeczywiście zatrzymaną nową inkarnacją. Świeży native config pin pod
   `OWNER.lock`; rewalidacja przed i pod lease. Nie używać false-bootstrap
   selektora ani starego journalu jako nowego `native_restart_metadata`.
2. Użyć istniejącego `start(previous_config_sha256=...)`, zapisu metadanych
   i kontrolowanego resume. Zachować generation-only rotator i atomowy backup.
   Po zamknięciu recreate i BuildKit ponownie sprawdzić kontekst pod nowym
   lease development; zapisać powiązany pending. Runtime sprawdza utrzymywany
   lease, attempt, brak terminala i piny przed użyciem starego SHA; po rotacji
   lub no-op zapisuje consumed. Consumed kieruje kolejny restart do zwykłego
   drain; martwy pending nie autoryzuje restartu. Przerwanie po publikacji
   pozwala aktywnej operacji dokończyć consumed bez powtórnej rotacji.
   Nie dodawać osobnego rozbudowanego protokołu intent.
3. Zarządzane regresje Python w grupie Compose: prawdziwy dodatni przypadek,
   drift dowodów, aktywne własne zasoby, brak proofu, lock/lease i replay.
   Bez lokalnej kompilacji testów Rust. Niezależny review całego przepływu.
4. Jedna kontrolowana próba na rzeczywistym zatrzymanym backendzie: aktualne
   piny terminala/Compose, ten sam storage/cache, build i native/API ready.
   Następnie stabilność, przeglądarka/WebGL, restart bez zmian i mała zmiana
   backendu. Zielone fixture nie zastępują tych dowodów.
5. Dalszy odbiór pełnego celu: HMR na Windows, skrypty `.py` z manual wait i
   auto Solve, FDM/FEM CPU/GPU w obsługiwanym zakresie, trwałość, izolacja
   grup i retencja. Nie oznaczać pełnego wdrożenia jako ukończonego wcześniej.

Root odpowiada za integrację, dokumentację, testy Docker i review. Worker hosta
przygotowuje launcher/helper; worker runtime przygotowuje minimalny guard
pending/consumed i regresje rotacji/replay. Nie zmieniają równolegle tych samych plików. Stan wykonania
pozostaje w rejestrze zadania; ten plan nie jest dowodem runtime.


## Dowody odbioru pełnej architektury — checkpoint 20.10.2026

Zakres pochodzi z siedmiu warunków odbioru przewodnika architektury, a nie
z listy zakończonych poprawek. Poniższe wyniki nie kwalifikują innych źródeł.

| Wymaganie | Aktualny dowód | Brakująca weryfikacja |
| --- | --- | --- |
| Dwie stałe usługi, backend buduje i uruchamia API | Compose oraz inspect własnej grupy pokazują backend i frontend; log backendu 1e5b6066 potwierdza Make exit 0 i pakiet 24 plików | Backend jest exited 1; API nie uruchomiło się z powodu bramki rotacji konfiguracji |
| Jeden log, cache, restart ze stałym ID | Make 97502 ms; zachowane wolumeny build/package v2; frontend pozostał uruchomiony | Restart bez zmian oraz rzeczywista mała zmiana backendu po naprawie startupu |
| Home i API pod adresem frontendu | GET 127.0.0.1:32871/workspace zwrócił HTTP 200 i 48853 bajty | Widoczny Home w przeglądarce, stabilne API, WebGL; sam HTML nie dowodzi renderu |
| Skrypt .py, aktywny model, auto Solve i manual wait | Historyczny accepted-run 9f453e3a jest nadal zachowany; readonly producer i preflight przeszły | Przywrócenie modelu w UI oraz oba osobne scenariusze startu skryptu; bez powtórzenia held Solve |
| Trwałość bazy, sesji i wyników | Mounty i dotychczasowy Windows storage zachowane | Porównanie danych przed i po prawidłowym restarcie |
| CPU/GPU i artefakty | Zbudowany pełny backend; źródłowy kontrakt mixed-P1 v2 istnieje | Rzeczywiste FDM/FEM CPU/GPU, requested/resolved/executed i poprawne artefakty; rings oraz fizyka nadal NOT VERIFIED |
| Izolacja grup i wspólne rezerwacje | Nazwa projektu i osobne wolumeny/sieć własnej grupy; cudza grupa nie była zatrzymywana | Równoczesny kontrolowany odbiór dwóch grup oraz brak obejścia wspólnych rezerwacji |

Dowód retencji jest osobny: actual readonly backup inventory po poprawce
przeszło w `verification/retention-inventory/46dc2f13f6f34480905bd76c5fb0df84.json`.
Nie usunięto wtedy danych. Potrzebny pozostaje rzeczywisty raport automatycznej
retencji kolejnych opublikowanych generacji i pomiar miejsca. Dane użytkownika,
bieżący pakiet, rollback i cache pozostają zachowane.

PR #222 scalono jako `d0031ce6d220738609b9fa055d90e52eb6e94213` po 17 zielonych
kontrolach CI; 9 kontroli pominięto. To dowód integracji dwóch poprawek, nie
ukończenia odbioru runtime. Lokalny główny checkout nadal ma cudze zmiany
blokujące fast-forward; własny worktree wskazuje wynikowy commit.

## Weryfikacja implementacji kontynuacji generacji

- Regresje runtime: 116 testów, 3 pominięte, wynik OK;
  `verification/interpreted-attempts/3ba43c584cf447c9a58b2044e053cee6.json`.
- Helper, konsument startu i wcześniejsza ścieżka pre-admission: 40/40;
  `verification/interpreted-attempts/a0c6f71094694840a711941fd0087504.json`.
  Po korekcie wyboru journalu przez dokładny ID ponowiono dotknięte testy
  konsumenta: 11/11, `verification/interpreted-attempts/17c42b8900494d56b94e5e8223f94a78.json`.
- Źródła w tych sprawdzeniach były niezmienne i readonly. Testy są interpretowane;
  nie kompilowano lokalnie testów Rust.
- Rzeczywisty odczytowy preflight zachowanych danych przeszedł:
  `verification/post-build-preflight/699fc6696d774142b3fb92b640894712.json`.
  Rozróżnia historyczny stop i bieżący kontener; zachowany accepted-run oraz
  konfiguracja nie zostały zmienione. Nie jest to start nowego runtime.
- PR #223 scalono jako `942f2f29475fcc7979d66a6a259e180e61cfc33c`;
  18 kontroli CI zakończyło się sukcesem, 9 pominięto.

Pełny odbiór z tabeli powyżej, w tym stabilny backend, nadal pozostaje
**NOT VERIFIED**. Te wyniki potwierdzają implementację i testy granic odzyskiwania,
nie wykonanie symulacji ani naprawę całego wdrożenia.

### Próba kontrolowanego odtworzenia i korekta snapshotu

Operacja `71f3f0c690124241807d91fd73ffc0fa` zakończyła stop/rm obu starych
usług. Nowy start `abaf8645e2ca429584e143d91be3315a` został odrzucony przed
zmianą certyfikatu, cache i ledgera: walidator błędnie wymagał zatrzymanego
frontendu w snapshotcie zapisanym jeszcze przed stop/rm. Poprawka wiąże obraz
każdej usługi z prior Compose i jej labels; frontend może wtedy jeszcze działać.
Potwierdzenie zakończenia nadal pochodzi z terminal receipt oraz sprawdzenia
nieobecności obu dokładnych ID. Backend w historycznym snapshotcie musi być
zatrzymany.

Po korekcie 72/72 testy helpera/startu/pre-admission/skryptu przeszły:
`verification/interpreted-attempts/75dd2cf98f2a436e8b83042e259714b2.json`.
Rzeczywiste retained evidence przeszło kontrolę readonly bez utrzymywania lease
ani mutacji runtime: `verification/post-build-preflight/17eb74135a894337ab6713c216b71a13.json`.
Nie oznacza to autoryzacji nowego startu. Testowe adaptery katalogu tymczasowego
i stałych continuation zostały uzupełnione po wynikach CI.

Obecnie ta grupa nie ma uruchomionych usług aplikacji. Standardowy resume
wymaga analizy późniejszej, odrzuconej przed startem próby `abaf...`; nie wolno
ręcznie cofać wskaźnika current ani usuwać historii. Sesja, owner, konfiguracja,
cache i wolumeny pozostały zachowane. Odbiór runtime pozostaje **NOT VERIFIED**.
