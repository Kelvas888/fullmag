# Fullmag all-in-Docker na Windows — plan i kontrakt storage

Cel: jeden kontener z UI, API, Pythonem, FEM i GPU NVIDIA; port hosta 3197;
sesje bezpośrednio w skonfigurowanym storage Windows, bez named volume.
Jednorazowy wyjątek użytkownika dotyczy wymaganej kompilacji testów w CI,
nie lokalnego kompilowania unit testów. Pozostała praca użytkownika zostaje zachowana.

## Zakończone etapy

- Recepty build/image/start, walidacja managed GPU release i immutable image.
- Niezależna kapsuła source bez osłabiania shared CAS; 7 kontroli Python Linux,
  6 Windows i jedna kontrola Bash pominięta na Windows.
- Commity: c9feee383bf72ba352b21c7a8b091d7a8b0bf8ca,
  34f68b6ff58f92e9ab1f5719b5f4b9a854415b39, 8c195ecd292ee5c300342265e30f8be35f1628fc.
- Managed GPU job e7325f418ca74bc0bc4d21e24c0fd090 przyjęty z czystego commita.
- Żywa sonda 7656cafdee4d4d78816536e272582fee: 9p 0x1021997, fsync katalogu,
  atomowa zamiana, lock pomiędzy procesami, no-follow symlink/junction oraz
  readback po ponownym starcie własnego kontenera przeszły. Power loss NOT VERIFIED.

## Kolejne etapy i bramki

1. Wdrożyć jawny `windows-folder-v1` dla roli session. Zwykłe 9p bez dowodu
   nadal jest odrzucane. Kwalifikacja dotyczy wyłącznie `/state` na lokalnym
   NTFS/ReFS potwierdzonym przez natywny Windows launcher.
2. Launcher wydaje readonly attestation hosta, przeprowadza probe/restart przed
   pierwszym uruchomieniem API i dopiero potem pozwala entrypointowi opublikować
   grant powiązany z namespace mountów oraz inode/device bieżącego kontenera.
3. Core Rust sprawdza grant, host attestation, zakres ścieżki, tożsamość source,
   aktualnego exe i obrazu. Native Windows odmawia użycia wewnętrznego store
   oznaczonego jako należący do Docker; nie zakładamy interoperacyjności locków
   Win32/Linux. Nie zmieniamy writera, lease, no-follow ani publication barriers.
4. Kontrole źródeł i CI unit tests; managed build końcowego commita; image assembly;
   create/save/reopen i ponowny start własnego kontenera; GPU oraz browser/canvas
   pozostają osobnymi bramkami. Nie restartować Docker VM ani obcych aplikacji.
5. Review, push/PR, wymagane checks, merge, główny master fast-forward i bezpieczny
   cleanup tylko własnego worktree. Dirty master może blokować końcową integrację.

## Kontrakt JSON v1 dla implementacji

Readonly host attestation: `/run/fullmag/windows-folder-host.json`.
Pola: `schema="fullmag.windows-folder-host.v1"`, `storage_profile="windows-folder-v1"`,
`role="session"`, `owner_scope="docker-desktop-linux"`, `host_root` (absolutny Windows),
`host_filesystem` (NTFS/ReFS), `host_drive_type=3`, `host_volume_serial` (u32),
`host_root_no_reparse=true`, `owner_token` (UUID), `engine_id`, `image_id` (sha256:hex64),
`source_commit` (hex40), `binary_hashes` (mapa nazwa pliku bin -> hex64),
`artifact_receipt_sha256` (hex64), `restart_expected_sha256` (hex64),
`restart_verified=true` przed uruchomieniem API.

Grant: `/state/.fullmag-windows-folder-grant.json`.
Pola: `schema="fullmag.windows-folder-session.v1"`, `storage_profile="windows-folder-v1"`,
`role="session"`, `state="operational"`, `container_root="/state"`,
`host_attestation_sha256` (hex64), `owner_token` (jak host), `root_device`, `root_inode`,
`mount_namespace_inode` (u64), `power_loss="NOT VERIFIED"`,
`checks` (mapa dokładnie poniższych nazw, wszystkie true): `file_sync`,
`directory_sync`, `atomic_replace`, `atomic_directory_publish`, `process_lock`,
`no_follow_symlink`, `no_follow_junction`, `sqlite_transactions`, `restart_readback`.

Host marker: `/state/.fullmag-windows-folder-owner.json`, ta sama host attestation
(na hoście ścieżka rootu Windows). Stan oznacza namespace tylko dla Docker;
nie jest upoważnieniem do takeover ani native Windows writer. Stary marker lub
niepotwierdzony właściciel wymaga kontrolowanego recovery, nigdy age/PID takeover.

To operacyjny admission na konkretnym montowaniu, nie kwalifikacja power-loss,
restartu VM, fizyki ani wszystkich konfiguracji Docker Desktop. Dowody pozostają
w storage i są powiązane z source/binary/image/artifacts.

## Checkpoint adaptera storage

Adapter Rust i kontrola launchera są zaimplementowane. Próba `fa70d054fb1f4ceead650d3cf9cd573e`
wykonała wszystkie dziewięć kontroli oraz native Windows readback (PASS),
bez kwalifikacji power-loss. Kontener próbny: `8d1bb2df28b18e3f70ad54ae66c4ac7a1fbe06d906d65787b3fc6f884de0b995`.
Dziewięć interpretowanych testów kontraktu Python przeszło na Linux.
Review wykrył brak katalogu certyfikatu i weryfikacji readonly mountu; poprawiono
te miejsca oraz bounded native no-follow read i porównanie hashy provenance.

Job `e7325f418ca74bc0bc4d21e24c0fd090` zakończył się kodem 2 przed kompilacją:
brak Rust nightly w pustym cache GPU. Uzupełniono wyłącznie pusty cache GPU
niezależną kopią istniejącego toolchaina CPU; readonly probe wykazał
`rustc 1.100.0-nightly (cea272fa3 2026-09-07)`. Nie zastąpiono GPU przez CPU.
Źródłowy cache CPU pozostał bez zmian. Artefakty błędu i kapsuła są zachowane
do diagnozy; nie usunięto execution, współdzielonych cache ani pakietów.
Skill `fullmag-build-stage-cleanup` jest niedostępny; zastosowano retencję governance.

Pozostałe bramki: nowy managed build końcowego commita, złożenie obrazu,
API/save/reopen/restart sesji, rzeczywista realizacja FEM GPU, przeglądarka/WebGL,
CI zadania i pełny cykl PR/integracji. Wyjątek kompilacji testów dotyczy tylko CI.
