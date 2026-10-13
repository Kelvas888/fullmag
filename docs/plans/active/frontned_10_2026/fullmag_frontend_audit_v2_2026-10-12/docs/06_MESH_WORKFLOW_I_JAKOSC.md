# Mesh: tożsamość, aktualność, publikacja i rebuild

ADR-05/06 — wariant rekomendowany, nie stan obecnego API. Źródła istniejącej infrastruktury: S06/S16–S20/S22/S23. Odróżniamy **recipe**, **job**, **published artifact**, **delivered/rendered data** i **model solver readiness**. Istniejące confirmation/observation i brak duplikacji build zachować.

## 1. Kontrakt właściciela i zakresu

Nowy `ArtifactProvenanceV2` to discriminated union, nie uniwersalne `object-context`. Przykłady JSON są DTO propozycji. Nazwy nie zastępują generated API.

```ts
// PROPOSED. The API schema, not this snippet, must own the wire contract.
type ArtifactOwner = {
  projectId: string;
  documentId: string;
  sourceSessionId: string;
};
type ExecutionBinding = {
  requested: { lane: 'fdm'|'fem'; device: string; precision: string };
  resolved: { lane: 'fdm'|'fem'; device: string; precision: string };
  qualificationId: string | null;
};
type CommonProvenance = {
  owner: ArtifactOwner;
  artifactId: string;
  generationId: string;
  buildId: string;
  sourceSceneRevision: number;
  inputDigest: string;
  digestSchema: 'mesh-input-v1';
  geometryDigest: string;
  recipeDigest: string;
  execution: ExecutionBinding;
};
type FemProvenance = CommonProvenance & {
  family: 'fem';
  scope: { kind: 'shared-domain'; objectIds: string[]; universeId: string | null };
  topologyDigest: string;
  regionMappingDigest: string;
  elementFamilies: string[];
};
type FdmProvenance = CommonProvenance & {
  family: 'fdm';
  scope: { kind: 'execution-plan'; planId: string; layerIds: string[] };
  gridFingerprint: string;
  layoutDigest: string;
  membershipDigest: string;
  membershipRevision: number;
};
```

`selectionContext={origin:'object-inspector', objectId:'A'}` opisuje miejsce kliknięcia, nie zakres artefaktu. FEM result w R1 obejmuje wspólną domenę i wymagane powietrze/interfejsy, również gdy kliknięto obiekt A. FDM grid jest własnością execution plan; obiekt/warstwa to scope zapytania, nie niezależna siatka Gmsh.

`sourceSessionId` jest pochodzeniem; ponowne otwarcie projektu nie kasuje poprawnych assetów. Użycie w nowej sesji wymaga serwerowego activation/binding do tego samego projectId/documentId oraz potwierdzenia inputDigest. Frontend nie przepisuje ownera i nie traktuje samego zbieżnego numeru revision jako prawa do użycia obcego meshu.

## 2. Digesty i kanonizacja

Autorytatywne digesty oblicza backend z rozwiązanego inputu i wersją algorytmu, nie każdy panel osobno. Propozycja `mesh-input-v1`: SHA256 nad wersjonowaną reprezentacją canonical input. Implementacja serializer-a ma golden bytes fixtures wspólne z Pythonem/IR. Deterministyczne reguły: UTF-8, klucze map uporządkowane leksykograficznie według bajtów, liczby skończone f64 w SI, −0 normalizowane do +0, jawne typy i długości pól. Listy zachowują semantyczną kolejność (np. operacje CSG/region priority); jedynie zbiory sortujemy po immutable ID. Quaternion normalizowany i kanonizowany znakowo według D13. Nie używać locale ani JSON pretty-print jako algorytmu hasha.

Dokładna implementacja binary canonical encoder należy do PR08 i wymaga wersjonowanych golden vectors przed pierwszą publikacją. Alternatywnie można wybrać istniejący repo serializer, ale nie mieszać dwóch kanonizacji pod tym samym `digestSchema`. Nieznany klucz wpływający na geometrię nie może zostać po cichu pominięty. Descriptor geometry zachowuje rozszerzenia albo staje się unsupported.

| Zmiana | Geometry digest | Recipe / input digest | Konsekwencja |
|---|---|---|---|
| name, widoczność widoku, kamera, kolor | Bez zmian | Bez zmian, o ile nie zmienia authored participation | Bez remeshu; field/display revisions niezależne |
| Wymiar / translation / realny TRS | Zmiana | Zmiana | Stale mesh/membership, nowa realizacja |
| Pivot-only ze skompensowaną translacją | Canonical evaluated affine bez zmian | Bez zmian jeśli żaden konsument recepty nie zależy od pivota | Osobna sceneRevision, bez remeshu przy pełnym kontrakcie |
| hmin/hmax/sweep/interface sizing | Bez zmian | Recipe i input zmienione | Rebuild |
| Grid spacing/origin/shape/layer plan | Shape geometry bez zmian | FDM layout/input zmienione | Grid+membership rebuild |
| Region geometry/priority | Zależnie od topologii | Mapping/membership zmienione | Backend określa, czy remesh, czy tylko rebind |
| Parametr materiału | Zwykle bez zmian | Zmiana, jeśli sizing kalibrowany z materiału; inaczej physics readiness | Nie utożsamiać zmiany fizyki z remeshem |
| Reimport | Nowa evaluated geometry lub source variant | Source/import settings w input | Backend porównuje zdefiniowany digest; region bindings ponownie sprawdzone |

Wykluczenie nazwy z digestu wymaga uprzedniego usunięcia semantycznych zależności od name. `object_id`, participation i authored physics są jawne. Brak zmiany digestu nie dowodzi gotowości całej fizyki: Run sprawdza również coefficients, initial state, boundaries i execution profile.

## 3. Jeden resolver

Dwa orthogonal modele: `ArtifactPresence = not-built | present`; `ResourceLoadState = idle | loading | ready | error`. Dla obecnego artefaktu wynik `ArtifactAssessment.state` jest dokładnie jednym z **current/stale/incompatible/unknown/loading/inconsistent**. `not-built` nie jest synonimem error ani dodatkowym rodzajem freshness. Dla not-built assessment może być null i Run zabroniony.

| Warunek, w tej kolejności | Wynik | Run |
|---|---|---|
| Brak artefaktu legalnie `not-built` | presence not-built, assessment null | Nie |
| Obcy project/document, niewspierany schema/lane/element family lub brak zgody na rebind | incompatible | Nie |
| Sprzeczne generation/mandatory hashes albo source revision większa od znanej sceny w tej samej linii historii | inconsistent; refetch authority | Nie |
| Ładujemy wymagany marker/scenę/provenance i nie mamy spójnego kompletu | loading | Nie |
| Brak wymaganego owner/digest/legacy revision; błąd odczytu bez dowodu | unknown, transport error osobno | Nie |
| Pełne input/recipe/membership dopasowanie i activation ważna | current | Dopiero razem z pozostałą readiness |
| Dopuszczalny artefakt, ale input różni się od zatwierdzonego modelu | stale | Nie dla bieżącego runu; inspekcja snapshotu tak |

Wariant `current + delivery:error` jest legalny: backend ma zgodny artefakt, viewport nie zdołał go pobrać. Retry Loading nie uruchamia Build. `current + quality:unavailable` też jest legalny, jeśli brakujący raport jest opcjonalny i mandatory topology validation przeszła.

**Migracja przed digestami:** jeden legacy adapter konsumuje tylko jawne revision/owner/runtime status. Zgodne sourceSceneRevision==sceneRevision, jawny stan ready i brak conflicting tags pozwalają na `current` z `evidence='legacy-revision'`; nie daje to dowodu hash parity. Mniejsza revision→stale, większa→inconsistent, brak danych→unknown. Rename przy wyższej revision pozostaje konserwatywnie stale; nie rekonstruować authority poprzez porównanie dwóch przypadkowych JSON-ów w UI. Dopiero serwerowy digest pozwala zachować current po samym rename. Ten koszt jest jawny, nie cichy błąd.

## 4. Konsumenci i invalidacje

Nowy owner `src/kernel/resources/artifactAssessment.ts` + `useArtifactAssessmentSelector.ts` zwraca wynik dla konkretnego artifact/owner. `useMeshDetailsModel`, viewport primitive/mesh adapter, MeshBuildDialog, ObjectMeshPolicyPanel, FdmGridInspectorPanel i Run gating korzystają z tego samego wyniku. Nie wolno tworzyć local `sourceRevision < sceneRevision` w następnym komponencie. Backend readiness pozostaje autorytatywna; klient nie przywraca Run lokalnym „current”.

Commit geometrii invaliduje geometry validation/realization, input assessment, membership/regions i simulation preparation. Policy change invaliduje właściwą receptę i assessment, ale nie usuwa ostatnich bajtów artefaktu. Camera/display change nie invaliduje geometrii ani recipe. Event zawiera resource key/revision/generation; status nie przenosi topologii ani pełnych histogramów.

## 5. Atomowa publikacja

Proponowany nowy `GET /v2/sessions/current/meshing/active-generation` zwraca:

```json
{"presence":"not-built","owner":{"projectId":"p","documentId":"d"},"family":"fem"}
```

albo `{presence:'present', activationRevision, binding, provenance, requiredResources, optionalResources, completeness:'committed'}`. To **nowy zasób**, nie podmiana istniejącego manifestu na niezgodny shape. Dotychczasowe endpoints mogą być adapterami.

Backend: build do tymczasowego generation directory → walidacja mandatory → zapis i hash wszystkich wymaganych plików → trwały manifest → atomowy marker aktywacji → command completed i event. Nie mieszać zasobów zapisywanych w miejscu pod starym generationId. Crash przed markerem pozostawia ostatnią generację; crash po markerze musi pozwolić odtworzyć receipt i command state. UI najpierw pobiera marker, potem immutable resources po generationId; marker zmieniony w trakcie odczytu powoduje nowy zestaw albo jawny snapshot, nigdy mieszaninę.

| Rodzina | Wymagane przed aktywacją | Opcjonalne |
|---|---|---|
| FEM | Manifest/units/families; nodes/connectivity; object/domain ownership; region/boundary mapping wymagane przez solver; mandatory topology validation; geometrical/source provenance; profile-specific certificate gdy wymaga go engine | Histogramy, per-element gamma, dodatkowa diagnostyka optymalizatora, LOD preview |
| FDM | Descriptor/layout dla każdej warstwy, shape/origin/spacing; immutable grid fingerprint; magnetic support i membership mapping; jawne transfer/interpolation maps jeśli wymagane przez plan; source provenance | Preview cells decimation, heatmaps/debug counters, dodatkowe statystyki |

Brak optional quality nie jest awarią poprawnej topologii. Ujemny/zerowy element Jacobian stwierdzony przez mandatory validation nie staje się legalny dlatego, że quality jest „optional”. Mandatory validation i optional analysis to różne zasoby.

## 6. ElementRef i metryki

```ts
// PROPOSED; add to generated schemas and Selection without dropping old identities.
type ElementRef = {
  owner: { projectId: string; documentId: string };
  artifactId: string;
  generationId: string;
} & (
  | { family:'fem'; topologyDigest:string; ordinal:number; stableElementId:string|null }
  | { family:'fdm'; gridFingerprint:string; membershipRevision:number;
      layerId:string|null; ijk:[number,number,number] }
);
```

Ordinal jest adresem w konkretnym connectivity buffer, nie trwałym ID elementu między meshami. Po remeshu: clear selection albo retained snapshot badge; nie kierować starego indeksu do nowej tablicy. `stableElementId` pozostaje null, dopóki backend rzeczywiście go nie nadaje. Highlight i refinement walidują ten sam ref co quality. Centroid służy fokusowi, nie zastępuje identity.

Metryka ma `id`, `definitionVersion`, units, range, betterDirection, family, generation, invalidMask. Nie rekonstruować wartości wyłącznie na podstawie etykiety Gamma. Jeśli pierwsza nowa metryka to tetra radius ratio, definicja musi być jawna `q=3*r_in/R_circ`, bezwymiarowa, idealny tetra q=1, gorsza blisko0; orientation osobno przez signed det. Nie nadpisywać istniejącego backend gamma nowym wzorem bez migracji. Dla innych rodzin używać ich zadeklarowanej metryki lub unavailable. NaN/invalid pokazuje osobny kolor/symbol, nie znika z histogramu ani nie zamienia się w q=1.

## 7. First-build, scope i błędy

| Sytuacja | Reakcja |
|---|---|
| Prawidłowa sesja, scene istnieje, previous artifact not-built | Build dozwolony po validation; comparison pokazuje „brak poprzedniej siatki” |
| Nieznany artifactId/generationId | 404 not-found, nie not-built |
| Brak aktywnej sesji / stara epoka | Osobny błąd scope, żadnego fallback do innej sesji |
| Network/5xx | Load error/unknown; nie kasować retained artifact |
| Legacy endpoint 404 | Nie mapować automatycznie; potrzebny rozpoznany kod no_mesh_yet lub nowy presence resource |
| Brak poprzedniej quality/history | Nie blokować pierwszego builda; sekcje mają empty state |

W R1 etykieta „Build Mesh” przy obiekcie otwiera dialog „Rebuild shared FEM domain; selected context: A”, z listą obejmowanych ownerów i airbox. Backend actual scope musi być zweryfikowany T58; jeśli obecny `mesh_target:object_mesh` wykonuje inną operację, nie zmieniać znaczenia bez adaptacji. „Build Selected” nie jest obietnicą lokalnego remeshu. FDM używa `grid.build-fdm`, planId i grid/membership snapshot; nie oferować hmax jako cell spacing.

## 8. Apply & Build jest sagą dwóch kroków

1. Przechwyć draft recepty. Apply zapisuje go przez zwykłą mutację z CAS/receipt. ACK zwraca nową scene/policy revision.
2. Z nowego kanonicznego snapshotu zbuduj confirmation i precondition builda. Nie używaj commandContext przechwyconego przed Apply jako źródła aktualnej revision.
3. Potwierdzenie użytkownika wysyła jeden job z osobnym `client_intent_id` i captured input/target. Zmiana sceny między krokami wymaga odnowienia confirmation; nie budować niejawnie starego lub innego modelu.
4. Odmowa jobu: **policy saved, build rejected**. Revert formularza nie cofa już zapisanego kroku. Undo Policy to oddzielna operacja, nie domniemana część rollbacku.
5. Completed oznacza opublikowanie właściwej generacji. Fetch/render readiness jest następnym, osobnym stanem. Jeśli scena zmieniła się w międzyczasie, wynik może zostać zachowany jako stale snapshot, nigdy current bez resolvera.

Double-click łączy się z tą samą aktywną intencją UI; osobne kliki po zakończeniu mogą tworzyć nowe jawne intencje. Lost ACK jobu wymaga lookup/reconcile po intencji; utrata odpowiedzi submit nie dowodzi rejection. Istniejący limit przeszukania ostatnich ośmiu komend nie daje pełności; plan dodaje autorytatywne wyszukiwanie/paginację z dowodem kompletności. Zawsze można wznowić obserwację tego samego commandId; nie należy wysyłać nowego builda tylko dlatego, że viewport jest pusty.

## 9. Build Geometry, przekrój i refinement

| Akcja | Owner / wejście | Wynik / lifecycle | Release i capability |
|---|---|---|---|
| Build Geometry | Model geometry backend; zatwierdzony scene snapshot, backend target | Descriptor realization + diagnostics/region candidates; nie mesh ani pełny CAD tessellation | Istniejąca komenda `builder-build-geometry`, R1 poprawność stanu/rewizji |
| Przekrój XY/XZ/YZ | Data-plane slice backend; generation + plane + units + scope | Faktyczne przecięcia elementów; binary/image delivery; cancel starego requestu | Zachować existing qualified; dodatkowa kwalifikacja R2-Q |
| Arbitrary plane | Ten sam slice owner, jawne origin+normal, bounded query | Tylko po sprawdzeniu kontraktu normal/frame/identity | Nie obiecywać w R1; R2-Q tylko z T45; custom construction workplane R3 |
| Per-element color | Quality resource + ElementRef family + definitionVersion | Zgodne buffers i legenda; optional unavailable bez utraty mesh | R2-Q, dane dostępne dla wybranej rodziny |
| Refine… | Recipe owner; region/size field z geometry anchor i captured generation | Najpierw preview zmiany recepty, Apply, nowy build; nie lokalny splice connectivity | R2-Q, jawne source generation precondition |
| Porównaj zbieżność | Study/results owner z serią fizycznie zgodnych runów | Potrzebny kontrakt obserwabli, normalizacji i parametrów | Odłożone R3; nie dodawać działającego-looking przycisku |

Test przekroju T45 używa jawnego tetra fixture z D08, nie samego clipping box wszystkich trójkątów rzutowanych na XY. Mesh quality nie jest dowodem zbieżności fizycznej; stosunek rozmiaru elementu do właściwych skal mikromagnetycznych i stabilność obserwabli należą do osobnej kwalifikacji naukowej D13.
