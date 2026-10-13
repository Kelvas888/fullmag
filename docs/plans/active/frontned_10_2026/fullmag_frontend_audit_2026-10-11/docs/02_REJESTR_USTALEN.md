# Szczegółowy rejestr ustaleń

Każda pozycja ma zakres dowodu, skutki, scenariusz odtworzenia, kierunek naprawy i kryterium odbioru. C/L/R/G zdefiniowano w [metodyce](01_ZRODLA_I_METODYKA.md).

| ID | Priorytet | Dowód | Ustalenie |
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

**Priorytet: P1. Klasa dowodu: L.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts); [S03: `InspectorEditSession.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorEditSession.tsx); [S21: `authoringHistoryMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts).

**Stan w kodzie.** Klucz szkicu to mode:objectId. applyGeometryPatch i applyTransformPatch używają draft.baseRevision, a po ACK publikują scenę/feedback bez aktualizacji draftState. Wspólny InspectorEditSession w trybie mutation-owned nie resetuje formularza. Snapshot historii nie zastępuje rewizji użytej w payloadzie.

**Skutek.** Po pierwszym zapisie drugi zapis z tego samego zamontowanego panelu może dostać 409 mimo braku innego edytora. Pola mogą pokazywać dane lokalne oderwane od nowego bazowego snapshotu.

**Scenariusz weryfikacji.** Otwórz obiekt w rewizji 10, zmień wymiar, Apply → ACK 11; bez zmiany selekcji zmień wymiar ponownie. Sprawdź base_revision drugiego requestu. R05 odtwarza sam wybór starego draftState, nie montaż React.

**Naprawa.** Wprowadź ACK reducer: przy zachowaniu tożsamości operacji zaktualizuj baseline i baseRevision z committed_scene. Zachowaj wyłącznie edycje wykonane po wysłaniu requestu. Nie resetuj szkicu po dowolnym refetchu.

**Kryterium odbioru.** Test DOM: trzy kolejne Apply wysyłają kolejno 10,11,12; po każdej odpowiedzi dirty=false. Osobny test zachowania nowszej, jeszcze niewysłanej edycji podczas ACK.

<a id="f02"></a>

## F02 — Udany Retry i Revert nie kończą stanu konfliktu

**Priorytet: P1. Klasa dowodu: C.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S03: `InspectorEditSession.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorEditSession.tsx).

**Stan w kodzie.** Rebase ustawia revisionConflictPhase=rebased. Ścieżki zapisu istniejącej geometrii i transformacji po sukcesie nie zerują tej fazy. revertDraft aktualizuje draftState i feedback, ale również nie zeruje konfliktu. Wspólne Apply blokuje każdy niepusty revisionConflictPhase.

**Skutek.** Można otrzymać komunikat sukcesu i jednocześnie pozostać z zablokowanym wspólnym Apply. Revert nie przywraca przewidywalnego stanu gotowości.

**Scenariusz weryfikacji.** Wywołaj 409, Refetch, Rebase, Retry; po ACK sprawdź wspólną stopkę. Powtórz, zastępując Retry przyciskiem Revert.

**Naprawa.** Zastąp niezależne flagi jednoznaczną maszyną stanów. ACK bieżącej operacji oraz świadome porzucenie szkicu muszą wyzerować konflikt, jego bazę, operation i flagi odświeżenia.

**Kryterium odbioru.** Testy DOM dla create/geometry/transform: conflict→refetched→rebased→success→clean oraz conflict→revert→clean; brak utraty niespokrewnionych szkiców.

<a id="f03"></a>

## F03 — Dwa poziomy Apply mają różne reguły i nie tworzą atomowej edycji obiektu

**Priorytet: P2. Klasa dowodu: C.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S03: `InspectorEditSession.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorEditSession.tsx).

**Stan w kodzie.** Wspólne Apply blokuje jednoczesną zmianę wymiarów i translacji, prosząc o dwa wpisy historii. Lokalne Apply Geometry/Apply Transform mają mniej restrykcyjne disabled i nie używają wspólnego applyBlockReason.

**Skutek.** Ten sam formularz ma kilka definicji gotowości. Dwa requesty pozwalają na stan pośredni, w którym wymiar zapisano, a pozycja pozostała stara. To szczególnie nieczytelne przed Build Mesh.

**Scenariusz weryfikacji.** Zmień size i translation. Porównaj stopkę inspektora z lokalnymi przyciskami; sprawdź historię oraz sytuację, gdy drugi request otrzyma 409.

**Naprawa.** Jeden właściciel transakcji edycji obiektu i jedna główna stopka. Atomowy batch zmian geometrii i transformu, jeśli backend go obsługuje; do tego czasu jawny sekwencyjny workflow z opisem częściowego sukcesu.

**Kryterium odbioru.** Identyczny command canExecute we wszystkich wejściach. Jeden zaakceptowany batch→jedna pozycja Undo. Błąd walidacji nie pozostawia częściowej zmiany.

<a id="f04"></a>

## F04 — Gest Move omija historię semantyczną używaną przez inspektor

**Priorytet: P1. Klasa dowodu: C.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S07: `objectTranslationMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectTranslationMutation.ts); [S08: `objectMoveConflictWorkflow.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts); [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx); [S21: `authoringHistoryMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts).

**Stan w kodzie.** Inspektor opakowuje translację w runAuthoringMutationWithHistory. Produkcyjny commitMove wywołuje commitObjectMoveWorkflow→commitObjectTranslation bez tego wrappera. Niskopoziomowa transakcja nie rejestruje historii.

**Skutek.** Znaczenie Undo zależy od tego, czy identyczny ruch wykonano myszą, czy wpisując liczby. Samo uruchomienie narzędzia przez CommandRegistry nie zapisuje późniejszego gestu.

**Scenariusz weryfikacji.** W czystej historii wykonaj Move przez gizmo, następnie Undo; porównaj z translacją przez inspektor. Reprodukcja integracyjna pozostaje do uruchomienia w aplikacji.

**Naprawa.** Wspólna komenda commitObjectEdit dla inspektora, gizma i skrótów. Historia należy do zaakceptowanej mutacji, nie do aktywacji narzędzia. Zapamiętuj before/after dla tej samej sesji i operacji.

**Kryterium odbioru.** Każdy ukończony gest zmieniający obiekt daje dokładnie jeden wpis; Escape i no-op nie dają wpisów. Undo/Redo działa jednakowo po obu drogach.

<a id="f05"></a>

## F05 — ACK poprzedniego gestu może wyczyścić podgląd następnego

**Priorytet: P1. Klasa dowodu: L.**

**Źródła:** [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx); [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx).

**Stan w kodzie.** createMoveGestureController.end zwalnia aktywny gest przed await onCommit. Można zacząć następny gest. Po ACK pierwszego end bezwarunkowo wywołuje onDraftChange(null), bez sprawdzenia numeru gestu.

**Skutek.** Nowy preview może zniknąć w trakcie przesuwania. Dodatkowo dwa gesty mogą korzystać z tego samego origin/baseRevision. R01 odtwarza bezpośrednio pierwszą część problemu.

**Scenariusz weryfikacji.** Opóźnij odpowiedź requestu A. Zakończ gest A, rozpocznij B i przesuń obiekt. Zwróć ACK A przed końcem B. Minimalny test jest w reproductions/reproduce.mjs.

**Naprawa.** Na pierwszy etap blokuj nowy gest do ACK/reconciliation. Docelowo numeruj gesty i operacje, a ACK niech modyfikuje wyłącznie szkic tej operacji. Nie kolejkować absolutnych transformów na nieaktualnej bazie.

**Kryterium odbioru.** Deferred-promise test: ACK A nie kasuje B; requesty mają poprawne rewizje. Testy odwrotnej kolejności odpowiedzi, zmiany obiektu i zamknięcia viewportu.

<a id="f06"></a>

## F06 — Viewport nie przekazuje ogrodzenia sesji do mutacji translacji

**Priorytet: P1. Klasa dowodu: R.**

**Źródła:** [S07: `objectTranslationMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectTranslationMutation.ts); [S08: `objectMoveConflictWorkflow.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts); [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx); [S11: `MoveObjectGizmo.test.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.test.tsx).

**Stan w kodzie.** commitObjectTranslation obsługuje sessionScopeKey i isCurrentSessionScope; jego test potwierdza odrzucenie późnego ACK. Produkcyjny workflow Move nie przyjmuje i nie przekazuje tych pól. Sprawdzenie aktywacji przed wysłaniem nie zastępuje kontroli po await.

**Skutek.** Ryzyko publikacji/inwalidacji ze starej sesji lub nieaktualnego feedbacku. Nie potwierdzono, czy dodatkowe zabezpieczenia klienta API całkowicie neutralizują ten scenariusz.

**Scenariusz weryfikacji.** W sesji A rozpocznij zapis, przełącz do B, zwróć ACK A. Rejestruj scope requestu, zasoby, feedback i historię B. Nie traktować samego testu helpera jako testu tej integracji.

**Naprawa.** Przenieś istniejący mechanizm scope/generation z inspektora do wspólnej komendy. Kontroluj tę samą tożsamość po każdym await i przed publikacją, feedbackiem oraz wpisem historii.

**Kryterium odbioru.** Test produkcyjnego hooka z dwiema sesjami: zero publikacji A do B, zero zmian historii B, poprawna możliwość wznowienia obserwacji w A.

<a id="f07"></a>

## F07 — Błąd Move inny niż 409 nie ma lokalnej obsługi w łańcuchu UI

**Priorytet: P2. Klasa dowodu: L.**

**Źródła:** [S08: `objectMoveConflictWorkflow.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts); [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx); [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx); [S11: `MoveObjectGizmo.test.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.test.tsx).

**Stan w kodzie.** Workflow ponownie rzuca błędy inne niż revision conflict. endAxisDrag jest wywoływany przez void bez catch w sprawdzonym łańcuchu. Test repozytorium świadomie oczekuje odrzuconej Promise helpera, ale nie bada komunikatu użytkownika.

**Skutek.** Po błędzie sieci lub 500 użytkownik nie dostaje w tym panelu porównywalnego do 409 mechanizmu naprawy. Istnienie globalnego loggera nie jest recoverable UI.

**Scenariusz weryfikacji.** Wymuś 500 lub zerwanie połączenia przy pointerup. R03 potwierdza propagację odrzucenia; przeglądarkowy unhandledrejection wymaga testu integracyjnego.

**Naprawa.** Zwracaj typowany wynik success/conflict/rejected/unknown-outcome. Zachowaj szkic i przedstaw Retry/Reconcile/Discard. Po utracie ACK nie powtarzaj mutacji bez identyfikatora intencji.

**Kryterium odbioru.** Brak unhandledrejection w E2E, zachowane wartości i jasny status, brak podwójnego zapisu przy nieznanym wyniku requestu.

<a id="f08"></a>

## F08 — Rebase oznacza zmianę rewizji, nie scalanie zmian

**Priorytet: P2. Klasa dowodu: R.**

**Źródła:** [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts); [S08: `objectMoveConflictWorkflow.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts); [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx).

**Stan w kodzie.** Oba helpery rebase zachowują payload i podmieniają wyłącznie baseRevision. Formularz geometrii wysyła pełny deskryptor, a ruch przechowuje absolutną translację.

**Skutek.** Po równoległej edycji możliwe jest nadpisanie cudzej zmiany po świadomym Retry. Nie jest to automatyczny konflikt-free merge i UI nie powinno tak go przedstawiać.

**Scenariusz weryfikacji.** Edytor A zmienia width, B zmienia height; A dostaje 409 i rebase. Osobno: A przesuwa o delta, B zmienia pozycję; sprawdź, czy Retry utrzymuje absolutny cel czy intencję względną.

**Naprawa.** Przechowuj baseline, lokalny patch i latest. Scalaj tylko rozłączne ścieżki. Konflikt na tej samej ścieżce wymaga wyboru. Delta i absolute muszą być oddzielnymi intencjami.

**Kryterium odbioru.** Testy three-way merge dla rozłącznych i kolidujących zmian; po rebase użytkownik widzi wartości mine/theirs/result.

<a id="f09"></a>

## F09 — Puste pole współrzędnej jest interpretowane jako zero

**Priorytet: P2. Klasa dowodu: L.**

**Źródła:** [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts).

**Stan w kodzie.** Konwersja przez Number(value) akceptuje pusty tekst i same spacje jako 0. Wymiary wymagające wartości dodatniej są później odrzucane, ale translacja i niektóre offsety mogą przejść.

**Skutek.** Wyczyszczenie pola podczas edycji może stać się rzeczywistym przemieszczeniem do zera. To różne intencje użytkownika.

**Scenariusz weryfikacji.** Usuń zawartość Translation X i spróbuj Apply; sprawdź payload. R04 odtwarza semantykę konwersji JavaScript.

**Naprawa.** Rozdziel rawText, parsedValue i parseStatus. trim()==="" oznacza empty, nie finite zero. Dodaj parser jednostek z jawnym wymiarem i bez eval.

**Kryterium odbioru.** Puste/whitespace/NaN/Infinity blokują zapis; jawne 0 przechodzi. Testy 10 nm, 0.01 um, 1e-8 m i niezależności jednostki widoku od danych SI.

<a id="f10"></a>

## F10 — Rotate i Scale są świadomie wyłączone

**Priorytet: P1. Klasa dowodu: G.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts); [S07: `objectTranslationMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectTranslationMutation.ts); [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx).

**Stan w kodzie.** Pola Rotation i Scale oraz przyciski E/R mają disabled. Serializer transformu wysyła wyłącznie translation. Tooltip odwołuje się do ograniczenia kanonicznego kontraktu nowszego niż ProblemIR 0.3.

**Skutek.** Workflow wymagany przez użytkownika nie jest kompletny. Obecność trzech pól lub ikon nie oznacza obsługi transformacji ani zgodności wizualizacji z mesherem.

**Scenariusz weryfikacji.** Zaznacz prymityw i sprawdź inspektor oraz ribbon. Skala importu pliku i transform tekstury magnetyzacji nie są dowodem obsługi skali obiektu.

**Naprawa.** Najpierw ustalić/zweryfikować end-to-end kontrakt object TRS, world bounds, serializację i oba meshing lanes. Następnie włączyć kontrolki sterowane capability, nie sam CSS.

**Kryterium odbioru.** Rotate/Scale round-trip UI→scene→export→reload→FEM/FDM. Zgodność bounds i masek; brak pozornej transformacji samego Three.js.

<a id="f11"></a>

## F11 — STL nie ma kompletnej ścieżki importu w sprawdzonym wejściu UI

**Priorytet: P1. Klasa dowodu: G.**

**Źródła:** [S12: `importFormats.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/start/model/importFormats.ts); [S13: `assets.rs`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-api/src/assets.rs); [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx); [S18: `ObjectMeshPolicyPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx).

**Stan w kodzie.** Ekran startowy klasyfikuje .stl/.vtk/.msh jako znane, lecz unavailable. Ribbon Geometry nie zapewnia w sprawdzonej definicji kompletnego kreatora Import. Backend ma parser podsumowania STL; pole source polityki meshu jest ścieżką, nie pełnym kreatorem importu.

**Skutek.** Użytkownik nie przechodzi spójnie przez plik→jednostki→walidację→umieszczenie→obiekt→mesh. Nie oznacza to braku obsługi STL w całym Fullmagu.

**Scenariusz weryfikacji.** Wybierz STL na ekranie startowym; otrzymasz odmowę. Oddzielnie prześledź ewentualne inne uploady przed deklaracją globalnego braku importu. IMPORT_ACCEPT obejmuje też formaty niedostępne.

**Naprawa.** Jeden asset workflow z capability registry, jawne jednostki i hash, naprawa/kontrola powłoki, preview, atomic commit obiektu. Rozdziel import geometrii, import gotowego meshu i import projektu.

**Kryterium odbioru.** E2E ASCII/binary STL, jednostki nm/mm, niepoprawna powłoka, anulowanie, ponowny import. Picker proponuje formaty zgodne z aktywną operacją.

<a id="f12"></a>

## F12 — Nieobsługiwany typ geometrii trafia do mylącego formularza wymiarów

**Priorytet: P2. Klasa dowodu: C.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts).

**Stan w kodzie.** Formularz ma dedykowane pola Cylinder/Sphere/ArchWaveguide i fallback Size XYZ. buildGeometryDraftPatch akceptuje tylko cztery znane typy; pozostałe zwracają Unsupported editable geometry kind.

**Skutek.** Obiekt importowany lub złożony może wyglądać jak edytowalny Box, choć zapis geometrii zostanie odrzucony. Wartości domyślne nie stanowią wymiarów rzeczywistego assetu.

**Scenariusz weryfikacji.** Podaj do inspektora scene-object z geometry_kind spoza dozwolonej czwórki. Porównaj widoczne pola z wynikiem serializeru.

**Naprawa.** Rejestr inspektorów po typie i capability. Imported: source, units, bbox, checks, placement; Boolean: operands i operation; unsupported: jednoznaczny read-only z rzeczywistą metryką.

**Kryterium odbioru.** Nieznany typ nie pokazuje aktywnych fikcyjnych wymiarów. Znany asset ma właściwy inspektor, a transform pozostaje osobną zdolnością.

<a id="f13"></a>

## F13 — Preview edycji i przesuwania nie reprezentuje całego obiektu

**Priorytet: P2. Klasa dowodu: G.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx).

**Stan w kodzie.** Overlay prymitywu publikowany jest dla draft-new, a dla committed jest czyszczony. Podgląd Move jest wireframe box opartym o bounds, także dla walca i innych kształtów.

**Skutek.** Użytkownik ocenia zmianę geometrii dopiero po zapisie albo widzi jedynie obwiednię. Nie wolno traktować tego jako wiernego preview STL/CSG.

**Scenariusz weryfikacji.** Zmień radius istniejącego walca bez Apply. Następnie przesuń go; sprawdź, czy preview odpowiada jego powierzchni czy tylko bbox.

**Naprawa.** Wspólny overlay szkicu dla tworzenia i edycji; renderuj transient transform istniejącego proxy. Bounding-box/LOD fallback oznaczaj jawnie, nie jako dokładny kształt.

**Kryterium odbioru.** Preview reaguje bez mutacji serwera; Revert/Escape odtwarza committed. UI oznacza approximate preview i pokazuje dokładną powierzchnię po jej uzyskaniu.

<a id="f14"></a>

## F14 — Zestaw narzędzi nie spełnia kontraktu precyzyjnego modelera

**Priorytet: P2. Klasa dowodu: G.**

**Źródła:** [S09: `Viewport3DObjectMoveInteraction.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx); [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx); [S14: `ribbonCommands.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonCommands.ts); [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx).

**Stan w kodzie.** Sprawdzony Move działa na pojedynczym obiekcie magnetycznym i osiach XYZ. Snap jest disabled. Brak w tym łańcuchu sterowania pivotem, układem Local/World, uchwytów płaszczyzn i transformacji wieloselekcji.

**Skutek.** Trudno zbudować układ wielu obiektów, ustawić szczelinę, wyrównać powierzchnie lub obracać wokół wybranego punktu. Nie jest to problem samych ikon.

**Scenariusz weryfikacji.** Próba ustawienia dolnej powierzchni obiektu na Z=0, zachowania odstępu 20 nm i ruchu dwóch obiektów razem. Sprawdź, które kroki można wykonać bez zewnętrznego skryptu.

**Naprawa.** Wspólny ToolController: selection, constraints, coordinate frame, pivot, snap, numeric delta/absolute, transform intent i preview. Capability rozstrzyga dostępność dla roli/typu.

**Kryterium odbioru.** Wszystkie operacje dostępne również klawiaturą/liczbowo; multi-edit atomowy. Blokada Camera podczas gestu i jawny powód nieaktywnego narzędzia.

<a id="f15"></a>

## F15 — Drag korzysta z punktu trafienia zamiast jawnej geometrii przeciągania

**Priorytet: P2. Klasa dowodu: R.**

**Źródła:** [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx); [S11: `MoveObjectGizmo.test.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.test.tsx).

**Stan w kodzie.** eventPoint czyta event.point, a ruch bierze różnicę jego jednej współrzędnej. Nie ma wyznaczenia płaszczyzny drag/ray-axis. R3F capture nie zastępuje hit-testu w taki sposób jak DOM.

**Skutek.** Ryzyko niestabilnego lub zatrzymującego się gestu po opuszczeniu wąskiego uchwytu, przy zmianie trafionego obiektu i osi prawie równoległej do kamery. Nie zmierzono tego w WebGL.

**Scenariusz weryfikacji.** W prawdziwym WebGL przeciągaj poza uchwyt w ortografii i perspektywie, przez puste tło i inny obiekt; sprawdź monotoniczność delta.

**Naprawa.** Użyć adaptera TransformControls lub własnej projekcji ray-plane z obsługą degeneracji. Nie używać braku point jako współrzędnej [0,0,0]. Rozmiar uchwytu w CSS px, nie wyłącznie world bbox.

**Kryterium odbioru.** Browser matrix kamer/kątów/DPI; drag ciągły, bez skoków, wygodne hit areas i stabilny rozmiar przy zoom. Test mock pointerów nie wystarcza.

<a id="f16"></a>

## F16 — Kliknięcie uchwytu bez ruchu wysyła mutację

**Priorytet: P2. Klasa dowodu: L.**

**Źródła:** [S10: `MoveObjectGizmo.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx).

**Stan w kodzie.** end zawsze wywołuje onCommit po begin, nawet jeśli translation==origin. Nie ma progu ruchu ani porównania wartości.

**Skutek.** Niepotrzebny request, potencjalne zwiększenie rewizji i unieważnienie meshu. To, czy backend eliminuje no-op, nie zostało zbadane; frontend go wysyła.

**Scenariusz weryfikacji.** Pointerdown/pointerup w tej samej pozycji. R02 pokazuje jeden commit z niezmienioną translacją.

**Naprawa.** Próg rozpoczęcia gestu w pikselach i semantyczny no-op check w jednostkach SI. Nie używać stałego tolerancji 1e-6 m w skali nanometrowej.

**Kryterium odbioru.** Klik bez ruchu, cancel oraz ruch powrotny do punktu startowego nie mutują sceny i nie tworzą Undo; sensowny ruch poniżej 1 nm nie jest gubiony.

<a id="f17"></a>

## F17 — Walidacja miesza brak danych z brakiem problemów

**Priorytet: P2. Klasa dowodu: C.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts).

**Stan w kodzie.** Przy pustej tablicy wiadomości panel wyświetla Backend validation: no object issues, niezależnie od statusu loading/error. Agregator przycina listę do pięciu ogólnych tekstów.

**Skutek.** Użytkownik może dostać fałszywie uspokajający opis, a brakujące problemy nie mają licznika ani ścieżki pola/severity. Sam widoczny badge statusu nie naprawia sprzecznego komunikatu.

**Scenariusz weryfikacji.** Otwórz obiekt przy niedostępnej walidacji i przy sześciu problemach. Sprawdź status, tekst oraz możliwość odnalezienia wszystkich problemów.

**Naprawa.** Typowana walidacja z revision, targetId, fieldPath, severity, code i total. Stany unknown/loading/stale/error/valid/invalid. Skrót do pełnego Diagnostics.

**Kryterium odbioru.** No issues tylko dla aktualnego successful response z zerem problemów. 5 z 12 oznaczone z przejściem do pełnej listy. Błąd requestu nie staje się valid.

<a id="f18"></a>

## F18 — Fallback bounds walca ignoruje jego wysokość

**Priorytet: P2. Klasa dowodu: L.**

**Źródła:** [S22: `viewport3dPrimitiveModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/viewport3dPrimitiveModel.ts).

**Stan w kodzie.** Gdy brak bounds_min/max i size/dimensions, boundsFromGeometry bierze radiusSize(radius), czyli [2r,2r,2r]. height nie uczestniczy w tej gałęzi. Przy braku danych fallback to [1,1,1].

**Skutek.** Warunkowo niepoprawny framing, skala gizma i ocena gabarytu; dla cienkiego walca błąd osi Z może być duży. Poprawne autorytatywne bounds omijają tę ścieżkę.

**Scenariusz weryfikacji.** Cylinder r=50 nm, h=10 nm bez bounds i size. R07 daje [100,100,100] nm zamiast [100,100,10] nm.

**Naprawa.** Bounds obliczane przez typowany descriptor i jego transform. Dla unknown brak fikcyjnego metrowego obiektu: pending/unavailable geometry proxy.

**Kryterium odbioru.** Testy Box/Cylinder/Sphere/Arch/imported: bbox zgodny z geometrią i orientacją. Brak bounds nie powoduje nagłego oddalenia kamery o dziewięć rzędów wielkości.

<a id="f19"></a>

## F19 — Freshness meshu uznaje niespójne rewizje za current

**Priorytet: P2. Klasa dowodu: L.**

**Źródła:** [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts).

**Stan w kodzie.** Kod oznacza stale tylko dla source_scene_revision < sceneRevision; każda inna para liczb daje current. Nie sprawdza w tej ekspresji gotowości zasobów ani równoważności geometrii/polityki.

**Skutek.** Podczas asynchronicznego odświeżania para scene=10,source=11 może zostać opisana jako aktualna. Jest to błąd predykatu, nie dowód niepoprawnych elementów siatki.

**Scenariusz weryfikacji.** R06 odtwarza tę parę liczb. W UI opóźnij refetch sceny względem manifestu i zobacz badge.

**Naprawa.** W jednym resolverze rozróżnić unknown, loading, inconsistent, stale, current. Docelowo autorytatywny digest geometrii i polityki; rewizje z różnych domen nie są porównywalne.

**Kryterium odbioru.** Current wymaga zgodnego, gotowego zestawu dowodów. Future/mixed-generation daje inconsistent, brak danych unknown, nie zielony status.

<a id="f20"></a>

## F20 — Viewport i inspektor stosują różne reguły stale meshu

**Priorytet: P2. Klasa dowodu: R.**

**Źródła:** [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts); [S22: `viewport3dPrimitiveModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/viewport3dPrimitiveModel.ts).

**Stan w kodzie.** Inspektor porównuje rewizje. objectMeshState viewportu opiera się na obecności obiektu i tagach mesh:dirty/building/failed, a jawne porównanie rewizji wykonuje dla szczególnego CSG preview.

**Skutek.** Ryzyko rozbieżnych statusów przy opóźnionych tagach lub brakujących danych. Nie wykazano, że backend zawsze publikuje niespójny zestaw; potrzebny test kontraktu.

**Scenariusz weryfikacji.** Podaj manifest starej sceny i zwykły Box bez tagów dirty; porównaj wyniki obu resolverów. Potem sprawdź realny geometry edit→refetch.

**Naprawa.** Jeden centralny resolver ArtifactCompatibility używany przez drzewo, inspektor, viewport i Run gating. Stan obiektu/meshu ma wynikać z tego samego zestawu rewizji/digestów.

**Kryterium odbioru.** Brak jednoczesnego current i stale dla tej samej tożsamości. Stary mesh widoczny opcjonalnie, ale zawsze podpisany.

<a id="f21"></a>

## F21 — Selekcja najgorszego elementu nie niesie tożsamości meshu

**Priorytet: P2. Klasa dowodu: R.**

**Źródła:** [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts); [S23: `FdmGridInspectorPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/fdm-grid/FdmGridInspectorPanel.tsx).

**Stan w kodzie.** selectWorstElement zapisuje elementIndex, centroid i metric, ale nie meshRevision/buildId/generation. Dla porównania inspektor FDM jawnie rozróżnia aktualną komórkę i stary snapshot przez fingerprint/membership.

**Skutek.** Po rebuild indeks może wskazywać inny element. Ryzyko błędnego highlight/refine, jeśli inne warstwy nie odrzucą starej selekcji.

**Scenariusz weryfikacji.** Wybierz worst element, przebuduj siatkę, zachowaj selekcję i wykonaj highlight/refine. Sprawdź, czy działa na starej czy nowej topologii.

**Naprawa.** ElementRef={artifactId,generationId,meshRevision,index}; przy nowym meshu selekcja wygasa lub pozostaje wyraźnie read-only snapshotem. Nie mapować po samym indeksie.

**Kryterium odbioru.** Rebuild nie przekierowuje refinementu na inny element. Wzorzec zabezpieczenia FDM wykorzystać także w FEM.

<a id="f22"></a>

## F22 — Reconciliation utraconego ACK szuka tylko ośmiu ostatnich komend

**Priorytet: P2. Klasa dowodu: R.**

**Źródła:** [S20: `geometryLifecycleCommandContributions.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts).

**Stan w kodzie.** reconcileMeshSubmission sortuje kandydatów malejąco po seq i ogranicza ich przez slice(0,8), po czym dopasowuje client_intent_id.

**Skutek.** Jeżeli poszukiwany intent wypadnie poza okno, UI może pozostać publication-unconfirmed mimo istnienia komendy. To bezpieczniejsze niż duplikowanie budowy, ale utrudnia odzyskanie obserwacji.

**Scenariusz weryfikacji.** Zasymuluj utracony ACK oraz co najmniej osiem nowszych komend tego rodzaju w kolejce. Sprawdź wynik reconciliation.

**Naprawa.** Backendowy lookup po client_intent_id albo stronicowane wyszukiwanie z jawnym ograniczeniem i diagnostyką. Zachować zasadę: reconnect nigdy sam nie wysyła ponownie build.

**Kryterium odbioru.** Intent odnaleziony niezależnie od pozycji w historii albo jednoznaczny nieznany wynik z odnośnikiem do jobu; nigdy cicha druga budowa.

<a id="f23"></a>

## F23 — Zakładka history polityki obiektu jest w praktyce widokiem JSON

**Priorytet: P2. Klasa dowodu: G.**

**Źródła:** [S18: `ObjectMeshPolicyPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx); [S16: `MeshDetailsPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/MeshDetailsPanel.tsx); [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts).

**Stan w kodzie.** ObjectMeshPolicyPanel renderuje w history JSON report/quality/size-field. Osobny globalny MeshDetailsPanel posiada rzeczywistą sekcję historii i restore-to-draft.

**Skutek.** Istniejące możliwości są rozproszone i etykieta lokalnej zakładki obiecuje inną treść. Nie należy pisać, że historii w projekcie w ogóle nie ma.

**Scenariusz weryfikacji.** Przejdź Object Mesh→History i Mesh Builds; porównaj zawartość i możliwość dotarcia do budowy danego obiektu.

**Naprawa.** Wspólny history view filtrowany po obiekcie/target, z linkiem do globalnego jobu. Surowy JSON przenieść do Diagnostics/Advanced.

**Kryterium odbioru.** Z inspektora obiektu można zobaczyć job, receptę, źródłową scenę, wynik, błąd i restore-to-draft bez szukania innej sekcji.

<a id="f24"></a>

## F24 — Ribbon eksponuje szeroki katalog trwale nieaktywnych funkcji

**Priorytet: P2. Klasa dowodu: G.**

**Źródła:** [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx).

**Stan w kodzie.** Geometry zawiera liczne disabled prymitywy, Union/Subtract/Intersect oraz Camera/Manipulate/Snap. Definitions ma nieaktywne Parameters/Functions/Coordinates. Nie wszystkie nieaktywne akcje mają tak precyzyjny powód jak Rotate/Scale.

**Skutek.** Widok przypomina kompletny modeler bardziej, niż pozwala rzeczywista funkcjonalność. Trudno odróżnić brak implementacji od nieprawidłowego zaznaczenia.

**Scenariusz weryfikacji.** Przejrzyj toolbar w pustej i wypełnionej scenie. Skategoryzuj każdą nieaktywną akcję: unsupported, unavailable-context, busy, permission, invalid draft.

**Naprawa.** Dwupoziomowy Create: wspierane typy na wierzchu, pozostałe w jawnej sekcji planowanych funkcji. Akcje budować z tego samego registry/capability co komendy i inspektor.

**Kryterium odbioru.** Każdy disabled ma czytelną przyczynę; brak martwego aktywnego menu. Odrębnie testować ikony skrótów i rzeczywiste bindings klawiatury.

<a id="f25"></a>

## F25 — Rozmiar modułów zwiększa ryzyko rozbieżności polityk UI

**Priorytet: P2. Klasa dowodu: R.**

**Źródła:** [S15: `ribbonContributions.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx); [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts); [S18: `ObjectMeshPolicyPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx); [S24: `package.json`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/package.json).

**Stan w kodzie.** Metadata drzewa wskazuje ok. 139 kB ribbonContributions i ok. 117 kB Viewport3DModule. Odczytane panele łączą formularze, transakcje, zasoby, historię, diagnostykę i renderowanie. To wskaźnik długu, nie pomiar wydajności.

**Skutek.** Łatwo naprawić jedną drogę Apply lub jeden badge bez zmiany pozostałych. Sam duży plik nie dowodzi spadku FPS ani wycieku pamięci.

**Scenariusz weryfikacji.** Prześledź jedną mutację translacji i jedną budowę przez wszystkie wejścia. Zmierz render/resource counts istniejącymi skryptami dopiero w uruchomionej aplikacji.

**Naprawa.** Wydziel domain services i selektory najpierw, komponenty widoku później. Nie tworzyć drugiego store sceny ani drugiej historii. Dodać dependency rules i testy kontraktów.

**Kryterium odbioru.** Inspektor/ribbon/gizmo odwołują się do tego samego command contract; mierzalne brak regresji CPU/GPU/network, a nie tylko mniejsza liczba linii.

<a id="f26"></a>

## F26 — Tożsamość szkicu jest zbyt słaba na zmianę typu lub sesji

**Priorytet: P2. Klasa dowodu: R.**

**Źródła:** [S01: `GeometryObjectPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx); [S02: `geometryObjectPanelModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts); [S04: `InspectorModule.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorModule.tsx).

**Stan w kodzie.** draftKey zawiera mode i objectId, a nowe prymitywy otrzymują objectId=draft. Nie zawiera primitive kind, session scope ani unikalnego draftId. InspectorModule nie nadaje Panel jawnego key zależnego od sesji.

**Skutek.** Ryzyko odziedziczenia danych po innym prymitywie lub obiekcie o takim samym ID w innej sesji, o ile rodzic nie wymusi remountu. Nie stwierdzono pełnego zachowania wszystkich tras.

**Scenariusz weryfikacji.** Zmień Box→Cylinder→Sphere bez opuszczania edytora; powtórz przełączenie sesji z identycznym objectId i aktywnym formularzem. Testować wraz z dirty-selection guard.

**Naprawa.** DraftIdentity={sessionId,epoch,targetId,draftId}; typ prymitywu jest częścią intencji tworzenia. Zmiana targetu rozwiązuje dirty state, nie jest ukrytym resetem.

**Kryterium odbioru.** Brak przecieku wartości/konfliktów między szkicami; jawne Apply/Discard/Cancel przy zmianie selekcji.

<a id="f27"></a>

## F27 — Historia może zniknąć bez komunikatu po poprawnej mutacji

**Priorytet: P2. Klasa dowodu: R.**

**Źródła:** [S21: `authoringHistoryMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts).

**Stan w kodzie.** captureAuthoringHistoryScene może zwrócić null; recordAuthoringMutationHistory wtedy pomija zapis. Wyjątki history.record są przechwytywane bez sygnalizacji użytkownikowi. Autorzy świadomie traktują historię jako observability layer.

**Skutek.** Model może być poprawnie zapisany, ale operacja nieodwracalna z UI. To nie powód, by cofać udany ACK; potrzebna jest informacja o zdegradowanej historii.

**Scenariusz weryfikacji.** Zasymuluj brak before snapshot i błąd history.record przy udanym commit. Sprawdź, czy UI ujawnia brak Undo.

**Naprawa.** Ustalić kontrakt historii: zachować ACK, raportować history-degraded, nie udawać wpisu. Dla mutacji krytycznych rozważyć serwerowy dziennik/intencje zamiast best-effort snapshotów.

**Kryterium odbioru.** Sukces zapisu nie znika, ale użytkownik widzi, że Undo tej operacji jest niedostępne; telemetria identyfikuje commandId i przyczynę.

<a id="f28"></a>

## F28 — Pierwsza budowa wymaga testu pustych zasobów w dialogu potwierdzenia

**Priorytet: P2. Klasa dowodu: R.**

**Źródła:** [S19: `MeshBuildDialog.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/overlay/MeshBuildDialog.tsx); [S20: `geometryLifecycleCommandContributions.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts); [S24: `package.json`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/package.json).

**Stan w kodzie.** computedSnapshot wymaga ready dla summary, latest successful oraz manifest. Kod może działać poprawnie, jeśli backend publikuje ready z pustym payloadem przed pierwszą budową; w audycie nie uruchomiono tego kontraktu.

**Skutek.** Ryzyko zablokowania pierwszej budowy, gdy któryś zasób poprawnie odpowiada not-built/404. To hipoteza do sprawdzenia, a nie potwierdzony deadlock.

**Scenariusz weryfikacji.** Nowa sesja FEM, jeden prymityw, brak wcześniejszego meshu i sukcesu; uruchom Build Mesh i zbadaj stany zasobów w dialogu. Istnieje skrypt verify:mesh-build-new-object, ale nie był tu uruchamiany.

**Naprawa.** Zdefiniować not-built jako legalny snapshot bez poprzedniego artefaktu. Odróżnić brak meshu od awarii jego odczytu. Nie obchodzić kontroli scene/policy readiness.

**Kryterium odbioru.** E2E pierwszej budowy z pustej sesji i po importowanym STL, obok rebuild istniejącego meshu oraz błędu odczytu manifestu.
