# ADR 0060 — launcher Docker z natywnym storage Linux/WSL

Status: implementacja; pełna kwalifikacja runtime NOT VERIFIED, 2026-10-15.

## Kontekst

Checkout i storage użytkownika znajdują się w WSL. Wymaganie natywnej atestacji
Windows w launcherze uniemożliwia start z takiej powłoki. Adapter
[windows-folder-v1](0059-docker-desktop-windows-session-storage.md) dotyczy
NTFS/ReFS eksportowanego przez Docker Desktop jako 9p; nie opisuje lokalnego
storage Linux.

## Decyzja

Launcher i kreator wybierają osobną trasę hosta `linux-native-v1` na Linux/WSL.
Checkout i kanoniczny storage muszą znajdować się na lokalnym ext4, XFS albo
Btrfs i przejść kontrolę ścieżek bez symlinków. Nie dopuszczamy DrvFS/9p,
CIFS/SMB, NFS ani ścieżek Windows przez ustawienie zmiennej profilu. Kontener
potwierdza lokalny typ filesystemu `/state` i używa istniejących natywnych
blokad oraz barier publikacji writera Linux. Nie dodajemy 9p do allowlisty.

Trasa Windows zachowuje atestację `windows-folder-v1` i scoped grant. Trasa
Linux nie tworzy certyfikatu Windows ani nie deklaruje Windows native readback.
Rustowy bootstrap fixed-layout wybiera admission zgodnie z profilem; Linux
sprawdza przypięty mount `/state`, jego filesystem i brak przekroczenia urządzenia.
Obie używają tego samego resolvera storage, kolejki managed build, pakietów,
wersjonowanego Compose oraz jednego runtime service i accepted store.

Nie zmieniamy fizyki, czterech realizacji solvera, Python DSL, ProblemIR,
requested/resolved execution, OpenAPI ani drzewa workspace. Dostępność hosta
Linux nie rozszerza capability map i nie kwalifikuje solvera GPU.

## Obowiązki implementacji

`scripts/setup_docker.py` waliduje host i zapisuje lokalną konfigurację bez
instalacji toolchaina i bootstrapu runnera. Launcher
`scripts/fullmag_docker_runtime.py` wybiera trasę hosta, kontroluje source/storage
oraz rzeczywisty mount kontenera i zapisuje profil w dowodach. Kontrakt
`scripts/linux_docker_host.py` współdzieli kontrolę filesystemu i ścieżek.
`scripts/docker_compose_attestation.py` oraz helpery entrypointu zachowują
izolację usług. `docker/all-in-one/entrypoint.py` sprawdza mount Linux i używa
istniejących prymitywów prób operacji z `windows_folder_probe.py`; nie wymaga
przez to atestacji hosta Windows. Testy hostowe muszą pokryć wybór profilu, odmowę sieciowych i
Windows filesystemów oraz zachowanie trasy Windows. Instrukcje użytkownika:
[Docker w WSL](../guides/docker-wsl.md).

## Konsekwencje i rollback

Nie przenosimy aktywnych sesji pomiędzy trasami, nie przejmujemy obcego storage
ani nie wykonujemy cichego fallbacku do named volume. Przenoszenie danych używa
istniejącego eksportu `.fms`. Błąd admission kończy start i zachowuje dowody.
Rollback wyłącza trasę Linux w launcherze, zachowując dane, logi i receipty;
nie przeklasyfikowuje istniejącej sesji jako Windows-folder.

## Weryfikacja

Kontrole konfiguracji i regresje launchera są odrębne od bramki pełnego runtime.
Cold-start, HMR/WebGL, rzeczywisty SessionStore z restartem, wykonanie GPU i
walidacja naukowa wymagają osobnych dowodów. Windows-specific
`verify_docker_all_runtime.py` nie jest dowodem kwalifikacji WSL. Power-loss
oraz restart całej VM pozostają NOT VERIFIED.
