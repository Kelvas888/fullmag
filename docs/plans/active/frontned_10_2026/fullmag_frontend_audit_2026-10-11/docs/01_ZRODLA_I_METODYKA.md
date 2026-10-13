# Źródła, zakres i metoda

## Zamrożony stan repozytorium

Repozytorium: `MateuszZelent/fullmag`. Gałąź: **master**. Commit: **`2a3c6becb9c7e111ae1497ec0cd9ac9576acba95`**.
Data commitu: **7 października 2026, 18:34:20 UTC**. Data audytu: **11 października 2026**.
Commit scala PR #146 dotyczący HUD viewportu. Analiza dotyczy tego snapshotu, nie wcześniejszego audytu z września ani nieznanych worktree.

Źródłem był odczyt GitHub przez konektor: metadane gałęzi, drzewa katalogów, pliki i fragmenty kodu na przypiętym SHA. `legacy_web` jest wyłączone. Aktywny frontend to `apps/control-room`; nazwy innych katalogów nie są dowodem, że stanowią bieżące UI.

## Co wykonano

Prześledzono główne ścieżki tworzenia i edycji prymitywu, serializacji transformu, rejestracji inspektora, Move, konfliktu i historii, wpisy ribbonu, startowy import, politykę meshu obiektu, potwierdzenie/obserwację budowy, freshness oraz wybór elementu jakości. Backendowy moduł assets sprawdzono tylko na granicy importu. Przeprowadzono drugi odczyt kluczowych ścieżek zapisu geometrii i porównano integrację Move z helperami oraz ich testami.

Uruchomiono **7 izolowanych reprodukcji JavaScript** w Node 22.16.0. Trzy bazują na źródłowo równoważnym porcie kontrolera gestu; pozostałe odtwarzają wskazane ekspresje/stany. Log oraz JSON są w `reproductions/`. Odtworzenie w izolacji nie jest równoznaczne z potwierdzeniem całego scenariusza w React, WebGL i backendzie.

## Czego nie wykonano

Nie uruchomiono pełnego checkoutu Fullmaga, jego buildu, Vitest, testów E2E, Gmsh, rzeczywistego WebGL ani benchmarków CPU/GPU. Bezpośrednie pobranie archiwum do środowiska roboczego nie powiodło się; odczyty konektora pozostały dostępne. Nie deklaruje się pełnego pokrycia wszystkich plików frontendu. To audyt statyczny najważniejszych ścieżek z celowanymi reprodukcjami, a nie certyfikat uruchomieniowy.

Makiety są **autorskim projektem docelowym, nie zrzutami działającego Fullmaga**. Liczby w makietach, w tym elementy/jakość/rewizje, są fikcyjnymi danymi demonstracyjnymi. Nie zmieniono repozytorium ani nie wykonano push/PR.

## Klasy dowodu

| Kod | Znaczenie |
|---|---|
| C | Zachowanie/struktura potwierdzone odczytem kodu; bez pełnego uruchomienia UI. |
| L | Odczyt kodu oraz izolowane odtworzenie mechanizmu; ograniczenia wskazane przy pozycji. |
| R | Konkretne ryzyko kontraktu/integracji; wymaga testu produkcyjnej ścieżki. |
| G | Luka funkcjonalna względem żądanego modelera, niekoniecznie defekt implementacji. |

P1 oznacza blokadę wydania pełnego workflow objętego zleceniem albo istotny defekt spójności. P2 wymaga naprawy lub jawnej redukcji zakresu. Nie stwierdzono dowodów uzasadniających P0. P1 przy ryzyku R jest priorytetem weryfikacji, nie deklaracją potwierdzonej awarii.

## Rejestr przeczytanych źródeł

Każdy link prowadzi do przypiętego commitu. Zakresy poniżej są zakresami rzeczywiście czytanymi; nie są deklaracją pełnego odczytu dużego pliku.

### S01 — `apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx`

Główny formularz geometrii; stan szkicu, Apply, konflikt, preview.

Zakres: **65–1080; także wcześniejszy odczyt początku**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/GeometryObjectPanel.tsx).

### S02 — `apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts`

Parser pól, typy geometrii, serializacja i rebase.

Zakres: **1–660**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/geometryObjectPanelModel.ts).

### S03 — `apps/control-room/src/modules/inspector/InspectorEditSession.tsx`

Wspólne Apply/Revert, rejestracja i dirty state.

Zakres: **cały plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorEditSession.tsx).

### S04 — `apps/control-room/src/modules/inspector/InspectorModule.tsx`

Montaż panelu i most do pending forms.

Zakres: **cały plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/InspectorModule.tsx).

### S05 — `apps/control-room/src/modules/inspector/panels/DedicatedExplorerInspectorPanels.tsx`

Routing dedykowanych inspektorów.

Zakres: **cały plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/DedicatedExplorerInspectorPanels.tsx).

### S06 — `apps/control-room/src/kernel/authoring/geometryLifecycleCommands.ts`

Mutacje geometrii i obserwacja terminalnego wyniku meshera.

Zakres: **1–380**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommands.ts).

### S07 — `apps/control-room/src/kernel/authoring/objectTranslationMutation.ts`

Wspólna transakcja translacji; opcjonalne ogrodzenie sesji.

Zakres: **cały plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectTranslationMutation.ts).

### S08 — `apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts`

Zapis gestu i rebase konfliktu.

Zakres: **cały plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/objectMoveConflictWorkflow.ts).

### S09 — `apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx`

Produkcyjna integracja Move z zasobami i sesją.

Zakres: **cały plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/Viewport3DObjectMoveInteraction.tsx).

### S10 — `apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx`

Kontroler gestu, raycast, capture, preview, osie.

Zakres: **cały plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx).

### S11 — `apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.test.tsx`

Testy kontrolera i niskopoziomowej translacji; nie uruchamiano.

Zakres: **1–330 / cały zwrócony plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.test.tsx).

### S12 — `apps/control-room/src/modules/start/model/importFormats.ts`

Rozpoznawanie formatów importu na ekranie startowym.

Zakres: **cały plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/start/model/importFormats.ts).

### S13 — `crates/fullmag-api/src/assets.rs`

Backendowe podsumowania uploadu STL/MSH/JSON; nie pełny mesher.

Zakres: **1–250**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-api/src/assets.rs).

### S14 — `apps/control-room/src/modules/ribbon/ribbonCommands.ts`

Aktywacja Move, sprawdzanie obiektu i roli.

Zakres: **1–360**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonCommands.ts).

### S15 — `apps/control-room/src/modules/ribbon/ribbonContributions.tsx`

Definicje Definitions/Geometry/Mesh i nieaktywne narzędzia.

Zakres: **1–230, 285–426 oraz fragment definicji Mesh**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/ribbon/ribbonContributions.tsx).

### S16 — `apps/control-room/src/modules/inspector/panels/MeshDetailsPanel.tsx`

Kompozycja paneli budowy, jakości, historii; FEM/FDM.

Zakres: **1–350**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/MeshDetailsPanel.tsx).

### S17 — `apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts`

Freshness, zasoby meshu, retained artifact, selekcja jakości.

Zakres: **1–320, 350–koniec**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/mesh-details/useMeshDetailsModel.ts).

### S18 — `apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx`

Polityka obiektu, Apply & Build, sesja, edytory i historia.

Zakres: **1–350, 1000–koniec**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx).

### S19 — `apps/control-room/src/modules/overlay/MeshBuildDialog.tsx`

Potwierdzenie budowy; snapshot, diff, warunki aktualności.

Zakres: **1–360**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/overlay/MeshBuildDialog.tsx).

### S20 — `apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts`

Realizacja geometrii, kolejka i wznowienie obserwacji budowy.

Zakres: **1–250, 500–860**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts).

### S21 — `apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts`

Przygotowanie i rejestracja mutacji w historii.

Zakres: **1–340 / cały zwrócony plik**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/authoringHistoryMutation.ts).

### S22 — `apps/control-room/src/modules/viewport-3d/viewport3dPrimitiveModel.ts`

Bounds, fallback, stan meshu per obiekt i model renderowania.

Zakres: **1–340, 435–koniec**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/viewport3dPrimitiveModel.ts).

### S23 — `apps/control-room/src/modules/inspector/panels/fdm-grid/FdmGridInspectorPanel.tsx`

Siatka FDM, komórka, fingerprint, membership i status stale.

Zakres: **1–340**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/fdm-grid/FdmGridInspectorPanel.tsx).

### S24 — `apps/control-room/package.json`

Deklarowane zależności i istniejące komendy testów/smoke.

Zakres: **1–120**. [Kod na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/package.json).

## Ograniczenia wnioskowania

Brak importera na ekranie startowym nie dowodzi braku importera Python. Obecność parsera STL nie dowodzi poprawnego zamknięcia powłoki ani przygotowania objętości do FEM. Nieaktywny obrót obiektu nie wyklucza osobnych transformacji tekstury. Snapshot test helpera z poprawnym scope nie potwierdza, że produkcyjny caller ten scope przekazuje. Rozmiar pliku nie jest benchmarkiem FPS. Starsze audyty i dokumentacja repozytorium służą nawigacji, nie zastępują dowodu w bieżącym kodzie.
