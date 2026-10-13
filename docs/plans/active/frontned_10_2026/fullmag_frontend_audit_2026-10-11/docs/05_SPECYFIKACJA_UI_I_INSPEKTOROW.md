# Specyfikacja UI: modelowanie, inspektory i narzędzia

## 1. Zasada kompozycji

Zachować istniejący shell Control Room, dockowanie, navbar, styl typografii i tokeny projektu. Makiety pokazują wyłącznie obszar roboczy po wybraniu kontekstu Geometry/Mesh; górny pasek nie jest projektem nowego globalnego navbaru. Kolory makiet są referencyjne i wymagają mapowania na istniejące tokeny, nie twardego kopiowania hex do produkcji.

Na desktopie obszar roboczy składa się z drzewa po lewej, viewportu pośrodku, inspektora po prawej i dolnej szuflady z Jobs/Diagnostics/History. Zalecane rozmiary projektowe: drzewo 240–320 px, inspektor 320–440 px; środek elastyczny. To propozycje, nie wymiary odczytane z aktualnego CSS. Użytkownik może zmieniać szerokości. Przy małej szerokości inspektor jest panelem wysuwanym; kontrolki nie kurczą się do nieczytelnych ikon.

Wspólny pasek statusu pokazuje: aktywna sesja, zapis sceny, lokalny draft, kompatybilność meshu. Te cztery informacje nie są jednym badge „Ready”. Nie zakrywać nowego view cube, legendy ani dimension frame.

## 2. Drzewo modelu

```text
Model
 ├─ Definitions
 │   ├─ Parameters [gdy capability pozwala]
 │   └─ Coordinate systems / work planes
 ├─ Geometry
 │   ├─ film [Box]                 committed
 │   │   ├─ Geometry
 │   │   ├─ Placement
 │   │   ├─ Regions & material bindings
 │   │   └─ Mesh policy
 │   ├─ disk [Cylinder]            draft edited
 │   ├─ imported_part [STL asset]  validation warning
 │   └─ construction_plane        construction-only
 ├─ Mesh / Grid
 │   ├─ Recipe / Execution plan
 │   ├─ Current artifact          stale
 │   ├─ Quality
 │   └─ Builds
 └─ Physics / Studies / Results   existing modules
```

Nowe węzły muszą mapować się na istniejące rodzaje Selection lub ich wersjonowane rozszerzenia. Nie tworzyć drugiego niezależnego drzewa modelu. Visibility, lock, solver participation i construction-only są odrębnymi właściwościami. Ukrycie obiektu nie może wyłączać go z obliczeń. Ikona oka nie jest checkboxem udziału w solverze.

Klik węzła wybiera obiekt; rozwinięcie nie zmienia selekcji. Dwuklik Geometry otwiera parametry, a nie uruchamia kosztownego meshera. Po zmianie zaznaczenia z dirty draft: Apply and switch, Discard and switch, Cancel. Ten sam guard obejmuje klik w viewport, drzewie i breadcrumb.

## 3. Ribbon kontekstowy

| Grupa | Kontrolki | Zasada |
|---|---|---|
| Create | Box, Cylinder, Sphere, Thin Film, Import | Tylko wspierane typy jako aktywne; reszta w jawnej sekcji unavailable. |
| Edit | Select, Move W, Rotate E, Scale R, Duplicate, Delete | Capability per typ/rola; nieaktywny przycisk wyjaśnia powód. |
| Placement | World/Local/Workplane, pivot, snap, align | Widoczne bieżące wartości i jednostki snap. |
| Geometry | Validate, Build Geometry | Nie mylić z zapisem draftu ani Build Mesh. |
| Mesh | Build Selected / Build Shared Domain lub Build Grid | Lane-specific etykiety; wskazanie faktycznego zakresu. |
| View | Frame Selected, Frame All, section view, projection | Zmienia wyłącznie prezentację. |

Shortcuts trzeba rejestrować centralnie i wyłączać podczas pisania w input/textarea lub w aktywnym dialogu. Sam napis „W” w definicji ribbonu nie jest dowodem działającego keybinding. Escape zawsze ma jedno znaczenie zależne od fazy narzędzia. Nie przypisywać tego samego klawisza do kamery, narzędzia i tekstury bez jawnego kontekstu.

## 4. Inspektor I01 — nowy prymityw

Nagłówek: Create Box/Cylinder/Sphere, draft badge, close. Sekcje: Identity, Shape, Placement, Assignment, Validation. Stopka jest sticky: Cancel i Create Object. Nie dodawać drugiego Apply wewnątrz formularza.

Identity: Name, typ read-only, opcjonalny opis. Shape: Box Lx/Ly/Lz; Cylinder radius/diameter jako dwa widoki jednej wielkości, height i axis; Sphere radius. Nie trzymać niezależnych radius i diameter mogących się rozjechać. Thin Film to jawny preset wymiarów, nie specjalny ukryty przelicznik jednostek.

Placement: anchor, position XYZ, unit selector i optional workplane. Początkowo preview może być na płaszczyźnie XY, ale Z nie jest niejawnie wyzerowywane. Assignment: istniejący materiał i region wybierane z listy po ID; możliwość „utwórz później” daje warning, jeżeli geometria sama w sobie jest legalna. Blokowanie solvera z powodu braku materiału nie musi blokować samego modelowania.

Walidacja lokalna działa podczas wpisywania; serwerowa dotyczy konkretnego baseline i draft hash. Przycisk Create aktywny przy poprawnym szkicu i bieżącej sesji. Wysyłanie blokuje powtórne kliknięcie. Błąd zachowuje pola. Po sukcesie obiekt zostaje zaznaczony i inspektor przechodzi w tryb edycji tego obiektu.

Makieta: [01 Geometry authoring](../mockups/01_geometry.svg).

## 5. Inspektor I02 — istniejąca geometria

Nagłówek: nazwa, typ, committed revision, local changes. Zakładki: Geometry, Placement, Assignment, Diagnostics; Mesh Policy prowadzi do właściwego inspektora, a nie otwiera drugi równoległy draft.

W każdej kontrolce aktualna wartość pochodzi ze wspólnej sesji edycji. Zmienione pola mają subtelne oznaczenie, a opcjonalny diff pokazuje old→new. Wymiary lokalne są oddzielone od world bounding box i scale. „Width=100 nm, Scale X=2” oznacza world extent zależny także od orientacji, nie to samo co lokalny width=200 nm.

Stopka: Revert i Apply Changes; obok opis skutku „Mesh becomes stale”. Po sukcesie baseline i dirty state są aktualizowane. Przy multi-selection pola wspólne pokazują wartość, różne pokazują Mixed; Apply nie zapisuje przypadkiem zer do obiektów nieedytowanych.

## 6. Inspektor I03 — transformacja i pivot

Nagłówek wyraźnie rozróżnia **Object transform**, **Texture transform** i **Camera**. Zakładki/narzędzia nie zmieniają tego zakresu niejawnie. Sekcja Transform ma frame, pivot mode, Position/Rotation/Scale, absolute/delta i trzy jednostki: długość, stopnie, mnożnik/procent.

Scale ma lock uniform. Po jego włączeniu użytkownik widzi, czy zachowuje proporcje z baseline czy wyrównuje wszystkie trzy skale; proponowane zachowanie to zachowanie proporcji. Reset Rotation/Scale jest osobną komendą draftu, nie natychmiastową mutacją backendu.

Pivot: bbox center, bottom/top center, world origin, picked anchor, custom XYZ. Tryb Affect Pivot Only wyraźnie podświetlony, z opisem „object stays in place”. Gizmo rysuje pivot, osie i płaszczyzny, a aktywna oś ma również literę, nie tylko kolor. Numeric entry jest równoprawną alternatywą dla przeciągania.

Gizmo powinno mieć stabilny rozmiar ekranowy; propozycja 88–120 CSS px przy referencyjnym zoom, hit area co najmniej 24 px dla końców osi. Wskaźnik delta obok kursora i readout w dolnym pasku przedstawiają tę samą wartość. Preview z LOD musi być oznaczony.

Makieta: [02 Transform and pivot](../mockups/02_transform.svg).

## 7. Inspektor I04 — Import Geometry

Kreator ma kroki File → Units & Placement → Surface checks → Commit. Przejście Back zachowuje stan i uploadId. Cancel nie tworzy scene-object; niepotrzebny upload może być usunięty zgodnie z polityką retencji, nie bez kontroli innych referencji.

File: nazwa, rozmiar, rozpoznany format/encoding, asset hash, upload progress, źródło lokalne vs asset projektu. Nie wymagać wpisywania ścieżki filesystemu serwera jako podstawowego sposobu importu. Nie odczytywać dowolnych lokalnych ścieżek na podstawie treści pliku.

Units: jednostka źródłowa obowiązkowa dla formatów bez wiarygodnej metadanej jednostki; pokazać bbox przed i po konwersji oraz porównanie z obiektami sceny. „Auto” może być sugestią, nigdy ukrytym przeskalowaniem. Import scale i Object scale mają osobne etykiety.

Surface checks: liczba trójkątów i komponentów, invalid vertices, zero-area faces, boundary/non-manifold edges, orientacja, self-intersections i objętości — tylko gdy backend rzeczywiście je zbadał. Unknown nie oznacza zero. Repair to osobna operacja z raportem before/after i zachowanym assetem źródłowym. Nie wykonywać destructive repair bez potwierdzenia.

Commit: nazwa obiektu, rola, materiał/region, placement, bounding box, lista warningów, docelowa ścieżka FEM/FDM. Surface-only może być poprawnym obiektem konstrukcyjnym, lecz nie legalną zamkniętą objętością magnetyczną. Create Object nie uruchamia automatycznie kosztownej siatki bez jawnej opcji.

Makieta: [03 STL import](../mockups/03_import.svg).

## 8. Inspektor I05 — obiekt importowany po utworzeniu

Sekcje Source & provenance, Surface checks, Placement, Reimport, Meshing support. Widoczne hash/version/source units, skala konwersji i aktualny transform. Source geometry pozostaje niemodyfikowane; operacje naprawy/reimportu tworzą kolejne wersje.

Reimport pokazuje bbox diff, zmienione komponenty i potencjalnie osierocone selections. Nie przepina regionów po samym numerze trójkąta. Parametry Width/Height mogą być wyłącznie read-only bbox lub jawną komendą Scale to bounds; nie udawać parametrów prymitywu.

## 9. Inspektor I06 — FEM Mesh Policy

Wykorzystać istniejące sekcje [S18: `ObjectMeshPolicyPanel.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/inspector/panels/ObjectMeshPolicyPanel.tsx) i poprawić hierarchię. Pierwszy ekran: scope, inherited/override, strategy, target sizes, thickness layers, quality request i skutki zmiany. Zaawansowane algorytmy oraz JSON są w Advanced, a nie dominują nad hmax i liczbą warstw.

Każda wartość może mieć trzy kolumny: requested, effective, source. Na przykład efektywne hmin obcięte przez politykę globalną wymaga wskazania źródła ograniczenia. „Preset Fine” nie jest dowodem dostatecznej rozdzielczości dla modelu fizycznego.

Stopka: Revert, Apply Policy, Apply & Build. Gdy czysty: Build Mesh. Nazwa zakresu obok przycisku, np. „Shared domain containing disk”, jeśli wybrany obiekt faktycznie powoduje budowę większej domeny. Nie obiecywać lokalnego remeshu, gdy backend przebudowuje całość.

Makieta: [04 FEM policy](../mockups/04_mesh_policy.svg).

## 10. Inspektor I07 — Build/Rebuild i Jobs

Potwierdzenie ma before/after: geometry revision/digest, recipe diff, target, dotknięte obiekty, retained mesh i konsekwencje dla stanu magnetyzacji. Szacowany koszt może być „unknown”; nie podawać fikcyjnej liczby elementów lub czasu.

Progress jest fazowy: accepted, queued, geometry realization, meshing, quality, publishing, loading viewport, rendered. Progress procentowy tylko z wiarygodnego raportu. Zamknięcie okna nie anuluje jobu. Cancel widoczne wyłącznie, gdy backend wspiera anulowanie danej fazy.

Po błędzie stary artefakt pozostaje podpisany jako retained i stale/incompatible. Retry zachowuje lub tworzy nową intencję zgodnie z rozpoznanym wynikiem, a reconnect jedynie wznawia obserwację. Istniejący [S20: `geometryLifecycleCommandContributions.ts`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/kernel/authoring/geometryLifecycleCommandContributions.ts) już implementuje znaczną część tej logiki.

Makieta: [05 Rebuild](../mockups/05_rebuild.svg).

## 11. Inspektor I08 — jakość i topologia

Zakładki Summary, Distribution, Worst elements, Region coverage, Diagnostics. Wybór metryki aktualizuje legendę i zakres tej samej rewizji meshu. Tabela elementów ma identyfikator artefaktu, indeks, centroid i wartość metryki. Klik centruje/izoluje element; refinement ma osobne potwierdzenie.

Przekrój XY/XZ/YZ i dowolna płaszczyzna powinny pokazywać rzeczywiście przecinane elementy, nie mylący rzut wszystkich krawędzi na płaszczyznę. Brak per-element quality oznacza „unavailable”, nie uniform green. Zmiana legendy, clippingu i wireframe nie uruchamia meshera.

Makieta: [06 Mesh quality](../mockups/06_quality.svg).

## 12. Inspektor I09 — FDM Grid

Dwa podwidoki: authored discretization owner oraz realized grid. W pierwszym użytkownik przechodzi do właściwej edycji planu spacing/extent/layers; w drugim ogląda shape, spacing, origin, total/active cells, membership i region legend. Projekt nie zakłada lokalnego edytowania read-only realized resource.

Build Grid jest odrębny od FEM Build. Status powierzchni schodkowej i cell occupancy nie jest jakością tetrahedrów. Widok komórki pokazuje IJK, ordinal, center, region, mask state oraz fingerprint. Stary fingerprint blokuje operacje na bieżącym gridzie.

Makieta: [07 FDM grid](../mockups/07_fdm.svg).

## 13. Inspektory uzupełniające

I10 Regions & materials: wybór obiektu/regionu, semantic ID, materiał, priorytet nadpisania, unresolved refs i coverage. I11 Boolean: operator, operands, kolejność, keep tools, wynik, provenance regionów i build status; pozostaje disabled do wdrożenia pełnego kontraktu. I12 History: filtrowana oś intencji i jobów, before/after, restore-to-draft, brak mylenia restore z aktywacją starej siatki.

## 14. Accessibility i błędy

Pełna obsługa Tab/Shift+Tab/Enter/Escape, focus trap w dialogach i powrót focusu do aktywatora. Wartości, osie i statusy mają etykiety tekstowe. Kolor nie jest jedynym nośnikiem błędu. Przy wysyłaniu ogłoszenie statusu przez aria-live nie powinno spamować przy każdym pointermove. Błędy inline wskazują pole, a summary prowadzi do pierwszego problemu.

Dla disabled command tooltip ma być dostępny również z klawiatury. Fatal resource error oferuje Retry odczytu; walidacja domenowa nie jest opisywana jako awaria sieci. Toast nie zastępuje trwałego statusu nieznanego wyniku mutacji.
