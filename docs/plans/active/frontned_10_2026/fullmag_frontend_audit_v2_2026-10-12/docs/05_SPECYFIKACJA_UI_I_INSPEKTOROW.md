# UI, Explorer, Inspector i narzędzia

Zakres: istniejący unified workspace, navbar i viewport. Nie tworzyć aplikacji „nowego buildera”, osobnych shelli FEM/FDM ani stage-switch Build/Study/Analyze. Makiety są diagramami intencji i etykiet, nie kodem CSS do skopiowania. Wiążąca integracja opiera się na S31: jeden typed client, resource hooks, manifesty, command registry, `fm-*` i tokeny `--fm-*`.

## 1. Mapa semantyczna widoków

Prefiks wszystkich ścieżek frontendowych: `apps/control-room/src/`. „Nowy” oznacza propozycję, nie odnaleziony plik/typ. Każdy child node dostaje własny Inspector view; wspólne primitive komponenty są dozwolone, kopiowanie całego widoku dla odmiennych węzłów nie.

| Węzeł / kind | Selection / referencja | Widok Inspector | Manifest/slot | Resource owner | Komendy / release |
|---|---|---|---|---|---|
| Objects root, `objects.root` zgodnie z aktualnym katalogiem | Weryfikacja dokładnej pisowni w registry przy PR04 | Istniejący ObjectsRootInspectorPanel | explorer tree / inspector slot | Scene resource | Add primitive, R1 |
| Nowy prymityw `builder.primitive` | Nowy draftId; przyszły object_id nie `draft` jako wspólny identyfikator | GeometryObjectPanel przez adapter | inspector + geometry ribbon | kernel.objectEdits + scene baseline | Create Object, Cancel, R1 |
| Obiekt `object.root` | `scene-object`, objectId | ObjectGeneralPanel | Obecny inspector manifest | Kanoniczny scene object | Rename/visibility istniejące; osobny transaction scope |
| Geometria `object.geometry` | Ten sam scene-object | GeometryObjectPanel, wyłącznie shape/content | Dedykowana istniejąca trasa | kernel.objectEdits | Apply/Revert, Validate, R1 |
| Położenie `object.placement` — nowy | scene-object + objectId, kind placement | **ObjectPlacementPanel** — nowy | Nowy wpis inspectorRouteCatalog; ten sam shell | Ta sama sesja draftu co Geometry | Move, Apply/Revert R1; TRS R2-T |
| Pivot `object.pivot` — nowy R2 | scene-object + local-anchor ref | **ObjectPivotPanel** — nowy, nie kopia Placement | Dedykowany view | Ten sam draft + geometry bounds | Affect Pivot Only, anchor select R2-T |
| Regiony `object.regions` / istniejące region kinds | Stabilny ownerObjectId/regionId, nie mesh ordinal | ObjectRegionsPanel i dedykowane child views | Obecne registry i node builders | Scene regions / realization resource | Własne Apply; nie dopisywać do geometry transaction |
| Materiał `object.material` / magnetic parameters | Stabilny material asset ID + objectId | Istniejące ObjectMaterialPanel routes | Obecny inspector slot | Material resource / scene binding | Przypisanie i parametry; zachować jawne physics modules |
| Object mesh `object.mesh` | scene-object, objectId; selectionContext | ObjectMeshPolicyPanel | Obecny inspector slot | Meshing policy, jeden owner per panel tree | Apply Policy / Apply & Build, R1 |
| Airbox parameters, istniejące lane routes | Canonical universe/airbox ref | AirboxMeshParametersPanel z adapterem transakcji | Istniejące Airbox lane views | Universe policy | Apply; Build shared domain FEM / Build Grid FDM |
| Mesh root / shared-domain | `mesh.root`, `mesh.shared-domain` | Obecne MeshDetailsPanel sekcje w dedykowanych widokach | Registry już istnieje | Active generation + legacy adapters | Overview/Build, R1; provenance R2 |
| Build history `mesh.builds` | commandId/buildId/owner | MeshBuildsInspectorPanel + job details | Obecny registry | Command resources + history | Observe/Retry Loading/Restore recipe to draft |
| Quality `mesh.quality` | **ElementRef/MetricRef z generation**, rozszerzenie Selection | MeshQualityInspectorPanel, osobny element detail | Dedykowane view, wspólne chart primitives | Quality binary + manifest | Focus element R1; color/refine R2-Q |
| FDM grid `mesh.grid` i layer kinds | grid fingerprint, layout/layer ID, membership generation | FdmGridInspectorPanel z odrębnymi widokami dziecka | Istniejące FDM routes | Execution plan + realized grid resources | Build Grid i Open Discretization Owner |
| Import `object.import-source`, `object.import-checks` — nowe | stageId lub objectId+assetVersion | **ImportSourcePanel**, **ImportChecksPanel** | Nowe contributions w istniejącym shellu | Asset resources, nie scene dla nieprzyłączonego uploadu | Upload/Check/Attach/Reimport R2-I |
| Unsupported geometry | Oryginalny geometry kind + owner | GeometryReadOnlyPanel, preview status i provenance | Capability-selected dedicated route | Raw canonical descriptor read-only | Export/view; brak fałszywych Size fields |

Nazwy nowych kind są kontraktem planu; przed dodaniem zarejestrować je w `selectionTypes.ts`, route catalog i explorer node builders razem. Nie uznawać wiersza z proponowanym kind za istniejącą deklarację typu. Dla istniejących node kinds zachować aktualne stringi; wskazany pierwszy wiersz ma jawne zadanie sprawdzenia literalnej nazwy zamiast cichej zmiany.

## 2. Dirty guard i przejścia

Geometry→Placement tego samego objectId i epoch nie pyta o Apply, bo obie strony edytują tę samą transakcję. Zmiana rodzaju prymitywu wymaga potwierdzenia discard i nowego draftId; nie przenosi przypadkiem pól Box do Cylinder. Przejście do innego obiektu albo Mesh Policy pyta: „Zmiany geometrii i położenia obiektu A: Apply / Discard / Cancel”. Zmiana tylko sekcji/kamery nie jest opuszczeniem draftu.

Apply and continue używa wspólnego canApply obejmującego conflict, outcome-unknown i execution lock. Przy Apply sukces i post-submit edits oznacza nadal dirty: guard pyta ponownie o **nowe** zmiany lub zostaje w edycji; nie porzuca ich po samym ACK pierwszego snapshotu. Dirty guard nie wymusza globalnego dimming. Jeśli target został zdalnie usunięty, opcje to eksport szkicu/discard; nie oferować Apply, które utworzy obiekt ponownie.

## 3. Układ panelu i stopka

Nagłówek: nazwa, immutable ID w kopii/tooltipie, typ prezentacyjny, stan draftu i scope. Zakładki Geometry/Placement/Regions/Mesh Policy są kontekstami, nie czterema globalnymi modelami. Pola mają SI/display unit, rawText i problem przy polu. Provenance/JSON przenieść do Diagnostics, bez zastępowania podstawowego formularza surowym JSON.

Jedna sticky stopka dla aktywnej transakcji: Apply Changes / Revert. Nowy obiekt: Create Object / Cancel. Mesh policy: Apply Policy i Apply & Build; licznik lokalnych zmian nie oznacza zmian backendu. Zmiana tekstu nie uruchamia meshera. Po ACK z nowszym rawText badge „Saved; newer edits remain”. Przy nieznanym wyniku: „Outcome unknown; Check status”, bez zielonego „Saved” i bez aktywnego kolejnego submit.

Dostępność kontrolek liczona centralnie per action, nie przez skopiowane warunki w ribbonie. Modele problemów zawierają owner/fieldPath/code/message, a payload trace jest zaawansowaną diagnostyką. Brak walidacji to „Not checked/Unavailable”, nigdy „No issues”.

## 4. Narzędzia i klawiatura

| Narzędzie | R1 | R2 | Zachowanie |
|---|---|---|---|
| Select / Focus | Zachować | Zachować | F fokusuje wybrany target; nie zmienia skali modelu |
| Move XYZ | Staged, world frame, liczby SI | World/Local + plane handles | Pointerup tylko kończy gest; Esc cofa wyłącznie gest |
| Rotate / Scale | Disabled z backend reason | Qualified lanes/geometry only | Ten sam draft; q/scale nie są stanem Three.js |
| Pivot | Informacja read-only dla legacy | Kanoniczny pivot-v1 | Pivot-only zachowuje macierz geometrii |
| Snap | Jawnie poza R1 lub tylko już dostępna funkcja | Off default; krok liczbowy | Bez zmiany siatki FDM ani recipe |
| Align | Nieaktywne | Do world origin/kanonicznej płaszczyzny jako jawne pojedyncze polecenie po kwalifikacji | Align do drugiego obiektu i face/vertex odłożone do R3 |
| Workplane | Wyłącznie referencyjne XY/XZ/YZ | Bez własnego construction plane w R2 | Custom plane i parametryczny szkic R3 |
| Multi-selection | Istniejące inspekcje można zachować | Brak nowego multi-object commit | R3 wymaga batch contract; Mixed nigdy nie jest zerem |
| CSG | Zachować istniejące qualified ograniczone przypadki | Ogólny edytor nie jest obietnicą R2 | Union/intersect/feature history R3 |

W/E/R działają tylko poza text input/contenteditable/dialog capture. Disabled shortcut nie wywołuje requestu. Pointer capture musi mieć pojedynczy cleanup na cancel/lostcapture/unmount. Model math pracuje w SI/f64; render może stosować local-origin normalization. Oś prawie równoległa do promienia kamery dostaje jawny degeneracy fallback (inna płaszczyzna drag albo odmowa), nie używa starego event.point jako nowej pozycji.

## 5. Dwanaście podstawowych widoków do odbioru

Do kwalifikacji pierwszych dostaw: (1) Create primitive, (2) Object identity, (3) Geometry parameters, (4) Placement, (5) Regions/bindings, (6) Object mesh policy, (7) Airbox policy, (8) Build confirmation, (9) Build job/retained artifact, (10) Mesh quality, (11) FDM grid/membership, (12) Import source/checks — ostatni dopiero R2-I. Pivot ma dodatkowy child view w R2-T. Żaden nowy import view nie jest deklarowany jako gotowy w R1.

## 6. Stabilność i accessibility — warunek odbioru

Test dla Object oraz Airbox (gdzie dotyczy): zapamiętaj referencję DOM root, focus, selectionStart/End, scrollTop, computed opacity i disabled niespokrewnionych kontrolek; wyślij Apply z opóźnioną odpowiedzią i invalidate/refetch; po ACK sprawdź ich zachowanie. Root ma być ten sam; brak animacji opacity; nowszy rawText zachowany; request/render counts zmierzone i porównane z zatwierdzonym budżetem. Nie „naprawiać” tego przez force remount.

Dialogi mają focus trap i poprawny powrót fokusu, stan nie zależy wyłącznie od koloru, wartości wektorów mają etykiety osi i jednostki. Nie zmieniać aktualnego design system ani StrictMode bez wymaganej kwalifikacji. Makiety V2 pokazują wariant projektu, nie wyłączają obowiązku użycia istniejących shared primitives.
