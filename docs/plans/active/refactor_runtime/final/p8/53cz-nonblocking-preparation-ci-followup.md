# P1/P8 — dalszy odbiór nieblokującego przygotowania

Data: 15.10.2026. Baza: `1c70c027775ee1cdb1a05a66402ae3d72b8e8ea5`.
Kontynuacja [53CY](53cy-nonblocking-preparation-workspace.md), nie zamknięcie
całego P1/P8 ani kwalifikacja solvera.

## Bieżące dowody i porażki

Browser receipt c7e641e48b16422fbcdad569c1eb05ff pozostaje zielonym dowodem
komponentów dla niezmienionych plików produkcyjnych: 7 kroków, preserved draft/
focus/canvas, zdrowy WebGL i compact accordion. Nie zastępuje testów powłoki.

CI bootstrap 38708719103, Control Room job 116334496254, wykryło błędny props
state w MountedWorkspace: wrapper SimulationStartupOverlay nie przyjmuje
propsów i sam wywołuje hook, a View przyjmuje state. Naprawa
`9d83d9517448127b0fcac209e9adb469245350b9` używa wrappera bez propsów i usuwa
nieużywany import hooka. Opublikowana na origin/master; produkcja bez zmian.

Kolejne CI 38709138658, job 116335882219, przeszło typecheck i doszło do
wykonania testów, gdzie wystąpiło 7 porażek. Własnych regresji testów nie
przypisano obcemu dirty WIP:

- testy omitted predicates/clipboard wymagają jawnego otwarcia dialogu błędu;
- fixture konsumenta diagnostyki musi montować jego SlotHost po usunięciu gate;
- dwie asercje braku aria-hidden były zbyt szerokie i łapały dekoracyjne SVG;
- fixture rzeczywistej powłoki wymaga kompletnego kontraktu kernel.realtime;
- audyt wydajności wciąż wymagał startupVisible w dependency list listenera.

Zmiana audytu zachowuje ref do najnowszych danych i stabilny listener
[kernel, sessionScopeKey], wymaga dispatchShortcutCommand oraz
enabled: !startupVisible dla danych runtime i zabrania globalnego
if (startupVisible). Interpretowany audit-compute-performance.mjs: exit 0,
"Compute performance audit passed.". Przygotowano naprawy sześciu testów
powłoki w czterech plikach: jawne akcje diagnostyki, realny SlotHost,
asercje root/panel tags i prawdziwy RealtimeConnectionController. Diff i
kontrakty fixture przejrzane; wykonanie wymaga nowego CI. Lokalnie nie
kompilowano testów jednostkowych.

Python job 116334496343 potwierdził Gmsh 45/45, sceny 127/127 oraz kolejny
zestaw 107/107. Następna porażka dotyczy dwóch ordered-stage roundtrip
asercji w test_script_builder_roundtrip.py:659/839. Trwa diagnoza temporalnego
scope save/clear_outputs; nie osłabiono asercji na podstawie samego wyjścia.

## Pełny pakiet Windows i zasoby

`just windows-workspace-build dev dev 3197 auto` zakończyło się exit 2 po
limicie 120 s wspólnego slotu, przed kompilacją. Brak nowego pakietu.
Obserwowany żywy PID 160168: powershell run_fullmag.ps1 BuildOnly release
FEM GPU z worktree fem-script-launch-20261013. Nie wywodzono właściciela
chatu ze ścieżki i nie zatrzymano procesu. Brak listenera 3197 przy preflight.

Resolver: profil windows-native-fdm-cpu-dev, worktree fullmag-0950f4dca4ffe38f,
storage C:/git/fullmag/storage. Wolne C: 33570582528 B, R: 75062390784 B;
to odczyt dostępności, nie odzysku miejsca. Zachować cache Cargo, poprzedni
zweryfikowany pakiet, źródła snapshotów, logi i receipty. Brak prune/usuwania.
Ponowna ocena slotu po zakończeniu obserwowanego procesu, retencja po
zweryfikowaniu następcy i referencji. Pełny startup/Save/Open nadal NOT VERIFIED.

Istniejący smoke-project-lifecycle-runtime.mjs zakłada aktywną sesję przed
New Project; nie dowodzi sam projektu bez RuntimeSession. Ścieżka project-only
powłoki i jej konsumenci są badani oddzielnie. Nie uznano samego API authoring
ani nazwy ProjectWorkspaceShell za dowód pełnego authoringu bez runtime.

## Diagnostyka pełnego lifecycle

smoke-project-lifecycle-runtime.mjs zapisuje teraz raport również przy błędzie
inicjalizacji/nawigacji/asercji lub zamykania przeglądarki: state, phase,
failed_phase, stack, wszystkie requests, HTTP/page/console errors. Nie wycisza
pageerror przez filtr tekstowych console errors. Zachowano istniejące asercje
New/Save/Open/Close, byte-roundtrip, nazwy plików, zakaz mutacji runtime i limity
spodziewanych idle 404. Nie przedstawiono tej zmiany jako wykonania lifecycle.

node --check i diff check PASS. Interpretowana próba invalid URL, bez launchu
przeglądarki i bez API: receipt
windows-control-room-source-check/lifecycle-harness-invalid-url/7e317e359f764341b0cf2ee17ff0c33f
PASS. Node exit 1 zgodnie z oczekiwaniem, report state failed,
failed_phase=playwright_setup, stack obecny i puste requests/page_errors;
hash źródła niezmieniony. Jest to dowód obsługi błędu harnessu, nie odbiór M1.

## Mapa otwartego P2 — authoring bez RuntimeSession

Ograniczony audyt potwierdził rozdział istniejącego ADR-0039: New Project
tworzy dokument bez sesji, ProjectWorkspaceShell montuje zapisane wyniki
i readonly Inspector. Nie jest to dowód geometrii/materialów bez sesji.

InspectorModule ogranicza project selection do materialized-dataset;
geometryLifecycleResources useSceneResource/useMaterialResource wymagają
sessionIdentity, a mutacje geometrii używają session model API. New simulation
tworzy sesję i ProjectAuthoringSessionBinding; to inna ścieżka niż New Project.

ProjectDocumentController.synchronizeAuthoring już wysyła kanoniczny dokument
do projects.authoringUpdate z project ID/revision fence. ProjectDocumentResource
zawiera archiwum i metadane, bez typowanej projekcji scene_document do edytorów.
Save bez authoringSessionBinding zapisuje bieżące archiwum, nie odczytuje sceny
z sesji. Pełny slice P2 wymaga więc kanonicznego odczytu sceny nowego/otwartego
projektu i podłączenia istniejących edytorów do tego właściciela oraz mutacji.
Nie tworzyć sztucznej RuntimeSession ani drugiego store dokumentu. Zmiana
kontraktu/projekcji i odpowiedni ADR muszą poprzedzić zależną implementację.
Ta mapa jest dowodem źródłowego ograniczenia i następnym krokiem, nie odbiorem P2.
