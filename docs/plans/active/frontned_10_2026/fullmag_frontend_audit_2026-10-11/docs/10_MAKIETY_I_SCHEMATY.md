# Makiety i schematy — przewodnik po projekcie

## Status materiałów

Wszystkie obrazy w katalogach `mockups/` i `diagrams/` są **autorskimi makietami lub schematami docelowymi**, a nie screenshotami uruchomionego Fullmaga. Liczby, nazwy assetów, identyfikatory buildów i metryki są danymi demonstracyjnymi. Nie stanowią pomiaru jakości ani dowodu działania aplikacji. SVG jest źródłem edytowalnym; PNG jest renderem do wygodnego podglądu.

Wspólny układ zachowuje koncepcję shell + ribbon + explorer + viewport + inspector + dolny pasek. Kolory i odstępy są propozycją nawiązującą do ciemnego Control Room, nie odczytaną w runtime certyfikacją jego tokenów CSS. Docelowy kod ma korzystać z istniejącego systemu stylów i navbaru.

[Otwórz galerię HTML](../index.html). Szczegółowa specyfikacja kontrolek i semantyki jest w [dokumencie 05](05_SPECYFIKACJA_UI_I_INSPEKTOROW.md).

## M01 — tworzenie geometrii

[SVG](../mockups/01_geometry.svg) · [PNG](../mockups/01_geometry.png)

Box w lokalnym preview, wymiary i jednostki, Name, placement, assignment i jedna stopka Create/Cancel. Explorer pokazuje, że obiekt jest draftem. Viewport może pokazać wymiarowanie bez sugerowania, że mesh został już zbudowany. Create wysyła jedną intencję i dopiero po ACK przełącza obiekt na committed.

Powiązania: F01, F03, F09, F12, F13, F17, F26. Podgląd zakresu i pola mają korzystać z tej samej sesji; makieta nie jest zgodą na niezależną geometrię Three.js.

## M02 — placement, obrót, skala i pivot

[SVG](../mockups/02_transform.svg) · [PNG](../mockups/02_transform.png)

Wspólne narzędzia Move/Rotate/Scale, wybór ramy, pivot, absolute/delta, uniform lock. Zaznaczona bryła ma osie i kontrolowany preview. Stopka informuje o stale mesh po Apply. Pivot-only oznacza zachowanie world geometry; to nie to samo co przesunięcie obiektu.

Powiązania: F04–F08, F10, F14–F16. Funkcje Rotate/Scale są docelowe i obecnie pozostają zablokowane w badanym kodzie.

## M03 — import STL

[SVG](../mockups/03_import.svg) · [PNG](../mockups/03_import.png)

Kroki source → units → checks → commit; panel pokazuje hash, bbox i jednostkę źródłową, a viewport powierzchnię. Diagnostyka odróżnia sprawdzone właściwości od unknown. Przycisk Create Object nie jest Build Volume Mesh. Dane raportu są ilustracją docelowej prezentacji, nie wynikiem parsera backendu.

Powiązania: F11, F12. Repair, gdy dostępny, tworzy nową wersję assetu i wymaga pokazania skutków. Cancel nie tworzy obiektu.

## M04 — FEM mesh policy

[SVG](../mockups/04_mesh_policy.svg) · [PNG](../mockups/04_mesh_policy.png)

Szybki dostęp do strategy, hmin/hmax, sterowania grubością i quality. Requested/effective/source nie mieszają się z już zrealizowaną siatką. Stary mesh pozostaje oznaczony jako stale. Zakres Build jest jawny, a Apply Policy pozostaje operacją oddzielną od budowy.

Powiązania: F19, F20, F23, F24. Rozbudowane pola istniejącego ObjectMeshPolicyPanel nie mają zniknąć; zostają uporządkowane, a Advanced i JSON nie dominują w podstawowym workflow.

## M05 — rebuild i zachowany artefakt

[SVG](../mockups/05_rebuild.svg) · [PNG](../mockups/05_rebuild.png)

Przedstawiony jest stan obserwacji już przyjętej intencji: fazy zadania, bieżące źródło geometrii, policy diff i last-good artifact. Zamknięcie obserwatora nie anuluje zadania. Interfejs odróżnia publication, ładowanie i wyrenderowanie topologii. Nie pokazuje fikcyjnego czasu ukończenia.

Powiązania: F22, F28. Przy unknown outcome zamiast nowego Build pojawia się Resume Observation. Przy failed można utworzyć nową intencję dopiero po ustaleniu skutku poprzedniej.

## M06 — jakość, przekrój i selekcja elementu

[SVG](../mockups/06_quality.svg) · [PNG](../mockups/06_quality.png)

Kolor/metryka i histogram mają wspólną identity z meshem. Przekrój i wireframe są wyłącznie operacją widoku. Worst elements pozwala przejść od tabeli do zaznaczenia, a refinement jest osobnym działaniem. Zielona metryka nie jest certyfikatem zbieżności fizycznej.

Powiązania: F19–F21, F23. Nowa generacja unieważnia stary ordinal; wymagana jawna tożsamość artefaktu. Geometria przekroju na makiecie jest schematyczna, nie pochodzi z meshera.

## M07 — FDM grid i membership

[SVG](../mockups/07_fdm.svg) · [PNG](../mockups/07_fdm.png)

Inspektor pokazuje zrealizowany grid, fingerprint, komórkę IJK i region. Edycja spacing prowadzi do właściciela planu, a Build Grid nie wywołuje FEM meshing. Grid display samples nie oznaczają zmniejszenia liczby komórek solvera.

Powiązanie z istniejącym dobrym wzorcem: [S23: `FdmGridInspectorPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/fdm-grid/FdmGridInspectorPanel.tsx). Ta makieta nie postuluje zastąpienia kontroli canonical membership przybliżeniem na podstawie koloru obiektu.

## Schematy systemowe

| Schemat | Znaczenie |
|---|---|
| [D01 — architektura](../diagrams/01_architecture.svg) | Jeden draft i wiele widoków; backend jako właściciel committed model; artefakty pochodne. |
| [D02 — sesja edycji](../diagrams/02_edit_state_machine.svg) | Poprawne przejścia Apply/ACK/conflict/unknown/reconcile; izolacja operacji. |
| [D03 — mesh lifecycle](../diagrams/03_mesh_lifecycle.svg) | Recepta, build, publication, rendered i retained artifact. |
| [D04 — import](../diagrams/04_import_pipeline.svg) | Źródło i jednostki, kontrola powierzchni, naprawa jako nowy asset, commit i lane. |

Każdy schemat ma plik `.dot` oraz wersję PNG. Pliki można edytować niezależnie od raportu. Schematy opisują projekt docelowy; obecny częściowy przepływ znajduje się w dokumencie 03.
