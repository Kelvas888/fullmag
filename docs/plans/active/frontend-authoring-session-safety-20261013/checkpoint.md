# R1 — bezpieczeństwo sesji authoringu

## Izolacja i zależność

- Worktree: C:/git/fullmag/worktrees/frontend-authoring-session-safety-20261013.
- Branch: codex/frontend-authoring-session-safety-20261013.
- Base: f054b25d31ffe02b821eac10133f5e3950543b0d (PR150; integracja zależna od niego).
- Owner: codex-thread-01a12cc7.
- Registry: storage/index/frontend-authoring-session-safet-9ee6f8d668b37641.json.
- Istniejący worktree frontend-geometry-mesh-r0-r1-20261013 należy do Antigravity; nie edytowano go.

## Kontrakt etapu

1. General i Geometry korzystają z jednego beginApply/acknowledge/reject. Jeden
   PatchObjectGeometry zawiera geometrię i pełny Transform3D pojedynczego obiektu.
   ACK po zmianie draftId/epoch nie publikuje invalidacji, feedbacku ani nowego draftu.
2. Wspólny czysty reconciler zachowuje post-submit delta i raw values; canonical
   baseline/revision/identity pozostają z ACK. Nie wprowadzamy wieloobiektowej API transakcji.
3. Rezerwacja sceny w sesji serializuje Apply; lokalne lease istniejących identity/delete
   zapobiegają wzajemnemu wyścigowi z Apply. Mapy ownerów pozostają per obiekt.
4. BeginGesture przed capture rezerwuje token; pending write blokuje początek gestu,
   aktywny gest blokuje Apply/Revert. End/cancel/unmount zwalnia wyłącznie własny token.
   Pointerup kończy się w kernel draft bez mutacji HTTP.
5. Komenda delete sprawdza dirty/pending owner i rezerwację przed pierwszym await
   oraz przed requestem. Zewnętrzny delete-vs-commit, trwałe receipts i WAL pozostają
   osobnym wymaganiem późniejszego etapu; ta lokalna blokada ich nie kwalifikuje.

## Własność zmian

- Worker authoring_apply_ack: General/Geometry, ich DOM testy i pure reconciliation helper.
- Worker authoring_gesture_boundary: gizmo, move interaction, production Module/Scene i regresje.
- Root: kontroler i jego regresje, command context/delete, dokumentacja/integracja.

## Weryfikacja

Wykonywalne regression checks: nowszy draft po ACK, podwójny Apply, A→B→A,
nieaktualna sesja, gest-vs-Apply, delete-vs-Apply, zwolnienie tokena i old-token
po clear. Browser: Object/Airbox stabilność i WebGL visible/not-lost/nonzero.
Lokalna kompilacja/uruchamianie unit tests zabronione; nowych testów nie
uruchomiono. Weryfikacja wykonawcza i browser pozostają NOT VERIFIED do CI.
Bieżący etap nie zamyka całego R0/R1; audyt pozostaje w dokumentacji PR150.

## Checkpoint 2026-10-13 — kontroler i komendy

- PR150 scalony: 9112d38880f45ff85db2bbd82dd5da67b778cb40. Nowy etap
  nadal bazuje na f054b25d; parent zostanie zaktualizowany po zapisaniu prac.
- Kontroler serializuje Apply, gesty i lokalne rezerwacje zmian sceny w obrębie
  sesji. Tokeny pozostają monotoniczne; późne zwolnienie nie usuwa nowej blokady.
- CommandContext udostępnia ten sam kontroler; jego powiadomienia odświeżają
  dostępność komend. Delete sprawdza szkice/formularze przed przygotowaniem i
  przed HTTP, rezerwuje zapis oraz zwalnia dokładny token w finally.
- Dodano regresje wzajemnych blokad, zmiany draftu przed Delete, awarii/retry
  i powiadomienia clear bez aktywnego szkicu. Testów lokalnie nie uruchomiono.
- Kontrole źródłowe: check-architecture-hygiene.mjs PASS,
  check-api-hygiene.mjs PASS, git diff --check PASS.
- Review kontrolera/komend: jedna uwaga P2 o powiadomieniu clear poprawiona
  z regresją; brak innych uwag w tym zakresie. Dowód wykonania NOT VERIFIED.
- Panele i viewport pozostają osobnym niezapisanym fragmentem. Otwarte review
  kombinacji identity + geometry i nowszych zmian po create ACK.
- Unit/DOM, browser Object/Airbox/WebGL oraz rzeczywiste API/runtime pozostają
  NOT VERIFIED dla tego etapu. Nie zamyka on reszty audytu R0/R1.

## Checkpoint — gesty viewportu

- Kontroler i komendy zapisane w 53ea1b4bb8d507408f554370da5c1106497d0f37.
- MoveObjectGizmo rezerwuje gest przed pointer capture/preview. Pointerup,
  cancel, lost capture i cleanup zwalniają dokładny token; dopiero potem
  pointerup aktualizuje lokalny kernel-owned draft. Gest odrzucony nie tworzy
  preview ani mutacji. Pending write blokuje ponownie commitMove.
- Prop jest przekazany przez Viewport3DModule, Viewport3DScene i model layer
  stack. Review wykrył brak destructuring w stacku; poprawiono przed zapisem.
- Dodano pure/DOM regresje odmowy, duplicate pointer, cancel, capture error,
  zwalniania przed staging i pointerup bez HTTP. Lokalnie nie uruchomiono.
- Scope review viewportu: jedna P1 poprawiona; wykonanie i browser/WebGL
  NOT VERIFIED. Następny dowód musi użyć produkcyjnego canvas/ścieżki Apply.

## Checkpoint — recovery komend mesh

- Gesty zapisane w f0ec935e94e01c191cfaa23b8d27efcbadecd28a.
- Oddzielny fragment PR11 usuwa limit ośmiu kandydatów w
  reconcileMeshSubmission. Zachowuje filtrowanie rodzaju komendy, kolejność
  od najnowszych i zgodność command_id + client_intent_id oraz scope.
- Regresje FDM/FEM umieszczają właściwą zaakceptowaną intencję za dwunastoma
  nowszymi kandydatami. Sprawdzają brak drugiego submit, pominięcie obcego
  rodzaju komendy i scope wszystkich detail reads.
- Przypadek 50 niepasujących komend sprawdza wszystkie 50 i nadal pozostawia
  pending; późniejszy offline pozostaje disconnected, bez duplicate POST.
- Diff/API/architecture source checks PASS. Pierwsze wywołanie architecture
  z rootu miało błędny cwd; poprawne wywołanie z apps/control-room przeszło.
- Wykonanie regresji i rzeczywisty API recovery NOT VERIFIED. Usunięcie limitu
  nie dowodzi lookup poza listą serwera ani reload portability; te kontrakty
  pozostają do osobnego audytu backendu/receipts.

## Otwarte review paneli — P1 metadata Create

- Recovery mesh zapisane w e4dbb3b1164b7db8916699ed57914385c24bae00.
- General/Geometry Apply używają wspólnego kontrolera i zachowują nowszą
  geometrię/translation; po identity ACK geometry przyjmuje kanoniczną rewizję.
  Zmiany paneli pozostają niezapisane do domknięcia review.
- Review wykazał P1: Name/Material/Region edytowane podczas Create ACK są
  pomijane przez geometry-only reconciler i znikają przy activate(createdDraft).
  Wyłączenie tych pól nie jest przyjętą naprawą: D04 §4 wymaga edytowalnych
  innych surowych formularzy podczas commit, bez target-wide disabled.
- Istniejący ObjectPatchRequest / patchObjectTransaction umożliwia zapis name,
  notes, material_ref i region_name pojedynczego obiektu; geometry Apply nadal
  musi użyć osobnego PatchObjectGeometry z geometrią i pełnym Transform3D.
- Wymagana naprawa: zachować raw metadata w kernel-owned committed draft,
  przenieść je do właściwego ownera/panelu, uwzględnić dirty oraz istniejące
  operacje metadata, zachować post-submit delta przy obu ACK. Samo dodanie
  metadata do reconcillera bez UI/persistence nie usuwa P1.
- Browser worker rozszerza smoke-inspector.mjs o native mouse drag z projekcją
  istniejących diagnostyk kamery i produkcyjnego gizmo. Mock API zostanie jawnie
  oznaczone; ten dowód nie zastępuje real backend/generation qualification.
- Brak PR dla etapu; merge niedopuszczalny przed usunięciem P1 i wymaganymi
  dowodami. Cel pozostaje active; nie ma globalnej blokady postępu.

## Checkpoint — metadata ACK i surowe wpisy (2026-10-13)

- Geometry udostępnia metadata istniejącego obiektu i zapisuje je przez istniejący `patch_object`; geometria/pełny TRS nadal używa pojedynczego `patch_object_geometry` z rewizją ACK metadanych.
- Jedna rezerwacja Apply obejmuje oba kroki. Częściowy sukces metadanych i błąd geometrii pozostawia niezapisaną geometrię z potwierdzoną rewizją do retry bez ponownego zapisu metadanych.
- Reconciler zachowuje późniejsze raw wpisy geometrii, name/notes/material/region. Publikacja tej samej skończonej rewizji nie normalizuje nowszego semantycznie równoważnego tekstu.
- Regresje źródłowe obejmują transfer create, geometry failure/retry, metadata-only oraz edycję podczas drugiego ACK. Review Geometry/helper: brak nowych actionable findings.
- Architecture hygiene: PASS; API hygiene: PASS; `git diff --check`: PASS; `node --check apps/control-room/scripts/smoke-inspector.mjs`: PASS. Nie kompilowano ani nie wykonywano testów jednostkowych/DOM. Browser/WebGL, rzeczywiste API i generacja: NOT VERIFIED.
- General i rozszerzenie browser smoke są osobnymi fragmentami, nadal wymagają końcowego review i integracji. Pełny R0/R1 nie jest zakończony.

## Checkpoint — General/CAS i browser source review

- General używa wspólnego kernel draft dla name/notes/material/region; identity ACK fence przed publikacją. Geometry ACK jawnie uzgadnia także niesubmitowane metadata, nawet bez nowszej edycji podczas tego requestu.
- Oba P1 review poprawione: combined identity A -> późniejszy raw B -> geometry ACK A zachowuje B dirty; jawna rewizja draftu jest CAS i nie jest zastępowana świeższym history read.
- Review General/controller i native mouse browser smoke: brak bieżących actionable findings. W smoke dopasowano staged banner do aktualnego pełnego tekstu produkcyjnego.
- Architecture/API hygiene: PASS; parser smoke i diff-check: PASS. Testy DOM/unit oraz browser/WebGL/API execution: NOT VERIFIED. Fixture używa mock API.
- Kolejny niezależny PR04: parser długości i jawne stany, payload/preview/equality wspólną ścieżką. Zmiany parsera nie należą do commita General.


## CI PR154 — pierwszy exact-head przebieg e3571622

- control-room-contracts job115279518462 FAIL na typecheck: brak findInput w Geometry DOM oraz closure narrowing pendingApply do never w viewport regresji. Poprawiono helper i odczyt faktycznego applyOperationId ze snapshotu; wymagane ponowne CI.
- React Doctor run38392514685 SUCCESS advisory: score90, 0 errors, 5 warnings. Wszystkie pięć async-await-in-loop dotyczą smoke-inspector: sekwencyjne resize/theme screenshot (311/331), polling Reset (555), mutacje stabilności panelu (822), polling quiet request (2774). Klasyfikacja false-positive dla proponowanej równoległości, wysoka pewność: każdy krok zależy od stanu poprzedniego kroku tej samej strony, polling wymaga kolejnej obserwacji po czasie. Nie zmieniono ani nie wyciszono reguły; nie deklarować 0 warnings.
- browser jobs i pozostałe CI w trakcie; managedFEM queued, NOT VERIFIED. PR154 draft; pełny R0/R1 pozostaje otwarty.


## Browser e357 — staging failure diagnoza i korekta

- browser-fixture-smoke job115279518775 FAIL na banner staging; bazowy WebGL fixture oraz negative control PASS. Nie ma dowodu R1 gesture PASS.
- Artefakt11811061377 viewport-3d-browser-audit pobrany do storage/evidence/frontend-authoring-session-safety-20261013/ci-e357; związany z e357 exactHEAD. Inspector actions fixture job115279518285 SUCCESS nie zastępuje gestu ani rzeczywistego API.
- Hipoteza źródłowa: punkt0.5*140nm leżał wewnątrz box +/-100nm; PrimitiveObjectLayer pointer handler stopsPropagation. Punkt0.9*140nm na odsłoniętej osi, nadal native mouse z pointer capture; asercje zachowane. Review bez nowych findings. Na timeout dodano screenshot/JSON, ponownie rzucany błąd. Skuteczność korekty browser NOT VERIFIED.
- PR04 parser sześć plików gotowe do source review; unitpicker i stan jednostki kontrolki nadal otwarte.
