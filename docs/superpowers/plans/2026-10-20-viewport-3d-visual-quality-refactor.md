# Plan refaktoryzacji wyglądu viewportu 3D

Data: 20.10.2026. Status: **W REALIZACJI — R7, 85%; R8 nie rozpoczęto**. Aktualne commity, wyniki i otwarte bramki: [checkpoint implementacji](2026-10-20-viewport-visual-quality-checkpoint.md). Poniższe wymagania zachowują pełny pierwotny zakres.

Podstawa: [audyt jakości wizualnej](../../audits/2026-10-20-viewport-3d-visual-quality-audit.md), zapisany i ponownie przeczytany przed przygotowaniem tego planu.

Baza audytu: `master`, `88a9b68d29ec173a0b1f1b8750c126da022b0244`, checkout `C:\git\fullmag\fullmag`. Dokumenty przygotowano na `masterze` zgodnie z prośbą. Przyszła implementacja wymaga osobnej izolacji i cyklu integracji określonego w AGENTS.md; ten plan nie uruchamia tego cyklu.

## 1. Cel i granice

Uzyskać spokojny, profesjonalny widok przestrzenny: delikatny gradient inspirowany wskazaną referencją 3ds Max, ciągłe osie pod podziałkami, czytelna siatka, zrozumiały HUD, kontrolowane oświetlenie brył i przewidywalna kamera.

Zachować jeden viewport FDM/FEM, rzeczywiste proporcje modelu, SI, poprawność map kolorów i legend, stabilną kamerę, renderowanie na żądanie oraz jawne zwalnianie zasobów. Nie zmieniać solverów, geometrii fizycznej, danych pola, ProblemIR ani transportu binarnego.

Pierwszy rezultat użytkowy to tło + ramka + skala, dostępne z istniejących kontrolek i możliwe do zapisania jako preferencje. Pełny zakres obejmuje również światło, kamerę, porządkowanie efektów i poprawny eksport. Nie uznawać pierwszego etapu za realizację całego planu.

## 2. Wnioski z ponownego przeczytania audytu

| Sprawdzenie | Wniosek dla planu |
|---|---|
| Czy brak głębi wynika tylko z tła? | Nie. Gradient poprawia odbiór przestrzeni, ale bryły wymagają właściwych materiałów, krawędzi i wskazówek zasłaniania |
| Czy trzeba napisać siatkę od początku? | Nie. Rozszerzyć `dimensionFrameModel` o gwarantowane baselines i semantykę początku skali |
| Czy obecne ticki oznaczają współrzędne świata? | Nie zawsze: tekst używa `value - center`. Dodać jawny tryb bez cichej reinterpretacji istniejących widoków |
| Czy można dodać gradient samym CSS? | Nie w aktualnej ścieżce `alpha:false` + jednolite tło sceny; eksport też pobiera sam canvas |
| Czy światło już istnieje? | Tak, ale aktualny rig zwraca ambient; wiele materiałów nie korzysta ze świateł sceny |
| Czy AO i kamera są brakującymi funkcjami? | Nie. Rozwinąć istniejące mechanizmy, nie tworzyć konkurencyjnych |
| Czy jeden preset może sterować jakością i fizycznym znaczeniem koloru? | Nie powinien. Oddzielić budżet obrazu od wyglądu geometrii i trybu interpretacji danych |
| Czy screenshot dowodzi błędu materiału konkretnego obiektu? | Nie. R0 musi ustalić aktywne ścieżki i stan runtime |
| Czy zapisane raporty historyczne są dowodem obecnego runtime? | Nie. Weryfikacja musi wiązać wybrany checkout, konfigurację i nowe artefakty |

Skorygowana kolejność: semantyka i własność → tło i osie → układ HUD → materiały/światło → dopracowanie kamery i ustawień → efekty/eksport → pełna weryfikacja.

## 3. Proponowane kontrakty

Są to decyzje proponowane do realizacji, nie istniejące interfejsy.

### 3.1 Własność stanu

| Stan | Właściciel i trwałość |
|---|---|
| Tło, siatka/HUD, preset światła, jakość | Prywatne preferencje viewportu; wersjonowany i walidowany zapis lokalnych preferencji UI |
| Kamera aktywnej sesji | Istniejący kernel `CameraRegistryController` i zasób visualization; lokalny stan tylko dla trwającego gestu |
| Kamera podglądu datasetu | Istniejący `useSavedViewportCamera`; w tym zakresie zachować jego obecną trwałość w pamięci |
| Nowe trwałe „zapisane ujęcia” | Rozszerzenie poza pierwszym wdrożeniem; wymaga określenia zakresu projektu/datasetu i osobnego kontraktu |
| Geometrie linii, tekstury gradientu/tekstu, materiały, render targety | Renderer/resource tracker, nie React state ani storage |
| Prostokąty etykiet i stan efektywny | Dane wyprowadzone z kamery, viewportu, preferencji i flag; nie druga kopia kanonicznego stanu |

Wzorce istnieją w `apps/control-room/src/kernel/workspace/analysisViewPreferences.ts` oraz `useAnalysisViewPreferencesHydration.ts`: schemaVersion, walidacja i `useSyncExternalStore` z server snapshot. Wykorzystać wzorzec, bez importowania store’a innego modułu i bez dopisywania preferencji viewportu do store’a analizy.

Nie persistować pól, topologii ani kopii sesji. Preferencje lokalne nie oznaczają synchronizacji między komputerami. Zapis wyglądu do projektu lub współdzielenie widoków jest osobnym rozszerzeniem; wtedy wymagany przegląd kontraktu API/ADR.

### 3.2 Tło

- `solid` i `gradient`; subtelny neutralny gradient jako proponowane domyślne tło nowych ustawień.
- Kolory top/bottom/solid z tokenów Mocha/Latte, opcjonalna kontrola siły.
- Gradient w przestrzeni ekranu, nierotujący z kamerą, bez geometrii podłogi i bez wpływu na światło.
- Preferowany pierwszy wariant: mała generowana tekstura gradientu jako tło istniejącej sceny. Potwierdzić interpolację i przestrzeń barw w zainstalowanym Three.js. Nie dodawać drugiego canvasa ani zewnętrznych assetów.
- Odświeżenie tylko po zmianie stylu/motywu; zwolnienie zastąpionej tekstury i przywrócenie poprzedniego właściciela tła przy teardown.

### 3.3 Ramka i skala

- Odseparować `axisLines`, `majorGrid`, `minorGrid`, `ticks`, `labels`, `extents`.
- Trzy linie bazowe odpowiadają wybranym krawędziom pomiarowym; opcjonalne globalne osie zera są odrębnym oznaczeniem.
- `originMode`: `frame-center` / `world`; dla dotychczasowego zachowania jawne `frame-center`. Oznaczyć początek w HUD.
- Fizyczne pozycje i kroki 1–2–5 pozostają poprawne; ekranowa długość ticka i liczba etykiet są ograniczane.
- Normalna siatka podlega zasłanianiu; ukryte krawędzie ramki wymagają osobnego, jawnego stylu. Nie rysować całej siatki przez obiekty.
- Priorytety etykiet i wspólne strefy HUD; redukcja kolizji bez ukrywania znaczenia osi/jednostki.

### 3.4 Światło, jakość i kolory

- Jakość (DPR/AA/budżet zasobów) oddzielna od appearance.
- Wygląd geometrii: `flat` / `studio`; studio to neutralne, ograniczone światło kluczowe i wypełniające, z kontrolą kierunku/siły.
- Tryb danych ilościowych: kolory danych nie podlegają światłu, AO, Bloom ani ekspozycji. Legenda używa tego samego mapowania i przestrzeni barw.
- Wspomagające cieniowanie powierzchni pola jest wyłącznie jawną opcją. Nie obiecywać zgodności piksela z legendą po modulacji jasności.
- Przypisanie roli materiału wynika z render modelu/targetu, nie z koloru, nazwy obiektu ani rozpoznawania konkretnego backendu w komponencie UI.

Zmiany mieszczące się w istniejącej architekturze wymagają aktualizacji specyfikacji, nie automatycznie nowego ADR. Jeżeli realizacja zmieni właściciela kamery, zakres zapisu projektu lub publiczny kontrakt visualization, najpierw zastosować `adr-check` i ścieżkę OpenAPI → generator → facade → hooks.

## 4. Kolejność i pokrycie audytu

| Etap | Wynik | Ustalenia | Zależność |
|---|---|---|---|
| R0 | Powtarzalny obraz bazowy i identyfikacja materiałów | V01–V15 | Brak |
| R1 | Kontrakt i zapis preferencji, wspólne komendy | V10,V11,V15 | Odczyt obecnego stanu; nie wymaga ukończenia pomiarów R0 |
| R2 | Gradient WebGL, osie i poprawna skala | V01,V02,V03,V04,V05,V12 | R1; odbiór względem R0 |
| R3 | Układ i czytelność HUD | V04,V06,V07 | R2 |
| R4 | Materiały geometrii i realne ustawienia światła | V08,V13 | R0,R1; można przygotować niezależnie od R3 |
| R5 | Dopracowana kamera i kompletny panel ustawień | V10,V11,V14,V15 | R1–R4 |
| R6 | Kontrolowane AO i eksport | V09,V12 | R2–R5 |
| R7 | Dowody jakości, wydajności i regresji | V01–V15 | Wszystkie wcześniejsze |
| R8 | Integracja i zamknięcie | Cały zakres | Zielone wymagane bramki R7 |

Poniższe zadania definiują kryteria realizacji. Obecność kodu R1–R6 nie oznacza zaliczenia całego zakresu; aktualne wyniki R0/R7 i ograniczenia odbioru są zapisane w checkpointcie.

## 5. Zadania wykonawcze

Ścieżki z prefiksem `V/` oznaczają `apps/control-room/src/modules/viewport-3d/`. Pliki oznaczone „nowy” są propozycją nazwy; pozostałe wskazują istniejące punkty integracji.

### R0 — Ustalić reprodukcję i obraz odniesienia

**Właściciel:** prowadzący implementację.

1. Zweryfikować wybrany checkout/HEAD/status, flagi `browserFullmagConfig`, profil i źródło sesji. Przypisać różową powierzchnię i bryłę do render targetu oraz materiału.
2. Odczytać istniejące `smoke-viewport-3d.mjs`, `screenshot-viewport-3d.mjs`, `audit-viewport-3d-profile-switch.mjs` i `audit-idle-performance.mjs` w `apps/control-room/scripts/`; wykorzystać odpowiednie części zamiast tworzenia niezależnego launchera.
3. Przygotować deterministyczne scenariusze: pusty viewport, bryła z otworem nad płaszczyzną, cienki film, przesunięta domena, FDM cuboids, FEM surface, duży airbox.
4. Zapisać kamerę, źródła danych, ustawienia, motyw, viewport/DPR oraz surowe obrazy i diagnostykę. Sceny autorstwa UI mogą być fixture; nie udawać, że fixture dowodzi całej ścieżki backendowej.

**Odbiór:** ten sam scenariusz daje porównywalne kadry i wiadomo, co przedstawia każda warstwa. Jeżeli oryginalnej sceny nie można odzyskać, użyć oznaczonej sceny zastępczej i pozostawić jej dokładną przyczynę `NOT VERIFIED`.

### R1 — Kontrakt preferencji i stan efektywny

**Pliki:** `V/viewport3dStore.ts`, `V/manifest.ts`, `V/public.ts`, `V/viewport3dVisualProfile.ts`; nowe `V/viewport3dAppearancePreferences.ts` i adapter hydratacji; istniejące testy store/manifest.

1. Wydzielić typy preferencji tła, ramki i oświetlenia oraz ich walidację/defaulty. Nie przenosić kanonicznej kamery do nowego obiektu.
2. Dodać schemaVersion, ograniczenia liczb, obsługę nieznanych pól/wersji, uszkodzonego zapisu i niedostępnego storage.
3. Zapewnić zgodny pierwszy render SSR/client; hydratacja nie resetuje aktywnego gestu kamery.
4. Rozdzielić żądaną i efektywną konfigurację przy flagach diagnostycznych. Ustawienia wyłączone technicznie mają podaną przyczynę.
5. Dodać komendy resetu sekcji i otwarcia ustawień; UI i ribbon korzystają z tych samych komend.
6. Uzupełnić `docs/specs/frontend-v2/04-state-management.md` i `14-viewport-3d-module.md` o proponowane pola i zakres trwałości w momencie implementacji.

**Interfejs do następnych etapów:** jeden read-only snapshot appearance, komendy mutacji i wyprowadzony effective state.

**Odbiór:** reload przywraca preferencje; reset sekcji nie zmienia sesji, modelu ani innych sekcji; zerowy nowy transport danych. Regresje parsera/hydratacji/store po zniesieniu zakazu testów jednostkowych.

### R2 — Gradient, linie bazowe i znaczenie skali

**Pliki:** `V/layers/Viewport3DScene.tsx`, `V/hooks/useViewport3DColors.ts`, `V/viewport3dTypes.ts`, `V/layers/dimensionFrameModel.ts`, `V/layers/DimensionFrameLayer.tsx`, `V/layers/viewport3DMaterialProfile.ts`, `apps/control-room/src/design/styles/theme.css`; nowy `V/layers/Viewport3DBackground.tsx`.

1. Zastąpić pojedyncze przypięcie koloru komponentem posiadającym tło solid/gradient i jego zasoby. Zachować eksport tego samego tła.
2. Dodać jawne linie bazowe dla trzech skal i oddzielić ich generowanie od `labelsVisible`. Zachować obecne tryby floor/cage/off i extents/both.
3. Wyróżnić baselines, major i minor; dodać odpowiednie tokeny motywów. Jeśli potrzebne są szersze linie, użyć wspólnego mechanizmu ekranowej szerokości z kontrolą `resolution`, DPR i cleanup; nie polegać na dowolnej szerokości `lineBasicMaterial`.
4. Rozwiązać depth bias współpłaszczyznowej siatki w renderowaniu. Offset nie może zmieniać wyświetlanych wartości pomiarowych.
5. Dodać tryb współrzędnych i jawny opis początku. Nie zmieniać jednostek wejściowych SI.
6. Wprowadzić czytelność cienkich domen bez sztucznego skalowania osi. Gęstość zależna od projekcji nie może powodować pełnej przebudowy topologii sceny.

**Odbiór:** gradient i trzy ciągłe skale są widoczne; w trybie „tekst off” linie pozostają; współrzędne przesuniętej sceny są poprawne; solid/gradient nie zmieniają RGB powierzchni ilościowej. Screenshoty i eksport dla obu motywów, perspektywy i ortho.

### R3 — Stabilny, responsywny HUD

**Pliki:** `V/layers/DimensionFrameLayer.tsx`, `V/orientation/hudLayout.ts`, `V/orientation/hudText.tsx`, `V/orientation/OrientationHudLayer.tsx`, `V/Viewport3DModule.tsx`, `apps/control-room/src/design/styles/viewport-3d.css`; opcjonalnie nowy czysty model kolizji etykiet.

1. Obliczać rzeczywiste ekranowe bounds etykiet, zamiast oceniać czytelność wyłącznie na podstawie jednej pary punktów.
2. Układać etykiety według priorytetów i zajętych stref. Ukrywać punkty za kamerą; zachować oznaczenia osi/jednostki i wyraźną semantykę skali.
3. Dodać histerezę przy zmianie krawędzi ramki/poziomu szczegółowości, bez opóźniania gestu kamery.
4. Wspólne marginesy dla ViewCube, HSL, legendy i komunikatów; tryb kompaktowy dla małego panelu.
5. Etykiety o czytelnym kontraście, halo/podkład zgodny z motywem; kontrolki dostępne z klawiatury i z poprawnymi nazwami. Nie animować opacity trwałych paneli.

**Odbiór:** brak kolizji i urwanych oznaczeń w macierzy R7, zachowany picking i orbitowanie. Cel projektowy dla tekstu UI: kontrast co najmniej 4.5:1 na jego podkładzie; krytyczne linie odniesienia co najmniej 3:1. Rzeczywiste kolory dobrać i zmierzyć na obrazach, nie tylko przez odczyt tokenów.

### R4 — Geometria reagująca na światło, dane o chronionych kolorach

**Pliki:** `V/layers/Viewport3DLightingRig.tsx`, `V/layers/viewport3DMaterialProfile.ts`, `V/layers/PrimitiveObjectLayer.tsx`, `V/layers/FdmCuboidLayer.tsx`, `V/layers/MeshPartLayer.tsx`, `V/layers/TopologyMeshLayer.tsx`, `V/viewport3dScalarSurfaceShader.ts`, `V/viewport3dVisualProfile.ts`.

1. Sporządzić macierz faktycznie używanych materiałów i ról renderowanych targetów. Zbadać normalne, transformacje, strony powierzchni i przezroczystość dla ścieżek objętych zmianą.
2. Zaimplementować neutralne studio key/fill dla powierzchni geometrii; określić czy układ świateł jest związany z kamerą czy światem. Proponowany default modelowania: światło związane z kamerą, z możliwością zablokowania kierunku.
3. Podłączyć materiały geometrii jednolitej do wybranego modelu światła; nie ograniczyć poprawki do prymitywów, pozostawiając zrealizowane powierzchnie płaskie bez wyjaśnienia.
4. Zachować instancing FDM, cache geometrii i częstotliwość uploadów. Nie zamieniać jednej instancjonowanej warstwy na osobne meshe.
5. Tryb ilościowy wyłącza modulację koloru danych i nie zmienia palety/range. Ewentualny tryb „cieniowanie kształtu pola” jest jawny i jednolity dla wspieranych ścieżek.
6. Oddzielić preset jakości od appearance. Capture nie może niejawnie zmieniać znaczenia kolorów ani wybranego trybu światła.

**Odbiór:** na sferze/bryle z otworem widoczne normalne i krzywizna; zmiana suwaka daje efekt na wspieranej geometrii. W próbkach wnętrza powierzchni ilościowej wartości RGB odpowiadają tej samej legendzie przed/po zmianie światła, z udokumentowaną tolerancją rasteryzacji. Brak nowych pobrań pola i przebudów topologii.

### R5 — Panel ustawień i kamera

**Pliki:** `V/components/Viewport3DSettingsDialog.tsx`, `V/components/Viewport3DCameraDialog.tsx`, `V/viewport3dCameraModel.ts`, `V/layers/CameraControls.tsx`, `V/manifest.ts`, `apps/control-room/src/modules/ribbon/ribbonContributions.tsx`, `ribbonTabViews.tsx`; konsument: `kernel/visualization/CameraRegistryController.ts`.

1. Połączyć dostęp do Tła, Siatki i skali, Oświetlenia, Kamery oraz Jakości/eksportu w istniejącym interfejsie ustawień. Nie tworzyć osobnego nowego okna aplikacji.
2. Zachować skróty Frame i kamery we wstążce; prowadzą do tych samych komend i stanu co dialog.
3. Opisać Position/Target jednostką i umożliwić wygodną prezentację wartości SI. Rozróżnić FOV w stopniach, dystans i skalę ortho.
4. Sprawdzić istniejące Fit/Reset; dopracować dopasowanie zaznaczenia, punkt obrotu i near/far wyłącznie tam, gdzie wykazano brak lub problem. Nie przebudowywać sterowania dla samej zmiany wyglądu.
5. Zachować sesyjny registry, epoch/ACK oraz odrębną kamerę podglądu zapisanego datasetu. Ustalenia R1 o trwałości są wiążące.
6. Zapewnić reset sekcji, klawiaturę, focus i reduced motion.

**Odbiór:** round-trip dialog → kamera → registry → ponowne otwarcie, bez cofania nowego gestu przez stary ACK; dane odświeżają się bez resetu ujęcia; inputy mają jednostki. Niedostępna opcja ma wyjaśnienie, nie nieskuteczny suwak.

### R6 — AO, postprocessing i wiarygodny eksport

**Pliki:** `V/layers/PostProcessingLayer.tsx`, `V/layers/Viewport3DScene.tsx`, `V/Viewport3DModule.tsx`, `V/viewport3dThumbnail.ts`, `V/viewport3dVisualProfile.ts`, dialog ustawień; proponowany osobny moduł kompozycji eksportu.

1. Sprawdzić API i wersję faktycznie zainstalowanego N8AO oraz znaczenie promienia, zanim zostanie zdefiniowany parametr użytkownika.
2. AO działa w określonej skali i na wskazanej klasie geometrii. Jeżeli obecna biblioteka nie pozwala bezpiecznie oddzielić danych/HUD, wyłączyć efekt w trybie ilościowym do czasu zgodnej realizacji; pokazać stan efektywny.
3. Zdefiniować kolejność renderowania: tło → geometria i dopuszczone efekty → adnotacje/HUD bez wpływu efektów. Jeden renderer/canvas; dodatkowe render targety tylko z jawnym właścicielem i budżetem.
4. Bloom pozostawić opcjonalnym dodatkiem poza analizą ilościową. Poprawić nazwę AO, aby nie obiecywała pełnych cieni rzucanych.
5. Eksport solid/gradient obejmuje wybrane oznaczenia, skalę i legendę. Skomponować potrzebne nakładki DOM w wynik obrazu albo przenieść ich render eksportowy do współdzielonego modelu.
6. Transparentny PNG wdrożyć przez kontrolowaną ścieżkę offscreen/alpha zgodną z rendererem, bez utraty aktywnej kamery i jej kontekstu. Jeśli wymaga szerszej zmiany, jawnie wydzielić do kolejnego zakresu i nie przedstawiać jako działającej opcji.
7. Po capture przywrócić profil/preferencje i zwolnić zasoby; thumbnail musi respektować wybraną politykę wyglądu.

**Odbiór:** AO poprawia kontakt i zagłębienia, nie niszczy cienkiej geometrii i nie zmienia legendy; PNG odpowiada wybranemu widokowi. Powtarzany capture nie zwiększa trwale pamięci ani liczby zasobów.

### R7 — Weryfikacja całości

**Pliki/scenariusze:** istniejące `apps/control-room/scripts/smoke-viewport-3d.mjs`, `screenshot-viewport-3d.mjs`, `audit-idle-performance.mjs`, `audit-viewport-3d-profile-switch.mjs`; nowy dedykowany scenariusz appearance/HUD korzystający z tego samego zarządzanego środowiska.

1. Uruchomić macierz z sekcji 6, porównując z R0.
2. Odczytać exit code, błędy konsoli, proof canvasa, liczniki geometrii/tekstur/klatek i network. Artefakty muszą identyfikować źródła i stan konfiguracji.
3. Wykonać typecheck, lint z zerem ostrzeżeń, architecture/API hygiene w zgodnej recepturze, jeśli dotyczy zmiany.
4. Wykonać wymagane regresje modelu/store/kamery/materialów po odwołaniu zakazu budowania testów jednostkowych. Do tego czasu pozostają niezrealizowaną bramką; dokumentacja lub screenshots nie zastępują tych testów.
5. Review obejmuje kolory danych, jednostki, właścicieli stanu, cleanup, invalidation i poprawność różnic FDM/FEM. Nie wystarcza ocena atrakcyjności jednego kadru.

**Odbiór:** każde V01–V15 ma wynik, dowód i jawne ograniczenie; brak wymaganej bramki oznacza brak pełnego zamknięcia.

### R8 — Integracja

Po autoryzacji implementacji obowiązuje procedura worktree z AGENTS.md i `finishing-a-development-branch`: spójne zweryfikowane commity → review → push/PR → wymagane kontrole → merge → lokalny fast-forward, jeżeli bezpieczny → weryfikacja i cleanup wyłącznie własnego worktree.

Chronić istniejące dirty zmiany. Jeżeli testy, CI, uprawnienia, cudza praca lub aktywne zasoby blokują cykl, zapisać dokładny stan i przyczynę. Nie scalać niezweryfikowanej implementacji tylko dlatego, że tło wygląda poprawnie.

## 6. Macierz dowodów odbioru

| Scenariusz | Minimalny dowód |
|---|---|
| Pusta scena, solid/gradient | Gradient w canvasie i PNG; brak geometrii udającej model |
| Bryła z otworem nad powierzchnią | Czytelna orientacja powierzchni, odległość od płaszczyzny i baselines |
| Model przesunięty od globalnego zera | World/frame-center i Lx/Ly/Lz mają poprawne, rozróżnione znaczenie |
| Cienki film / wydłużona domena | Brak fałszywego rozciągania Z, rozsądne ticki i widoczna skala |
| Perspektywa, ortho, widoki osiowe | Brak znikających osi, skoków targetu i nieczytelnego FOV/scale |
| Orbita przez ćwiartki i widok spod podłogi | Stabilny wybór krawędzi, spójne hidden edges, brak osieroconego tekstu |
| Mocha/Latte, DPR 1/2 | Kontrast i rozmiar tekstu; brak kolorów wpisanych lokalnie poza tokenami |
| Viewport 1200×800 i 480×320 CSS px | Brak kolizji HUD; tryb kompaktowy zachowuje jednostki i orientację |
| FDM, FEM, primitive preview | Jedno UI; każda zmieniona ścieżka materiału ma osobny dowód |
| Scalar/HSL/vector, airbox, clip | Ochrona koloru i legendy; poprawne zasłanianie i przezroczystość |
| Zmiana stylu/światła/HUD | Zero nowych requestów pól i zero rebuildów topologii z tego powodu |
| Idle, orbit, resize | Zero ciągłych klatek w idle po ustaniu pracy; zmierzone koszty CPU/GPU interakcji |
| 20 przełączeń 3D/2D i efektów | Liczba zasobów wraca do ustalonego baseline/cache; brak monotonicznego wzrostu |
| Reload, nowa sesja, dataset | Preferencje zgodne z zakresem; brak wycieku kamery między tożsamościami |
| Capture i błąd capture | Poprawny obraz i przywrócony stan; cleanup także po błędzie |

Każdy browser proof: widoczny canvas, `gl.isContextLost() === false`, `drawingBufferWidth > 0`, `drawingBufferHeight > 0`. Dodatkowo sprawdzenie obrazu i interakcji; te cztery asercje same nie wystarczą do oceny HUD.

Budżet wydajności należy ustalić na podstawie R0 dla tych samych źródeł, danych, DPR i urządzenia. Plan nie deklaruje niezmierzonego wzrostu FPS ani stałego limitu ms dla każdego GPU. Zachować obecną jakość danych; nie maskować kosztu zmniejszaniem liczby glyphów lub wyłączaniem warstw.

## 7. Recepty i ograniczenia wykonania

W tym zadaniu dokumentacyjnym nie uruchomiono żadnej z poniższych operacji.

Przyszły build aplikacji wyłącznie w grupie Compose wybranego checkoutu, przez launcher/resolver. Przed startem odczytać aktualny `justfile`, reguły backendu i skill `fullmag-docker-build`. Z tego samego wybranego checkoutu:

```powershell
just docker-dev-toolchain
just docker-dev "<absolutna-ścieżka-wybranego-worktree>" <wolny-port-loopback>
just docker-dev-browser-qa "<absolutna-ścieżka-wybranego-worktree>" <ten-sam-port>
```

Ostatnia recepta istnieje w audytowanym `justfile:55–60`; sama jej obecność nie dowodzi, że obejmuje planowaną macierz HUD. Scenariusz należy dołączyć do zgodnej ścieżki QA, nie zastępować jej hostowym buildem lub ręcznym kontenerem.

Znane skrypty npm: `typecheck`, `lint`, `check:architecture-hygiene`, `check:api-hygiene`, `smoke:viewport-3d`, `audit:idle-performance`, `audit:viewport-3d-profile-switch`, `validate:viewport-proof`. Ich nazwy nie stanowią zgody na uruchomienie na hoście; wykonanie i output muszą pozostać w granicach zarządzanej recepty.

Obowiązuje czasowy zakaz kompilowania testów jednostkowych i zadań, których celem jest taka kompilacja. Plan nie odwołuje tego zakazu i nie proponuje obejścia. Pełny merge czeka na wymagane dowody albo jawną zmianę bramki przez użytkownika; nie trzeba odwoływać zakazu, aby zakończyć obecne zadanie audytu i planu.

## 8. Wycofanie zmian i rozszerzenia

Każdy etap powinien zachowywać bezpieczny preset: Solid, dotychczasowy tryb frame-center, flat oraz AO/Bloom off. Reset preferencji nie usuwa modelu, wyników ani sesji. Rollback schematu preferencji nie może usuwać obcych kluczy storage.

Po podstawowym wdrożeniu można osobno rozważyć: cienie kontaktowe, lepszą prezentację clipping/cutaway, trwałe zapisane ujęcia projektu i bardziej rozbudowany eksport publikacyjny. Te rozszerzenia nie mogą stać się warunkiem uzyskania prostego gradientu i czytelnych osi.

## 9. Status pierwotnego przekazania dokumentacji

- [x] Audyt bieżących źródeł `master` i dwóch obrazów użytkownika.
- [x] Ponowny odczyt zapisanego audytu i sprawdzenie wniosków przed planem.
- [x] Plan z plikami, zależnościami, właścicielami stanu i kryteriami odbioru.
- [ ] R0–R8: implementacja, dowody runtime i integracja.

Pierwotny etap dostarczył dokumenty. Użytkownik następnie zlecił implementację; aktualny stan aplikacji, dowody i niezaliczone bramki określa checkpoint, bez zmiany kryteriów tego planu.
