# Wspólna edycja obiektu — kontrakt wykonawczy V2

Wariant rekomendowany ADR-01; nie jest jeszcze zaakceptowany ani wdrożony. Odwołania do konkretnych obecnych struktur: S01–S10/S21 w `sources.json`; uzupełnienie atomowego payloadu: S25/S26. Kontrakt TRS i fizyki: D13. Transport/recovery: D11.

## 1. Własność i granice modułów

Nie powstaje drugi SceneDocument store. Committed model nadal posiada istniejąca warstwa zasobów. `kernel.objectEdits` jest serwisem lokalnej sesji edycji z referencją do konkretnego baseline snapshotu; nie jest alternatywnym backendem. Jeden panel-owner subskrybuje zasoby, jego dzieci otrzymują modele/selektory. Viewport korzysta z kernelowych selektorów draftu i warstwy zasobów, nie z prywatnych modułów Inspectora.

| Plik / granica | Rola | Status |
|---|---|---|
| `src/kernel/authoring/object-edit/ObjectEditSessionController.ts` | Własność draftów i operacji, lifetime, token epoch, reducer dispatch | Nowy; instancja na kernel, bez mutable singletona modułu |
| `src/kernel/authoring/object-edit/objectEditReducer.ts` | Czysta maszyna stanów z ACK/rebase; powstaje już w PR02 | Nowy, ponownie używany w B1; nie przepisywać drugi raz |
| `src/kernel/authoring/object-edit/objectEditTypes.ts` | Grupy semantyczne, phase, identity, captured operation | Nowy; nie duplikuje generowanych DTO |
| `src/kernel/authoring/object-edit/useObjectEditSelector.ts` | Target-scoped `useSyncExternalStore`, immutable snapshot | Nowy; neutralny `getServerSnapshot` |
| `src/kernel/authoring/object-edit/objectEditCommands.ts` | Apply/Revert/begin/update/end/cancel, canExecute | Nowy; rejestracja w istniejącym CommandRegistry |
| `src/kernel/authoring/object-edit/authoringIntentJournal.ts` | Lokalny intent envelope/reload reconciliation | Nowy; trwały serwerowy receipt opisuje D11 |
| `src/kernel/KernelProvider.tsx`, `src/kernel/types.ts` | Utworzenie i udostępnienie serwisu; dispose przy końcu kernela | Modyfikacja istniejąca; bez nowego shella |
| `src/modules/inspector/InspectorEditSession.tsx` + nowy `ObjectEditSessionAdapter.tsx` | Rejestracja Apply/Revert/dirty/valid w istniejącej stopce | Adapter; nie posiada kopii wartości |
| `GeometryObjectPanel.tsx` / nowy `ObjectPlacementPanel.tsx` | Oddzielne widoki nad jedną sesją edycji obiektu | Istniejący / nowy panel |
| `Viewport3DObjectMoveInteraction.tsx`, `MoveObjectGizmo.tsx` | Geometria gestu i render preview; pointerup wywołuje endGesture | Modyfikacja; usunięcie direct API write |
| `src/kernel/authoring/object-edit/public.ts` | Jedyna publiczna granica nowych typów i selektorów | Nowy; moduły importują public API |

Proponowane API serwisu: `open(target)`, `select(target)`, `updateRaw(group, field, text)`, `beginGesture(capture)`, `updateGesture(id, intent)`, `endGesture(id)`, `cancelGesture(id)`, `apply(draftId)`, `revert(draftId)`, `observeCanonical(snapshot)`, `resolveConflict(choice)`, `suspend(reason)`, `dispose()`. Każda metoda mutująca draft sprawdza tożsamość targetu i kernel epoch. Przekazanie current selection po await jest niedopuszczalne.

## 2. Jedyna granica zapisu w R1/R2

Przykład: bazowy Cylinder ma radius=50 nm, translation=[0,0,0], revision=10.

| Czynność | Draft / preview | Scena backendu | Model Undo |
|---|---|---|---|
| Wpisz radius=80 nm | radius=80 nm; dirty | radius=50 nm, rev10 | 0 nowych wpisów |
| Pointerdown Move | capture całego startDraft i ramy | Bez zmian | 0 |
| Przeciągnij X o 300 nm | radius=80 nm, x=300 nm | Bez zmian; **0 HTTP mutacji** | 0 |
| Pointerup | endGesture → editing-valid | Bez zmian | 0 |
| Revert | radius=50 nm, x=0, clean | Bez zmian | 0 |
| Alternatywnie Apply | Snapshot radius80+x300; committing | Jeden `patch_object_geometry` z transform; oczekiwany rev11 | Jeden wpis dla potwierdzonego zapisu, lub history-degraded |
| Undo po potwierdzeniu | Odczyt wyniku inverse write | Nowa revision; powrót do stanu bazowego | Jeden krok Undo, nie dwa |

Escape w trakcie gestu przywraca **startDraft gestu**: zmiana promienia zrobiona wcześniej pozostaje. Escape po pointerup nie odrzuca całej edycji; całe zmiany odrzuca Revert. `Ctrl+Enter`, ribbon Apply i stopka muszą wywoływać tę samą komendę. Create jest jedynym końcem draft-new, ma odrębny object ID przeznaczony dla przyszłego obiektu.

Nie oferować w R1/R2 ukrytego przełączania na immediate gesture commits. R0 to wewnętrzny etap hotfixów, nie pierwszy publiczny release; może tymczasowo zachować obecny pointerup tylko do migracji adaptera. Bramka R1 sprawdza brak zapisu przy każdym pointerup.

## 3. Draft, baseline i wpisy po submit

Stan logiczny zawiera `identity`, `baselineSceneRevision`, `baselineObject`, `rawFields`, `semanticPatch`, `fieldEditVersion`, `phase`, `gesture`, `submittedOperation`, `problems`, `historyState`. Baseline pochodzi z zatwierdzonej sceny, nie z renderowego bbox. Numer sceny nie jest kluczem React root ani kluczem całego draftu.

Przy Apply: parsuj całość, oblicz semantic patch, zweryfikuj capability i stan runu, uchwyć `draftId/epoch/objectId/operationId`, zamroź `submittedObject`, `submittedRaw`, `submittedEditVersions`, `baseRevision` i `client_intent_id`. Zapisz lokalny intent envelope przed wysłaniem. Brak bezpiecznego local journal wyłącza deklarację recovery po reload; komunikat musi być jawny, zapis nie może przypadkowo ulec podwojeniu.

Przy ACK: transport wiąże odpowiedź z lokalnym `operationId` w closure; obecny serwer nie zwraca tego ID (S25). Po poprawnej identyfikacji operacji publikuj committed scene. Dla każdej **grupy semantycznej**:

1. Jeżeli `currentEditVersion == submittedEditVersion`, grupa otrzymuje kanoniczną wartość z ACK. Format rawText można zachować, jeśli reprezentuje dokładnie tę samą wartość; normalizacja przez backend ma widoczny feedback.
2. Jeżeli wersja jest wyższa, zachowaj rawText i lokalną intencję. Nowym baseline jest ACK. Przelicz tylko nowszy patch względem niego; nie odtwarzaj całego starego deskryptora geometrii.
3. Jeżeli późniejszy rawText jest incomplete/invalid, zachowaj go jako taki; preview tej grupy pozostaje last-valid z oznaczeniem, Apply jest zablokowane.
4. Wersje promienia i średnicy należą do jednego atomu; quaternion i Euler do jednego atomu orientacji. Nie nadpisywać połowy quaternionu.

ACK starej epoki/sesji aktualizuje co najwyżej historyczny journal właściwej intencji; nie zmienia aktywnego draftu, selekcji, feedbacku ani invalidacji bieżącej sesji. `isCurrent` musi pamiętać przejście A→B→A; porównanie samych końcowych ID nie wystarcza. Refresh kanonicznego zasobu podczas dirty draftu uruchamia analizę three-way, nie reset formularza.

## 4. Pending bez blokady całego inspektora

| Kontrolka / akcja | `committing` dla Object Geometry+Placement | Powód |
|---|---|---|
| RawText wymiarów i pozycji | Edytowalne; nowsze editVersion | Nie gubić wpisywania podczas ACK |
| Apply tego draftu i inne scene-changing commit w tej sesji | Zablokowane do terminalnego wyniku | Jeden aktywny zapis sceny na klienta; to nie zastępuje backend CAS |
| BeginGesture w tej transakcji | Zablokowane | Nowy gest nie bazuje na nierozstrzygniętym zapisie |
| Pointermove/pointerup już trwającego gestu | Apply jest niedostępne do endGesture; ta kombinacja nie powinna powstać | Granica gestu przed submit |
| Zmiana typu, delete, reimport targetu | Zablokowane albo odrębna kolejka po rozwiązaniu intencji | Uniknięcie zmiany tożsamości wysłanego targetu |
| Revert całego draftu | Zablokowane do ACK/odrzucenia | Nie może sugerować cofnięcia requestu w locie |
| Discard newer edits | Opcjonalna jawna akcja: odrzuca tylko post-submit delta | Nie anuluje submittedObject |
| Visibility, opacity suwak, kamera, sekcje, scroll, zakładki diagnostyczne | Działają | Niezależne UI state; żadnego globalnego dimming |
| Inne surowe formularze authoringu | Edytowalne; commit rezerwuje scenę dopiero po zwolnieniu aktywnej intencji | Kontrolki nie są objęte target-wide disabled |

Analogiczny controller transakcji stosuje Object Mesh Policy i Airbox; zakres danych jest receptą, nie entire target UI. Root panelu pozostaje ten sam. Aktualizacja zasobu nie zmienia `key` root, scrollTop, focus ani selection range wpisywanego tekstu. Zero animacji opacity na trwałych kontrolkach. Requesty pointermove i raw typing: dokładnie zero mutacji; liczba renderów mierzona w D14, nie arbitralny wymóg „jeden render”.

## 5. Tabela przejść maszyny stanów

`phase` jest jedną z: clean, editing-valid, editing-invalid, committing, conflict, reconciling, rejected, outcome-unknown, target-missing, suspended. `gesture` jest orthogonal: idle/armed/dragging; nie tworzymy osobnego modelu zapisu gestu. `rejected` zachowuje draft i problemy serwerowe. `suspended` przechowuje poprzednią fazę; nie oznacza wyniku serwera.

| State | Event | Guard | Next | Effects |
|---|---|---|---|---|
| clean/editing-* | RAW_CHANGE | Ten sam target/epoch | editing-valid albo editing-invalid | Raw + editVersion; local preview z last-valid; bez HTTP |
| editing-valid | APPLY | Brak active write/gesture, parsed valid, capability, run idle | committing | Capture intencji, local journal, jedno wysłanie |
| clean | APPLY | Patch jest no-op | clean | Bez zapisu i historii |
| editing-invalid | APPLY | Zawsze | editing-invalid | Focus pierwszego błędu; zero requestów |
| editing-valid/clean | BEGIN_GESTURE | Capability, brak write/unknown | Ta sama phase + dragging | Snapshot startDraft i baseline/frame; pointer capture |
| * + dragging | MOVE | Id/epoch zgodne, ray rozwiązany | editing-valid + dragging | Tylko local semantic patch; snap od startu |
| * + dragging | POINTER_UP | Id zgodne | editing-valid albo clean + idle | Release capture; **zero commit** |
| * + dragging | ESC/CANCEL/UNMOUNT | GestureId zgodne | Phase wynikająca ze startDraft + idle | Cofnij gest, zachowaj wcześniejsze raw; odblokuj orbit |
| committing/outcome-unknown | BEGIN_GESTURE/APPLY | Ta sama transakcja/scena | Bez zmiany | Jawny disabled reason; brak nowego requestu |
| committing | RAW_CHANGE | Ta sama identity | committing | Nowszy raw/patch/version, status queued edit |
| committing | ACK_COMMITTED | Pasujące operation/epoch/draft | clean albo editing-* | Nowy baseline; zachowaj post-submit edits; dedup history |
| committing | KNOWN_REJECT | Odpowiedź walidacji/revision jest wiarygodna | rejected albo conflict | Zachowaj draft; zwolnij wyłącznie write slot |
| committing | LOST_ACK/AMBIGUOUS_5XX | Wynik nieznany | outcome-unknown | Zachowaj journal, blokada retry inną intencją |
| outcome-unknown | LOOKUP | Capability receipt i właściwy owner | reconciling | GET jednej intencji; bez POST |
| reconciling | COMMITTED_RECEIPT | Digest/owner/intencja zgodne | clean albo editing-* | Ten sam reducer ACK; nie dopisuj drugiego Undo |
| reconciling | REJECTED_RECEIPT | Wynik definitywny | rejected/conflict | Można poprawić draft i utworzyć nową intencję |
| reconciling | IN_PROGRESS/INDETERMINATE/ERROR/EXPIRED | Brak wyniku definitywnego | outcome-unknown | Nie traktuj timeout jako failure zapisu |
| conflict | REMOTE_SNAPSHOT | Baza i najnowszy owner zgodne | conflict albo editing-* | Three-way merge; konflikty semantyczne wymagają wyboru |
| conflict | RESOLVE | Wszystkie konflikty rozstrzygnięte | editing-* | Nowa baza, zachowany patch; brak automatycznego submit |
| clean/editing-*/conflict/rejected | REVERT | Brak unresolved write | clean | Raw z najnowszego znanego baseline; clear problems/conflict |
| każda | TARGET_DELETED | Potwierdzone na aktualnej scenie | target-missing | Draft wyłącznie do eksportu; Apply wyłączone, selekcja targetu nie rozwiązuje, bez upsert |
| target-missing | EXPORT/DISCARD | Decyzja użytkownika | suspended albo clean bez targetu | Bez mutacji; Create as new jest osobną intencją z nowym ID |
| każda | SESSION_SWITCH/PROJECT_CLOSE | Epoka zmieniona | suspended | Cancel gesture, detach render subscriptions; journal in-flight zachowany |
| suspended | RESUME | Sprawdzony owner, nowa epoch, reconciliation | clean/editing-*/conflict/outcome-unknown | Nie przenoś starego fence; wyznacz nowy |

Wyścig usunięcia z pending write ma dwa rozstrzygnięcia. Jeśli delete zatwierdzi się przed patch, odpowiedź `TARGET_DELETED` prowadzi do `target-missing`: draft pozostaje tylko do eksportu, Apply jest wyłączone, selekcja nie rozwiązuje obiektu, historia nie dostaje wpisu i klient nie wykonuje upsert. Jeśli patch zatwierdzi się pierwszy, jego receipt rozlicza tę intencję najwyżej raz; późniejszy delete z aktualnej sceny nadal przełącza target do `target-missing`, bez wskrzeszenia draftu ani wykonywalnego Undo dla nieobecnego obiektu.

Komenda guard i dialog dirty stosują tę samą funkcję `canApply`; nie tylko valid/pending. `Apply and continue` jest niedostępne przy nierozstrzygniętym konflikcie nawet gdy wszystkie liczby są poprawne.

## 6. Lifetime i SSR

| Zdarzenie | Draft | Preview/GPU | Operacja/journal |
|---|---|---|---|
| Geometry→Placement tego samego obiektu | Zachowany; to jedna sesja edycji | Zmieniają się narzędzia, nie geometria źródłowa | Ta sama |
| Geometry→Mesh Policy / inny obiekt | Dirty guard: Apply/Discard/Cancel; dialog mówi o zakresie obiektu | Brak porzucenia preview przed decyzją | Apply musi zakończyć się definitywnie przed continue |
| Zmiana centralnej zakładki / ukrycie Inspectora | Draft zachowany w kernelu | Preview zawieszone tam, gdzie nie renderujemy | Nie anulować zapisu przez unmount |
| Zamknięcie viewportu | Draft zachowany | Cancel gesture; dispose geometry/material/buffers i subskrypcji | Brak kasowania receipt |
| Wejście na Start | Lokalna sesja suspended; guard przed opuszczeniem niezapisanego targetu | Bez render loop i GPU references | Intent w local journal zachowany |
| Zmiana sesji / projekt zamknięty | Osobny namespace; stare drafty suspended, nigdy reuse objectId | Wszystkie stare GPU/DOM leases zwolnione | Stare odpowiedzi nie invalidują nowej sesji |
| Reload strony | Odtwórz journal i opcjonalnie raw draft po potwierdzeniu owner | Nie odtwarzaj pointer capture/gesture | Najpierw lookup, nie ponowne Create |
| Usunięcie obiektu | target-missing, raw do eksportu | Usuń aktywne gizmo; stary model wyłącznie oznaczony snapshot | Brak niejawnego upsert |

Pierwszy render klienta musi użyć tego samego pustego immutable snapshotu co SSR. Dopiero po hydration następuje odczyt local journal/resource cache. Nie renderować live localStorage w initializerze komponentu. Instancja per kernel; `dispose()` kończy nasłuchy, timery i Workers, a nie usuwa trwałych operacji z nieznanym wynikiem.

## 7. Tożsamości

| ID | Kto nadaje | Unikalność / trwałość | Transport |
|---|---|---|---|
| projectId/documentId | Persistence/backend | Projekt i dokument; survives reopen | Nowy provenance/receipt; nie wyprowadzać z nazwy |
| sessionScopeKey / kernel epoch | Obecny session/runtime + kernel token | Epoka aktywacji; A→B→A nie odżywa | RequestOptions i capture; nie nazwa projektu |
| object_id == objects[].id | Klient UUID przy Create; backend waliduje unikalność | Dokument; niezmienny; rename nie zmienia | Request `object_id`; ACK wewnątrz committed_scene |
| name / presentation type | Użytkownik/model UI | Zmienny; nigdy routing fizyki | Jawne pola modelu, nie ID |
| draftId | Kernel UUID | Jedno otwarcie logicznego draftu; type-change tworzy nowe | Lokalny journal; nie musi być w API |
| gestureId | Kernel monotonic counter + draftId | Jeden gest; nie survives reload jako active | Tylko lokalny |
| operationId | Kernel counter/UUID | Jedno wykonanie async; mapuje closure ACK | Lokalny; **nie występuje w aktualnym ACK** |
| client_intent_id | Klient UUID przed submit | Trwała intencja zwykłej mutacji w proponowanym receipcie | Nowe pole transakcji/receipt; nie zakładać obecnej obsługi |
| command_id | Backend command subsystem | Jeden długi job mesh/grid | Już istniejący model komendy; nie zastępuje object/draft ID |
| assetId/version/hash | Asset subsystem | Niezmienna wersja bajtów i import settings | Referencja projektu i preview binary |
| generationId/ElementRef | Backend publisher / adapter selection | Jedna publikacja, ordinal tylko wewnątrz niej | Manifest i zasoby danych; D06 |

Duplikacja: nowe object_id, nowe ID encji regionów własnych, kopiowane jawne przypisania z odpowiednim owner rebind; referenced immutable asset może być współdzielony. Funkcja duplikacji z pełnym zapisem jest odłożona do R3 poza niezmienionymi obecnymi ścieżkami. Reimport: ten sam object_id, nowa asset version, ten sam display name chyba że użytkownik zmieni; orphan bindings jawne.

## 8. Three-way rebase

Dla grupy semantycznej: B=baseline, L=local intent, R=remote current. Najpierw normalize jednostki i aliasy. Jeżeli L=B, przyjmij R; jeżeli R=B, przyjmij L; jeżeli L=R, przyjmij tę wartość; inaczej konflikt. Porównanie nie może wyrzucać nieznanych pól geometry descriptor. Serializer odtwarza kompletny descriptor z nowej bazy i zaakceptowanego patcha.

| Przypadek | B | L | R | Result |
|---|---|---|---|---|
| Rozłączne wymiary Box [nm] | [100,50,10] | X=120 | Y=60 | [120,60,10] |
| Promień vs średnica [nm] | r=50 | r=80 | d=160 | r=80; ten sam atom, bez konfliktu |
| Promień vs średnica konflikt | r=50 | r=80 | d=140 | Konflikt 80 vs 70; wybór użytkownika |
| Absolute position X [nm] | 100 | Cel150 | Remote120 | Konflikt: keep target150 albo use remote120; nie dodaj 50 automatycznie |
| Delta position X [nm] | 100 | +50 od B, cel150 | Remote120 | Konflikt; keep absolute150 lub jawne reapply delta→170 |
| Remote position bez lokalnej zmiany pozycji | 100 | Tylko radius80 | Remote120 | Position120 + radius80 |
| Quaternion | q0 | q1 | −q1 | Ta sama orientacja, bez konfliktu; porównanie znakowo niezależne |
| Dwie różne rotacje | q0 | qx | qz | Jeden konflikt orientacji, nie merge czterech składowych |
| Zmiana typu | Cylinder | radius80 | Box | type-conflict, zachowaj raw; nie wklej radius do Box |
| Usunięcie targetu | Obiekt A istnieje | patchA | Brak A | target-missing, eksport/discard; nigdy upsert |
| Import/reimport | assetV1 | lokalny anchor V1 | assetV2 | Anchor unresolved; wymagany jawny rebind |

Delta jest uchwycona w frame z BEGIN_GESTURE; obrót ramy remote czyni także lokalną deltę zależną i wymaga decyzji. Wyrażenia typu radius=width/2 są poza R1/R2, więc nie stosować automatycznego algebraicznego merge. Zatwierdzony rebase czyści conflict marker, ale nie wysyła requestu samodzielnie.

## 9. Parser, no-op i snap

Pole ma `rawText`, `unit`, `dimension`, `parseStatus`, `parsedSI`, `lastValidSI`; status jest empty/incomplete/invalid/valid. Gramatyka kompletnej liczby to znak opcjonalny + część dziesiętna + opcjonalny wykładnik `e/E[+-]?digits`; pojedyncza kropka lub pojedynczy przecinek jest separatorem dziesiętnym. Nie akceptować separatorów tysięcy, dwóch separatorów, `NaN`, `Infinity`, hexadecimal ani wyrażeń. `1,2` oznacza 1.2 w jednym polu; wektor ma trzy pola, więc nie ma heurystyki rozdzielania tuple.

Jednostki długości: m, mm, um, µm, μm, nm; kąty: deg, °, rad; skala bezwymiarowa. Jedna spacja przed sufiksem jest dozwolona. Bez sufiksu obowiązuje jednostka wybrana w kontrolce. `100 nm`, `0,1 um`, `1e-7 m` są równoważne. `''`/whitespace→empty; `-`, `+`, `.`, `,`, `1e`, `1e-`→incomplete; nieznana jednostka→invalid. Sufiks nie może zmienić wymiaru (np. nm w polu scale). Walidacja domenowa dodatniości jest oddzielna od parsowania.

Zmiana jednostki przy valid: przelicz tekst z parsedSI bez zmiany fizycznej wartości. Przy incomplete/invalid: zablokuj zmianę jednostki **tego pola** z powodem albo wymagaj Revert field; nie reinterpretuj niedokończonego tekstu według nowej jednostki. Nie globalizować blokady.

No-op test dla skalaru długości a,b: `|a−b| ≤ 8·ulp(max(|a|,|b|,Lchar))`, gdzie Lchar to dodatni lokalny rozmiar obiektu w SI (bez arbitrarnych jednostek świata). Dla zera stosuj ulp najmniejszej dodatniej liczby representable. To **proponowana tolerancja serializacji f64**, a nie tolerancja fizycznej geometrii ani weldingu. K=8 służy amortyzacji kilku konwersji/operacji; testy niezależnego oracle i porównanie z rzeczywistą ścieżką muszą potwierdzić, że nie ukrywa zmian. Nie używać jednego epsilon=1e−6 w metrach. Przy Lchar=100 nm tolerancja jest około 1.06e−22 m; przesunięcie 0.001 nm=1e−12 m nie jest no-op. Przy bardzo dużych world coordinates wymagany jest komunikat o utracie precyzji, a nie „przyklejenie” obiektu; renderer powinien używać local origin.

Próg rozpoczęcia drag: rekomendowane 3 CSS px jako decyzja interakcji, niezależna od tolerancji modelu. Pointerdown/up bez przekroczenia progu to click i nie zmienia draftu. Snap domyślnie OFF; początkowe wartości kontrolek: 1 nm, 1°, 1% skali (propozycja UX, nie wynik pomiaru). Quantize `delta_from_start` do n·step; najbliższa wielokrotność, dokładny remis połowy kroku zaokrąglany od zera. Nie stosować domyślnego, niesymetrycznego `Math.round` bez adaptera. Nigdy nie kwantyzować przyrostów z poprzedniej klatki. Wpisane wartości nie są zaokrąglane snapem bez polecenia. Grid-cell snap jest osobną przyszłą funkcją; zwykły snap nie zmienia spacing/mesh policy.
