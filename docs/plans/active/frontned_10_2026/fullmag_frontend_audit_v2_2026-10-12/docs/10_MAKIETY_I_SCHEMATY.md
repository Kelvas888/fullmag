# Makiety i schematy — semantyka v2

## 1. Status i sposób użycia

Siedem makiet zachowuje geometrię rysunku i układ v1. W v2 poprawiono etykiety, wskazanie release oraz granice commit, pending i kwalifikacji. To **makiety projektowe z danymi demonstracyjnymi**, nie screenshot Fullmaga ani certyfikat gotowej funkcji. Nie stanowią wymagania kopiowania ich CSS. Implementacja pozostaje w jednym istniejącym shellu, navbarze, viewportcie, module registry i tokenach `--fm-*`. Wszystkie ADR oznaczone `proposed` w D00 pozostają niezaakceptowane.

Precyzyjny raster makiet i czytelny kontakt-sheet są dołączone obok edytowalnych SVG. Diagramy mają edytowalne DOT; ich kompletna tabela przejść i reguły są w D04/D06/D11/D12. Diagram wysokopoziomowy nie zastępuje tabeli edge cases.

| ID / plik | Release pokazanej funkcji | Semantyka obowiązująca po korekcie |
|---|---|---|
| [M01 Geometry](../mockups/01_geometry.png) | R1 — pojedynczy primitive + Move | Wymiary i pozycja są jednym draftem; Create jest jedną intencją; import/TRS/CSG nie udają R1 support |
| [M02 Transform](../mockups/02_transform.png) | R2-T proposal | Pointerup tylko draft, Apply jedną intencją; pivot-v1 i extrinsic XYZ; pending nie blokuje unrelated controls |
| [M03 Import](../mockups/03_import.png) | R2-I proposal | Stage nie jest obiektem, checks unknown nie są pass, source scale oddzielna od object transform; Cancel nie usuwa referenced asset |
| [M04 Mesh Policy](../mockups/04_mesh_policy.png) | R1 proposal | Recipe draft, committed policy i realized artifact osobno; Apply & Build ma dwie fazy, nie jedną transakcję |
| [M05 Rebuild](../mockups/05_rebuild.png) | R1 proposal | Rewizja/generacja retained artifact jawna; policy saved/build rejected rozróżnione; Retry Loading nie buduje ponownie |
| [M06 Quality](../mockups/06_quality.png) | R2-Q proposal | Metric i ElementRef należą do generacji; brak optional quality ≠ invalid topology; refine aktualizuje receptę |
| [M07 FDM](../mockups/07_fdm.png) | R1 plan + qualification | Grid/membership/fingerprint jedna realizacja; display stride nie zmienia grid; właściciel planu FDM odrębny od FEM meshera |

Pozostałe widoki (Geometry/Placement/source/checks/material/regions/mesh policy/quality/history) określa D05. Nie każdy nowy route potrzebuje nowego pełnoekranowego layoutu. Węzeł semantyczny musi mieć własny detail view, ale wspólną stopkę i zasady sesji edycji.

## 2. Schematy

[D01 — Architektura](../diagrams/01_architecture.svg): kernel objectEdits, committed resource, typed API, draft preview, intent receipt i artifact activation; brak private Inspector store eksportowanego do viewportu.

[D02 — Edycja](../diagrams/02_edit_state_machine.svg): wszystkie phase labels zgodne z D04; gest orthogonal, pointerup nie ma strzałki do zapisu; reconciliation wyłącznie capability-gated proposed receipt. ACK może pozostawić editing-valid/invalid przy późniejszym rawText.

[D03 — Mesh](../diagrams/03_mesh_lifecycle.svg): Apply Policy → nowa confirmation → job → stage required resources → activate generation → viewer delivery; błędy zachowują poprzedni artifact, bez obietnicy atomowej operacji policy+job.

[D04 — Import](../diagrams/04_import_pipeline.svg): source stage/lease/checks/portable asset/new version; capability reżimu construction/FEM/FDM; atomowy attach/reimport, osierocone regiony zamiast ordinal rebind.

## 3. Akceptacja wizualna implementacji

Celem nie jest pikselowa zgodność z obrazem, lecz zgodność znaczenia: label statusu, zakres Apply, unikalny target, jednostka i frame, disabled reason, reprezentacja dirty/stale/unknown, provenance generacji, action semantics i dostępność klawiaturą. Obowiązuje test stabilnego Inspectora oraz rzeczywistego WebGL. Mock-up przedstawiający canvas nie stanowi wyniku tego testu.
