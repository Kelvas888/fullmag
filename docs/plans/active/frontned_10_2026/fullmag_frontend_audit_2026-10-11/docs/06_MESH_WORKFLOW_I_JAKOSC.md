# Geometria → recepta → mesh → inspekcja → przebudowa

> Specyfikacja docelowa. Mechanizmy istniejące są wskazane źródłami; nowe identyfikatory i warunki publikacji są propozycją, a nie deklaracją obecnego kontraktu API.

## 1. Jednostka poprawności

Nie wystarcza, że scena jest widoczna, job zakończył się bez wyjątku i renderer ma trójkąty. Trzeba wiedzieć, **jaka zatwierdzona geometria, jaka recepta, jaki zakres oraz jaka wersja wykonawcy** dały konkretny artefakt. Tożsamość siatki musi następnie przejść do topologii, jakości, selekcji elementu i danych solvera.

Proponowany klucz pochodzenia obejmuje: session/project identity, geometry digest, semantic-partition digest, recipe digest, mesher/version/capability profile oraz jawny target. `meshId` i `generationId` wskazują konkretny wynik; `sceneRevision` pozostaje tokenem kolejności, nie zastępuje wszystkich zależności. Samo porównanie `<` rewizji nie dowodzi kompatybilności. F19–F21 opisują aktualne niespójności. [S17: `useMeshDetailsModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts), [S22: `viewport3dPrimitiveModel.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/viewport3dPrimitiveModel.ts).

Przykładowy kontrakt, nie gotowy payload obecnego endpointu:

```ts
interface MeshProvenanceVNext {
  meshId: string;
  generationId: string;
  sourceSceneRevision: number;
  geometryDigest: string;
  partitionDigest: string;
  recipeDigest: string;
  target: { kind: 'study-domain' } | { kind: 'object-context'; objectId: string };
  mesher: { name: string; version: string; capabilityProfile: string };
}
```

Do lookupu jakości używać `(meshId, generationId, metric, elementId)`, a nie samego ordinalu. Przy przejściu na inną generację stare zaznaczenie pozostaje snapshotem albo znika z komunikatem. Nigdy nie wskazuje przypadkowo elementu o tym samym indeksie w nowej siatce.

## 2. Stany modelu i artefaktu są niezależne

| Warstwa | Przykładowy stan | Co użytkownik może zrobić |
|---|---|---|
| Draft | dirty-valid / dirty-invalid | Preview; Apply tylko po poprawnej walidacji. |
| Geometria zatwierdzona | valid / needs-realization / invalid | Build Geometry lub naprawa wskazanego problemu. |
| Recepta | inherited / override / dirty | Zapis polityki bez niejawnego uruchamiania meshera. |
| Zadanie | queued / running / outcome-unknown / failed / completed | Obserwacja; anulowanie tylko przy potwierdzonej możliwości. |
| Artefakt | absent / current / stale / incompatible / identity-unknown | Oglądanie z etykietą; użycie obliczeniowe tylko zgodnie z readiness. |
| Viewport | loading / rendered / failed | Ponowienie ładowania bez ponownego meshowania. |

Diagram: [03 Mesh lifecycle](../diagrams/03_mesh_lifecycle.svg). Nie redukować tych stanów do jednej zielonej lampki „Ready”. Na przykład build failed + retained mesh jest prawidłową kombinacją, a completed + viewport loading nie jest błędem meshera.

## 3. Reguły unieważniania

| Zmiana | Geometria/partycja | Recepta i mesh | Render / fizyka |
|---|---|---|---|
| Kamera, clipping, opacity, kolor obiektu | Bez zmian | Bez zmian | Tylko render. |
| Nazwa/notatka obiektu | Bez zmiany kształtu | Nie wymuszać remeshu wyłącznie z tego powodu | Metadane UI/provenance. |
| Wymiar, translacja, obrót, skala | Nowy geometry digest | Wynik stary lub niekompatybilny; rebuild zgodnie z zakresem | Nowy preview; stan fizyczny wymaga jawnej polityki. |
| Źródło STL/reimport/repair | Nowa wersja assetu i geometrii | Ponowna walidacja i build | Kontrola osieroconych selections. |
| hmin/hmax/strategia/warstwy | Geometria bez zmian | Nowy recipe digest; stary mesh | Wyniki solvera nie przechodzą automatycznie. |
| Materiał bez zmiany granic regionów | Kształt bez zmian | Nie zakładać koniecznego remeshu; sprawdzić zależności polityki | Parametry operatorów i readiness wymagają aktualizacji. |
| Granica lub sposób przypisania regionu | Możliwa nowa partycja | Przebudowa membership i ewentualnie siatki zgodnie z kontraktem | Nie kopiować starych markerów w ciemno. |

To reguły docelowe. Aktualna implementacja używa szerszych invalidation groups; optymalizacja po digestach wymaga audytu zależności backendu. Nie usuwać istniejących invalidacji bez testu kontraktu. [S07: `objectTranslationMutation.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectTranslationMutation.ts), [S20: `geometryLifecycleCommandContributions.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts).

## 4. Pierwsza budowa od pustego projektu

Użytkownik tworzy geometrię, nadaje poprawne jednostki i rolę, zatwierdza obiekt, a potem otwiera Mesh Policy. Przed pierwszą budową brak poprzedniego meshId jest stanem **absent**, nie błędem odczytu. Preflight pokazuje zakres i parametry; w porównaniu „Previous mesh” widnieje „Not built”. Nie należy wymagać starej siatki do zbudowania pierwszej.

Aktualny dialog wymaga zasobów summary/latest/manifest w stanie ready, aby zbudować snapshot. To może być poprawne, jeżeli backend zwraca ready z pustą reprezentacją. F28 nie stwierdza deadlocku: wymaga sprawdzenia rzeczywistych odpowiedzi 200-empty/404/error. Naprawa powinna rozróżniać brak artefaktu od niedostępności usługi. [S19: `MeshBuildDialog.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/overlay/MeshBuildDialog.tsx).

Preflight ma zweryfikować najpierw stan zatwierdzony. Przy dirty geometrii dać decyzję Apply & Continue / Discard & Continue / Cancel. Nie mieszać starej geometrii z nowymi niezapisanymi wymiarami widocznymi obok.

## 5. FEM — właściwy podział ustawień

**Object geometry** odpowiada za kształt. **Object mesh policy** określa cel rozdzielczości i dopuszczalną strategię. **Shared domain/universe policy** określa wspólny kontekst, otoczenie i interfejsy. Etykieta Build Selected powinna pokazywać rzeczywisty zakres pracy backendu; nie obiecywać lokalnej aktualizacji węzłów, jeżeli wykonywana jest globalna przebudowa domeny.

W panelu użytkownik powinien widzieć hmax, hmin, growth/transition, sterowanie krzywizną, refinement przy interfejsie i przez grubość oraz żądanie quality. Pola istnieją już w znacznym zakresie i wymagają głównie uporządkowania. Surowe numery algorytmów Gmsh, selectors JSON i ręczne tags należą do Advanced. [S18: `ObjectMeshPolicyPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx).

Każde ograniczenie musi pokazywać **requested → effective → realization**. Requested opisuje intencję. Effective opisuje rozwiązanie dziedziczenia i ograniczeń. Realization/report opisuje to, co faktycznie zbudowano, łącznie z fallbackiem. Powierzchniowa triangulacja importowanego obiektu nie może otrzymać etykiety volume mesh, dopóki nie istnieje sprawdzona reprezentacja objętościowa.

Dla cienkich warstw panel musi rozdzielać liczbę elementów przez grubość od liczby płaszczyzn węzłów. Nie nazywać obu „layers”. Wskazywać, kiedy wymagana strategia nie jest dostępna dla geometrii/rodziny elementów. Preset nie może maskować odrzuconego ustawienia, a fallback do innej strategii nie może pozostawać wyłącznie w JSON report.

Dla imported geometry konieczne są informacje, które operacje sizing mają semantyczne powierzchnie/krawędzie, a które działają tylko na triangulacji. Nie zakładać stabilności surowych tagów Gmsh po reimporcie lub CSG. Selections muszą być związane z semantyką geometrii albo jawnie oznaczone jako fragile.

## 6. FDM — osobny kontrakt

Rozmiar komórki, extent, origin, shape i konfiguracja warstw należą do właściciela dyskretyzacji/planu. Realized grid jest wynikiem. Edytor nie powinien patchować read-only topologii po zmianie spacingu. Build Grid musi atomowo zrealizować nowy grid oraz zgodną z nim maskę/membership.

W badanym kodzie istnieją fingerprint i kontrola starego snapshotu komórki. Zachować je i doprowadzić analogiczną ochronę do FEM. Ekran FDM pokazuje total cells, active cells, spacing, regiony i status maski. Stride wizualizacji nie zmienia solver cells i ma osobną etykietę. [S23: `FdmGridInspectorPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/fdm-grid/FdmGridInspectorPanel.tsx).

Jeżeli geometria mieści się między komórkami albo jest cieńsza niż zadany spacing, UI powinno przedstawić diagnostykę rozdzielczości z backendu, nie automatycznie „naprawiać” wymiaru obiektu. Nie postuluję uniwersalnego progu poprawności numerycznej: wymagane są kryteria konkretnego modelu i badanie zbieżności.

## 7. Przebudowa i publikacja

Przebudowa zaczyna się od zamrożonej intencji i jawnych preconditions. Kolejne etapy: accepted → queued → realization/meshing → quality → publication → loading viewport → rendered. Istniejący observer już odróżnia accepted od completion i wymaga nowej opublikowanej rewizji. Zachować tę ochronę. [S06: `geometryLifecycleCommands.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommands.ts), [S20: `geometryLifecycleCommandContributions.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts).

Propozycja kontraktu publikacji: nowa generacja staje się aktywna dopiero, gdy manifest, topologia, wymagane markery i diagnostyka mają zgodną tożsamość. Błąd quality lub publikacji nie powinien usuwać poprzedniej poprawnej generacji. Sama obecność retained artifact nie oznacza zgodności z aktualnym modelem. Gdy geometria zmieni się w trakcie jobu, wynik może być poprawnym artefaktem historycznym, ale nie automatycznie bieżącym meshem.

Przed rebuild należy jawnie określić los stanu magnetyzacji: reinicjalizacja zgodna z modelem albo kwalifikowana projekcja/przeniesienie. Aktualny dialog zapowiada reinicjalizację; nie zmieniać komunikatu na „state preserved” bez implementacji i walidacji. [S19: `MeshBuildDialog.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/overlay/MeshBuildDialog.tsx).

## 8. Utrata połączenia, błędy i odzyskanie

Lost ACK oznacza unknown outcome. Nie wolno od razu wysyłać kolejnego build. Odczytać status po client intent ID; jeżeli nie ma serwerowego lookupu, zachować stan nierozstrzygnięty i zaoferować command history. Obecne odtwarzanie przegląda jedynie osiem najnowszych kandydatów: to ograniczenie F22, a nie zgoda na ponowne wysłanie. [S20: `geometryLifecycleCommandContributions.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts).

Błąd meshera pokazuje etap, przyczynę, zakres i diagnostykę. Błąd pobrania mesh buffer daje Retry Loading, nie Rebuild. Cancel jobu wymaga potwierdzonej możliwości backendu i stanów cancelled vs cancellation requested. Zamknięcie modalnego okna nie jest cancel.

## 9. Inspekcja jakości i wydajność

Rozdzielić jakość geometryczną elementów, poprawność topologii/regionów, rozdzielczość fizyczną i zbieżność wyniku. Zielona metryka kształtu nie dowodzi dokładności relacji dyspersji ani dynamiki. UI powinno umożliwiać porównanie wyników kolejnych rozdzielczości, ale ten audyt nie wyznacza uniwersalnych tolerancji fizycznych.

Viewport jakości oferuje przekrój, wyświetlanie zewnętrznych powierzchni, wireframe, izolację komponentu, wybór metryki i worst elements. Dane muszą dotyczyć tego samego artifact identity. Histogram z innej rewizji pozostaje podpisanym snapshotem, nie aktualizuje zaznaczenia bieżącej siatki.

Budżety wydajności ustalić na reprezentatywnych modelach i sprzęcie: koszt parsowania/importu, allocations podczas drag, liczba requestów, transfery topologii, czas przełączenia przekroju, retained CPU/GPU memory po powtórzeniach. Nie podaję pomiarów FPS lub pamięci — nie uruchamiałem aplikacji. Wymaganie architektoniczne: zero requestów zapisu podczas pointermove; zmiana koloru/clippingu nie generuje nowej siatki; zbędne odczyty quality/history nie powinny dominować przy edycji prostego obiektu.
