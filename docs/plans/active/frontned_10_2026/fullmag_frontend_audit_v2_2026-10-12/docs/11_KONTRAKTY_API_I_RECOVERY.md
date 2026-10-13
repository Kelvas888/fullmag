# API, ordinary mutation recovery i capabilities

Źródła potwierdzone: S25/S26/S27 oraz dotychczasowe frontendowe S06/S07/S21. Wszystkie pola receipt, FieldProblem, nowe resources i capability fields poniżej są **projektem**. Nie wolno wywoływać ich z klienta, dopóki backend nie publikuje odpowiadającej capability i nie przejdą generatorów.

## 1. Istniejąca transakcja geometry+transform

Sprawdzona droga źródłowa:

`GeometryObjectPanel → patchObjectGeometryTransaction → api.model.commitTransaction → POST /v2/sessions/current/model/transactions → AuthoringTransactionRequest::PatchObjectGeometry → commit_authoring_transaction → apply_object_geometry_patch → commit_current_live_scene_document_for_context → AuthoringTransactionResponse`.

`apply_object_geometry_patch` sprawdza base revision na pobranej scenie, deserializuje `SceneGeometry`, deserializuje opcjonalny `Transform3D` i dopiero po obu poprawnych deserializacjach przypisuje je do obiektu oraz oznacza mesh dirty. Dispatcher robi jeden wspólny commit tego kandydata. S25 definiuje ACK z `transaction_kind`, `scene_revision`, `committed_scene`; **brak lokalnego operationId w obecnym ACK**. Wrapper `runAuthoringMutationWithHistory` (S21) potrafi użyć committed_scene dla historii.

Payload do reużycia dla jednego obiektu, przed rozszerzeniem receipt:

```json
{
  "kind": "patch_object_geometry",
  "base_revision": 10,
  "object_id": "object-A",
  "geometry": {"geometry_kind":"Cylinder","geometry_params":{"radius":8e-8,"height":1e-8}},
  "transform": {"translation":[3e-7,0,0],"rotation_quat":[0,0,0,1],"scale":[1,1,1],"pivot":[0,0,0]}
}
```

Transform ma **replace semantics** w tym handlerze. Wysłanie tylko translation powoduje deserializację pozostałych pól do defaults, a nie merge z istniejącym q/scale/pivot. Klient buduje pełny transform z baseline + zaakceptowanej intencji i zachowuje nieedytowane pola. Dla unsupported nonidentity transform ma odmówić niebezpiecznej edycji, nie zresetować go do identity. Euler `rotation` z formularza nie jest wire `rotation_quat`.

`geometry` także jest pełnym deskryptorem, nie dowolnym JSON patch. Dlatego three-way merge musi zachować nowe zdalne pola przed serializacją. Material/region assignment nie staje się automatycznie częścią tego payloadu. Dla Create można reużyć istniejące pola material_ref/region_name; dla edycji istniejącego obiektu są odrębne transakcje. Multi-object batch nie jest wymaganiem B1 i pozostaje R3.

### Granica dowodu atomowości

Potwierdzono wspólnego kandydata sceny i pojedyncze wywołanie commitu. Nie udowodniono finalnego lock/CAS, walidacji naukowej całego inputu, atomowego zapisu plików ani rollbacku na wszystkich ścieżkach wspólnego committera. Nie klasyfikujemy tego jako wykrytego błędu współbieżności. To konkretna bramka w PR01: odczyt `commit_current_live_scene_document_with_context` i jego konsumentów, a następnie T51/T52 w realnym backendzie.

Wymagany kontrakt finalnego commitu: validate candidate bez mutacji stanu aktywnego → przejęcie serializera zapisu danego dokumentu/sesji → ponowne sprawdzenie epoch, run gate i `base_revision == current.revision` → jeden nowy commit kandydata → publikacja ACK/event. Jeżeli walidacja wykonuje się poza lockiem, finałowy CAS nadal jest obowiązkowy. Dwa requesty z bazą r i różnymi wartościami nie mogą oba nadpisać się jako niezależne sukcesy. Oczekiwane: jeden success r+1, drugi409; alternatywny automatyczny merge wymagałby oddzielnego kontraktu, którego tu nie zakładamy.

## 2. Rozszerzenie istniejącego API zamiast nowego batcha

Dla wspieranych mutacji dodać opcjonalny `client_intent_id` do requestu i ACK oraz zapisywany server-side request digest. W generowanym DTO nie może to być wyłącznie lokalny `as any`. Klient R1 sprawdza capability `authoring.transaction_receipts` (proponowana nazwa). Podstawowy endpoint transactions pozostaje ten sam. Nowa ścieżka read-only:

`GET /v2/sessions/current/model/transaction-intents/{client_intent_id}`.

Identyfikatory requestu: project/document są rozstrzygane autorytatywnie z bieżącego request scope; klient nie może przypisać sobie obcego dokumentu przez body. Receipt przechowuje także originating logical session i epoch, lecz klucz deduplikacji wiąże `projectId + documentId + client_intent_id` i zweryfikowany payload digest. Po reopen lookup wymaga aktywnego mount tego samego dokumentu albo dedykowanego autoryzowanego scope; nie odpytuje się przypadkowej current session.

`operationId` pozostaje identyfikatorem lokalnego wykonania Promise i nie musi przechodzić po sieci. Repeated POST tej samej intencji może mieć nowy lokalny operationId, ale nigdy nowy `client_intent_id` dla tej samej nieznanej mutacji. Mesh command_id i jego job receipt należą do istniejącego command subsystem; nie sklejaj ich z ordinary transaction ledger.

## 3. Stany receipt i deduplikacja

| Lookup state | Znaczenie | Dopuszczalne działanie klienta |
|---|---|---|
| not-seen | Autorytatywny journal nie zarejestrował tej intencji w poprawnym owner scope | Ponowienie **tej samej** intencji dopiero przy zadeklarowanej idempotencji; nigdy nowy ID |
| in-progress | Intencja zarejestrowana, efekt jeszcze nierozstrzygnięty | Obserwuj; brak nowego Apply |
| committed | Receipt zawiera commit revision, request digest i ref do wynikowego snapshotu | Zastosuj ten sam ACK reducer; bez ponownej mutacji |
| rejected | Trwałe odrzucenie bez efektu zapisu | Pokaż problem; poprawiony payload dostaje nową intencję |
| indeterminate | Po awarii journal wymaga naprawy/recovery | Fail-closed, nie przechodź do rejected |
| expired | Receipt niewystarczający do odtworzenia, ale pozostaje tombstone | Brak automatycznego ponowienia; owner recovery |
| wrong-owner / id-payload-mismatch | Błędny scope albo próba reuse ID dla innego payloadu | Odmowa, żadnego mapowania na success |

Klucz deduplikacji rezerwuje się **przed** efektem zmiany. Replay z tym samym digestem zwraca ten sam terminalny receipt; ten sam ID z inną treścią→409 `intent_payload_mismatch`. CAS conflict zostaje terminalnym rejected receipt; retry po rebase ma nową intencję. `base_revision` w źródle jest opcjonalne, ale klient R1 wymaga go we wszystkich objętych edycjach; backend vNext powinien odrzucać brak bazy dla nowej capability zamiast korzystać z przypadkowego last-write-wins.

Trwałość: zapis efektu sceny i receiptu musi mieć jeden punkt commit/recovery w istniejącym project storage. Nie proponujemy naiwnych dwóch niezależnych write() „najpierw scena, potem receipt”. Należy użyć wspólnego transaction record/WAL albo równoważnej gwarancji istniejącej warstwy persistence. Record zawiera base revision, commit revision, request digest, immutable snapshot ref i terminal status. Po crash replay record odtwarza stan i receipt bez drugiego zastosowania operacji. Osobny journal intencji nie może omijać locka stosowanego przez inne mutacje sceny.

Proponowana retencja: terminalne receipt i dedup tombstone przez życie zapisanego dokumentu; eksport projektu zachowuje niezbędną tożsamość zapisanych intencji. Retencję pełnych snapshotów można ograniczyć, lecz tombstone/commit reference musi zapobiegać ponownemu wykonaniu. Usunięcie projektu usuwa te dane zgodnie z jego polityką, nie ukrytą procedurą cache cleanup. To decyzja ADR-02 o koszcie storage, nie już obowiązująca polityka repo.

## 4. Utracony ACK — scenariusze wykonawcze

**Create:** object_id i client_intent_id generowane przed POST. Po timeout nie tworzymy nowego objectId. Lookup committed identyfikuje utworzony obiekt i rewizję. Sam fakt, że w scenie istnieje podobny obiekt/nazwa, nie dowodzi, że ten request się udał.

**Apply po zmianie wymiaru i Move:** pointerup niczego nie wysyła; dopiero Apply tworzy intencję. Timeout blokuje następny scene-changing commit, ale pozwala zachować późniejszy rawText. Receipt committed używa submittedEditVersions i zachowuje późniejsze zmiany.

**Reload:** local journal zawiera owner, draftId, intent, captured payload i digest oraz nieznany stan. Po hydration klient najpierw weryfikuje mount właściciela i pobiera receipt. Nie odtwarza gestu ani starych pointer captures. Nieznany wynik nie może być „naprawiony” bezwarunkowym wysłaniem zachowanego formularza.

**Stary backend bez receipts:** recovery ordinary mutation nie jest zagwarantowane. Jednorazowy POST może pozostać outcome-unknown. GET scene służy porównaniu, ale nie dowodzi przyczynowości ani nie rozstrzyga requestu w locie. Bez serwerowego barrier/drain lub rozstrzygniętego CAS nie wolno uznać retry za bezpieczne. Hotfix działa fail-closed; pełny R1 wymaga PR05, a nie samego nowego panelu „Retry”.

**5xx:** błąd sieci/500 po zapisie jest wynikiem nieznanym, dopóki receipt nie mówi inaczej. Abort fetch nie anuluje transakcji serwera. 409 revision_conflict jest definitywny tylko gdy pochodzi z rozpoznanego kontraktu i oznacza brak efektu tej intencji.

## 5. Gwarancja historii R1

R1: **best-effort lokalne Undo z jawnym `history-degraded`**, przy trwałym receipcie do recovery. Jeden zaakceptowany semantic Apply ma co najwyżej jeden wpis historii, deduplikowany po docId+intentId+commitRevision. Warunkiem pełnego wpisu jest znany before i after snapshot. Brak history storage nie cofa poprawnego zapisu i nie wysyła go ponownie. UI informuje „Saved; Undo unavailable for this change”.

Receipt committed odczytany po reload może odzyskać zapis, ale nie gwarantuje całego łańcucha Undo. Nie rekonstruować before z aktualnej sceny po innych zmianach. Undo/Redo są nowymi mutacjami z własnymi intencjami i aktualną bazą; przy niezgodnym stanie powinny odmówić zamiast przywrócić cały stary snapshot nad cudzymi zmianami. Historia musi rejestrować faktyczną postać pełnego obiektu, nie tylko przesunięcie podglądu.

## 6. Pełna ścieżka zmiany API

| Zmiana | Backend schema / route | Generated i facade | Hook/cache/event | Konsumenci / kompatybilność |
|---|---|---|---|---|
| geometry+transform | Reuse S25/S26 | Zweryfikować ObjectGeometryPatchRequest; helper w geometryLifecycleCommands | Committed scene + istniejące invalidacje | B1; brak nowego batch endpointu |
| receipt i client_intent_id | Rozszerzenie schemas/authoring.rs + nowy intent GET w model route | `openapi_v2` → `generate:openapi-v2` → `generate:api-v2-types` → `generate:api-v2-client` → typed facade | `model/transaction-intents/{id}` scoped owner; events thin | objectEdits, recovery dialog, local journal; capability przed wywołaniem |
| FieldProblem | Nowy schema `{code, field_path, message, severity, target_ref, source_revision}` | Typowany error mapper; brak any | Problem list przypięta do operation/field editVersion | Inline errors i diagnostics; fallback stary error.message jawny |
| TRS semantics | SceneDocument schema/version + Python/IR adapters | Generated scene types i serializer full transform | Geometry realization/validation + assessment invalidation | Geometry/Placement/viewport/export; stary klient read-only przy nowej semantyce |
| ArtifactProvenance/active generation | Meshing schemas + nowy active-generation GET | Typowane DTO i facade; stare manifest endpoints jako adapter | Owner+generation cache key, activation event | Mesh, FDM, quality, Run gating |
| ElementRef / metric metadata | Data/meshing schemas | Selection extension oraz generowane resource types | Binary buffers immutable per generation | Highlight/quality/refinement bez ordinal reuse |
| Staged import/assets | Nowe assets schemas w rodzinie model/persistence | Generated stage/check/version/asset facade | Stage leases + version-keyed binary preview | Import views; brak direct fetch w React |

Powyższe polecenia generatorów istnieją w S24, ale ich uruchomienie wymaga dozwolonego profilu i storage. Dla nowego schematu sprawdzić, że został włączony do OpenAPI registration i że generated output jest deterministyczny. TypeScript lokalny typ nie jest zmianą API. Testy compatibility obejmują stary projekt/nowy klient i nowy projekt/stary klient; brak obsługi oznacza read-only/explicit error, nie ignorowanie pól.

## 7. Capability owners i disabled reasons

| Kontrolka | Autorytatywny owner | Istniejące vs projektowane pole | Przykład powodu odmowy |
|---|---|---|---|
| Primitive create/edit | Model geometry capabilities | Reuse istniejących primitive capabilities; dodać qualification ref gdzie brak | Geometry kind not editable for this realization |
| Rotate/Scale/Pivot | Geometry semantics + session execution resolution | **Proponowane** `transforms[op].{authorable,realizable,qualified,reason}` | Rotation is not qualified for requested FDM GPU precision |
| Apply with recovery | Model transaction service + request scope | **Proponowane** authoring.transaction_receipts | Reliable mutation recovery unavailable; compatibility mode only |
| FEM meshing strategy/order | Meshing capabilities / policy service | Reuse istniejącego capability model; exact DTO przez generator | Element family/order unsupported by resolved runtime |
| FDM Build Grid | Session lane + execution plan | Reuse grid.build-fdm gating; dodać evidence do nowego planu | Structured-grid plan unresolved |
| Import construction / FEM volume / FDM occupancy | Platform installed importer + geometry/session capability | **Proponowane** import.modes/limits/checks | Surface checks incomplete for volume attachment |
| Quality color/refine | Data catalog + meshing recipe capabilities | **Proponowane** metric availability i generation binding | Quality belongs to another generation / refinement unsupported |
| Apply podczas runu | Session run admission | Backend authoritative execution lock | Run is preparing/running; finish or stop explicitly |

Kernel `resolveActionAvailability` tylko agreguje powyższe fakty i lokalny stan draftu/operacji. Nie jest dodatkową bazą capabilities. Model nie ma być uznany za CPU-ready dlatego, że GPU brakuje; forced GPU odmawia, auto zachowuje requested/resolved provenance. Nazwa/type obiektu nigdy nie włącza interakcji fizycznej.
