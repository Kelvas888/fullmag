# ADR 0059 — sesja Docker Desktop w bezpośrednim folderze Windows

Status: implementacja i kwalifikacja w toku, 2026-10-14.

## Kontekst

Użytkownik wymaga UI/API/Python/FEM/GPU w jednym kontenerze oraz sesji zapisanej
bezpośrednio w Windows storage. Docker Desktop udostępnia lokalny NTFS jako 9p,
który istniejący writer słusznie odrzuca jako niekwalifikowany. Named volume nie
spełnia uzgodnionego wymagania. Nie zmieniamy fizyki, DSL, ProblemIR, API ani
requested/resolved execution.

## Decyzja

Wprowadzamy scoped adapter `windows-folder-v1` dla sesji, zgodny z istniejącą
rodziną profili z Windows-first development. Nie dodajemy 9p do globalnej allowlisty.
Admission wymaga natywnego NTFS/ReFS i no-reparse preflight hosta, jawnego readonly
attestation, pojedynczego owned namespace, rzeczywistych prób operacji oraz
readback po ponownym starcie własnego kontenera. Grant musi odpowiadać bieżącemu
mount namespace, device/inode `/state` i źródłom/binary/image/artefaktom.

Writers kontenera nadal używają istniejących native locks i publication barriers.
Native Windows writer odmawia użycia wewnętrznego namespace oznaczonego jako
Docker-owned. Nie zakładamy współdzielenia locków Win32/Linux. Portable `.fms`
pozostaje sposobem przenoszenia danych pomiędzy odrębnymi runtime'ami.

## Obowiązki i rollback

Launcher oraz entrypoint muszą wydawać i sprawdzać dowody; `fullmag-session`
sprawdza je przed admission. Brak, zmiana, błąd lub rozszerzenie zakresu dowodu
ma kończyć się odmową. Zachowujemy no-follow, owner metadata, niepewną publikację
po błędzie bariery i kontrolowane recovery. Dowody oraz sesje pozostają w storage.

Rollback wyłącza profil i zachowuje dane; nie przenosi ich do named volume,
nie usuwa ich ani nie dopuszcza niekwalifikowanego 9p. Active session nie jest
restartowana z powodu końca buildu. Nowy obraz nie obiecuje automatycznego restore.

## Dowody

Sonda 7656cafdee4d4d78816536e272582fee potwierdziła podstawowe operacje 9p
na lokalnym NTFS, w tym no-follow Windows junction i readback po restarcie.
Właściwy SessionStore, restart API, browser/WebGL i GPU wymagają osobnych bramek.
Awaria zasilania i restart całej VM pozostają NOT VERIFIED, jak w obecnym
platformowym kontrakcie durability. Szczegółowy plan i schema:
[plan zadania](../plans/active/docker-all-windows-20261014.md).
