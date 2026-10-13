# PR04 — integracja jednostek pól z kernel draft

Stan: plan kolejnego fragmentu R1, nie dowód wykonania. Parser SI jest w commicie abf7eddd7642dda832b468efa83b84b0f22c3227. Pozostają wybrana jednostka kontrolki oraz last-valid preview.

## Kontrakt

- Raw tekst pozostaje w GeometryObjectDraft. Wybrana jednostka i lastValidSI należą do tej samej sesji kernela, per scalar/axis; nie tworzyć prywatnej kopii formularza w Inspectorze.
- Dodać opcjonalne metadane quantityFields per klucz: size.0–2, translation.0–2, radius, height, length, width, archHeight, z0. Brak wpisu oznacza m. Parse status i parsedSI pozostają danymi pochodnymi wspólnego parsera; nie utrwalać ich drugiej kopii.
- Zmiana raw aktualizuje lastValidSI tylko po poprawnym parsowaniu i walidacji domenowej. Niepoprawny raw pozostaje widoczny; podgląd korzysta z last-valid z jawnym oznaczeniem błędu; Apply jest zablokowane.
- Zmiana jednostki konwertuje poprawny raw z SI bez zmiany modelu ani HTTP. Incomplete/invalid blokuje wyłącznie selector tego pola z podanym powodem; inne pola pozostają edytowalne.
- Parser payloadu, preview, porównanie no-op, conflict/rebase i ruch programowy muszą odczytywać jednostkę tego samego atomu. Jawny sufiks ma pierwszeństwo nad jednostką wybraną.
- ACK zachowuje wybraną jednostkę widoku. Kanoniczne SI z ACK jest formatowane w tej jednostce przed zastąpieniem raw; późniejsze raw i jego jednostka są uzgadniane atomowo. Brak nowszego tekstu nie może powodować reinterpretacji SI jako nm.
- Canonical resource refresh dla nowej rewizji zachowuje jednostki widoku i analizę dirty/rebase. Object A→B→A i nowa sesja stosują dotychczasowe draftId/epoch fences.

## Fragmenty i własność zmian

1. Kernel: objectEditTypes.ts, objectEditDraftModel.ts/test, nowy quantityDraftFields.ts/test. Typowane klucze i czyste operacje raw/unit/format canonical. Kryterium: round-trip SI, field-only blocking, atomowe raw+unit, last-valid bez zero fallbacku.
2. Konsumenci: geometryObjectPanelModel.ts/test, objectEditAckReconciliation.ts/test, viewport3dPrimitiveModel.ts/test i Viewport3DObjectMoveInteraction.tsx/test. Wszystkie ścieżki stosują ten sam parser/metadane; ruch nie zmienia fizycznego rozmiaru.
3. UI: istniejące FormField/Vector3Field oraz GeometryObjectPanel.tsx/DOM. Mały selector obok każdego pola/osi zgodny z tokenami Inspectora; aria-label, powód blokady, brak globalnego disabled podczas ACK. Revert przywraca canonical SI w wybranych jednostkach; unit-only nie włącza Apply.

## Dowody odbioru

Regresje: 100 nm = 0,1 um = 1e-7 m; zmiana unit i późniejsze wpisanie liczby bez sufiksu; '-' blokuje tylko własną zmianę unit; invalid podczas ACK pozostaje raw; geometry+translation jeden PatchObjectGeometry pełny Transform3D; unit-only zero HTTP/history; A→B→A; pending ACK z późniejszą zmianą jednostki; zmiana jednostki po reconnect.

Zakaz lokalnej kompilacji/uruchamiania unit suite pozostaje. Kontrole źródłowe nie zastępują Q-API/Q-BROWSER: browser musi sprawdzić realne kontrolki, canvas/WebGL, brak podwójnej konwersji i stabilność Object/Airbox. Real API i generation qualification nadal NOT VERIFIED.