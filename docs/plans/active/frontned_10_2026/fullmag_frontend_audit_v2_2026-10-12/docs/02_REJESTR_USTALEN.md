# Rejestr ustaleń — wersja 2

Snapshot: `2a3c6becb9c7e111ae1497ec0cd9ac9576acba95`. Zachowano 28 identyfikatorów, priorytety i klasy V1. Żadnej pozycji nie zamknięto jako naprawionej. Zmiany interpretacji wyróżniono w sekcji „Korekta V2”. Nowa propozycja kontraktu nie jest istniejącą implementacją.

| ID | Priorytet | Klasa | Ustalenie |
|---|---|---|---|
| [F01](#f01) | P1 | L | Szkic zachowuje starą baseRevision po poprawnym Apply |
| [F02](#f02) | P1 | C | Udany Retry i Revert nie kończą stanu konfliktu |
| [F03](#f03) | P2 | C | Dwa poziomy Apply mają różne reguły i nie tworzą atomowej edycji obiektu |
| [F04](#f04) | P1 | C | Gest Move omija historię semantyczną używaną przez inspektor |
| [F05](#f05) | P1 | L | ACK poprzedniego gestu może wyczyścić podgląd następnego |
| [F06](#f06) | P1 | R | Viewport nie przekazuje ogrodzenia sesji do mutacji translacji |
| [F07](#f07) | P2 | L | Błąd Move inny niż 409 nie ma lokalnej obsługi w łańcuchu UI |
| [F08](#f08) | P2 | R | Rebase oznacza zmianę rewizji, nie scalanie zmian |
| [F09](#f09) | P2 | L | Puste pole współrzędnej jest interpretowane jako zero |
| [F10](#f10) | P1 | G | Rotate i Scale są świadomie wyłączone |
| [F11](#f11) | P1 | G | STL nie ma kompletnej ścieżki importu w sprawdzonym wejściu UI |
| [F12](#f12) | P2 | C | Nieobsługiwany typ geometrii trafia do mylącego formularza wymiarów |
| [F13](#f13) | P2 | G | Preview edycji i przesuwania nie reprezentuje całego obiektu |
| [F14](#f14) | P2 | G | Zestaw narzędzi nie spełnia kontraktu precyzyjnego modelera |
| [F15](#f15) | P2 | R | Drag korzysta z punktu trafienia zamiast jawnej geometrii przeciągania |
| [F16](#f16) | P2 | L | Kliknięcie uchwytu bez ruchu wysyła mutację |
| [F17](#f17) | P2 | C | Walidacja miesza brak danych z brakiem problemów |
| [F18](#f18) | P2 | L | Fallback bounds walca ignoruje jego wysokość |
| [F19](#f19) | P2 | L | Freshness meshu uznaje niespójne rewizje za current |
| [F20](#f20) | P2 | R | Viewport i inspektor stosują różne reguły stale meshu |
| [F21](#f21) | P2 | R | Selekcja najgorszego elementu nie niesie tożsamości meshu |
| [F22](#f22) | P2 | R | Reconciliation utraconego ACK szuka tylko ośmiu ostatnich komend |
| [F23](#f23) | P2 | G | Zakładka history polityki obiektu jest w praktyce widokiem JSON |
| [F24](#f24) | P2 | G | Ribbon eksponuje szeroki katalog trwale nieaktywnych funkcji |
| [F25](#f25) | P2 | R | Rozmiar modułów zwiększa ryzyko rozbieżności polityk UI |
| [F26](#f26) | P2 | R | Tożsamość szkicu jest zbyt słaba na zmianę typu lub sesji |
| [F27](#f27) | P2 | R | Historia może zniknąć bez komunikatu po poprawnej mutacji |
| [F28](#f28) | P2 | R | Pierwsza budowa wymaga testu pustych zasobów w dialogu potwierdzenia |

<a id="f01"></a>
## F01 — Szkic zachowuje starą baseRevision po poprawnym Apply

**Plan v2:** PR02, PR07; **testy:** T01, T54.

**Priorytet P1; klasa L; status: nie wykonano retestu produkcji.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts); [S03: `InspectorEditSession.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorEditSession.tsx); [S21: `authoringHistoryMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts).

**Stan odczytany w V1.** Klucz szkicu to mode:objectId. applyGeometryPatch i applyTransformPatch używają draft.baseRevision, a po ACK publikują scenę/feedback bez aktualizacji draftState. Wspólny InspectorEditSession w trybie mutation-owned nie resetuje formularza. Snapshot historii nie zastępuje rewizji użytej w payloadzie.

**Skutek / ryzyko.** Po pierwszym zapisie drugi zapis z tego samego zamontowanego panelu może dostać 409 mimo braku innego edytora. Pola mogą pokazywać dane lokalne oderwane od nowego bazowego snapshotu.

**Scenariusz reprodukcji.** Otwórz obiekt w rewizji 10, zmień wymiar, Apply → ACK 11; bez zmiany selekcji zmień wymiar ponownie. Sprawdź base_revision drugiego requestu. R05 odtwarza sam wybór starego draftState, nie montaż React.

**Plan naprawy V2.** Wprowadź ACK reducer: przy zachowaniu tożsamości operacji zaktualizuj baseline i baseRevision z committed_scene. Zachowaj wyłącznie edycje wykonane po wysłaniu requestu. Nie resetuj szkicu po dowolnym refetchu.

**Kryterium odbioru.** Test DOM: trzy kolejne Apply wysyłają kolejno 10,11,12; po każdej odpowiedzi dirty=false. Osobny test zachowania nowszej, jeszcze niewysłanej edycji podczas ACK.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f02"></a>
## F02 — Udany Retry i Revert nie kończą stanu konfliktu

**Plan v2:** PR02, PR07; **testy:** T03, T04.

**Priorytet P1; klasa C; status: nie wykonano retestu produkcji.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S03: `InspectorEditSession.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorEditSession.tsx).

**Stan odczytany w V1.** Rebase ustawia revisionConflictPhase=rebased. Ścieżki zapisu istniejącej geometrii i transformacji po sukcesie nie zerują tej fazy. revertDraft aktualizuje draftState i feedback, ale również nie zeruje konfliktu. Wspólne Apply blokuje każdy niepusty revisionConflictPhase.

**Skutek / ryzyko.** Można otrzymać komunikat sukcesu i jednocześnie pozostać z zablokowanym wspólnym Apply. Revert nie przywraca przewidywalnego stanu gotowości.

**Scenariusz reprodukcji.** Wywołaj 409, Refetch, Rebase, Retry; po ACK sprawdź wspólną stopkę. Powtórz, zastępując Retry przyciskiem Revert.

**Plan naprawy V2.** Zastąp niezależne flagi jednoznaczną maszyną stanów. ACK bieżącej operacji oraz świadome porzucenie szkicu muszą wyzerować konflikt, jego bazę, operation i flagi odświeżenia.

**Kryterium odbioru.** Testy DOM dla create/geometry/transform: conflict→refetched→rebased→success→clean oraz conflict→revert→clean; brak utraty niespokrewnionych szkiców.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f03"></a>
## F03 — Dwa poziomy Apply mają różne reguły i nie tworzą atomowej edycji obiektu

**Plan v2:** PR05, PR07; **testy:** T02, T51, T52.

**Priorytet P2; klasa C; status: nie wykonano retestu produkcji.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S03: `InspectorEditSession.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorEditSession.tsx); [S25: `authoring.rs`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-api/src/schemas/authoring.rs); [S26: `authoring.rs`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-api/src/router_v2/handlers/model/authoring.rs).

**Stan odczytany w V1.** Wspólne Apply blokuje jednoczesną zmianę wymiarów i translacji, prosząc o dwa wpisy historii. Lokalne Apply Geometry/Apply Transform mają mniej restrykcyjne disabled i nie używają wspólnego applyBlockReason.

**Skutek / ryzyko.** Ten sam formularz ma kilka definicji gotowości. Dwa requesty pozwalają na stan pośredni, w którym wymiar zapisano, a pozycja pozostała stara. To szczególnie nieczytelne przed Build Mesh.

**Scenariusz reprodukcji.** Zmień size i translation. Porównaj stopkę inspektora z lokalnymi przyciskami; sprawdź historię oraz sytuację, gdy drugi request otrzyma 409.

**Plan naprawy V2.** Wspólny ObjectEditSessionController w kernelu i jedna komenda Apply. Dla jednego istniejącego obiektu reużyć patch_object_geometry z geometry, pełnym transform i jednym base_revision. Nie tworzyć ogólnego batcha. Potwierdzić końcowy CAS i brak częściowego zapisu w realnym backendzie. Wieloobiektowy commit jest poza R1/R2.

**Kryterium odbioru.** T02/T51: radius+translation, pointerup bez HTTP, jeden Apply; jedna zmiana rewizji i co najwyżej jeden deduplikowany wpis Undo, history-degraded przy niedostępnej historii. T52 sprawdza atomowość konkurujących zapisów.

**Korekta V2.** Potwierdzono istniejącą ścieżkę geometry+transform w jednym żądaniu i jednej scenie. Nie jest to certyfikat linearizowalności zapisu.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f04"></a>
## F04 — Gest Move omija historię semantyczną używaną przez inspektor

**Plan v2:** PR03, PR07; **testy:** T25, T26.

**Priorytet P1; klasa C; status: nie wykonano retestu produkcji.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S07: `objectTranslationMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectTranslationMutation.ts); [S08: `objectMoveConflictWorkflow.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts); [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx); [S21: `authoringHistoryMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts).

**Stan odczytany w V1.** Inspektor opakowuje translację w runAuthoringMutationWithHistory. Produkcyjny commitMove wywołuje commitObjectMoveWorkflow→commitObjectTranslation bez tego wrappera. Niskopoziomowa transakcja nie rejestruje historii.

**Skutek / ryzyko.** Znaczenie Undo zależy od tego, czy identyczny ruch wykonano myszą, czy wpisując liczby. Samo uruchomienie narzędzia przez CommandRegistry nie zapisuje późniejszego gestu.

**Scenariusz reprodukcji.** W czystej historii wykonaj Move przez gizmo, następnie Undo; porównaj z translacją przez inspektor. Reprodukcja integracyjna pozostaje do uruchomienia w aplikacji.

**Plan naprawy V2.** Przed publikacją R1 przenieść Move do kernelowego draftu. Pointerup nie zapisuje. Apply używa wspólnej mutacji i historii. Minimalny wewnętrzny hotfix starego pointerup może istnieć tylko jako niewydawany etap przejściowy.

**Kryterium odbioru.** T25: jeden Apply po dowolnej liczbie gestów daje jeden wpis Undo; same gesty dają zero zapisów i zero wpisów historii serwerowego modelu.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f05"></a>
## F05 — ACK poprzedniego gestu może wyczyścić podgląd następnego

**Plan v2:** PR03, PR07; **testy:** T18, T54.

**Priorytet P1; klasa L; status: nie wykonano retestu produkcji.**

**Źródła:** [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx); [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx).

**Stan odczytany w V1.** createMoveGestureController.end zwalnia aktywny gest przed await onCommit. Można zacząć następny gest. Po ACK pierwszego end bezwarunkowo wywołuje onDraftChange(null), bez sprawdzenia numeru gestu.

**Skutek / ryzyko.** Nowy preview może zniknąć w trakcie przesuwania. Dodatkowo dwa gesty mogą korzystać z tego samego origin/baseRevision. R01 odtwarza bezpośrednio pierwszą część problemu.

**Scenariusz reprodukcji.** Opóźnij odpowiedź requestu A. Zakończ gest A, rozpocznij B i przesuń obiekt. Zwróć ACK A przed końcem B. Minimalny test jest w reproductions/reproduce.mjs.

**Plan naprawy V2.** R1: podczas zapisu blokować rozpoczęcie kolejnego gestu dla tej transakcji; rawText pozostaje edytowalny. ACK sprawdza epokę/draft/operację i zachowuje wpisy po submit. Test nakładających się gestów zostaje historyczny; nie opisuje kontraktu R1.

**Kryterium odbioru.** T18: gest B odrzucony w committing/outcome-unknown; po ACK możliwy nowy gest. T54: późniejszy rawText nie jest kasowany.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f06"></a>
## F06 — Viewport nie przekazuje ogrodzenia sesji do mutacji translacji

**Plan v2:** PR03, PR06, PR07; **testy:** T05, T06, T65.

**Priorytet P1; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S07: `objectTranslationMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectTranslationMutation.ts); [S08: `objectMoveConflictWorkflow.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts); [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx); [S11: `MoveObjectGizmo.test.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.test.tsx).

**Stan odczytany w V1.** commitObjectTranslation obsługuje sessionScopeKey i isCurrentSessionScope; jego test potwierdza odrzucenie późnego ACK. Produkcyjny workflow Move nie przyjmuje i nie przekazuje tych pól. Sprawdzenie aktywacji przed wysłaniem nie zastępuje kontroli po await.

**Skutek / ryzyko.** Ryzyko publikacji/inwalidacji ze starej sesji lub nieaktualnego feedbacku. Nie potwierdzono, czy dodatkowe zabezpieczenia klienta API całkowicie neutralizują ten scenariusz.

**Scenariusz reprodukcji.** W sesji A rozpocznij zapis, przełącz do B, zwróć ACK A. Rejestruj scope requestu, zasoby, feedback i historię B. Nie traktować samego testu helpera jako testu tej integracji.

**Plan naprawy V2.** Przenieś istniejący mechanizm scope/generation z inspektora do wspólnej komendy. Kontroluj tę samą tożsamość po każdym await i przed publikacją, feedbackiem oraz wpisem historii.

**Kryterium odbioru.** Test produkcyjnego hooka z dwiema sesjami: zero publikacji A do B, zero zmian historii B, poprawna możliwość wznowienia obserwacji w A.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f07"></a>
## F07 — Błąd Move inny niż 409 nie ma lokalnej obsługi w łańcuchu UI

**Plan v2:** PR03, PR06; **testy:** T18, T65.

**Priorytet P2; klasa L; status: nie wykonano retestu produkcji.**

**Źródła:** [S08: `objectMoveConflictWorkflow.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts); [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx); [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx); [S11: `MoveObjectGizmo.test.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.test.tsx).

**Stan odczytany w V1.** Workflow ponownie rzuca błędy inne niż revision conflict. endAxisDrag jest wywoływany przez void bez catch w sprawdzonym łańcuchu. Test repozytorium świadomie oczekuje odrzuconej Promise helpera, ale nie bada komunikatu użytkownika.

**Skutek / ryzyko.** Po błędzie sieci lub 500 użytkownik nie dostaje w tym panelu porównywalnego do 409 mechanizmu naprawy. Istnienie globalnego loggera nie jest recoverable UI.

**Scenariusz reprodukcji.** Wymuś 500 lub zerwanie połączenia przy pointerup. R03 potwierdza propagację odrzucenia; przeglądarkowy unhandledrejection wymaga testu integracyjnego.

**Plan naprawy V2.** Zwracaj typowany wynik success/conflict/rejected/unknown-outcome. Zachowaj szkic i przedstaw Retry/Reconcile/Discard. Po utracie ACK nie powtarzaj mutacji bez identyfikatora intencji.

**Kryterium odbioru.** Brak unhandledrejection w E2E, zachowane wartości i jasny status, brak podwójnego zapisu przy nieznanym wyniku requestu.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f08"></a>
## F08 — Rebase oznacza zmianę rewizji, nie scalanie zmian

**Plan v2:** PR07; **testy:** T03, T13.

**Priorytet P2; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts); [S08: `objectMoveConflictWorkflow.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts); [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx).

**Stan odczytany w V1.** Oba helpery rebase zachowują payload i podmieniają wyłącznie baseRevision. Formularz geometrii wysyła pełny deskryptor, a ruch przechowuje absolutną translację.

**Skutek / ryzyko.** Po równoległej edycji możliwe jest nadpisanie cudzej zmiany po świadomym Retry. Nie jest to automatyczny konflikt-free merge i UI nie powinno tak go przedstawiać.

**Scenariusz reprodukcji.** Edytor A zmienia width, B zmienia height; A dostaje 409 i rebase. Osobno: A przesuwa o delta, B zmienia pozycję; sprawdź, czy Retry utrzymuje absolutny cel czy intencję względną.

**Plan naprawy V2.** Three-way merge na grupach semantycznych z D04; promień/średnica to jedna wielkość, quaternion jeden atom. Zmiana rodzaju/usunięcie: jawny konflikt. Delta zachowuje capture baseline; reapply-on-remote wymaga wyboru.

**Kryterium odbioru.** Testy three-way merge dla rozłącznych i kolidujących zmian; po rebase użytkownik widzi wartości mine/theirs/result.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f09"></a>
## F09 — Puste pole współrzędnej jest interpretowane jako zero

**Plan v2:** PR04; **testy:** T08, T09, T56.

**Priorytet P2; klasa L; status: nie wykonano retestu produkcji.**

**Źródła:** [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts).

**Stan odczytany w V1.** Konwersja przez Number(value) akceptuje pusty tekst i same spacje jako 0. Wymiary wymagające wartości dodatniej są później odrzucane, ale translacja i niektóre offsety mogą przejść.

**Skutek / ryzyko.** Wyczyszczenie pola podczas edycji może stać się rzeczywistym przemieszczeniem do zera. To różne intencje użytkownika.

**Scenariusz reprodukcji.** Usuń zawartość Translation X i spróbuj Apply; sprawdź payload. R04 odtwarza semantykę konwersji JavaScript.

**Plan naprawy V2.** Rozdziel rawText, parsedValue i parseStatus. trim()==="" oznacza empty, nie finite zero. Dodaj parser jednostek z jawnym wymiarem i bez eval.

**Kryterium odbioru.** Puste/whitespace/NaN/Infinity blokują zapis; jawne 0 przechodzi. Testy 10 nm, 0.01 um, 1e-8 m i niezależności jednostki widoku od danych SI.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f10"></a>
## F10 — Rotate i Scale są świadomie wyłączone

**Plan v2:** PR13, PR14, PR15; **testy:** T14, T64.

**Priorytet P1; klasa G; status: nie wykonano retestu produkcji.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts); [S07: `objectTranslationMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectTranslationMutation.ts); [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx); [S27: `scene.rs`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-authoring/src/scene.rs); [S28: `adapters.rs`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-authoring/src/adapters.rs); [S29: `scene_document.py`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/packages/fullmag-py/src/fullmag/runtime/scene_document.py); [S30: `geometry.rs`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-authoring/src/geometry.rs).

**Stan odczytany w V1.** Pola Rotation i Scale oraz przyciski E/R mają disabled. Serializer transformu wysyła wyłącznie translation. Tooltip odwołuje się do ograniczenia kanonicznego kontraktu nowszego niż ProblemIR 0.3.

**Skutek / ryzyko.** Workflow wymagany przez użytkownika nie jest kompletny. Obecność trzech pól lub ikon nie oznacza obsługi transformacji ani zgodności wizualizacji z mesherem.

**Scenariusz reprodukcji.** Zaznacz prymityw i sprawdź inspektor oraz ribbon. Skala importu pliku i transform tekstury magnetyzacji nie są dowodem obsługi skali obiektu.

**Plan naprawy V2.** Reużyć istniejące pola; wprowadzić wersjonowaną semantykę pivotu i migrację bez cichej zmiany geometrii. Domknąć Python→ProblemIR→evaluatory→realizacje. Włączać Rotate/Scale osobno po dowodach dla lane/device/precision/geometry.

**Kryterium odbioru.** Rotate/Scale round-trip UI→scene→export→reload→FEM/FDM. Zgodność bounds i masek; brak pozornej transformacji samego Three.js.

**Korekta V2.** Transform3D już ma translation/rotation_quat/scale/pivot. Brak dotyczy domknięcia adapterów, semantyki i kwalifikacji, nie samego istnienia pól. W odczytanym bounds pivot nie uczestniczy w obliczeniu.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f11"></a>
## F11 — STL nie ma kompletnej ścieżki importu w sprawdzonym wejściu UI

**Plan v2:** PR16, PR17, PR18; **testy:** T27, T32, T59.

**Priorytet P1; klasa G; status: nie wykonano retestu produkcji.**

**Źródła:** [S12: `importFormats.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/start/model/importFormats.ts); [S13: `assets.rs`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-api/src/assets.rs); [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx); [S18: `ObjectMeshPolicyPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx).

**Stan odczytany w V1.** Ekran startowy klasyfikuje .stl/.vtk/.msh jako znane, lecz unavailable. Ribbon Geometry nie zapewnia w sprawdzonej definicji kompletnego kreatora Import. Backend ma parser podsumowania STL; pole source polityki meshu jest ścieżką, nie pełnym kreatorem importu.

**Skutek / ryzyko.** Użytkownik nie przechodzi spójnie przez plik→jednostki→walidację→umieszczenie→obiekt→mesh. Nie oznacza to braku obsługi STL w całym Fullmagu.

**Scenariusz reprodukcji.** Wybierz STL na ekranie startowym; otrzymasz odmowę. Oddzielnie prześledź ewentualne inne uploady przed deklaracją globalnego braku importu. IMPORT_ACCEPT obejmuje też formaty niedostępne.

**Plan naprawy V2.** Jeden asset workflow z capability registry, jawne jednostki i hash, naprawa/kontrola powłoki, preview, atomic commit obiektu. Rozdziel import geometrii, import gotowego meshu i import projektu.

**Kryterium odbioru.** E2E ASCII/binary STL, jednostki nm/mm, niepoprawna powłoka, anulowanie, ponowny import. Picker proponuje formaty zgodne z aktywną operacją.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f12"></a>
## F12 — Nieobsługiwany typ geometrii trafia do mylącego formularza wymiarów

**Plan v2:** PR04, PR12; **testy:** T11, T63.

**Priorytet P2; klasa C; status: nie wykonano retestu produkcji.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts).

**Stan odczytany w V1.** Formularz ma dedykowane pola Cylinder/Sphere/ArchWaveguide i fallback Size XYZ. buildGeometryDraftPatch akceptuje tylko cztery znane typy; pozostałe zwracają Unsupported editable geometry kind.

**Skutek / ryzyko.** Obiekt importowany lub złożony może wyglądać jak edytowalny Box, choć zapis geometrii zostanie odrzucony. Wartości domyślne nie stanowią wymiarów rzeczywistego assetu.

**Scenariusz reprodukcji.** Podaj do inspektora scene-object z geometry_kind spoza dozwolonej czwórki. Porównaj widoczne pola z wynikiem serializeru.

**Plan naprawy V2.** Rejestr inspektorów po typie i capability. Imported: source, units, bbox, checks, placement; Boolean: operands i operation; unsupported: jednoznaczny read-only z rzeczywistą metryką.

**Kryterium odbioru.** Nieznany typ nie pokazuje aktywnych fikcyjnych wymiarów. Znany asset ma właściwy inspektor, a transform pozostaje osobną zdolnością.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f13"></a>
## F13 — Preview edycji i przesuwania nie reprezentuje całego obiektu

**Plan v2:** PR07, PR15, PR18; **testy:** T02, T23, T27.

**Priorytet P2; klasa G; status: nie wykonano retestu produkcji.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx).

**Stan odczytany w V1.** Overlay prymitywu publikowany jest dla draft-new, a dla committed jest czyszczony. Podgląd Move jest wireframe box opartym o bounds, także dla walca i innych kształtów.

**Skutek / ryzyko.** Użytkownik ocenia zmianę geometrii dopiero po zapisie albo widzi jedynie obwiednię. Nie wolno traktować tego jako wiernego preview STL/CSG.

**Scenariusz reprodukcji.** Zmień radius istniejącego walca bez Apply. Następnie przesuń go; sprawdź, czy preview odpowiada jego powierzchni czy tylko bbox.

**Plan naprawy V2.** Wspólny overlay szkicu dla tworzenia i edycji; renderuj transient transform istniejącego proxy. Bounding-box/LOD fallback oznaczaj jawnie, nie jako dokładny kształt.

**Kryterium odbioru.** Preview reaguje bez mutacji serwera; Revert/Escape odtwarza committed. UI oznacza approximate preview i pokazuje dokładną powierzchnię po jej uzyskaniu.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f14"></a>
## F14 — Zestaw narzędzi nie spełnia kontraktu precyzyjnego modelera

**Plan v2:** PR15; **testy:** T23, T24.

**Priorytet P2; klasa G; status: nie wykonano retestu produkcji.**

**Źródła:** [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx); [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx); [S14: `ribbonCommands.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonCommands.ts); [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx).

**Stan odczytany w V1.** Sprawdzony Move działa na pojedynczym obiekcie magnetycznym i osiach XYZ. Snap jest disabled. Brak w tym łańcuchu sterowania pivotem, układem Local/World, uchwytów płaszczyzn i transformacji wieloselekcji.

**Skutek / ryzyko.** Trudno zbudować układ wielu obiektów, ustawić szczelinę, wyrównać powierzchnie lub obracać wokół wybranego punktu. Nie jest to problem samych ikon.

**Scenariusz reprodukcji.** Próba ustawienia dolnej powierzchni obiektu na Z=0, zachowania odstępu 20 nm i ruchu dwóch obiektów razem. Sprawdź, które kroki można wykonać bez zewnętrznego skryptu.

**Plan naprawy V2.** Wspólny ToolController: selection, constraints, coordinate frame, pivot, snap, numeric delta/absolute, transform intent i preview. Capability rozstrzyga dostępność dla roli/typu.

**Kryterium odbioru.** Wszystkie operacje dostępne również klawiaturą/liczbowo; multi-edit atomowy. Blokada Camera podczas gestu i jawny powód nieaktywnego narzędzia.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f15"></a>
## F15 — Drag korzysta z punktu trafienia zamiast jawnej geometrii przeciągania

**Plan v2:** PR03, PR15; **testy:** T21, T22.

**Priorytet P2; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx); [S11: `MoveObjectGizmo.test.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.test.tsx).

**Stan odczytany w V1.** eventPoint czyta event.point, a ruch bierze różnicę jego jednej współrzędnej. Nie ma wyznaczenia płaszczyzny drag/ray-axis. R3F capture nie zastępuje hit-testu w taki sposób jak DOM.

**Skutek / ryzyko.** Ryzyko niestabilnego lub zatrzymującego się gestu po opuszczeniu wąskiego uchwytu, przy zmianie trafionego obiektu i osi prawie równoległej do kamery. Nie zmierzono tego w WebGL.

**Scenariusz reprodukcji.** W prawdziwym WebGL przeciągaj poza uchwyt w ortografii i perspektywie, przez puste tło i inny obiekt; sprawdź monotoniczność delta.

**Plan naprawy V2.** Użyć adaptera TransformControls lub własnej projekcji ray-plane z obsługą degeneracji. Nie używać braku point jako współrzędnej [0,0,0]. Rozmiar uchwytu w CSS px, nie wyłącznie world bbox.

**Kryterium odbioru.** Browser matrix kamer/kątów/DPI; drag ciągły, bez skoków, wygodne hit areas i stabilny rozmiar przy zoom. Test mock pointerów nie wystarcza.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f16"></a>
## F16 — Kliknięcie uchwytu bez ruchu wysyła mutację

**Plan v2:** PR03, PR04; **testy:** T19, T56.

**Priorytet P2; klasa L; status: nie wykonano retestu produkcji.**

**Źródła:** [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx).

**Stan odczytany w V1.** end zawsze wywołuje onCommit po begin, nawet jeśli translation==origin. Nie ma progu ruchu ani porównania wartości.

**Skutek / ryzyko.** Niepotrzebny request, potencjalne zwiększenie rewizji i unieważnienie meshu. To, czy backend eliminuje no-op, nie zostało zbadane; frontend go wysyła.

**Scenariusz reprodukcji.** Pointerdown/pointerup w tej samej pozycji. R02 pokazuje jeden commit z niezmienioną translacją.

**Plan naprawy V2.** Próg rozpoczęcia gestu w pikselach i semantyczny no-op check w jednostkach SI. Nie używać stałego tolerancji 1e-6 m w skali nanometrowej.

**Kryterium odbioru.** Klik bez ruchu, cancel oraz ruch powrotny do punktu startowego nie mutują sceny i nie tworzą Undo; sensowny ruch poniżej 1 nm nie jest gubiony.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f17"></a>
## F17 — Walidacja miesza brak danych z brakiem problemów

**Plan v2:** PR04; **testy:** T12.

**Priorytet P2; klasa C; status: nie wykonano retestu produkcji.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts).

**Stan odczytany w V1.** Przy pustej tablicy wiadomości panel wyświetla Backend validation: no object issues, niezależnie od statusu loading/error. Agregator przycina listę do pięciu ogólnych tekstów.

**Skutek / ryzyko.** Użytkownik może dostać fałszywie uspokajający opis, a brakujące problemy nie mają licznika ani ścieżki pola/severity. Sam widoczny badge statusu nie naprawia sprzecznego komunikatu.

**Scenariusz reprodukcji.** Otwórz obiekt przy niedostępnej walidacji i przy sześciu problemach. Sprawdź status, tekst oraz możliwość odnalezienia wszystkich problemów.

**Plan naprawy V2.** Typowana walidacja z revision, targetId, fieldPath, severity, code i total. Stany unknown/loading/stale/error/valid/invalid. Skrót do pełnego Diagnostics.

**Kryterium odbioru.** No issues tylko dla aktualnego successful response z zerem problemów. 5 z 12 oznaczone z przejściem do pełnej listy. Błąd requestu nie staje się valid.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f18"></a>
## F18 — Fallback bounds walca ignoruje jego wysokość

**Plan v2:** PR04; **testy:** T14.

**Priorytet P2; klasa L; status: nie wykonano retestu produkcji.**

**Źródła:** [S22: `viewport3dPrimitiveModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/viewport3dPrimitiveModel.ts).

**Stan odczytany w V1.** Gdy brak bounds_min/max i size/dimensions, boundsFromGeometry bierze radiusSize(radius), czyli [2r,2r,2r]. height nie uczestniczy w tej gałęzi. Przy braku danych fallback to [1,1,1].

**Skutek / ryzyko.** Warunkowo niepoprawny framing, skala gizma i ocena gabarytu; dla cienkiego walca błąd osi Z może być duży. Poprawne autorytatywne bounds omijają tę ścieżkę.

**Scenariusz reprodukcji.** Cylinder r=50 nm, h=10 nm bez bounds i size. R07 daje [100,100,100] nm zamiast [100,100,10] nm.

**Plan naprawy V2.** Bounds obliczane przez typowany descriptor i jego transform. Dla unknown brak fikcyjnego metrowego obiektu: pending/unavailable geometry proxy.

**Kryterium odbioru.** Testy Box/Cylinder/Sphere/Arch/imported: bbox zgodny z geometrią i orientacją. Brak bounds nie powoduje nagłego oddalenia kamery o dziewięć rzędów wielkości.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f19"></a>
## F19 — Freshness meshu uznaje niespójne rewizje za current

**Plan v2:** PR08, PR10; **testy:** T42, T68.

**Priorytet P2; klasa L; status: nie wykonano retestu produkcji.**

**Źródła:** [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts).

**Stan odczytany w V1.** Kod oznacza stale tylko dla source_scene_revision < sceneRevision; każda inna para liczb daje current. Nie sprawdza w tej ekspresji gotowości zasobów ani równoważności geometrii/polityki.

**Skutek / ryzyko.** Podczas asynchronicznego odświeżania para scene=10,source=11 może zostać opisana jako aktualna. Jest to błąd predykatu, nie dowód niepoprawnych elementów siatki.

**Scenariusz reprodukcji.** R06 odtwarza tę parę liczb. W UI opóźnij refetch sceny względem manifestu i zobacz badge.

**Plan naprawy V2.** Jeden resolver ArtifactAssessment i oddzielny ResourceLoadState. Przyszła source revision jest inconsistent; brak dowodu unknown. Przejście na serwerowe digesty; legacy resolver konserwatywny i jawnie ograniczony.

**Kryterium odbioru.** Current wymaga zgodnego, gotowego zestawu dowodów. Future/mixed-generation daje inconsistent, brak danych unknown, nie zielony status.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f20"></a>
## F20 — Viewport i inspektor stosują różne reguły stale meshu

**Plan v2:** PR08, PR09, PR10; **testy:** T42, T68.

**Priorytet P2; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts); [S22: `viewport3dPrimitiveModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/viewport3dPrimitiveModel.ts).

**Stan odczytany w V1.** Inspektor porównuje rewizje. objectMeshState viewportu opiera się na obecności obiektu i tagach mesh:dirty/building/failed, a jawne porównanie rewizji wykonuje dla szczególnego CSG preview.

**Skutek / ryzyko.** Ryzyko rozbieżnych statusów przy opóźnionych tagach lub brakujących danych. Nie wykazano, że backend zawsze publikuje niespójny zestaw; potrzebny test kontraktu.

**Scenariusz reprodukcji.** Podaj manifest starej sceny i zwykły Box bez tagów dirty; porównaj wyniki obu resolverów. Potem sprawdź realny geometry edit→refetch.

**Plan naprawy V2.** Jeden centralny resolver ArtifactCompatibility używany przez drzewo, inspektor, viewport i Run gating. Stan obiektu/meshu ma wynikać z tego samego zestawu rewizji/digestów.

**Kryterium odbioru.** Brak jednoczesnego current i stale dla tej samej tożsamości. Stary mesh widoczny opcjonalnie, ale zawsze podpisany.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f21"></a>
## F21 — Selekcja najgorszego elementu nie niesie tożsamości meshu

**Plan v2:** PR10, PR19; **testy:** T43, T44.

**Priorytet P2; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts); [S23: `FdmGridInspectorPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/fdm-grid/FdmGridInspectorPanel.tsx).

**Stan odczytany w V1.** selectWorstElement zapisuje elementIndex, centroid i metric, ale nie meshRevision/buildId/generation. Dla porównania inspektor FDM jawnie rozróżnia aktualną komórkę i stary snapshot przez fingerprint/membership.

**Skutek / ryzyko.** Po rebuild indeks może wskazywać inny element. Ryzyko błędnego highlight/refine, jeśli inne warstwy nie odrzucą starej selekcji.

**Scenariusz reprodukcji.** Wybierz worst element, przebuduj siatkę, zachowaj selekcję i wykonaj highlight/refine. Sprawdź, czy działa na starej czy nowej topologii.

**Plan naprawy V2.** ElementRef={artifactId,generationId,meshRevision,index}; przy nowym meshu selekcja wygasa lub pozostaje wyraźnie read-only snapshotem. Nie mapować po samym indeksie.

**Kryterium odbioru.** Rebuild nie przekierowuje refinementu na inny element. Wzorzec zabezpieczenia FDM wykorzystać także w FEM.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f22"></a>
## F22 — Reconciliation utraconego ACK szuka tylko ośmiu ostatnich komend

**Plan v2:** PR11; **testy:** T38, T39.

**Priorytet P2; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S20: `geometryLifecycleCommandContributions.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts).

**Stan odczytany w V1.** reconcileMeshSubmission sortuje kandydatów malejąco po seq i ogranicza ich przez slice(0,8), po czym dopasowuje client_intent_id.

**Skutek / ryzyko.** Jeżeli poszukiwany intent wypadnie poza okno, UI może pozostać publication-unconfirmed mimo istnienia komendy. To bezpieczniejsze niż duplikowanie budowy, ale utrudnia odzyskanie obserwacji.

**Scenariusz reprodukcji.** Zasymuluj utracony ACK oraz co najmniej osiem nowszych komend tego rodzaju w kolejce. Sprawdź wynik reconciliation.

**Plan naprawy V2.** Backendowy lookup po client_intent_id albo stronicowane wyszukiwanie z jawnym ograniczeniem i diagnostyką. Zachować zasadę: reconnect nigdy sam nie wysyła ponownie build.

**Kryterium odbioru.** Intent odnaleziony niezależnie od pozycji w historii albo jednoznaczny nieznany wynik z odnośnikiem do jobu; nigdy cicha druga budowa.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f23"></a>
## F23 — Zakładka history polityki obiektu jest w praktyce widokiem JSON

**Plan v2:** PR12; **testy:** T25, T26.

**Priorytet P2; klasa G; status: nie wykonano retestu produkcji.**

**Źródła:** [S18: `ObjectMeshPolicyPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx); [S16: `MeshDetailsPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/MeshDetailsPanel.tsx); [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts).

**Stan odczytany w V1.** ObjectMeshPolicyPanel renderuje w history JSON report/quality/size-field. Osobny globalny MeshDetailsPanel posiada rzeczywistą sekcję historii i restore-to-draft.

**Skutek / ryzyko.** Istniejące możliwości są rozproszone i etykieta lokalnej zakładki obiecuje inną treść. Nie należy pisać, że historii w projekcie w ogóle nie ma.

**Scenariusz reprodukcji.** Przejdź Object Mesh→History i Mesh Builds; porównaj zawartość i możliwość dotarcia do budowy danego obiektu.

**Plan naprawy V2.** Wspólny history view filtrowany po obiekcie/target, z linkiem do globalnego jobu. Surowy JSON przenieść do Diagnostics/Advanced.

**Kryterium odbioru.** Z inspektora obiektu można zobaczyć job, receptę, źródłową scenę, wynik, błąd i restore-to-draft bez szukania innej sekcji.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f24"></a>
## F24 — Ribbon eksponuje szeroki katalog trwale nieaktywnych funkcji

**Plan v2:** PR07, PR12, PR15; **testy:** T50, T63.

**Priorytet P2; klasa G; status: nie wykonano retestu produkcji.**

**Źródła:** [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx).

**Stan odczytany w V1.** Geometry zawiera liczne disabled prymitywy, Union/Subtract/Intersect oraz Camera/Manipulate/Snap. Definitions ma nieaktywne Parameters/Functions/Coordinates. Nie wszystkie nieaktywne akcje mają tak precyzyjny powód jak Rotate/Scale.

**Skutek / ryzyko.** Widok przypomina kompletny modeler bardziej, niż pozwala rzeczywista funkcjonalność. Trudno odróżnić brak implementacji od nieprawidłowego zaznaczenia.

**Scenariusz reprodukcji.** Przejrzyj toolbar w pustej i wypełnionej scenie. Skategoryzuj każdą nieaktywną akcję: unsupported, unavailable-context, busy, permission, invalid draft.

**Plan naprawy V2.** Dwupoziomowy Create: wspierane typy na wierzchu, pozostałe w jawnej sekcji planowanych funkcji. Akcje budować z tego samego registry/capability co komendy i inspektor.

**Kryterium odbioru.** Każdy disabled ma czytelną przyczynę; brak martwego aktywnego menu. Odrębnie testować ikony skrótów i rzeczywiste bindings klawiatury.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f25"></a>
## F25 — Rozmiar modułów zwiększa ryzyko rozbieżności polityk UI

**Plan v2:** PR01, PR07, PR12; **testy:** T49, T55.

**Priorytet P2; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx); [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts); [S18: `ObjectMeshPolicyPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx); [S24: `package.json`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/package.json).

**Stan odczytany w V1.** Metadata drzewa wskazuje ok. 139 kB ribbonContributions i ok. 117 kB Viewport3DModule. Odczytane panele łączą formularze, transakcje, zasoby, historię, diagnostykę i renderowanie. To wskaźnik długu, nie pomiar wydajności.

**Skutek / ryzyko.** Łatwo naprawić jedną drogę Apply lub jeden badge bez zmiany pozostałych. Sam duży plik nie dowodzi spadku FPS ani wycieku pamięci.

**Scenariusz reprodukcji.** Prześledź jedną mutację translacji i jedną budowę przez wszystkie wejścia. Zmierz render/resource counts istniejącymi skryptami dopiero w uruchomionej aplikacji.

**Plan naprawy V2.** Wydziel domain services i selektory najpierw, komponenty widoku później. Nie tworzyć drugiego store sceny ani drugiej historii. Dodać dependency rules i testy kontraktów.

**Kryterium odbioru.** Inspektor/ribbon/gizmo odwołują się do tego samego command contract; mierzalne brak regresji CPU/GPU/network, a nie tylko mniejsza liczba linii.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f26"></a>
## F26 — Tożsamość szkicu jest zbyt słaba na zmianę typu lub sesji

**Plan v2:** PR02, PR07; **testy:** T06, T07.

**Priorytet P2; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts); [S04: `InspectorModule.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorModule.tsx).

**Stan odczytany w V1.** draftKey zawiera mode i objectId, a nowe prymitywy otrzymują objectId=draft. Nie zawiera primitive kind, session scope ani unikalnego draftId. InspectorModule nie nadaje Panel jawnego key zależnego od sesji.

**Skutek / ryzyko.** Ryzyko odziedziczenia danych po innym prymitywie lub obiekcie o takim samym ID w innej sesji, o ile rodzic nie wymusi remountu. Nie stwierdzono pełnego zachowania wszystkich tras.

**Scenariusz reprodukcji.** Zmień Box→Cylinder→Sphere bez opuszczania edytora; powtórz przełączenie sesji z identycznym objectId i aktywnym formularzem. Testować wraz z dirty-selection guard.

**Plan naprawy V2.** DraftIdentity={sessionId,epoch,targetId,draftId}; typ prymitywu jest częścią intencji tworzenia. Zmiana targetu rozwiązuje dirty state, nie jest ukrytym resetem.

**Kryterium odbioru.** Brak przecieku wartości/konfliktów między szkicami; jawne Apply/Discard/Cancel przy zmianie selekcji.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f27"></a>
## F27 — Historia może zniknąć bez komunikatu po poprawnej mutacji

**Plan v2:** PR06, PR12; **testy:** T26, T65.

**Priorytet P2; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S21: `authoringHistoryMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts).

**Stan odczytany w V1.** captureAuthoringHistoryScene może zwrócić null; recordAuthoringMutationHistory wtedy pomija zapis. Wyjątki history.record są przechwytywane bez sygnalizacji użytkownikowi. Autorzy świadomie traktują historię jako observability layer.

**Skutek / ryzyko.** Model może być poprawnie zapisany, ale operacja nieodwracalna z UI. To nie powód, by cofać udany ACK; potrzebna jest informacja o zdegradowanej historii.

**Scenariusz reprodukcji.** Zasymuluj brak before snapshot i błąd history.record przy udanym commit. Sprawdź, czy UI ujawnia brak Undo.

**Plan naprawy V2.** R1: best-effort lokalne Undo z widocznym history-degraded, bez drugiego requestu po awarii zapisu historii. Trwały receipt mutacji służy reconciliation, nie jest automatycznie trwałą historią Undo.

**Kryterium odbioru.** Sukces zapisu nie znika, ale użytkownik widzi, że Undo tej operacji jest niedostępne; telemetria identyfikuje commandId i przyczynę.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.

<a id="f28"></a>
## F28 — Pierwsza budowa wymaga testu pustych zasobów w dialogu potwierdzenia

**Plan v2:** PR08, PR11; **testy:** T33.

**Priorytet P2; klasa R; status: nie wykonano retestu produkcji.**

**Źródła:** [S19: `MeshBuildDialog.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/overlay/MeshBuildDialog.tsx); [S20: `geometryLifecycleCommandContributions.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts); [S24: `package.json`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/package.json).

**Stan odczytany w V1.** computedSnapshot wymaga ready dla summary, latest successful oraz manifest. Kod może działać poprawnie, jeśli backend publikuje ready z pustym payloadem przed pierwszą budową; w audycie nie uruchomiono tego kontraktu.

**Skutek / ryzyko.** Ryzyko zablokowania pierwszej budowy, gdy któryś zasób poprawnie odpowiada not-built/404. To hipoteza do sprawdzenia, a nie potwierdzony deadlock.

**Scenariusz reprodukcji.** Nowa sesja FEM, jeden prymityw, brak wcześniejszego meshu i sukcesu; uruchom Build Mesh i zbadaj stany zasobów w dialogu. Istnieje skrypt verify:mesh-build-new-object, ale nie był tu uruchamiany.

**Plan naprawy V2.** Zdefiniować not-built jako legalny snapshot bez poprzedniego artefaktu. Odróżnić brak meshu od awarii jego odczytu. Nie obchodzić kontroli scene/policy readiness.

**Kryterium odbioru.** E2E pierwszej budowy z pustej sesji i po importowanym STL, obok rebuild istniejącego meshu oraz błędu odczytu manifestu.

Powiązanie z dostawą i testami: `backlog.json`, `tests.json`. Historyczny scenariusz nie stanowi oczekiwanego zachowania nowego UI.
