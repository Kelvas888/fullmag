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
Źródłem jest pełny SHA commita właściwego checkoutu:

```text
just runner-container-status
just runner-build commit fem-gpu-release <pelny-sha>
just runner-wait <job-id> 30
just docker-all-image <job-id> <pelny-sha>
```

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
CUDA lub GPU kończy start przed uruchomieniem API. Wymuszenie GPU nie ma
cichego fallbacku CPU.

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

Kontener odrzuca system plików sesji nieobsługiwany przez writer Fullmaga.
Bind mount Windows w Docker Desktop może mieć typ `9p` (`0x1021997`), który
obecny writer odrzuca. Taki katalog nie jest kwalifikowanym miejscem trwałej
sesji; start ma zakończyć się błędem, bez zamiany na nietrwały katalog kontenera.

Zielony receipt składania obrazu oznacza tylko złożenie sprawdzonych artefaktów.
Health API nie dowodzi działania canvas/WebGL, symulacji FEM GPU ani poprawności
naukowej. Te bramki wymagają osobnych dowodów. Zakaz kompilowania testów
jednostkowych pozostaje w mocy.
