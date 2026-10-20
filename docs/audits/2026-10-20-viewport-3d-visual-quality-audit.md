# Audyt jakości wizualnej viewportu 3D: głębia, HUD, skala, światło i kamera

Data: 20.10.2026. Status: **audyt źródeł i obrazów użytkownika; bez implementacji**.

## 1. Wniosek

Viewport potrzebuje przede wszystkim spójnych wskazówek przestrzennych: subtelnego gradientu tła, ciągłych linii odniesienia pod podziałkami, czytelnej hierarchii siatki oraz cieniowania geometrii. Dodanie samych efektów postprocessingu nie rozwiąże problemu. W obecnej implementacji część powierzchni jest celowo niezależna od światła, a podziałki i etykiety mają różne reguły zasłaniania.

Rekomendowany pierwszy zakres to **gradient + ciągłe osie ramki + czytelniejszy HUD**, a następny to rozdzielenie sposobu prezentacji geometrii i danych naukowych oraz użyteczne ustawienia oświetlenia. Kamera, ViewCube, siatka pionowa, AO i eksport już mają implementację; należy je uzupełnić i uporządkować.

## 2. Zakres, tożsamość i granice dowodów

- Checkout: `C:\git\fullmag\fullmag`, branch `master`.
- HEAD podczas audytu: `88a9b68d29ec173a0b1f1b8750c126da022b0244`.
- `git status --short --ignore-submodules` przed zapisem dokumentów: zmodyfikowane wyłącznie `scripts/docker_volume_activation_reconcile.py` i `scripts/docker_volume_stop_unadmitted.py`. Nie należą do tego zadania.
- Podczas pracy pojawiły się również cudze zmiany w `SimulationStartupOverlay.tsx`, `simulationPreparationModel.ts`, `docker_startup.rs`, `live_scene_preparation.rs` i `scheduler.rs`. Nie były edytowane w tym zadaniu. HEAD pozostał bez zmian; odciski źródeł viewportu są zapisane w sekcji 10.
- Pełny `git status --short` zakończył się błędem dostępu do `.git/modules/external_solvers/3`. Stan wnętrza submodułów: **NOT VERIFIED**.
- Nie wykonano fetch, pull, checkout, commita, buildu, testów jednostkowych ani restartu aplikacji.
- Audyt dotyczy obecnych źródeł Control Room. Nie ustalono, z jakiego SHA, profilu i ustawień pochodzi działająca aplikacja na pierwszym obrazie.
- **Potwierdzone w źródłach** oznacza obecność konkretnej ścieżki kodu, nie potwierdzenie jej działania w przeglądarce.
- **Obserwacja obrazu** opisuje wyłącznie dostarczony kadr. **Hipoteza** wymaga reprodukcji. **Propozycja** nie jest dostarczoną funkcją.
- Browser/WebGL, rzeczywisty FPS, pamięć GPU, poprawność eksportu w uruchomionej aplikacji i kwalifikacja FDM/FEM: **NOT VERIFIED**.

Materiały użytkownika:

1. Fullmag: `codex-clipboard-16e052ae-93b0-416c-8a51-0d3da372e66e.png` — różowa bryła z otworem, rozległa różowa powierzchnia, ciemne tło, słabo powiązane przestrzennie podziałki.
2. Referencja 3ds Max: `codex-clipboard-11d6a8e5-adba-4923-b8d6-e3cfae264d83.png` — spokojne szare tło, perspektywiczna siatka i wyróżnione ciągłe osie. Użytkownik wskazał subtelny gradient jako docelowy charakter tła.

Nie można z pierwszego kadru ustalić, czy różowa płaszczyzna jest obiektem, airboxem, przekrojem czy inną warstwą. Nie należy jej automatycznie usuwać, zmniejszać opacity ani traktować jako dekoracyjnej podłogi. Nie można też przypisać płaskiego wyglądu wyłącznie kamerze lub brakowi normalnych.

## 3. Co już istnieje

| Obszar | Stan w źródłach | Konsekwencja |
|---|---|---|
| Ramka wymiarowa | `off`, `floor`, `cage`; podziałki, wymiary całkowite, jednostki auto/nm/µm/mm/m | Rozwijać istniejący model, bez drugiej siatki FDM/FEM |
| Linie siatki | Oddzielne major/minor; ograniczenia liczby segmentów | Problem dotyczy też widoczności i hierarchii, nie samej obecności |
| Etykiety | Rozmiar ekranowy, halo, przerzedzanie liczb | Zachować te mechanizmy i uzupełnić układ/kontrast |
| Tło | Jednolity kolor sceny i token CSS | Brak gradientu sceny w analizowanej ścieżce |
| Profile jakości | Interactive Lite, Interactive, Balanced, Figure, Capture | Nie utożsamiać jakości obrazu z trybem oświetlenia |
| Oświetlenie | `Viewport3DLightingRig` i profile materiałów | Samo dodanie suwaka światła może nie zmienić części powierzchni |
| Efekty | AO, Bloom, antialiasing | AO i Bloom są domyślnie wyłączone; nie są brakującymi funkcjami |
| Orientacja | ViewCube oraz referencja HSL | Istniejący HUD wymaga wspólnego planu rozmieszczenia |
| Eksport | PNG bezpośrednio z canvasa | Tło i ważne oznaczenia muszą mieć określony udział w eksporcie |

Podstawa: [E01–E12] poniżej. Szczegółowe ustalenia o kamerze i materiałach zawiera sekcja 6.

## 4. Mapa dowodów źródłowych

Ścieżki są względem repozytorium, zakresy wierszy odnoszą się do wskazanego HEAD i odczytanych plików roboczych. Skrót `V/` oznacza `apps/control-room/src/modules/viewport-3d/`.

| ID | Źródło i wiersze | Istotny dowód |
|---|---|---|
| E01 | `V/layers/Viewport3DScene.tsx:2043–2044` | `<color attach="background" args={[colors.background]} />` i istniejący lighting rig |
| E02 | `V/viewport3dVisualProfile.ts:39–152,173–216` | Wszystkie obecne profile wybierają `lighting: "minimal"` i `toneMapping: "none"`; canvas ma `alpha: false` |
| E03 | `V/layers/dimensionFrameModel.ts:70–84,154–229,232–281` | Osobne bufory siatki, ticków i wymiarów; podłoga na `bounds.min.z`; brak osobnego bufora ciągłych osi ramki |
| E04 | `V/layers/dimensionFrameModel.ts:366–411,413–508` | Dobór krawędzi względem kamery; ticki od `start` do `end`; etykieta `formatDimensionFrameTickValue(value - center, unit)` |
| E05 | `V/layers/DimensionFrameLayer.tsx:67–76,125–183,198–221` | Fonty 11/12 px; osobne geometrie; linie `depthTest`, `depthWrite={false}`, `lineBasicMaterial` |
| E06 | `V/layers/DimensionFrameLayer.tsx:357–410,456–472,498–527` | Rozmieszczenie etykiet na klatkę; przerzedzanie 1/2/5; tekst `depthTest={false}` |
| E07 | `V/layers/viewport3DMaterialProfile.ts:47–100` | Dla minimal: major opacity 0.26, minor 0.14, tick 0.4, label 0.76; odrębna siła shade powierzchni |
| E08 | `V/layers/Viewport3DScene.tsx:1071–1095,1666–1681` | Podłączenie ramki, osobne flagi linii/etykiet, OrientationHud i postprocessingu |
| E09 | `apps/control-room/src/kernel/browserFullmagConfig.ts:99–127,147–168` | Flagi diagnostyczne mogą wyłączyć ramkę, jej linie, orientację i postprocessing |
| E10 | `V/layers/PostProcessingLayer.tsx:1–41` | Jeden composer, N8AO `aoRadius={0.5}`, `intensity={2.5}`, `halfRes`; Bloom threshold 0.5/intensity 1.2 |
| E11 | `V/orientation/hudLayout.ts:1–30` | Stałe marginesy kotwic ViewCube 104 px i HSL 96 px; brak wejściowych stref kolizji |
| E12 | `V/Viewport3DModule.tsx:1361–1379` | Eksport: `canvas.toDataURL("image/png")` |
| E13 | `apps/control-room/src/modules/ribbon/ribbonContributions.tsx:3394–3520` | Istniejący Frame: Floor, Floor + vertical, Off, Tick scales, Overall size, Both, gęstość, etykiety i jednostki |
| E14 | `V/viewport3dStore.ts:165–175` | Domyślne `floor`, `ticks`, `auto`; AO/Bloom off |
| E15 | `V/hooks/useViewport3DColors.ts:34–108`; `apps/control-room/src/design/styles/theme.css:10,104–106,122,215–217` | Kolory i HUD pochodzą z tokenów Mocha/Latte |
| E16 | `V/layers/dimensionFrameModel.test.ts:1–207` | Istnieją testy jednostek, kroków 1–2–5, wyboru ścian, ticków i wymiarów; nie uruchamiano ich |

## 5. Ustalenia i rekomendacje

Priorytet P1 oznacza podstawową czytelność lub ryzyko błędnej interpretacji; P2 — jakość pracy i powtarzalność; P3 — dodatki po zamknięciu fundamentów. To priorytety proponowanego zakresu, nie potwierdzone awarie runtime.

### V01 — Jednolite tło daje za mało wizualnego odniesienia [P1, źródła + obraz]

`scene.background` otrzymuje jeden kolor [E01]. Obraz użytkownika pokazuje jednolitą, bardzo ciemną przestrzeń wokół geometrii. Proponuję neutralny gradient pionowy: ciemniejsza góra, łagodnie jaśniejszy dół, bez mocnego pasa horyzontu. Kolory jako nowe tokeny Mocha/Latte; regulacja siły i powrót do tła jednolitego.

Gradient jest wskazówką percepcyjną, nie fizycznym efektem perspektywy i nie dostarcza sam informacji o odległości obiektu. Powinien współdziałać z siatką, przesłanianiem i cieniowaniem.

**Pułapka implementacyjna:** gradient CSS pod obecnym canvasem nie będzie widoczny: canvas jest nieprzezroczysty, a scena wypełnia tło [E01–E02]. Ponadto nie trafi do obecnego eksportu PNG [E12]. Docelowo tło renderowane przez istniejący renderer WebGL, bez drugiego canvasa i bez zależności od HDRI.

**Odbiór:** gradient widoczny przy pustej scenie i eksporcie, stabilny przy orbitowaniu i resize, możliwy do wyłączenia, bez zmiany wartości kolorów danych.

### V02 — Podziałki nie mają gwarantowanej ciągłej linii bazowej [P1, źródła]

Model posiada `majorLines`, `minorLines`, `majorTickLines`, `minorTickLines` i `extentLines`, lecz nie osobne linie bazowe trzech skal [E03–E04]. Siatka może przypadkowo utworzyć linię na granicy, ale nie gwarantuje pełnego połączenia podziałek na wybranej krawędzi. W domyślnym `ticks` linie wymiarów całkowitych są puste; tryb `extents` nie zastępuje osi skali.

**Propozycja:** jawny zestaw trzech linii bazowych X/Y/Z odpowiadających dokładnie krawędziom wybranym dla ticków. Ich widoczność niezależna od linii minor i od przełącznika tekstu. Nie należy mylić tych linii na obwiedni z osiami przechodzącymi przez globalne zero.

**Odbiór:** każda widoczna skala ma ciągłą podstawę; brak „wiszących” ticków także przy nierównych rozmiarach obwiedni i po zmianie ćwiartki kamery.

### V03 — Siatka jest słaba i może być zasłaniana przez powierzchnie [P1, źródła; przyczyna kadru pozostaje hipotezą]

Linie mają `depthTest=true`, a podłoga leży na dolnej granicy domeny. Przezroczystości major/minor 0.26/0.14 tworzą bardzo delikatny raster [E03,E05,E07]. Powierzchnia współpłaszczyznowa lub zasłaniająca siatkę może utrudniać jej odczyt. Z kadru nie da się rozstrzygnąć, czy występuje z-fighting, normalne zasłanianie czy wyłączona warstwa.

**Propozycja:** osobna hierarchia: linie bazowe > major > minor. Zwykła siatka powinna respektować zasłanianie; opcjonalne ukryte krawędzie ramki mogą być słabsze/przerywane. Unikać globalnego `depthTest=false`, które narysuje siatkę przez wszystkie obiekty. Rozwiązać współpłaszczyznowość w przestrzeni renderera, bez zmiany współrzędnych fizycznego modelu.

**Odbiór:** bliska powierzchnia i obiekt nad podłogą pozostają rozróżnialne; siatka nie wygląda jak mesh solvera i nie przykrywa mapy pola.

### V04 — Długość ticków i gęstość siatki słabo adaptują się do projekcji [P2, źródła]

Długość ticka wynosi 0.024/0.012 największego wymiaru sceny, a krok siatki wylicza się z największej rozpiętości. Etykiety mają rozmiar ekranowy i przerzedzanie, lecz model nie otrzymuje wymiarów viewportu do dobrania gęstości [E03,E04,E06]. Cienkie filmy i bardzo wydłużone obiekty wymagają szczególnej kontroli.

**Propozycja:** zachować fizyczne położenie i kroki 1–2–5; ograniczać ekranową długość ticków i odstęp widocznych linii. Dodać histerezę przełączeń poziomu szczegółowości. W pierwszym etapie zachować wspólną skalę odniesienia; ewentualny osobny krok osi musi być jawnie czytelny. Nie rozciągać Z, aby sztucznie „poprawić” głębię.

**Odbiór:** zoom nie tworzy migoczącego rastra ani gęstego grzebienia; cienka geometria zachowuje prawdziwe proporcje.

### V05 — Zero skali oznacza środek obwiedni, ale etykieta tego nie wyjaśnia [P1, źródła]

Tekst ticka powstaje z `value - center`, natomiast podpis to samo `x/y/z` i jednostka [E04]. Przesunięty model może więc wyglądać jak wycentrowany w globalnym zerze. To ryzyko interpretacji, niezależne od estetyki.

**Propozycja:** jawny tryb „współrzędne świata” albo „względem środka ramki”, z oznaczonym początkiem i jednostkami. Zachować dotychczasowy tryb jako jawny tryb zgodności, bez cichej zmiany interpretacji zapisanych widoków. Oddzielić współrzędne od wymiarów Lx/Ly/Lz.

**Odbiór:** na obiekcie odsuniętym od zera użytkownik rozpoznaje użyty układ; przesunięcie geometrii zmienia odpowiednie wartości świata.

### V06 — Tekst i linie mają niespójną politykę głębi [P1, źródła]

Tekst jest rysowany bez testu głębi, linie z testem [E05–E06]. Możliwe są czytelne liczby przy niewidocznym odcinku, do którego się odnoszą. Aktualny kod dba o rozmiar i odstęp tekstu, ale nie stanowi pełnego systemu rozwiązywania kolizji etykiet.

**Propozycja:** traktować linię, tick i etykietę jako jedno powiązanie. Priorytety: nazwa osi/jednostka, zero/ekstrema, pozostałe liczby. Odrzucać etykiety za kamerą/poza kadrem; uwzględnić prostokąty innych elementów HUD i sąsiednich etykiet. Przewidywalna polityka ukrytych krawędzi, bez gwałtownych przeskoków.

**Odbiór:** brak etykiet osieroconych, nakładających się i uciętych przy testowanych kamerach; linia bazowa pozostaje przy wyłączonym tekście.

### V07 — Orientacja i dane HUD potrzebują wspólnego układu [P2, źródła; kolizje runtime niezweryfikowane]

ViewCube i HSL mają kotwice o stałych marginesach [E11]. Układ nie dostaje zajętych obszarów legend, skali i innych nakładek. Na wąskim panelu rezerwy miejsca powinny być ustalane wspólnie.

**Propozycja:** jeden model stref ekranowych dla orientacji, legend, statusu i skali. Tryb kompaktowy przy małym rozmiarze, czytelne nazwy dostępności, obsługa klawiatury i reset. Referencja HSL pozostaje dostępna wtedy, gdy pomaga interpretować aktywny sposób kolorowania.

**Odbiór:** Mocha/Latte, DPR 1/2, szeroki i wąski viewport; ważne oznaczenia nie pokrywają się i nie przechwytują przypadkowo gestów sceny.

### V08 — Światło wymaga rozdzielenia geometrii od koloru danych [P1, źródła]

Profile wizualne już mają pole `lighting`, ale wszystkie aktualne wartości presetów to `minimal` [E02]. Profil materiałów oddziela powierzchnie i glyphy [E07]. Nie należy wdrażać efektu „studio” przez jednolite pomnożenie wszystkich kolorów przez intensywność światła.

**Propozycja:** niezależne wybory „wygląd geometrii” i „jakość/wydajność”. Materiały geometrii mogą reagować na normalne i neutralne światło; tryb ilościowy zachowuje zgodność koloru z legendą. Wspomagające cieniowanie pola tylko jako jawny tryb z czytelną informacją, że jasność obrazu nie jest wtedy bezpośrednią wartością legendy.

**Odbiór:** bryła z otworem, sfera, cienki dysk i płaskie ściany pokazują orientację powierzchni; zmiana światła nie zmienia legendy ani nie zabarwia ilościowej mapy pola.

### V09 — AO/Bloom istnieją, lecz mają stałe parametry i szeroki zasięg [P2, źródła]

N8AO ma stały promień 0.5 i intensywność 2.5, Bloom intensywność 1.2 [E10]. Nie ma w tej warstwie powiązania promienia z fizyczną skalą domeny ani rozdzielenia efektu na geometrię, dane i HUD. Konkretny wpływ i jednostkę promienia w zainstalowanym N8AO należy sprawdzić przed zmianą; sama liczba 0.5 nie dowodzi błędu runtime.

**Propozycja:** umiarkowane AO dla geometrii, jawny suwak siły i promień związany z kontrolowaną skalą renderowania lub ekranem. HUD/legenda bez AO/Bloom. Bloom pozostawić dodatkiem demonstracyjnym, domyślnie wyłączonym w analizie. AO nie nazywać zamiennie pełnymi cieniami rzucanymi.

**Odbiór:** skale nm/µm/mm/m, obiekt blisko innej powierzchni, krawędzie cienkiego filmu; bez czarnych obwódek, utraty małych detali i zmiany barw legendy.

### V10 — Flagi diagnostyczne mogą zmienić widoczność mimo wyboru użytkownika [P2, źródła]

Ramka, linie major/minor, tekst i postprocessing mają osobne flagi browser config [E08–E09]. Nie oznacza to, że są wyłączone w sesji użytkownika.

**Propozycja:** w diagnostyce widoku pokazywać requested/effective dla warstw i przyczynę wyłączenia. Nie usuwać flag bez ustalenia ich zastosowań diagnostycznych. W zwykłych ustawieniach nie prezentować przełącznika jako działającego, gdy funkcja jest faktycznie zablokowana.

### V11 — Ustawienia są rozproszone; potrzebny jeden czytelny punkt wejścia [P2, źródła + propozycja UX]

Frame ma już rozbudowane menu we wstążce [E13]; efekty mają osobny dialog; kamera ma własną obsługę. „Brak ustawień” nie jest właściwym opisem całego produktu. Brakuje spójnego doświadczenia strojenia przestrzeni.

**Propozycja:** istniejący dialog widoku rozwinąć o sekcje „Tło”, „Siatka i skala”, „Oświetlenie”, „Kamera”, „Jakość i eksport”, z resetem sekcji i presetem domyślnym. Używać wspólnego rejestru komend. Nie wprowadzać drugiego właściciela danych kamery ani bezpośrednich requestów z kontrolek.

### V12 — Eksport musi odtwarzać świadomie wybrany widok [P2, źródła]

Obecny zapis pobiera wyłącznie canvas [E12]. Nakładki DOM nie stają się automatycznie częścią PNG, a zmiana profilu na Capture może zmieniać parametry obrazu.

**Propozycja:** jawne opcje tło jednolite/gradient/przezroczyste oraz uwzględnienie legendy, jednostek i orientacji. Zdefiniować spójny eksport canvasa i potrzebnych adnotacji, zamiast zakładać, że zrzut UI jest gotowym rysunkiem. Transparentny eksport wymaga osobnej obsługi, ponieważ canvas aktualnie powstaje z `alpha:false`.

**Odbiór:** porównanie viewportu i PNG na tym samym stanie, jednostki i kolory zgodne; zakończenie capture przywraca preferencje i zasoby.

### V13 — Nowe efekty nie mogą uruchomić stałego renderowania [P1 jako warunek wdrożenia]

Specyfikacje wymagają jednej sceny FDM/FEM, renderowania na żądanie i jawnego zwalniania zasobów. Gradient, zmiana światła lub układu HUD powinny unieważniać tylko prezentację; nie mogą przebudowywać topologii ani ponownie pobierać pól.

**Odbiór:** po ustaniu interakcji nie ma ciągłych klatek; przełączanie 3D/2D, motywu i efektów nie zwiększa bez końca liczby tekstur/materialów/render targetów; zdrowy WebGL i niezerowy drawing buffer.

## 6. Oświetlenie, materiały i kamera — uzupełnienie źródłowe

### Co rzeczywiście oświetla scenę

`resolveViewport3DLightingRig` zwraca tylko białe ambient light: intensywność 0.6 przy `minimal`, 0.72 dla pozostałych wartości; `directional: []`, `hemisphere: null`. Źródło: `V/layers/Viewport3DLightingRig.tsx:26–59`. W połączeniu z E02 oznacza to, że obecne presety nie zapewniają kierunkowego modelowania kształtu przez ten rig.

Istotne ścieżki materiałów:

| Ścieżka | Dowód | Wniosek |
|---|---|---|
| Prymityw przed uzyskaniem właściwej powierzchni | `V/layers/PrimitiveObjectLayer.tsx:211` — `meshBasicMaterial` | Samo directional light nie nada mu cieniowania |
| Powierzchnia cuboid FDM | `V/layers/FdmCuboidLayer.tsx:1121–1141` — `new MeshBasicMaterial`, kolory instancji | Oświetlenie sceny nie steruje tą powierzchnią |
| Powierzchnia skalarna | `V/layers/MeshPartLayer.tsx:510`; `V/viewport3dScalarSurfaceShader.ts:492–509` | Paleta jest mnożona przez cieniowanie o stałym kierunku w przestrzeni widoku |
| Figure/Capture | `V/layers/viewport3DMaterialProfile.ts:50–65` | `shadeStrength` wynosi 0; w innych profilach 0.45 |

Istotny fragment własnego shadera:

```glsl
vec3 base = bad ? vec3(0.85, 0.0, 0.85) : paletteColor(t);
vec3 n = normalize(vNormalView) * (gl_FrontFacing ? 1.0 : -1.0);
float ndl = clamp(dot(n, normalize(vec3(0.35, 0.55, 0.75))) * 0.5 + 0.5, 0.0, 1.0);
vec3 shaded = base * mix(1.0, 0.55 + 0.75 * ndl, fmShadeStrength);
```

To potwierdza **niespójne źródła cieniowania**, a nie ogólny brak cieniowania całej aplikacji. Wdrożenie V08 wymaga macierzy materiałów: prymitywy, mesh z kolorem jednolitym, scalar, HSL/vector i airbox; shaderów danych nie wolno masowo zamienić na PBR.

### V14 — Kamera jest rozbudowana, lecz brakuje jawnych jednostek i spójnej prezentacji [P2]

- `V/layers/CameraControls.tsx:116,1199` — obsługa orbit/pan/zoom i OrbitControls.
- `V/manifest.ts:229–264` — komendy kamery, w tym otwarcie dialogu; istnieją Fit/Reset i przełączanie projekcji.
- `V/components/Viewport3DCameraDialog.tsx:243–350` — pozycja, target, yaw/pitch/roll, FOV i skala ortho oraz Apply.
- `V/components/Viewport3DCameraDialog.tsx:373–386` — pola wektorowe podpisane tylko X/Y/Z; brak jednostki przy tych inputach.

**Rekomendacja:** doprecyzować jednostki świata przy Position/Target, stopnie przy kątach i definicję skali ortho. Dodać łatwo dostępne „dopasuj scenę”/„dopasuj zaznaczenie” zgodnie z faktycznym zakresem istniejących komend, jawny punkt obrotu oraz reset parametrów. Nie duplikować funkcji już obecnych. Presety FOV, zapisane ujęcia i przejścia kamery są rozszerzeniami po sprawdzeniu istniejącego zachowania; zachować reduced motion.

**Odbiór:** pozycja i target są jednoznaczne w SI i wybranej jednostce prezentacji; przełączenie perspektywa/ortho nie gubi obiektu; aktywny gest nie zostaje cofnięty przez późny ACK; odświeżenie danych nie resetuje ujęcia.

### V15 — Trwałość ustawień wymaga jawnego zakresu [P2]

Efekty i profil mają wartości startowe i metody zmieniające snapshot w pamięci `V/viewport3dStore.ts:154–180,400–420,550–575`. W analizowanej ścieżce nie znaleziono trwałego zapisu tych preferencji. Nie jest to dowód braku wszelkiej persystencji w aplikacji.

Kamera aktywnej sesji już ma właściciela: `apps/control-room/src/kernel/KernelProvider.tsx:172` i `kernel/visualization/useVisualizationStateResource.ts:22` wiążą ją z zasobem sesji. `kernel/visualization/CameraRegistryController.ts:254,321,485` realizuje opóźniony zapis i flush, w tym po okresie bezczynności oraz przy ukrywaniu/opuszczaniu strony. Nie zastępować tego bezpośrednim zapisem z dialogu.

Kamera zapisanego datasetu używa `V/hooks/useSavedViewportCamera.ts:82,209` i cache’u w pamięci dla maksymalnie ośmiu identyfikatorów. `V/hooks/useViewport3DSceneModel.ts:3790` wybiera odpowiednią ścieżkę. Utrwalenie kamery datasetu jest odrębną zmianą kontraktu, nie skutkiem dodania gradientu.

**Rekomendacja:** osobno sklasyfikować preferencje użytkownika (tło, HUD, światło, jakość), stan sesji (kamera) oraz stan zapisanego widoku/datasetu. Dodać wersjonowany, walidowany zapis preferencji i reset bez zapisywania pól/topologii. Eksport obrazu może otrzymać snapshot wyglądu bez tworzenia nowej kanonicznej kopii kamery.

**Odbiór:** restart frontendu odtwarza preferencje; nowa sesja nie dziedziczy cudzej kamery; uszkodzony zapis daje bezpieczny domyślny widok, a pierwszy render klienta pozostaje zgodny z SSR.

## 7. Docelowy charakter wizualny

| Element | Rekomendowany kierunek | Czego unikać |
|---|---|---|
| Tło | Subtelny neutralny gradient, bez wyraźnego horyzontu, opcja Solid | Mocna winieta, kolorowy HDRI, tło zmieniające barwy danych |
| Podłoga odniesienia | Linie major/minor i wyraźne osie, łagodne wygaszanie dalekiej siatki po pomiarze | Dodanie nieprzezroczystej „podłogi” zasłaniającej model |
| Ramka | Trzy ciągłe skale, jednoznaczny początek, oddzielne wymiary całkowite | Uznawanie każdej skali ramki za oś globalnego zera |
| Materiały geometrii | Neutralne cieniowanie, kontrolowany kontrast krawędzi i refleks | Płaska plama bez wskazówki orientacji powierzchni |
| Wyniki | Wierność mapy kolorów i zgodność z legendą | Domyślny Bloom, barwne światła, mgła zmieniająca wynik |
| Kamera | Zachowane proporcje, czytelne projection/FOV/target, przewidywalny Fit | Automatyczne rozciąganie Z i reset pozycji przy odświeżeniu |
| HUD | Hierarchia informacji, ekranowy rozmiar, marginesy i strefy | Wszystkie widgety jednocześnie w narożnikach bez kontroli kolizji |

Na dalszy etap P3 pozostawić: kontrolowane cienie kontaktowe, clipping/cutaway jako narzędzie eksploracji, zapisane kompozycje widoku i rozszerzony eksport. Depth of field, motion blur, lens flare i silna mgła nie są domyślnymi narzędziami analizy naukowej; nie wchodzą do proponowanego pierwszego wdrożenia.

## 8. Odniesienie do 3ds Max i Three.js

Dokumentacja Autodesk opisuje konfigurowalne kolory górny/dolny gradientu oraz tło jednolite. Wspomina też wyjątki związane z trybem wyświetlania, w tym Wireframe. Dlatego drugie zdjęcie jest referencją kompozycji i osi, a nie dowodem dokładnego algorytmu gradientu użytego w tej konkretnej sesji. Kierunek użytkownika — delikatny gradient — pozostaje rekomendacją dla Fullmag. [Autodesk: Background Panel](https://help.autodesk.com/cloudhelp/2024/ENU/3DSMax-Customizing/files/GUID-D1419AE6-1CDE-44FC-8D46-E77F8F4DD2D0.htm).

Autodesk rozdziela ustawienia oświetlenia, cieni i AO, a światło domyślne może służyć czytelności modelowania. Wniosek projektowy dla Fullmag: mały zestaw kontrolowanych opcji geometrii zamiast mnożenia dekoracyjnych efektów. [Autodesk: Active Viewport Settings](https://help.autodesk.com/cloudhelp/2024/ENU/3DSMax-Basics/files/GUID-E7FB1028-2566-4B32-801A-30079978ECDF.htm).

`MeshBasicMaterial` nie reaguje na oświetlenie. Three.js wymaga też świadomej konwersji przestrzeni barw; własne shadery mają własne obowiązki dotyczące wyjścia. Przy wdrożeniu należy sprawdzić wersję faktycznie rozwiązaną w lockfile. Manifest audytowanego frontendu deklaruje `three: ^0.186.1`; aktualna dokumentacja internetowa nie jest dowodem zgodności każdej funkcji z instalacją. [Three.js: MeshBasicMaterial](https://threejs.org/docs/pages/MeshBasicMaterial.html), [Three.js: Color Management](https://threejs.org/manual/pages/color-management.html).

## 9. Weryfikacja wymagana przed uznaniem poprawek za gotowe

1. Odtworzyć scenę z pierwszego kadru lub równoważny przypadek; zapisać źródła, rzeczywisty profil, ustawienia, projekcję, rozmiar canvasa, DPR, widoczne warstwy i materiał różowej powierzchni.
2. Porównać ten sam kadr przed/po: pusty viewport, bryła z otworem nad powierzchnią, cienki film, przesunięta domena, duży airbox i zbliżenie.
3. Sprawdzić perspektywę i ortho, widoki osiowe, orbitę przez wszystkie ćwiartki, resize, Mocha/Latte i DPR 1/2.
4. Wykonać odpowiednie regresje modelu ramki, stanu i kamery po zniesieniu obowiązującego zakazu kompilowania testów jednostkowych. Nie obchodzić tego zakazu zmianą nazwy recepty.
5. Browser smoke musi potwierdzić widoczny canvas, `gl.isContextLost() === false`, drawing buffer o niezerowych wymiarach oraz czytelność konkretnego HUD. Sam niepusty canvas nie dowodzi jakości.
6. Sprawdzić zgodność mapy pola i legendy, renderowanie na żądanie, stabilność kamery oraz brak zmian topologii/requestów pól po edycji stylu.
7. Sprawdzić export/capture i zwalnianie zasobów. Wszystkie buildy wyłącznie w przypisanej grupie Compose przez istniejącą zarządzaną ścieżkę.

Stan tych bramek w tym audycie: **NOT VERIFIED — nie uruchamiano aplikacji ani testów**. Dokument jest podstawą refaktoryzacji, a nie raportem jej wykonania.

## 10. Odcisk źródeł audytu

SHA-256 surowych plików roboczych odczytanych 20.10.2026. Hashe nie identyfikują uruchomionego kontenera.

| Plik | SHA-256 |
|---|---|
| `apps/control-room/src/modules/viewport-3d/layers/Viewport3DScene.tsx` | `760e6e018839598df4bd878019317d846f7aefb800b83f4618134081d51eace9` |
| `apps/control-room/src/modules/viewport-3d/layers/dimensionFrameModel.ts` | `7fea34e9bd2883a16f527ad4edb330db237201048a84a24ff59e2c124f877e60` |
| `apps/control-room/src/modules/viewport-3d/layers/DimensionFrameLayer.tsx` | `e90a8a701a13c98cb83f57179a59abfa569fbed9edf8af8b1f216d0035b4cf86` |
| `apps/control-room/src/modules/viewport-3d/layers/Viewport3DLightingRig.tsx` | `7fe54eff91915a7ed3e4318e0aeb09e8bb600258ac95fc2cf7e4aaf84f43b8a9` |
| `apps/control-room/src/modules/viewport-3d/layers/viewport3DMaterialProfile.ts` | `1477a5c05a1846197231807b846fb50042cc6f90f0dad64108a3ba18af85a236` |
| `apps/control-room/src/modules/viewport-3d/layers/PostProcessingLayer.tsx` | `f6a8bdb41171e7318a2beab0e342c0b486387900a7132365961967cc96a35920` |
| `apps/control-room/src/modules/viewport-3d/layers/PrimitiveObjectLayer.tsx` | `7a14c2f83f370cb520c5c8517e36474e40b61b1cdadc2fd304b2046e8730d49e` |
| `apps/control-room/src/modules/viewport-3d/layers/FdmCuboidLayer.tsx` | `582ddfc9577acdfee0c8cc830f0b96d95ce031d45a80083c6255ac05b2bd30f4` |
| `apps/control-room/src/modules/viewport-3d/viewport3dScalarSurfaceShader.ts` | `5847040ed9ece985029402459f17d7e8820db0938c4952dfd41be582b961dedb` |
| `apps/control-room/src/modules/viewport-3d/viewport3dVisualProfile.ts` | `0040da6218f9753dbaf5f6961c8bdf618e044ff0f336c3b940a528c2aaa3b592` |
| `apps/control-room/src/modules/viewport-3d/viewport3dStore.ts` | `e2f117756d1d57c608d7f79b71c78054216a1515a7d7bf44f5274e0e0d01592a` |
| `apps/control-room/src/modules/viewport-3d/components/Viewport3DCameraDialog.tsx` | `2ca6c9b563f93cf3e86bad31cdb5a0a72fd86b04fd03e8b8587734e523ea5bbe` |
| `apps/control-room/src/modules/viewport-3d/components/Viewport3DSettingsDialog.tsx` | `282c980565f14438fd0a6a6f26ef84dca6fe36940a7835132b81d9512aa19d04` |
| `apps/control-room/src/modules/viewport-3d/orientation/hudLayout.ts` | `0cbba59a1d41edd7d311e744b49425e254c009af07fef3f3d3b0d82a6f74f1fe` |
| `apps/control-room/src/modules/viewport-3d/Viewport3DModule.tsx` | `1e5a3222d9f2ab9a3b9f32c222136de5a000d0351639658d38bc163c41db2f9b` |
| `apps/control-room/src/kernel/browserFullmagConfig.ts` | `bef8fffdb3cd867f66017382039ce4309ead70c0528c8bf10e767185d745bdef` |
| `apps/control-room/src/modules/ribbon/ribbonContributions.tsx` | `7689470d331613b21ef5f24753eabceb3d5f822a0d8cfd1605d5cbd831b5fa9a` |
| `apps/control-room/src/kernel/visualization/CameraRegistryController.ts` | `19fbd21065e323b4b7b11f303920c94d7f295ffbd2dcbcfcf191670be5ca9385` |
| `apps/control-room/src/design/styles/theme.css` | `d70fc6d0a3211ae3d8f26be5843c1312d3c81c7517d24512951c8421057c24f6` |
| `apps/control-room/package.json` | `be9076b11ce87e1b250b8509ca05ee616996d224d0c24afa617e85ca230c24c0` |
