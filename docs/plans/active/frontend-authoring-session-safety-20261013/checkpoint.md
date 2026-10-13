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
