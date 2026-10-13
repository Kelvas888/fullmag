# Docelowa architektura authoringu i transformacji

> Ten rozdział jest projektem wdrożeniowym. Nazwy nowych typów i pól oznaczone jako propozycje nie opisują automatycznie obecnego API.

## 1. Cztery rozdzielone rodzaje stanu

**Committed model** pochodzi z kanonicznej sceny backendu. **Draft** zawiera surowe wpisy i lokalne intencje. **Preview** jest pochodną draftu, committed modelu i wybranego LOD. **Artifact** to zbudowana geometria/siatka z trwałym opisem pochodzenia. Kamera, zaznaczenie i tryb renderowania są osobnym UI state.

Niedozwolone zależności: zapisywanie preview matrix jako niejawnej zmiany modelu; zmiana meshu przez samo przełączenie wireframe; traktowanie dirty draftu jako zatwierdzonej geometrii; nazywanie starego artefaktu aktualnym tylko dlatego, że jest widoczny. Istniejące transakcje i selektory trzeba połączyć tym kontraktem, nie zastępować drugim store. Punkty integracji: [S03: `InspectorEditSession.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorEditSession.tsx), [S06: `geometryLifecycleCommands.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommands.ts), [S20: `geometryLifecycleCommandContributions.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts), [S21: `authoringHistoryMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts).

Proponowany przepływ jest w [diagramie](../diagrams/01_architecture.svg).

## 2. Jeden właściciel edycji

Proponowany `ObjectEditSession` obejmuje tożsamość sesji i epoki, targetId, draftId, baseline scene snapshot, baseline revision, lokalny patch, status parsowania, problem list, numer operacji i aktywny gestureId. Inspektor i manipulator czytają ten sam draft. Nie utrzymują dwóch niezależnych kopii translacji.

```ts
// PROPOZYCJA INTERFEJSU; wymaga adaptacji do istniejących typów API.
type EditPhase =
  | 'clean' | 'editing-valid' | 'editing-invalid' | 'committing'
  | 'conflict' | 'reconciling' | 'failed-known' | 'outcome-unknown';

type ObjectEditIdentity = {
  sessionScopeKey: string;
  targetId: string;
  draftId: string;
};

type CommitOutcome =
  | { kind: 'committed'; operationId: string; sceneRevision: number }
  | { kind: 'conflict'; latestSceneRevision: number }
  | { kind: 'rejected'; problems: readonly FieldProblem[] }
  | { kind: 'unknown'; clientIntentId: string };
```

`FieldProblem` trzeba zdefiniować w generowanym kontrakcie, nie pozostawić jako `any`. Request nie może zależeć od bieżącej selekcji po rozpoczęciu `await`; target i scope są przechwytywane przed wysłaniem.

## 3. ACK reducer i zachowanie zmian wpisanych w międzyczasie

ACK jest przyjmowany tylko, gdy pasuje session scope, target, draft i operationId. Baseline staje się zatwierdzonym snapshotem. Gdy edycja była zablokowana na czas commit, formularz staje się clean. Gdy umożliwiono dalsze wpisywanie, należy porównać `submittedDraft` z aktualnym draftem i na nowy baseline nałożyć tylko późniejsze zmiany. Bezwarunkowe `setDraft(committed)` może zgubić tekst użytkownika.

Po sukcesie zerują się conflict phase, conflict base i error state odpowiedniej operacji. Revert oznacza odrzucenie lokalnej edycji i powrót do bieżącego baseline; nie wykonuje Undo na serwerze. Undo jest osobną mutacją z historią. Usunięcie obiektu z innej sesji powoduje `target-missing`, a nie automatyczne utworzenie go pod tym samym ID.

Minimalna poprawka F01 musi być mała i testowalna. Nie należy uzależniać jej od ukończenia całego nowego modelera.

## 4. Kontrakt narzędzia

Narzędzie ma fazy idle, armed, dragging, committing, reconciling/conflict. W pierwszym wdrożeniu `committing` blokuje nowy gest na tej samej edit session. To prostsze i bezpieczniejsze niż optymistyczne kolejkowanie transformów bazujących na starych rewizjach.

Pointerdown zapisuje origin, pivot, frame, start ray i gestureId. Pointermove wylicza lokalny preview; nie wykonuje requestów. Pointerup wykonuje no-op check i jeden commit. Escape przed wysłaniem cofa preview. Escape po wysłaniu nie może obiecywać cofnięcia już zaakceptowanej mutacji; może zakończyć obserwację UI albo przejść do reconciliation. Zmiana kamery podczas drag jest zablokowana lub jawnie obsłużona, nigdy przypadkowa.

Można użyć adaptera `TransformControls`, ale wyłącznie jako warstwy interakcji. Obiekt Three.js nie staje się źródłem prawdy. Aktualna dokumentacja potwierdza tryby transformacji, lokalny/globalny frame i snap; zgodność z deklarowanym w repo `three ^0.183.2` trzeba sprawdzić na lockfile przed użyciem nowszych metod. [S24: `package.json`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/package.json); [Three.js TransformControls](https://threejs.org/docs/pages/TransformControls.html).

## 5. Jednostki i liczby

Dane modelu zapisujemy w SI, a kontrolki operują na wartościach z jednostką wybraną przez użytkownika. Pole ma `rawText`, `parsedSI`, `dimension`, `status`. Puste pole nie jest zerem. Zmiana nm→µm aktualizuje prezentację, nie fizyczny rozmiar. Wprowadzanie `100 nm`, `0.1 um`, `1e-7 m` daje ten sam wynik. Separator dziesiętny powinien mieć jedną udokumentowaną politykę; bez heurystycznego traktowania przecinka raz jako separatora wektora, raz części dziesiętnej.

Wyrażenia parametrów są osobną funkcją. Jeżeli nie są wdrożone, UI nie może udawać obsługi `width/2`. Jeżeli będą wdrażane, używać parsera AST z wymiarami, zależnościami i detekcją cykli, nigdy `eval`. Wprowadzić bazową walidację finite/range, a domenową pozostawić również backendowi.

## 6. Kanoniczny transform

Proponowany kontrakt obiektu przechowuje translację w metrach, quaternion `[x,y,z,w]`, bezwymiarową skalę oraz pivot w lokalnych współrzędnych SI. Euler służy do edycji, z jawną kolejnością np. intrinsic XYZ i jednostką stopni; zapis jest quaternionem. Nie mieszać eulerowego pola `rotation` z `rotation_quat` bez migracji.

Dla punktu lokalnego:

\[
\mathbf{x}_w=\mathbf{t}+\mathbf{p}+R(q)D(\mathbf{s})(\mathbf{x}_l-\mathbf{p}).
\]

Macierz lokalna wynosi `T(t) T(p) R(q) S(s) T(-p)`. Przy hierarchii `M_world = M_parent M_local`. Kolejność mnożeń jest częścią kontraktu i musi być ta sama w frontendzie, backendzie, eksporcie i mesherze. Skala importu przelicza source units do SI raz, przed transformem obiektu; nie mnożyć jej drugi raz przez ogólną scale.

W pierwszym etapie dozwolić tylko dodatnie, skończone skale i niezerowy quaternion normalizowany z kontrolą normy. Skala zerowa jest błędem. Mirror/ujemny determinant wymaga jawnej obsługi orientacji i nie powinien być efektem ubocznym pola Scale. Nierównomierna skala rodzica z obrotem dziecka może prowadzić do shear; początkowo odmówić takiej konfiguracji albo świadomie przejść na pełny affine, zamiast błędnej dekompozycji TRS.

Dla normalnej powierzchni stosować znormalizowane `A^{-T} n`, gdzie `A=R D`. World AABB otrzymuje się z transformacji lokalnej geometrii/bounds, nie z dodania translacji do dowolnego starego bbox. Fallback nie może pomijać wysokości walca.

## 7. Pivot i anchors

Pivot ma pozycję i ewentualny frame, natomiast anchor jest semantycznym celem: środek, min/max powierzchni bbox, środek powierzchni, vertex, koniec osi, punkt użytkownika. Wybór „Bottom center” nie jest zmianą geometrii.

Dwa jawne tryby: **Affect Pivot Only** i **Transform Object**. Przy zmianie pivotu z p na p′ bez zmiany world transform, dla A=RD należy skorygować:

\[
\mathbf{t}'=\mathbf{t}+(I-A)(\mathbf{p}-\mathbf{p}').
\]

To algebraiczne przepisanie tego samego affine map. Test powinien porównać world coordinates kilku punktów przed i po zmianie pivotu. Nie wolno przesuwać modelu przy operacji opisanej jako „pivot only”.

Anchory na topologii importu muszą mieć provenance do assetu i wersji. Po reimport lub zmianie CSG mogą stać się unresolved. AABB anchor można przeliczyć; indeks losowego trójkąta nie stanowi stabilnej referencji.

## 8. Absolute, delta, Local, World i Align

Pole Position Absolute określa pozycję wybranego punktu odniesienia w wybranym frame; delta określa przesunięcie względem baseline. Mieszane tryby muszą mieć inną etykietę, a nie ukryty przełącznik. Dla wieloselekcji różne wartości są oznaczone jako Mixed, nie zero.

Align wymaga source anchor, target anchor, osi, offsetu i zakresu. Preview pokazuje oba punkty i wynik. Przykład: bottom-center walca do top-center filmu z gap=20 nm. „Center on origin” i „Place on plane Z=0” są różnymi komendami. Snap działa w jawnym frame i jednostce; nie oznacza zaokrąglania do komórek FDM, chyba że wybrano Grid Cell Snap.

## 9. Konsekwencje fizyczne

Transform geometrii nie powinien niejawnie obracać laboratoryjnego pola zewnętrznego. Wartości przypisane do materiału, np. lokalna oś anizotropii lub tekstura początkowej magnetyzacji, wymagają jawnego rozróżnienia frame `object-local` i `world`. Dla właściwego obrotu R pole wektorowe związane z ciałem może być mapowane jako `m′(x)=R m(M^{-1}x)`; skalowanie geometrii nie skaluje normy znormalizowanej magnetyzacji.

To propozycja semantyki, nie potwierdzenie obecnego modelu fizyki w kodzie. Dla mirror, pseudowektorów, tensorów i pól definiowanych przez wyrażenia wymagany jest osobny kontrakt. W pierwszym release nie wprowadzać tych operacji bez testów.

Zmiana geometrii/położenia wpływa na wspólną domenę, odległości i maski. Dla FEM może wymagać remeshu i ponownej realizacji regionów; dla FDM ponownej rasteryzacji membership. Obrócenie samego surface mesh w rendererze nie zmienia solvera. Nonuniform scale nie jest zachowaniem tej samej dyskretyzacji z podmienionym obrazkiem.

## 10. Historia i persistencja

Jedna zaakceptowana intencja daje jeden wpis historii. Undo przywraca semantyczny stan obiektu przez nową transakcję, z nową rewizją; nie cofa globalnego licznika czasu. Przywrócenie geometrii nie oznacza, że stary mesh jest automatycznie aktywny — musi przejść sprawdzenie zgodności.

Historia best-effort może przetrwać jako etap przejściowy, ale brak zapisu historii ma być widoczny. Zachować istniejące fences i workspace selection restore; nowe narzędzia korzystają z [S21: `authoringHistoryMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts) zamiast własnych tablic Undo.
