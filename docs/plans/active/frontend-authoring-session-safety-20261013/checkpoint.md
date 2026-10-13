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


## PR04 parser ilości — etap źródłowy

- quantityInput zawiera jednostki D04§9, rawText/parsedSI/lastValidSI/statusy, decimal dot/comma/exponent, jawny wymiar, osobną zmianę jednostki. Nie używa eval; hex/wyrażenia/NaN/Infinity/overflow odrzucone.
- Preview/payload geometry oraz kernel semantic no-op korzystają ze wspólnego parsera SI. Dodatniość domenowa pozostaje oddzielna; non-positive preview dimensions pozostają null.
- Review P2 bare wrong suffix poprawiony i pokryty regresją. Root sprawdził fix oraz dodatniość. Architecture/API/diff źródłowe PASS, unit/typecheck/browser NOT VERIFIED.
- Pozostałe integracje: viewport placement preview Number() do zastąpienia; wybrana jednostka kontrolki i per-field unit selector do podłączenia. Ten commit nie kończy PR04 ani R0/R1.


## CI043 — typecheck PASS, lint i framing

- Typecheck przeszedł wcześniejsze błędy. Lint FAIL exhaustive-deps475; poprawiono zależność do wyodrębnionego callbacka interaction. Review source bez findings.
- Browserfixture FAIL staging. Artefakt11809464566 w storage/evidence/frontend-authoring-session-safety-20261013/ci-043 zawiera failureJSON: camera[0,0,1] m, start/end oddalone0.00002 CSSpx, pointerdown1, selectionNothing, writes0. To dowód złego framingu, nie PASS gestu.
- Smoke używa produkcyjnego Fit view i czeka na kamerę blisko obiektu; wymaga drag>3 CSSpx. Review source bez findings; browserexecution korekty NOT VERIFIED.
- ParserSI abf7eddd7642dda832b468efa83b84b0f22c3227 zapisany; viewport sharedparser reviewed i zapisany w osobnym fragmencie. Unitmetadata kernel helper etap w realizacji wg pr04-unit-controls-plan.md.


## CI2a — rzeczywista granica dispatchu Move i blokada integracji

- HEAD 2a412864427473d8fbe942428fe7d3ecbefdb9f2, PR154 draft/open. Workflow38394922734: control-room-contracts FAIL (translation fixture string[] zamiast tuple), browser-fixture-smoke FAIL, rust-contracts FAIL, python-contracts FAIL. Inspector-actions-browser-smoke i generated-api-determinism PASS nie zastępują pozostałych bramek.
- Browser artefakt11811900779, SHA2569001b567796450bbd5957a8222f884b579e74be037ff21cfeb0cd8fa8eacb1a0, w storage/evidence/frontend-authoring-session-safety-20261013/ci-2a. Po Fit view drag ma >3 CSSpx, nativePointerDowns1, writes0, ale kamera orbituje zamiast staging. Wcześniejsze hipotezy punktu/framingu były niewystarczające.
- Przyczyna źródłowa: viewport3dEventManager odracza down do click, blokuje pressed move i usuwa up. Naprawa dispatchu: native capture probe wyłącznie istniejących move-axis (getter kernel.objectMoveTool), zatrzymanie Orbit tylko przy trafieniu; zwykła selekcja nadal deferred. Captured pointer move i pointerup przekazywane do R3F; static gizmo click nie replayuje down.
- Move controller przechowuje płaszczyznę gestu i używa bieżącego ray poza cylindrem. Native pointercancel/lostpointercapture fence pointerId; capture throw również sprząta R3F capture. Dodano regresje źródłowe. Review źródeł bez nowych actionable findings. Zgodność adaptera sprawdzona ze źródłem upstream https://raw.githubusercontent.com/pmndrs/react-three-fiber/master/packages/fiber/src/web/events.ts i core/events.ts; wykonanie wersji z lockfile pozostaje CI.
- Architecture/API hygiene uruchomione z apps/control-room PASS, diff-check PASS. Unit/DOM/typecheck/browser/WebGL po zmianie NOT VERIFIED; lokalnie nie kompilowano testów. Pierwsze wywołanie architecture z root miało błędny cwd, nie dowodziło awarii aplikacji.
- Rust: session_checkpoint_create_captures_live_magnetization zwraca500 session store writer is busy (969 PASS/1 FAIL/3 ignored); diagnoza osobna. Python: test_multi_object_sizing_cylinder_and_waveguide odrzuca component_aware zamiast conformal_occ po trzech odrzuceniach degenerate tetra volume; nie osłabiono asercji ani progu jakości.
- Niezacommitowany PR04 unit kernel/UI zachowany, nie włączany do commita dispatchu. Pełny R0/R1 (units consumers, durable receipts, generation/publication i kwalifikacja) pozostaje aktywny; merge wymaga zielonych kontroli i review.

## PR04 — kernel metadata jednostek, etap pomocniczy

- objectEditTypes definiuje opcjonalne quantityFields per scalar/axis: wybrana jednostka długości i lastValidSI; raw nadal źródłem tekstu, status/parsedSI są pochodne. Brak metadata oznacza m.
- quantityDraftFields udostępnia immutable raw update, domain-aware parse, unit change zachowujące SI i canonicalDraftInSelectedUnits dla ACK. Overflow formatowania zachowuje jawne SI z sufiksem m. Invalid/incomplete nie zmienia lastValidSI i blokuje tylko unit selector danego pola.
- Regresje źródłowe: roundtrip nm/um/m, pole/osiowa izolacja, invalid/incomplete/domain guard, overflow ACK i niemutowalność. Niezależny review helpera bez actionable findings; root sprawdził API i kod. Diff-check PASS. Testy/typecheck/browser NOT VERIFIED, nie uruchamiano kompilacji.
- Ten etap nie kończy PR04. Konsumenci payload/preview/equality/rebase w realizacji; root integruje ACK/refresh/reset, gest i kontrolki. Nie pushujemy pomocniczego commita przed otrzymaniem bieżącego CI be015852 dla dispatchu, aby zachować dowód tego źródła.

## CIbe015 i integracja jednostek

- be015852580522be44ace6bbb3379f040beb51bb: workflow38397322063 terminalny. Typecheck/lint PASS; control-room testy 7713 PASS/10 FAIL; browser-fixture FAIL na niejednoznacznym selektorze Apply już po skutecznym staging gestu. Rust/Python/generated API/inspector-actions browser i pozostałe lekkie bramki PASS.
- Smoke adresuje wspólną stopkę .fm-inspector__action-bar, zachowując rygorystyczne asercje transakcji i historii. Testy konwersji SI używają 8 ULP zamiast dokładnej równości zmiennoprzecinkowej. Create fixture ACK zwraca ID żądania, a produkcja publikuje ACK sceny przed wyborem nowego obiektu, chroniąc późniejsze wpisy przed przejściem przez missing target.
- PR04: payload/preview/equality/rebase/ACK/refresh/reset i gest korzystają z kernelowej metadata jednostek. Invalid raw zachowuje lastValidSI wyłącznie dla preview; payload blokowany. Selektor per pole/osię korzysta z istniejących prymitywów Inspectora. Unit-only nie oznacza dirty także dla nowego obiektu.
- Niezależny review źródeł konsumentów i integracji bez dalszych actionable findings; zgłoszone P1 import General i P2 create raw comparison poprawiono. Architecture/API hygiene oraz parser smoke PASS; diff-check PASS. Nie uruchamiano lokalnie testów, typecheck ani builda. Wykonanie nowych regresji i browser proof pozostaje CI, nie deklarujemy PASS przed wynikiem.
- Pełne R0/R1 i ordinary durable receipts/generation qualification pozostają oddzielnym niezakończonym zakresem. Użytkownik żąda merge bieżącego etapu; merge dopiero po wymaganych kontrolach.
