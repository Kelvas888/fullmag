# Viewport 3D — macierz odbioru R7

20.10.2026, kandydat źródłowy `0a536ffb78ee05c57a1febedae73b9156760f280`, branch `codex/viewport-visual-quality-20261020`. Ocena względem pełnego planu R0–R8, bez zmiany kryteriów. Całość NIEUKOŃCZONA; R8 nierozpoczęte, brak PR/merge.

## Zasady dowodowe

Ostatnia dopuszczona próba browser: `aa32af77928847a5ad04e93c8736a170`, exit1 (2 × 404, 20 × 422), page errors 0, transport failures 0. JSON `browser-qa/attempts/<id>/runner-output.json` w control volume własnej grupy. Osiem partial proofs jest dowodem ograniczonych zachowań, nie zielonego przebiegu. Próba poprzedza nowe baselines2 CSS px, więc nie dowodzi ich obrazu ani aktualnego baseline zasobów.

Grupa `fullmag-worktree-viewport-visual-quality-20261020-781a03fef79664b6`, frontend3218. W chwili audytu backend jest unhealthy/failed_outcome_retained; nowa próba browser została odrzucona przed dopuszczeniem. Stare dowody pozostają historyczne i nie zastępują nowego admission.

## V01–V15 — kolejne wiersze macierzy sekcji 6 planu

| ID | Wymaganie | Stan i istniejący dowód | Brakujący dowód |
|---|---|---|---|
| V01 | Pusta scena, solid/gradient | Częściowy: appearance porównuje rzeczywiste piksele solid/gradient na scenie z bryłą. | Kanoniczna pusta scena, PNG i brak geometrii zastępczej. |
| V02 | Bryła z otworem nad powierzchnią | NOT VERIFIED. Zastępczy film jest bryłą bez otworu. | Krzywizna, orientacja, dystans od płaszczyzny, baselines. |
| V03 | Przesunięcie od globalnego zera | Częściowy: ID qa-offset-film-mvgw65uf, camera/bounds SI, world/frame-center zmienia piksele i tekst ustawienia; model-unit regressions zielone. | Pełny odbiór wartości wszystkich etykiet i Lx/Ly/Lz w nowym obrazie. |
| V04 | Cienki film/wydłużona domena | Częściowy: 40 × 30 × 10 nm nie jest próbą skrajnie cienką. | Skrajny aspect ratio, ticki bez fałszywego skalowania Z. |
| V05 | Perspektywa/ortho / widoki osiowe | Częściowy: projection transitions potwierdzone,11 póz przez dialog, FOV 35/70 i 84 630 zmienionych pikseli przy stałej pozie; Fit zmienia dystans. | Nowe baselines we wszystkich widokach, pełna ocena oznaczeń/FOV. |
| V06 | Orbita przez ćwiartki/pod podłogą | Częściowy: 4 ukośne kwadranty i under-floor przez dialog, rzeczywisty klik+X i 5 próbek ciągłego dragu; restore verified. | Gest przez całą macierz i pełna ocena histerezy/hidden edges w nowych liniach. |
| V07 | Mocha/Latte, DPR 1/2 | Częściowy: layout DPR1/2 zachowany; rdzenie liter Latte 5,70/6,05/5,84:1, stare baseline fragmentami 2,35–2,86:1. | Pomiar kontrastu nowej szerokości2 CSS px, wszystkich krytycznych linii/ticków. |
| V08 | Viewport 1200 × 800 i 480 × 320 | Częściowy: 4 zrzuty na DPR, oba motywy, sprawdzone canvas/context/buffer i publiczny HUD; ustawienia narrow bez kolizji. | Pełna ocena nowych linii/pickingu oraz wszystkich scen, nie tylko jednej bryły. |
| V09 | FDM,FEM,primitive | Częściowy: primitive Studio/Flat45 918 / 0 zmienionych pikseli,1 Lambert candidate i 0 innych powierzchni. | Rzeczywiste zrealizowane FDM iFEM; nazwa sesji FDM nie jest tym dowodem. |
| V10 | Scalar/HSL/vector, airbox, clip | NOT VERIFIED dla pełnego zakresu. Brak rozwiązanego payloadu pola w tej scenie. | Ochrona RGB/legendy, zasłanianie i przezroczystość na danych. |
| V11 | Styl/światło/HUD bez pobrań/rebuildów | Częściowy: lifecycle.appearance_request_check dla gradient → solid: matching_requests=[] pól/topologii. | Wszystkie zmiany światła/HUD i brak rebuildów topologii na gotowych polach. |
| V12 | Idle/orbit/resize | Częściowy: liczniki ramek i próbki idle w diagnostyce, rzeczywista orbita iresize. | Porównywalny R0 i koszty CPU/GPU dużej sceny; bez deklaracji FPS. |
| V13 |20 przełączeń 3D/2D i efektów | Częściowy: 20 cykli / 40 przejść,20 powrotów canvasa, tracker baseline/post/idle geometries 7, textures 1, inne 0;20 inactive samples. | Nowy resource baseline po LineSegments2; oddzielna pełna sekwencja efektów; brak globalnych HTTP błędów. |
| V14 | Reload/nowa sesja/dataset | Częściowy: preference reload, ta sama identity i dokładny restore storage. | Nowa sesja i dataset bez wycieku kamery; stale ACK w runtime. |
| V15 | Capture/błąd capture | Częściowy: opaque/transparent PNG, adnotacje, DPR2, restore wcześniejszej wersji. | Nowe linie w eksporcie oraz kontrolowany błąd capture/cleanup. |

## Doprecyzowanie żądań422

W źródłach kilku konsumentów shared planar hook może wysłać query. Dowód lifecycle z próby aa32 podaje jednak fazę wszystkich 20 requestów: `cycle-1:to-2d`…`cycle-20:to-2d`, GET `/v2/sessions/current/data/fields/m/planar-default/meta`, topology_count 0. To przypisuje je przejściom do 2D, a nie zmianie appearance w 3D. Nie rozstrzyga, czy konkretnym nadawcą był FieldMapModule czy równolegle zamontowany planar Inspector. Kontrakt availability/materializacji nadal wymaga snapshotu i initiatora; nie ukrywano 422.

## Pozostałe bramki

- Agregat scoped viewport regressions 827/827; aktualny fragment:27 layer/model + 11 lighting audit. Wszystkie w frontend własnej grupy Docker.
- Produkcyjny typecheck i narrow lint zmienionych plików exit 0; architecture hygiene exit 0. Source review bez findings.
- Pełny lint dużego modelu sceny nadal OOM przy 1536 MiB, również pojedynczo. Narrow lint nie zastępuje tej bramki.
- R6 rzeczywiste AO, R7 scientific RGB i pozostałe sceny niezaliczone. Nie ma dowodu GPU parity ani kwalifikacji naukowej/release.
- R8: brak push, PR, merge, lokalnego fast-forward i cleanup. Master ma odrębne zmiany i własny proces integracji; nie jest miejscem naszej bieżącej implementacji.
- Następny zależny krok: jawna decyzja w sprawie [recovery własnej grupy](../superpowers/plans/2026-10-20-viewport-runtime-recovery-proposal.md). Bez niej nie mutujemy unknown ownera. Wymagany ponowny browser proof aktualnych źródeł po odzyskaniu admission.
