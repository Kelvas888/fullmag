# ADR 0066 — kontynuacja generacji po buildzie przed nowym ownerem

Status: implemented; odbiór runtime **NOT VERIFIED**.

## Kontekst

Backend DEV może opublikować poprawny pakiet i przejść bramki storage/cgroup,
a następnie zakończyć się przed utworzeniem nowego native ownera. Pozostaje
historyczny owner `Failed` oraz starszy process-tree. Zwykły restart nie może
uznać tego rekordu za udany drain bieżącej inkarnacji.

Istniejąca ścieżka kontrolowanego odtworzenia już przekazuje świeży
`previous_config_sha256` do backendu. `ensure_configuration` porównuje dokładne
stare bajty i pozwala zmienić wyłącznie `runtime_generation_sha256` przy
identycznym profilu operatora. Sam zapisany w Compose stary hash nie jest
wystarczającą autoryzacją: restart po zakończeniu operacji hosta mógłby go
użyć ponownie, jeśli pierwsza próba zakończyła się jeszcze przed rotacją.

## Decyzja

Rozszerzamy hostowe ustalenie kontekstu kontrolowanego odtworzenia oraz
dodajemy minimalną kontrolę jego jednorazowego użycia w runtime.
Odrębny, zamknięty rekord metadanych wiąże niezmienny oryginalny stop/accepted
proof, nadal ten sam `Failed OWNER.json`, process/archive raw digests, aktualną
zatrzymaną inkarnację kontenera, certyfikat i held catalog/start-release.
Świeży hash natywnego `docker-all.json` jest odczytywany pod `OWNER.lock`.
Hash konfiguracji Compose pozostaje innym pinem.

Historyczny journal nie staje się journalem nowego kontenera. Bieżący
stopped-namespace proof jest oddzielny; samo istnienie starego process-tree
nie dowodzi, że nowy API nigdy nie wykonał kodu. Obcy owner, nowy ACK/claim,
zmieniony katalog lub brak wymaganych dowodów blokują tę ścieżkę. Sprawdzamy
zakres tej aplikacji/runu; obca grupa nie musi być zatrzymana i ledger całego
hosta nie musi być pusty.

Caller porównuje cały kontekst przed operacją oraz pod lease `recreate-services`
bezpośrednio przed stop/rm. Ta operacja kończy się przed przygotowaniem obrazów
i startem. Kontekst musi więc zostać sprawdzony ponownie pod nowym lease
`development`, przed zmianą certyfikatu, alokacją cache/ledgera i utworzeniem kontenera. Nie trzymamy starego lease podczas
zagnieżdżonych operacji BuildKit. Nowa operacja zapisuje zamknięte powiązanie
pending z własnym attemptem i hashem kontekstu w control volume oraz przekazuje
runtime ścieżkę i SHA tego rekordu. Nie przedstawia go jako
`native_restart_metadata` lub container recovery.
Incoming image i pakiet przechodzą dotychczasowe rzeczywiste bramki buildu;
nie wymagamy nieistniejących jeszcze przyszłych digestów w stop proofie.

Dotyczy to opublikowanego profilu `restart_verified=true`. Wyjątek
false-bootstrap pozostaje odrębny. Nie resetujemy ownera, nie zwalniamy
zasobów i nie powtarzamy Solve. Dotychczasowa kontrolowana rotacja pól obrazu
certyfikatu zachowuje jego zamkniętą tożsamość hosta; bramka storage ponownie
potwierdza gotowość przed wejściem do API. Istniejący natywny
`service-ensure` nadal odpowiada za nowy claim po stanie terminalnym.

## Ponowienie i późniejszy restart

Zachowujemy obecne zabezpieczenia rotatora: dokładny backup
`docker-all.previous-<sha>.json`, kontrolę starego hasha i atomową publikację.
Ponowienie przy konfiguracji już równej expected nie wykonuje drugiej rotacji.
Przed użyciem starego pinu runtime wymaga dokładnego powiązania pending,
zgodnego aktualnego attemptu `development`, utrzymywanego lease i braku
terminala tej operacji. Sam plik active nie dowodzi utrzymywania lease.
Kontrola obejmuje również niezmienione piny ownera, process-tree i accepted.
Po poprawnej rotacji albo potwierdzonym no-op powstaje niezmienny rekord
consumed. Nie tworzymy dodatkowego protokołu intent: atomowy backup i rotator
pozostają istniejącą granicą publikacji konfiguracji.

Zmienna ze starym pinem może pozostać w środowisku kontenera, ale consumed
wyłącza jej specjalne uprawnienie. Późniejszy restart korzysta ze zwykłego
uwierzytelnionego drain. Pending z zakończonej lub niepotwierdzonej operacji
nie pozwala na rotację po restarcie w Docker Desktop. Kontrolowane ponowienie
przez launcher ponownie zbiera dowody pod nowym lease; nie resetuje ownera.
Po przerwaniu między publikacją configu a zapisem consumed ta sama nadal
aktywna operacja może dokończyć zapis bez drugiej rotacji. Zakończona operacja
wymaga świeżego kontrolowanego kontekstu, z weryfikacją backupu i profilu.

Jeżeli host odrzuci nowy start jeszcze przed zmianą certyfikatu i publikacją
Compose/cache, `development/current.json` może wskazywać tę nieudaną próbę.
Wznowienie zakończonego odtworzenia zachowuje oryginalny development attempt
jako punkt odniesienia. Dopuszcza wyłącznie kanoniczny terminal
`failed-confirmed`, dokładnie powiązany z tym samym dowodem odtworzenia,
źródłami, profilem urządzeń, konfiguracją i pełnym producentem accepted-run.
Istniejąca projekcja accepted-run w continuation musi odpowiadać temu
producentowi. Wymagane są pending binding, brak aktywnego lease, consumed,
Compose oraz artefaktów cache/runtime. Kolejne takie odrzucenie może być
wznowione tylko z identycznym przypiętym dowodem; stan unknown lub rozpoczęta
publikacja wymagają osobnej właściwej procedury. Nie cofamy current ani historii.
Przed nową operacją i pod jej lease pozostają dotychczasowe rewalidacje ownera,
konfiguracji, certyfikatu, accepted-run i nieobecności starych kontenerów.

## Zakres, walidacja i wycofanie

Zmiana obejmuje hostowy helper/launcher, runtime guard i regresje. Nie zmienia solverów
FDM/FEM CPU/GPU, Python DSL, ProblemIR, OpenAPI ani natywnego protokołu claimu.
Wymagane są realistyczne testy opublikowanego profilu, driftu, braku dowodów,
rozróżnienia historycznego i bieżącego kontenera oraz rewalidacji pod lease.
Istniejące testy rotacji/replay/drain pozostają obowiązujące. Dodatkowo
wymagane są regresje zakończenia operacji przed rotacją, replay starego env,
przerwania po publikacji przed consumed i zdrowego restartu po konsumpcji.

Oddzielny dowód stanowi rzeczywisty start API/native ownera na zachowanym
storage. Build i fixture nie kwalifikują stabilności, GPU ani fizyki. Do uzyskania
dowodów status pozostaje **NOT VERIFIED**. Wycofanie launchera pozostawia rekordy
jako historię; nie usuwa konfiguracji, ownera ani lease.
