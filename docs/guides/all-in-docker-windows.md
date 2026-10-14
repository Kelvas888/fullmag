# Fullmag w całości w Docker Desktop

Ten tryb składa jeden obraz uruchomieniowy zawierający backend API, statyczny
Control Room, publiczny Python DSL, rozszerzenie PyO3 oraz biblioteki FEM/CUDA.
Windows udostępnia przeglądarkę i Docker Desktop. UI i API używają tego samego
portu: `http://localhost:3197/workspace`. Kontener nie potrzebuje checkoutu,
socketu Dockera ani hostowego Pythona podczas uruchomienia.

## Budowanie

Pełną kompilację wykonuje istniejący `Fullmag_build_runner`. Nie uruchamiaj
równoległego ciężkiego buildu przez `docker build` ani hostowy Cargo.
Przed zgłoszeniem sprawdź zdrowie runnera i konfigurację `fem-gpu-release`.
Worktree musi być wcześniej zarejestrowany przez `fullmag_storage.py register`
w ramach cyklu zadania. Źródłem jest pełny SHA commita właściwego checkoutu:

```text
just runner-container-status
just docker-all-build <pelny-sha>
just runner-wait <job-id> 30
just docker-all-image <job-id> <pelny-sha>
```

Zgłoszenie używa obsługiwanej niezależnej kopii niezmiennej kapsuły źródeł,
bez hardlinków do współdzielonego source CAS. Nie modyfikuje ani nie naprawia
obiektów CAS odrzuconych przez kontrolę niezmienności. Job nadal wykonuje
jeden istniejący koordynator, z profilem `fem-gpu-release`.
Przed POST do kolejki zapisuje `submission.json` z `capture_id`, `request_key`
i ścieżką kapsuły. Po timeoutcie stan `submission_unconfirmed` wymaga sprawdzenia
kolejki według `request_key`; nie zgłaszaj ponownie nowego capture, dopóki nie
ustalisz, czy koordynator przyjął poprzedni job.

Ostatnie polecenie nie kompiluje kodu. Sprawdza terminalny receipt, profil GPU,
hashy artefaktów, tożsamość commita i kapsułę źródeł. Następnie składa obraz
offline z przypiętego obrazu toolchaina, całego pakietu release i źródeł DSL.
Wynik zawiera `image_id` oraz ścieżkę `receipt.json` pod resolverowym
`storage/runtimes/<worktree-id>/docker-all-images/<id>`.
Kontekst składania pozostaje pod profilem `storage/builds/<worktree-id>/docker-all-gpu`.
Obraz zawiera pełny toolchain i może być duży; nie jest wersją slim.

## Uruchomienie

```text
just docker-all-start <absolutna-sciezka-do-assembly-receipt.json> 3197
```

Port hosta jest konfigurowalny. W kontenerze zawsze używany jest port `8081`;
publikacja następuje wyłącznie na `127.0.0.1` Windows. Statyczny frontend
korzysta z tego samego originu dla API i WebSocket; nie ma osobnego serwera Node.
Docker Desktop musi używać silnika Linux i udostępniać GPU NVIDIA. Brak drivera
CUDA lub GPU kończy start przed uruchomieniem API. Dostępne urządzenie nie
nadpisuje wyboru CPU/GPU/auto w kanonicznym modelu. Jawne żądanie GPU nie ma
cichego fallbacku CPU; dostępność konkretnych zadań nadal określa capability map
bieżącego Fullmaga.

Start zapisuje Compose i receipt z nazwą projektu, ID kontenera, ścieżką stanu
oraz URL. Stan sesji jest osobnym montowaniem `/state`. Zatrzymanie kontenera
nie usuwa danych. Dla konkretnego projektu z receiptu:

```text
docker compose -f <compose.json> --project-name <compose-project> stop
docker compose -f <compose.json> --project-name <compose-project> start
```

## Storage i granice weryfikacji

Launcher rozwiązuje storage przez `fullmag_storage.py`, przed pierwszym zapisem.
Kontekst składania, logi, provenance, receipty i pliki Compose pozostają w storage
projektu. Nie kopiuje hostowego `.env` ani Git do obrazu. Nie wykonuje prune ani
automatycznego kasowania kontekstu, obrazów lub sesji.

Sesje pozostają bezpośrednio w nowym folderze kanonicznego storage Windows,
montowanym do `/state`. Launcher działa natywnie w Windows i sprawdza lokalny
NTFS/ReFS, wolumen fixed oraz brak reparse points w przodkach. Nie używa wolumenu
nazwanego ani zastępczego katalogu kontenera. Utworzony namespace należy do
Dockera; bieżący natywny writer Windows odrzuca jego marker właściciela.
Do przenoszenia sesji między runtime’ami używaj eksportu `.fms`.

Dla bind mountu 9p (`0x1021997`) wymagany jest jawny `windows-folder-v1`.
Przed API launcher uruchamia i restartuje własny kontener próbny, weryfikuje
native readback oraz dziewięć kontroli: fsync pliku i katalogu, atomic replace,
publikację katalogu, blokadę między procesami, no-follow symlink/junction,
transakcje SQLite i odczyt po restarcie. Certyfikat hosta jest montowany readonly;
grant startowy wiąże go z obrazem, źródłem, binariami i bieżącym mount namespace.
Domyślna odmowa 9p pozostaje w mocy poza tym konkretnym profilem i folderem.

Te kontrole dopuszczają operacyjne użycie folderu. Nie dowodzą odporności na
utratę zasilania ani restart całej VM Docker Desktop. Power-loss pozostaje
`NOT VERIFIED`, zgodnie z istniejącym kontraktem trwałości Fullmaga.

Zielony receipt składania obrazu oznacza tylko złożenie sprawdzonych artefaktów.
Health API nie dowodzi działania canvas/WebGL, symulacji FEM GPU ani poprawności
naukowej. Te bramki wymagają osobnych dowodów. Lokalny zakaz kompilowania testów
jednostkowych pozostaje w mocy; użytkownik dopuścił wyjątek wyłącznie dla CI
tego zadania.
