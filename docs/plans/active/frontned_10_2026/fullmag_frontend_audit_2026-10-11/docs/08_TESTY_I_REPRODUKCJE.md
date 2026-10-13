# Testy, reprodukcje i plan kwalifikacji

## 1. Co rzeczywiście uruchomiono

Uruchomiono siedem izolowanych testów w Node.js, bez React, WebGL, backendu i meshera. Wynik jest w [results.json](../reproductions/results.json), log w [run.log](../reproductions/run.log), kod w [reproduce.mjs](../reproductions/reproduce.mjs).

Kontroler gestu jest ręcznym portem semantyki sprawdzonego helpera po usunięciu typów TypeScript; pozostałe przypadki są minimalnymi modelami wyrażeń/wyboru stanu. To nie automatyczny import plików produkcyjnych i nie test binarnej zgodności. W README reprodukcji podano źródła. Wyniki nie dowodzą, że każdy scenariusz wystąpi w identyczny sposób przy pełnym montowaniu aplikacji.

```bash
cd fullmag_frontend_audit_2026-10-11
node reproductions/reproduce.mjs
```

| Test wykonany | Związek | Odtworzony mechanizm | Czego nie dowodzi |
|---|---|---|---|
| R01 | F05 | ACK gestu A emituje draft=null po rozpoczęciu gestu B. | Częstości wystąpienia w zamontowanym viewportcie. |
| R02 | F16 | begin/end bez ruchu wywołuje commit. | Czy backend tworzy nową rewizję dla no-op. |
| R03 | F07 | Błąd onCommit propaguje się z end jako rejected Promise. | Ostatecznego globalnego UI błędu w całej aplikacji. |
| R04 | F09 | Pusty/whitespace string przechodzi Number jako zero. | Każdego pola i całej serwerowej walidacji. |
| R05 | F01 | Ten sam draft key zachowuje stary baseRevision. | Pełnego cyklu efektów React i routingu. |
| R06 | F19 | „Przyszła” source revision jest klasyfikowana jako current. | Czy serwer w danym wdrożeniu publikuje taką kombinację. |
| R07 | F18 | Fallback radiusSize nie uwzględnia wysokości cylindra. | Czy w danej sesji brakuje kanonicznych bounds. |

## 2. Testy obecne w repozytorium

[S11: `MoveObjectGizmo.test.tsx`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.test.tsx) zawiera m.in. kontrolę lokalnego ruchu i pojedynczego commit, zachowania draftu przy 409, Escape/unmount, pointercancel/lostpointercapture, release capture przy błędzie i niskopoziomowego session fence. To istotne pokrycie, którego nie należy usuwać. Brakującym dowodem jest m.in. interleaving dwóch gestów i rzeczywiste użycie fence przez produkcyjny caller.

[S24: `package.json`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/package.json) deklaruje Vitest, typecheck i zestaw smoke/diagnostic scripts. Nie uruchomiłem tych skryptów w pełnym repo; nie raportuję ich jako PASS. Poniższe polecenia służą do kwalifikacji w istniejącym środowisku developerskim po instalacji zależności zgodnie z repozytorium:

```bash
pnpm --dir apps/control-room test
pnpm --dir apps/control-room typecheck
pnpm --dir apps/control-room run smoke:scratch-authoring-ui
pnpm --dir apps/control-room run smoke:scratch-authoring-fem
pnpm --dir apps/control-room run smoke:scratch-authoring-fdm
pnpm --dir apps/control-room run verify:mesh-build-new-object
pnpm --dir apps/control-room run smoke:fem-preview-freshness
```

Smoke scripts mogą wymagać działających runtime/backendów i konfiguracji środowiska. Nie traktować samego istnienia wpisu package.json jako dowodu przejścia testu.

## 3. Macierz nowych testów akceptacyjnych

Warstwy: U — unit/reducer, C — kontrakt API/runtime, B — przeglądarka, V — rzeczywisty WebGL, N — walidacja numeryczna/meshera. Macierz jest **planem**, nie listą wykonanych PASS.

| ID | Warstwa | Scenariusz | Oczekiwany wynik / oracle |
|---|---|---|---|
| T01 | U/B/C | Dwie kolejne edycje wymiaru jednego Box. | Drugi request używa rewizji po pierwszym ACK. |
| T02 | U/B | Geometry+translation w jednej sesji. | Jedna jawna intencja i spójny atomic commit lub wyraźnie rozdzielone potwierdzenia. |
| T03 | U/B | 409 → refetch → rebase → retry success. | Conflict phase cleared, dirty=false, nowy baseline. |
| T04 | U/B | Revert po konflikcie. | Pola baseline i brak stale conflict banner. |
| T05 | B/C | Zmiana selekcji podczas wysyłania. | ACK nie czyści draftu drugiego obiektu. |
| T06 | B/C | Zmiana sesji A→B; ten sam objectId. | Brak obcych invalidacji, historii i feedbacku. |
| T07 | U/B | Draft Box→Cylinder przed Create. | Właściwy typ, nowe draftId, jawna decyzja o poprzednich danych. |
| T08 | U/B | Puste, whitespace, '-', '1e', NaN, infinity. | Stany incomplete/invalid, nigdy niejawne zero. |
| T09 | U/C | nm/µm/mm/m i zapis scientific notation. | Jeden wynik SI, brak podwójnej konwersji. |
| T10 | U/B | Ujemny wymiar, zero radius/height. | Inline error i zablokowany commit. |
| T11 | B | Unsupported imported/CSG geometry. | Prawdziwy read-only inspector; bez fałszywego edytora Size. |
| T12 | B | Walidacja loading/error/absent/stale. | Brak zielonego „no issues” bez dowodu. |
| T13 | U/C | Czterowymiarowy quaternion nienormalny/zerowy. | Jawna walidacja/normalizacja według kontraktu. |
| T14 | U/C/N | TRS ze wskazanym pivotem i kolejnością. | Zgodność transformowanych punktów, bounds i realizacji. |
| T15 | U/C | Pivot-only change. | World geometry nie zmienia się; deterministyczny round-trip. |
| T16 | U/C | Nonuniform parent scale + child rotation. | Jawna obsługa shear albo odmowa, nigdy cicha dekompozycja. |
| T17 | U/C | Mirror/zero scale. | Fail closed do czasu kwalifikacji kontraktu. |
| T18 | U/V | Drag A, rozpoczęcie B, ACK A. | B pozostaje aktywny i widoczny. |
| T19 | U/V/C | Click osi bez ruchu. | Bez zapisującego requestu i wpisu historii. |
| T20 | U/V | Escape / lost capture / pointercancel / unmount. | Dokładnie jedno cleanup; OrbitControls odblokowane. |
| T21 | V | Kamera orthographic/perspective, oś prawie równoległa do ray. | Stabilny solver gestu; brak skoku do starego intersection. |
| T22 | V | Przeciągnięcie poza obszar osi i viewport. | Kontynuacja lub jawne cancel według ustalonego kontraktu. |
| T23 | B/V | Plane handles XY/XZ/YZ, World vs Local. | Zmieniają tylko dozwolone DOF we właściwej ramie. |
| T24 | B/V | Snap + numeric entry. | Ta sama wynikowa wartość i preview; brak dryfu kumulacyjnego. |
| T25 | B/C | Move → Undo → Redo. | Jeden wpis semantyczny; nowa rewizja; prawidłowe stale descendants. |
| T26 | B/C | History capture failure. | Zapis zachowany, Undo degraded widoczne, brak fałszywego sukcesu historii. |
| T27 | C/B | ASCII STL / binary STL. | Rozpoznanie, units, preview, asset identity, commit. |
| T28 | C/B | STL truncated, counts mismatch, invalid/nonfinite vertex. | Odrzucenie z przyczyną, bez częściowego scene-object. |
| T29 | C/B | STL open surface/non-manifold/self-intersections. | Rzeczywisty raport checks; brak nieuprawnionej zgody na volume. |
| T30 | C/B | Source units zmienione mm→nm. | Bbox po konwersji czytelny; object scale niezależne. |
| T31 | C/B | Cancel po upload / reconnect. | Brak przypadkowego obiektu; reuse identity zgodnie z retencją. |
| T32 | C/B | Reimport ze zmianą triangulacji. | Regiony nie przypisują się według starego ordinalu. |
| T33 | C/B/N | Pierwszy mesh od pustej sceny. | Absent previous artifact nie blokuje first-build. |
| T34 | C/B | Dirty geometry przy Build Mesh. | Apply/Discard/Cancel; zakres modelu jednoznaczny. |
| T35 | C/B/N | Zmiana hmax i Apply bez Build. | Recepta nowa, artefakt stale, bez niejawnego kosztownego jobu. |
| T36 | C/B/N | Apply & Build, szybki double click. | Jeden zapis intencji i jeden build. |
| T37 | C/B | Geometry zmienia się podczas meshowania. | Wynik nie jest oznaczany current bez kompatybilności. |
| T38 | C/B | Lost ACK + więcej niż osiem późniejszych jobów. | Lookup właściwego client_intent_id lub jawne unknown; zero duplikatów. |
| T39 | C/B | Reconnect/reload podczas jobu. | Przywrócenie tej samej obserwacji bez resubmit. |
| T40 | C/B/N | Failure quality/publication po poprzednim sukcesie. | Retained artifact z prawidłową identity i stale label. |
| T41 | C/B | Backend completed, viewport fetch fails. | Retry Loading bez ponownej budowy. |
| T42 | U/B | sourceSceneRev > currentSceneRev lub brak identity. | unknown/inconsistent, nigdy current. |
| T43 | C/B/V | Worst element → remesh → klik ponownie. | Stale selection nie trafia w nową generację. |
| T44 | C/B/V | Quality metric z rewizji różnej od topologii. | Wstrzymanie koloru lub jawny snapshot, zgodna legenda. |
| T45 | V/N | Przekrój przez mesh. | Elementy przecinane płaszczyzną, nie rzut wszystkich elementów. |
| T46 | B/V | Wireframe/opacity/clipping. | Brak nowych komend build i zapisów modelu. |
| T47 | C/B/N | FDM Build Grid po zmianie spacing. | Grid i membership tej samej generacji/fingerprint. |
| T48 | B/V | FDM display stride. | Zmiana wyłącznie próbkowania widoku, nie liczby komórek solvera. |
| T49 | B/V | Duży STL i wielokrotne create/delete/switch. | Pomiar allocations, cleanup CPU/GPU; brak twierdzeń bez profilu. |
| T50 | B | Klawiatura, disabled reason, focus dialogs. | Każdy krytyczny workflow bez wyłącznej zależności od myszy/koloru. |

## 4. Fixtures i dowody

Minimalny zestaw geometryczny: Box o nierównych bokach; Cylinder z height różnym od diameter; Sphere; ArchWaveguide; importowana zamknięta powierzchnia; otwarta powierzchnia; dwa obiekty z interfejsem; cienka warstwa; obiekt o dużej translacji względem małych wymiarów. Dane fixture mają jawne jednostki i oczekiwane bounds. Wymiary dobrać do konkretnego testu, nie do arbitralnego „ładnego” preview.

Dla transformów oracle to punkty kontrolne, macierz i AABB obliczone niezależnie, nie screenshot. Dla meshu oracle to artifact identity, topology/region coverage, raport jakości i testy backendu. Dla interakcji potrzebny jest również screenshot/video z osiami, ramą i stanem draftu. Test DOM helpera nie zastępuje rzeczywistego raycastingu WebGL.

Każdy dowód ma zawierać commit, backend/lane/version, fixture hash, środowisko, kroki, request/response identity, expected/actual, log i ewentualny capture. Dla testów numerycznych jawnie podać tolerancję i metodę jej uzasadnienia. Wyniki odnoszą się do konkretnej konfiguracji; test CPU frontendowego state machine nie kwalifikuje automatycznie realizacji GPU.

## 5. Retest po naprawie

R01–R07 powinny zostać zastąpione testami importującymi produkcyjne moduły lub ich nowo wydzielone czyste funkcje. Zachować minimalne reprodukcje jako zapis mechanizmu starego błędu. Naprawa nie polega na zmianie expected w tym pakiecie tak, aby stare zachowanie otrzymało PASS.
