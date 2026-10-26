# Zatrzymanie diagnostycznego API przed przejęciem runtime

## Problem i zakres

Pakiet backendu został zbudowany, lecz jego start odmówił ponownego użycia zużytej autoryzacji container recovery wobec późniejszej historii LAUNCH. Obecne diagnostyczne API nie przejęło runtime. Historyczny OWNER jest Failed, a process-tree pozostaje historycznym shutdown_unknown. Nie wolno użyć go jako dowodu tożsamości obecnego procesu ani zmienić dawnych receiptów.

## Rozwiązanie

`scripts/docker_volume_startup_diagnostic.py` identyfikuje faktyczny proces i instancję API przez /proc, środowisko, startup fence i zgodne nagłówki HTTP. Zachowuje osobny hash historycznego process-tree. Rzeczywista kontrola `just docker-dev-inspect-startup-diagnostic` przeszła: PID 2834, brak aktywnych rezerwacji; dowód `verification/antenna-operation-profile-20261026/startup-diagnostic-inspection-03.json` w wolumenie kontrolnym grupy anten.

Nowa recepta `just docker-dev-stop-startup-diagnostic` ma domyślne preview i osobne apply. Wymaga zakończonego failed-confirmed resume, pełnych pinów kontenerów/obrazów/StartedAt, kanonicznego requestu, zgodnego preview oraz ponownego odczytu dowodów pod lease. Przed sygnałem sprawdza namespace i natywne proofy zwolnienia zasobów z obu rodzin lease. Wysyła najwyżej jeden stop do wskazanego backendu. Zachowuje frontend, OWNER, konfigurację, historyczny process-tree, storage i cache. Niepewność po sygnale pozostawia journal stop-planned i unknown do odrębnego uzgodnienia; nie upoważnia do ponowienia stopu.

`scripts/docker_volume_startup_diagnostic_restart.py` uwierzytelnia osobny journal stopped-confirmed, jego immutable terminal, dawną completed recovery oraz niezmienione zasoby. Dopiero wtedy oddzielny StartupDiagnosticStopContext przekazuje restart tej samej sesji bez ponownej aktywacji skryptu i bez dawnych zmiennych recovery. Recreate i start ponownie weryfikują kontekst pod własnymi lease oraz wymagają dowodu zakończonego usunięcia starego namespace. Nie zmieniono schematów native stop ani post-build continuation.

## Weryfikacja i ograniczenia

W istniejącym backendzie Docker wykonano 41 interpretowanych kontroli: 20 stop/request/workflow, 4 read-only inspection, 17 restart/authentication. Wszystkie PASS; nie kompilowano testów jednostkowych. Scenariusze workflow z mockowanym daemonem nie stanowią dowodu rzeczywistego zatrzymania. Weryfikują m.in. brak sygnału bez preview lub po zmianie dowodów, pojedynczy sygnał przy kompletnym dowodzie oraz zachowanie niepewności po niepotwierdzonym stopie.

Rzeczywiste preview, apply, recreate i zdrowe API pozostają NOT VERIFIED do czasu terminalnego wyniku aktywnego resume 6f44e81b7f8e476c8d9588731ae0a562. Nie wolno skracać oczekiwania przez zabicie obserwatora, zmianę jego stanu ani podmianę historycznych dowodów. Po udanym przywróceniu należy odtworzyć zachowaną scenę przy pustej sesji, sprawdzić V/J/H przez publiczne HTTP i dopiero dalej kwalifikować pełne Universe. Cały zakres E0–E12 pozostaje nieukończony.
