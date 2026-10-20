# Viewport 3D — checkpoint implementacji

## Aktualny checkpoint R7 — 86%, 20.10.2026

Poniższe sekcje historyczne opisują kolejne próby; ten blok określa aktualny stan. HEAD przed bieżącym fragmentem: `1bfb26078b40dc13d0667d81ce6e5fd9bb11ce61`. R8 pozostaje nierozpoczęte. Nie ma zgody na uznanie częściowych dowodów za ukończenie macierzy R7.

Fragment zapisano jako `f946bf577123c472dad91ccf9eda92feb68bdc73` — `Strengthen viewport contrast and lighting verification`. Rejestr worktree aktualny dla tego commita, state=active. Commit hook zakończył się exit 0; React Doctor zgłosił 10 ostrzeżeń w helperze QA, nie w produkcyjnym rig: osiem o sekwencyjnych odczytach DOM (prawdziwa, niskiego wpływu możliwość skrócenia harnessu) oraz dwa o await w pętli. W pętli kroków klawiatury zakresu i kolejnych scrollIntoView odczyty zależą od poprzedniej mutacji; równoległe wykonanie zmieniłoby scenariusz. Nie wyłączono reguł i nie potraktowano wyniku Doctor jako pełnego odbioru React.

- Próba browser `b426e8b189134cbe94d977bd8017d6a3`: wszystkie osiem wpisów partial proof zachowane, w tym model readiness, appearance, camera, export, layout DPR1/2, export DPR2 i lifecycle. Kamera przywrócona przez widoczny dialog; zachowany canvas/kontekst. Studio 0→2: 45 918 zmienionych pikseli; Flat: 0. To dowód zastępczej bryły, nie pola FDM/FEM.
- Cały przebieg: `failed-confirmed`, exit 1; 6 odpowiedzi HTTP 404 frequency response oraz 19 odpowiedzi 422 planar-default, brak page errors i request failures. Błędy pozostają w wyniku i nie są filtrowane.
- Layout obu motywów w 480×320: identyczne position `[9.308214556237385e-8,4.261914480490918e-8,8.058214556237386e-8]`, target `[2e-8,-1e-8,7.500000000000001e-9]`, up `[0,0,1]`, perspective; bounds center=target, size `[4e-8,3e-8,1.5000000000000002e-8]` m. Model count=1 dowodzi adopcji modelu, nie widoczności mesha.
- Końcowy raster Latte: rdzenie X/Y/Z względem lokalnego pierścienia tła odpowiednio 5,70 / 6,05 / 5,84:1. FG/BG: X `(171,24,56)/(226,229,236)`, Y `(54,94,48)/(228,231,237)`, Z `(36,80,166)/(223,226,233)`. ROI włącznie: X `(326..339,226..240)`, Y `(119..132,254..269)`, Z `(63..77,176..190)`. To pomiar wybranych rdzeni po rasteryzacji, nie pełny dowód WCAG ani kontrastu wszystkich ticków i linii.
- Natywny PNG Latte `viewport-final-contrast-Latte-b426e8b1.png`, SHA256 `141615e50060aadcb160a0106ab6312cfb13d413934b7acba24b24b960cd2c50`; Mocha `viewport-final-contrast-Mocha-b426e8b1.png`, SHA256 `d7ba0eac8626588e0d848a48e70dd9be6a941ac6e44e82793d5e494f4677d363`. Pliki w katalogu wizualizacji tego czatu; eksport dokładnych bajtów PNG bez transformacji. Mocha identyczny z wcześniejszym obrazem bazowym.
- Bieżące wzmocnienie QA: pozytywny warunek oświetlenia oparty o rzeczywiste widoczne Mesh warstwy world, Lambert, opacity, istniejące bounding sphere i frustum. Osobny reader wyłącznie DEV, bez mutacji sceny, bez obliczania bounds i bez pracy per frame. Sceny z innymi powierzchniami pozostają `NOT VERIFIED`. Sam frustum nie dowodzi fragmentów GPU; pozytywna różnica pikseli jest odrębnym dowodem. Nowe testy i test rig: 13/13; narrow lint exit 0; review źródeł bez findings. Próba `aa32af77928847a5ad04e93c8736a170` potwierdziła runtime readera: litPrimitiveMeshCount=1, otherSurfaceMeshCount=0, ID `qa-offset-film-mvgw65uf`; Studio 45 918 / Flat 0, restore appearance i kamery verified, wszystkie osiem partial proofs zachowane. Globalnie exit 1: 2×404 i 20×422; page errors=0, request failures=0. Nie maskowano błędów.
- Produkcyjny typecheck po integracji readera: exit 0 z GOMEMLIMIT=768MiB/GOMAXPROCS=2 we frontend tej grupy; architecture hygiene exit 0. Poprzednią próbę typechecku zatrzymano podczas presji pamięci przy niemal 6/6 GiB; nie traktowano jej jako dowodu zielonego wyniku. Wartości środowiska dotyczą tylko procesu kontroli, bez zmiany limitów kontenera lub konfiguracji runtime.
- Pełny lint dwóch dużych konsumentów (`Viewport3DModule.tsx`, `hooks/useViewport3DSceneModel.ts`) nadal `NOT VERIFIED`: próba z heap 1024 MiB zakończyła się rzeczywistym Node heap OOM/SIGABRT. Nie zmniejszono zestawu reguł i nie zwiększano limitów współdzielonego runtime. Narrow lint zmienionych plików tego fragmentu pozostaje zielony; nie zastępuje brakującej bramki całej implementacji.
- Dotychczasowy agregat regresji: 33 pliki, 816/816; nowy plik dodaje 10 przypadków (łącznie 34 pliki, 826/826 dla niezmienionych wcześniejszych źródeł). Wyjątek użytkownika nadal obejmuje tylko regresje viewportu w tej grupie Docker.

### Rozpoznanie współdzielonych 404 — bez implementacji poza zakresem

`kernel/resources/studyRuntimeResources.ts` hooki response sweep/progress używają ogólnych rewizji artifact/artifacts/stages; brak tam pozytywnego warunku publikacji danego podproduktu. Konsumenci obejmują FooterTelemetry, ResultsNavigator, Explorer oraz Inspector. Źródła nie identyfikują konkretnego nadawcy żądania z tej próby. W viewport-3d nie ma callsite tych hooków.

Spec `frequency-domain-results-product-projection-v1.md:74` wymaga dla sweep gotowego result_manifest oraz deklaracji response_sweep_v1_path/v2 lub response_sweep_resource_key. Spec `frequency-domain-artifacts-v2.md:2250,2322` rozdziela opublikowany progress/checkpoint i aktywne stage execution. Proponowana korekta to publication gate zgodny z manifestem; zadeklarowane zasoby nadal muszą ujawniać rzeczywisty 404. Nie wprowadzono catch/ignoreMissingResource ani zmiany wspólnych hooków. To osobna nierozwiązana przyczyna czerwonego QA; nie rozszerza wyjątku testowego na ogólne API.

### Rozpoznanie planar 422 — granice ustaleń

Callsite `usePlanarFieldMetaResource` są poza viewport-3d: FieldMapModule, PlanarVisualizationSection i PlanarMonitorInspectorPanel; fasada wybiera `planar-default/meta` dla source=default. FieldMap używa warunków active/visible/scope; PlanarVisualizationSection coverage/state, bez pozytywnego warunku materializacji descriptoru. Kontrakt `resource-first-control-room-api-v2.md:236` rozdziela możliwości ilości (data/quantities) od gotowych danych (data/fields). Pusty katalog nie oznacza automatycznie braku preview capability. Dlatego nie dodano prostego `catalog.length > 0` ani pobocznego compute_fields. Minimalna dalsza diagnoza wymaga initiatora i snapshotu aktywnego widoku/materializacji z chwili 422; źródła same nie przypisują tej konkretnej odpowiedzi do komponentu ani nie dowodzą jej przyczyny. Nie ukrywano 422.

### Koordynacja i retencja

Jednorazowe przekazanie diagnozy cancelled/missing artifact catalog wykonano zgodnie ze zgodą użytkownika. Dalsze krótkie READY dla freeze/sync mastera oparto na odczytanej bezpośredniej instrukcji użytkownika „Skoordynuj przerwę z agentami” w czacie „Przywróć wizualizacje FEM i FDM”, user message `01a15a5b-66cd-7b72-89f2-cbd8394b2271`; nie na samym żądaniu innego agenta. Nie zmieniamy mastera ani jego indeksu. Trwa uzgodnione okno bez zapisów mastera do RELEASE.

Po terminalnych próbach zachowano receipty, runner-output, obrazy, cache przyrostowy i dane użytkownika. Launcher usunął własne terminalne helpery QA; żadnego ręcznego prune ani usuwania danych. Worktree i dwie stałe usługi pozostają potrzebne do brakujących scen R7; ponowna ocena ich zbędności dopiero po integracji i sprawdzeniu aktywnych mountów/procesów. Blokada cancelled run pozostaje nierozwiązana w tym runtime; nie powtórzono Stop, nie resetowano ownera i nie tworzono katalogu artefaktów zastępczo.

Pomiar po etapie: C: wolne `110905458688` B; filesystem control volume 548 GiB dostępne (43% zajęte). Docker ps tej grupy potwierdził tylko backend/frontend, oba healthy, bez helperów QA. To pomiar miejsca i stanu, nie kwalifikacja danych do usunięcia.

Brakujące dowody nadal obejmują pełną macierz scen (pusta, otwór, skrajnie cienka, live FDM/FEM), RGB danych ilościowych, rzeczywiste AO, kontrast wszystkich linii, performance dużej sceny, nową sesję/dataset, stare ACK oraz błąd capture. Nie wykonano push/PR/merge ani cleanup aktywnego worktree.

## R7 — grubość ciągłych baselines, kolejny fragment

Na zrzutach `b426e8b1` wyznaczono położenie baselines z bieżącego `buildDimensionFrameModel` oraz zapisanych bounds/kamery/FOV 42°. Dla 480×320 końce CSS: X `(318.61464,163.68673)`→`(242.00360,248.77429)`, Y `(153.45276,198.19070)`→`(242.00360,248.77429)`, Z `(153.45276,198.19070)`→`(145.69532,155.57747)`. Latte ma faktyczne 481×320, więc przy próbkowaniu X skalowano 481/480. Osiem punktów t=.15… .85, najsilniejszy rdzeń w promieniu 1,5 px, mediana tła 3×3 oddalonego o 5 px na zewnątrz. Projekcja źródłowa nie jest maską semantyczną; próbki przecięcia z geometrią lub tickami nie kwalifikują całej osi.

W Latte wiarygodne szare próbki X t=.35 i .85 miały 2,35 i 2,64:1; Y t=.25/.35/.75: 2,57/2,75/2,86:1; Z t=.25/.75: 2,81/2,95:1. Potwierdzono brak wystarczającego kontrastu wybranych rdzeni 1-pikselowej linii, mimo poprawionego kontrastu kolorowych liter. Mocha bez wiarygodnej próbki <3:1; nie jest to dowód dla każdego piksela.

Poprawka źródłowa: tylko trzy ciągłe baselines używają istniejącego Drei Line/LineSegments2 z szerokością 2 CSS px. Końce Float32 SI skopiowane bez przesunięcia; depthTest/LEQUAL zachowany, depthWrite=false, toneMapped=false. Polygon offset dotyczy rasteryzacji. Grids/ticki/extents pozostają dotychczasową ścieżką. Drei zwalnia geometrię i materiał; usunięto zbędną alokację starego axisGeometry. Audyt światła wyklucza liniowe quady `isLineSegments2`, które technicznie dziedziczą po Mesh; nowa regresja używa rzeczywistej klasy Three.js. Pierwsza próba testu nie wystartowała z powodu niebezpośredniej zależności three-stdlib; poprawiony import używa bezpośrednio Three/examples, bez instalowania zależności.

Weryfikacja: 27/27 regresji layer/model, 11/11 lighting audit (agregat 827/827), lint trzech zmienionych plików exit0, produkcyjny typecheck exit0. Focused source review bez actionable findings. Nowy runtime/kontrast i baseline zasobów oczekują na próbę browser; nie uznano starego zrzutu za dowód nowej szerokości.

Lint dużego modelu sceny również pojedynczo przekracza heap 1536 MiB. Próba rozdzielenia plików nie usunęła ograniczenia; nie zmniejszano reguł ani nie restartowano serwisów. Jednorazowe `HeapProfiler.collectGarbage` na istniejącym loopback inspectorze wyłącznie własnego Next (bez Runtime.evaluate) zmniejszyło usedSize 3509924488→3350725616 B i totalSize 3746902016→3524202496 B; po GC grupa miała około 3,99 GiB/6 GiB, lecz lint nadal OOM. Nie deklarujemy optymalizacji aplikacji ani rozwiązania bramki lint.

Świeży GET current run nadal: `run-live-0cc7302699581e9e1c11d5b210107633b74e674f8874d33d64b883ecac0d9084`, stopping, revision8, completed_at=null. Inny czat zakończył okno Git mastera komunikatem RELEASE; nasze worktree i jego źródła nie zostały zintegrowane z nowym masterem. Nie dotykano mastera.

## Nowa blokada admission browser QA — 20.10.2026

Próba nowych baselines zakończyła się przed utworzeniem dopuszczonej przeglądarki: `Development recovery does not identify exactly one live group`. Bieżący backend ma unhealthy, OOMKilled=false, restart0; na liście procesów brak API i native. Receipt PID1: failed_outcome_retained, api_shutdown=unknown, api_exit_code nieobecny. Pierwotna przyczyna to utrata supervision identity probe `/v2/platform/openapi.json` przez31s. SHA receipt `eedfb3d64c4856f87355b7d25b18c8763cf6f12758c03df45bf986825aac30c0`. Owner ma unknown, SHA `b1908cbaf9c9472f2cafa85b16d805b054d14215c06222ed804ad40a6ff0999a`; owner PID i dzieci nie istnieją, dzieci zapisane exited_success. Nie jest to dowód kompletnego drain.

Nie restartowano kontenerów ani nie poprawiano receiptów. Przygotowano [przeglądalną propozycję recovery](2026-10-20-viewport-runtime-recovery-proposal.md) i zadano pytanie o jawną autoryzację odzyskania tylko tej grupy oraz potrzebnych regresji zarządzanej ścieżki. Zależne mutacje czekają na odpowiedź. Kod baselines ma źródłowy review/testy/typecheck/lint, ale runtime pozostaje NOT VERIFIED. Architecture hygiene dla nowych źródeł exit0.

## Tożsamość

- Zadanie: `viewport-visual-quality-20261020`.
- Owner: `codex:01a15981-ab31-7ca0-960f-3d1145a8311d`.
- Worktree: `C:\git\fullmag\worktrees\viewport-visual-quality-20261020`.
- Branch: `codex/viewport-visual-quality-20261020`.
- Baza: `88a9b68d29ec173a0b1f1b8750c126da022b0244`.
- Rejestr: `storage/index/viewport-visual-quality-20261020-781a03fef79664b6.json`.
- Cel: pełny plan R0–R8, nie tylko gradient.

## R0 — stan początkowy

20.10.2026: master ma cudze dirty zmiany; implementacja odizolowana. Kopie audytu i planu zachowane w worktree. Docker po uzyskaniu dostępu pokazuje zdrowe backend/frontend `fullmag-master` na porcie 3198. Zarządzane `docker_dev_browser_qa.py --source-root .../fullmag --port 3198` zakończyło się kodem 1: `Browser QA requires a succeeded live volume DEV receipt`. Zdrowy kontener nie jest dowodem admission. Nie zmieniano receiptów ani nie restartowano tej grupy. Próba otwarcia IAB przekroczyła limit narzędzia; nie uzyskano obrazu bazowego runtime. Referencją wizualną pozostają dwa obrazy użytkownika; tożsamość oryginalnej sceny i materiałów pozostaje NOT VERIFIED.

## Zakresy równoległe

- Worker appearance_preferences: R1, prywatne preferencje/store/manifest; bez kamery i danych fizycznych.
- Worker dimension_hud: R2/R3, model ramki i etykiety; bez sceny i store.
- Prowadzący: tło, światło/materiały, integracja UI, kamera, efekty, eksport i weryfikacja.

## Bramy

- Użytkownik udzielił wyjątku wyłącznie dla regresji tej refaktoryzacji viewportu w grupie Docker worktree. Najnowsze wyniki dla 26 sprawdzonych plików: 594/594 passed. Pozostałe testy pozostają objęte zakazem.
- Wszystkie buildy i ciężkie kontrole wymagają właściwej grupy Compose oraz danych technicznych w named volumes.
- R0 runtime, R1–R8: w toku / NOT VERIFIED. Brak podstaw do deklaracji ukończenia.

## Próby środowiska

- Toolchain: `61e713183ebf41ee8b9c098c343f9114`, succeeded, image `sha256:fd6aaecf9d9534741ece960786e0adbbdfadca84c29662a74cf90aa0fc898eb7`.
- Grupa: `fullmag-worktree-viewport-visual-quality-20261020-781a03fef79664b6`, port 3218.
- Próba DEV `47764242ed494f8ebbc8c8d3acd69603`: terminalny `failed-confirmed`, kod 1. Backend zakończył się przed kompilacją aplikacji: live source changed while creating its closed manifest. Dwie kontrolne kopie źródeł różniły się podczas równoległych edycji. Zachowano control volume, logi, obrazy i cache; niczego nie usuwano. Nie ponawiać startu do czasu zakończenia aktywnych zapisów.
- Control volume: `fullmag-build-control-fullmag-worktree-viewport-visual-quality-20261020-781a03fef79664b6-e17595d5cb3174c4`.
- R2: dodano renderer tła solid/gradient, tokeny Mocha/Latte i integrację Scene. Panel ustawień w trakcie integracji z R1. Weryfikacja browser/typy pozostaje NOT VERIFIED.

## Kandydat źródłowy R1–R6 — 20.10.2026

Dokumenty bazowe zapisano commitem `2215e8313cbdf04c0d447a64cfaa1fc4350a03ef`.
Poniższe elementy są zaimplementowane w źródłach, ale nie mają jeszcze odbioru runtime:

- Wersjonowane preferencje localStorage z walidacją, stałym snapshotem SSR, hydratacją i resetami sekcji. Kamera pozostaje własnością istniejącego registry; nie jest zapisywana w preferencjach appearance.
- Gradient WebGL z tokenów Mocha/Latte, niezależny od materiałów danych; alternatywa solid i regulacja siły.
- Trzy ciągłe baselines, ticki o ekranowej długości, współrzędne world/frame-center, projektowane bounds etykiet, priorytety, strefy zajętego HUD i histereza wyboru krawędzi. Bias dotyczy wyłącznie głębokości po projekcji, bez zmiany współrzędnych pomiarowych.
- Studio key/fill związane z kamerą albo kierunkiem określonym w świecie; uniform geometry używa Lambert, kolory ilościowe pozostają domyślnie bez modulacji światłem i tone mappingu. Instancing FDM zachowany. Normale FEM są przygotowywane raz dla wymagającego ich materiału.
- Panel Tło / Siatka i skala / Światło / Kamera / Jakość / Eksport; komendy otwarcia, resetów, Fit i capture współdzielone z registry komend. Position/Target opisane w metrach SI.
- Bazowy render/composer ma priorytet 1, HUD layer 31 priorytet 2, snapshot eksportu priorytet 3. Liczniki gl.info obejmują cały render, a nie tylko końcowy HUD.
- AO/Bloom są konserwatywnie wyłączane przy aktywnych kanałach danych, w tym zachowanych buforach modalnych. Jest to ochrona na podstawie planu/kanałów, nie dokładny odczyt aktualnych pikseli GPU. Lokalne bufory zachowane przez MeshPartLayer uzasadniają ostrożność przy wymianie danych.
- PNG opaque synchronicznie kopiuje skomponowany canvas i DOM legend; transparent używa targetu RGBA w tym samym rendererze i pomija AO/Bloom (informacja w UI). Odwracanie premultiplication częściowego alpha odbywa się w linear light. Renderer/profile są przywracane przez finally, błędy pojawiają się w HUD, kolejne kliknięcie nie gubi profilu powrotnego. Capture zachowuje konfigurację kontekstu wyjściowego widoku.

### Macierz materiałów w zmienionych ścieżkach

| Ścieżka | Jednolita geometria | Kolor danych | Granica dowodu |
|---|---|---|---|
| PrimitiveObjectLayer | Lambert w studio, Basic w flat | istniejący podgląd/paleta | odczyt źródeł, obraz NOT VERIFIED |
| FdmCuboidLayer | instancjonowany Lambert/Basic | Basic lub istniejący shader, zawsze unlit | odczyt źródeł, RGB/normalne NOT VERIFIED |
| MeshPartLayer / TopologyMeshLayer | Lambert/Basic, normale przy wymagającym ich shaderze | Basic/custom scalar shader bez tone mappingu | odczyt źródeł, RGB/normalne NOT VERIFIED |
| Antenna / artifact / vectors | zachowane materiały naukowe | ochrona przed globalnym AO/Bloom | brak kwalifikacji ich wizualnego runtime |

### Wykonane kontrole

- `git diff --check`: passed dla bieżącego kandydata przed checkpointem.
- ESLint `src/modules/viewport-3d` oraz runner/helper browser QA: exit 0, zero ostrzeżeń (kontener frontend `3afd4865666f`, grupa zadania). Pierwsza próba z domyślnym limitem pamięci zakończyła się OOM; późniejszy skan użył jawnego limitu 4096 MiB.
- `check-architecture-hygiene.mjs`: exit 0 w grupie zadania.
- Produkcyjny TypeScript `--noEmit --incremental false --project tsconfig.typecheck.json`: brak błędów w zmienianym viewporcie; exit 1 z pięcioma istniejącymi błędami w primitiveSurfaceColor.ts:95, FieldMapModule.tsx:610/613 i ObjectRegionMagneticParametersPanel.tsx:48/198. Wszystkie trzy pliki są identyczne z bazą `88a9b68d29ec173a0b1f1b8750c126da022b0244`. Cały typecheck NIE przeszedł.
- API hygiene: narzędzie uruchomiono, ale jego wyszukiwania kończą się błędem, ponieważ obraz frontendu nie zawiera `rg`; nie jest to zielona bramka. Skrypt uruchomił własne interpretowane regresje Node, bez kompilacji testów jednostkowych.
- React Doctor `--scope changed --base 88a9... --include-untracked --no-score --no-supply-chain`: exit 1, bazowy ref niedostępny w cieniu źródeł frontendu. Bez automatycznego fetch i bez skanu zastępczego całego projektu.
- Review źródłowe R1–R5: bez potwierdzonego blokera. Review R6 wykryło niepoprawne unpremultiplication sRGB i asynchroniczny rozjazd obrazu/legendy; poprawki zapisane. Testy regresyjne są przygotowane, ale nie uruchomione ani skompilowane.

### Kolejna próba środowiska

- Odtworzenie usług `8894536233c54ea59b6a1f86d07462c9`: succeeded; jawny fresh-state zachowuje poprzedni root.
- DEV `5f57cccc6bd54cdfa3d8a9b975b47bbc`: `failed-confirmed`. Oba przebiegi manifestu były zgodne (9130 plików), ale późniejszy sync ponownie sprawdza live source i wykrył edycję eksportera. Następny start wymaga wstrzymania WSZYSTKICH zapisów przez capture, sync i kompilację.
- SHA konfiguracji tej próby: `82a065a154f6977317555b48a44c0ceafe625fc4311a356394fabadcee6dfcd9`.
- Usługi po tej próbie: backend `bc2c9636ddad` zatrzymany po błędzie, frontend `3afd4865666f` zachowany. Dokładne IDs i stan trzeba ponownie sprawdzić przed operacją.

## Macierz odbioru R7

### Checkpoint po uruchomieniu runtime i review

- Kandydat R1–R6: commit `722c18e63ac139b4e7e95ae649e2969316d5fdcf`.
- Resume `b0dfaf3874124dcfb78844b73e921dd1`: **succeeded**, konfiguracja `82a065a154f6977317555b48a44c0ceafe625fc4311a356394fabadcee6dfcd9`. Backend API/runtime ready; wersja `0.1.0-dev.20261020.g722c18e63ac1+9789`, snapshot `faed34783fcdc557977a14b252b3dab34e8ee3914ae6bd6bf1803561c7ec69ec`. Jest to dowód uruchomienia tej kompilacji, nie kwalifikacja solverów ani bieżących późniejszych edycji HMR.
- Aktualne kontenery zadania: backend `bc2c9636ddadf53604d655f072274146323f15faee55e608969733f249d85a33`, frontend `3afd4865666f`; grupa i port jak wyżej. Oba zdrowe podczas kontroli. Nie zmieniano grupy master.
- Aktywacja `2636a68de78641079e079fefb30cdc25` przykładu `viewport_2d_default_slice_fdm_smoke.py` odrzucona: runtime nie wykonuje prymitywnego etapu `hysteresis`. Pozostał model geometryczny i status startup_failed. Nie ponawiano tego intentu. Próba innego małego przykładu `230faa4bc11c46db96e1db9c71abeafa` została zatrzymana przed POST przez ochronę aktywnej/nieznanej sesji. Nie resetowano ownera ani bazy.
- Podgląd Chrome na `127.0.0.1:3218/workspace` pokazuje gradient, oświetloną bryłę, baselines, ticki i HUD. Po przeładowaniu otwarcie panelu View settings działa. To **wyłącznie geometry preview**, nie FDM field ani FEM mesh. Zapis obrazu: `C:/Users/Mateusz/.codex/visualizations/2026/10/20/01a15981-ab31-7ca0-960f-3d1145a8311d/viewport-preview-candidate-722c18e.png`.
- Późniejsze poprawki źródłowe: usunięto opcjonalne cieniowanie danych; wszystkie kolory ilościowe są unlit, także fallback shader. Obliczenia normalnych są pomijane przy zerowej sile cieniowania. Nieaktywne regulatory gradientu/światła są disabled z wyjaśnieniem. Przegląd ograniczonego diffu nie wykazał potwierdzonej regresji.
- Te poprawki zapisano commitem `34f05f42bc56e12bd03d8e39723bee796bfe163f`. Hook React Doctor: 14 plików, jedno ostrzeżenie o istniejącym `array.find` w FdmCuboidLayer:781, poza zmienionym fragmentem; bramki frameworkowe wyłączone przez brak rozpoznanego frameworka w korzeniu repo. Nie jest to pełny React proof.
- Ręcznie sprawdzono przełączenie Mocha → Latte → Mocha na tej samej scenie. Gradient zmienia się razem z motywem. Zapis Latte: `C:/Users/Mateusz/.codex/visualizations/2026/10/20/01a15981-ab31-7ca0-960f-3d1145a8311d/viewport-preview-latte.png`. Bez pomiaru DPR/kontrastu i bez danych pól: tylko częściowy dowód wizualny.
- Harness odczytuje rzeczywiste piksele canvasu z PNG Playwright, zamyka overlay ustawień na czas zdjęcia, przywraca UI w finally i porównuje hashe własnych źródeł przed/po. Wcześniejszy gl.readPixels po oddaniu bufora nie był wiarygodnym pomiarem; nie jest używany jako dowód.
- Ostatni ESLint viewportu i runner/helper QA: exit 0. Powtórny produkcyjny TypeScript: te same pięć błędów bazowych, bez błędów w zmienionym viewporcie; całe sprawdzenie nadal exit 1.
- Pierwsza próba QA zatrzymana przed przeglądarką: wrapper ignorował succeeded resume, wymagając succeeded pierwotnego development/current. Poprawka konsumenta korzysta z istniejących `_linked_runtime_terminals` i `_validate_running_group`, waliduje current/terminal, config CAS, źródła, obraz i aktywne kontenery; nie zmienia historycznych receiptów. Provenance rozdziela development attempt i runtime phase/attempt/hash. Po uzyskaniu lease ponownie sprawdzany jest fence pierwotnej próby.
- Poprawki podstawowego QA zapisano commitem `4a92b5c0619f34ed3ec1df1019cb7982bc406e2e`. Dalsze zmiany opisane poniżej pozostają kandydatem źródłowym.
- Managed browser QA `faa969d54b3f482f885d01b5b8f97626`: obraz Playwright pobrany, przeglądarka uruchomiona; klient Compose przekroczył limit 300 s, a przeglądarka zakończyła się po około 337 s kodem 1. Output utracony, brak pozytywnego dowodu QA. Zachowano nieznany receipt. Wąska, przypięta reconciliation potwierdziła stopped/exit 1, źródło, obraz, komendę, konfigurację i tożsamość helperów; zapisała evidence przed usunięciem wyłącznie zatrzymanej przeglądarki. Techniczny terminal pozwolił oryginalnemu helperowi zwolnić własny lease: **exit 0, lease_released=true, verification=NOT VERIFIED**. Nie dotykano backendu, ownera ani markerów ręcznie. Powtórzenie po przerwaniu korzysta z trwałego evidence i CAS; obcy aktywny token jest odrzucany.
- Próby `b83107673048410b9d02d0ea9b2c6a0d`, `27a045f76a8a40d3a0a6a33e300eacaf`, `38c70f330c0841c198a1169b0391b5e6`: terminalne failed-confirmed, zasoby helperów zamknięte normalnie. Ograniczenie akcji do 30 s pozwoliło zachować błąd i diagnostykę: brak widocznego workspace, klient na Home/reconnecting, bezpośredni status API 200 z active/startup_failed, błędy HMR dla originu `frontend`. Nadpisanie runtime API base nie rozwiązało tego przebiegu. Nie wolno przedstawiać samej hipotezy API-base jako potwierdzonej przyczyny.
- Odczyt mountu QA wymaga normalizacji równoważnych ścieżek Windows i Docker Desktop (`/run/desktop/mnt/host/c/...`). Wrapper używa istniejącego `_canonical_host_path`, nadal porównując dokładną wybraną ścieżkę i readonly bind.
- Testowy alias `frontend` nie był obecny w zainicjalizowanym next.config zapisanym jako immutable dependency input w named volume. Tymczasową zmianę next.config wycofano; nie resetowano ani nie przepisywano tej konfiguracji w działającym wolumenie.
- QA loopback proxy w jednorazowym helperze słucha tylko na `127.0.0.1:<wybrany port>` wewnątrz jego namespace i przekazuje HTTP/WS wyłącznie do `frontend:8080` tej samej prywatnej grupy. Przeglądarka używa normalnego originu aplikacji; nie publikuje się dodatkowego portu hosta, nie zmienia auth ani konfiguracji aplikacji. Osobna sonda nadal sprawdza rzeczywisty publiczny loopback hosta. Próba `87116a5b611b4072ad08db7095988c51`: w toku w chwili zapisu.
- Przygotowano oddzielne helpery pobrania/dekodowania PNG (opaque, transparent, annotations, powrót profilu) i 20 cykli 3D/2D (canvas, zasoby, idle, requesty). Jeszcze nie podłączono ich do runnera: **NOT VERIFIED**. Brak liczników jest raportowany jawnie, nie zastępowany zerem.
- Regresje wrappera i reconciliation są zapisane jako źródła; AST i diff-check przeszły. Nie uruchamiano ani nie kompilowano testów jednostkowych. ESLint runnera/proxy/nowych helperów: exit 0.

### Częściowe wyniki wykonanej próby `bdc54a0dfc9a4245a7e75c3a4c59f0ef`

Cała próba: **failed-confirmed**, 18 błędów HTTP 422 w konsoli przy przejściach do 2D na wcześniejszej scenie bez poprawnej siatki. Nie oznaczać jej jako passed. Page errors, błędy transportu i błędy proxy: zero. Pełne dane częściowe są w `browser-qa/attempts/bdc54a0dfc9a4245a7e75c3a4c59f0ef/runner-output.json` w control volume wskazanym wyżej.

- Gradient → solid → gradient: 243137 zmienionych pikseli, różnice próbek górnej/dolnej 6 / 15.333; powrót do początkowych próbek: różnica zero. World/frame-center: 12337 zmienionych pikseli. Są to testy geometry preview, nie dowód niezmienności RGB pola.
- Eksport opaque: 712×554, wszystkie 394448 pikseli alpha=255. Transparent bez oznaczeń: 339371 pikseli alpha=0, 55077 pikseli widocznej geometrii. Zmiana annotations on/off: 33874 piksele. Profil Interactive i ustawienia wróciły. Przy DPR1 nie dowodzi to przejścia rozdzielczości Interactive 1.25 → Capture 2.
- Dwadzieścia cykli 3D/2D: po powrocie zdrowy WebGL2 i niezerowy buffer 712×554. Zasoby przed/po: geometries=7, materials=0, renderTargets=0, textures=1, workers=0; wszystkie 20 pomiarów po odmontowaniu: zero. Przyrosty klatek idle: [0,0,0] w trzech odcinkach po 350 ms. To dowód dla tej małej sceny, nie budżet dużego FEM.
- Zmiana tła nie spowodowała pasujących requestów pól/topologii. Po przeładowaniu preferencje zachowane, tożsamość sesji stabilna. Okno ustawień sprawdzone przy rozmiarze okna 480×320; nie był to jeszcze canvas 480×320.
- Próba `87116a5b611b4072ad08db7095988c51` również terminalna: workspace dostępny przez proxy, bez błędów strony/proxy/HMR. Ówczesna bramka uznawała anulowanie przestarzałych GET przez resource hooks za awarię; te anulowania są teraz rejestrowane oddzielnie, bez ukrywania błędów HTTP/konsoli.

### Własna scena do dalszego odbioru

Przez zwykły formularz New Problem utworzono własną sesję **Viewport visual quality QA FDM**, zastępując wyłącznie własny nieudany model testowy. CPU/double, początkowo status Awaiting command. Backend zaproponował storage `/state/runs/projects/viewport-visual-quality-qa-fdm_2026-10-20_182016/results.zarr`; opcja zapamiętywania ustawień storage pozostała wyłączona. Nie potwierdzono zapisu projektu. Późniejszy odczyt UI pokazuje **No project**, Save Project disabled: wymagany writable project; sesja nie jest dowodem utworzenia trwałego dokumentu projektu.

Obiekt `qa-offset-film-mvgw65uf`, nazwa `QA offset film`: box [40,30,10] nm, przesunięcie [20,-10,10] nm. Zakresy x=[0,40], y=[-25,5], z=[5,15] nm. Obraz `C:/Users/Mateusz/.codex/visualizations/2026/10/20/01a15981-ab31-7ca0-960f-3d1145a8311d/viewport-offset-geometry-mocha.png` potwierdza podgląd geometrii, gradient, linie skali i oświetlenie; nie potwierdza pól, materiału ani solvera.

Dodano warunek montowania ramki wymiarowej tylko dla skończonych bounds z przynajmniej jednym dodatnim rozmiarem. Brak danych i punkt nie generują pozornej skali; domeny 1D, płaskie 2D i cienkie 3D pozostają obsługiwane. Regresje źródłowe przygotowane, bez wykonania unitów. Helper rzeczywistego canvasu 1200×800/480×320, Mocha/Latte i DPR1/2 jest podłączany do runnera; jego obecność nadal nie jest dowodem wykonania.

V01–V15: **odbiór częściowy, bez pełnego zaliczenia**. Brakuje kompletnej macierzy DPR/motywów i kamer, FDM/FEM, ilościowego kontrastu/RGB oraz poprawnej sceny pól w całym przepływie 2D/3D. Nie ma zgody na pominięcie tych bramek.

### Kolejna macierz layout/eksport — `b5a45fc604634867b1e009fc1abe8bdd`

Próba terminalna **failed-confirmed** z powodu 19 odpowiedzi 422 zasobu `data/fields/m/planar-default/meta` przy przełączaniu do 2D bez gotowych danych. Wszystkie poprzedzające ten końcowy gate scenariusze zwróciły wyniki częściowe. Page errors, request failures i proxy failures: zero; HTTP/konsola pozostają fatal, nie są filtrowane. Źródła harnessu były niezmienione w trakcie próby.

- DPR1: Mocha/Latte, rzeczywisty canvas około 1200×800 i 480×320 CSS px (tolerancja ±3 px); effective buffer scale 1. DPR2: te same cztery warianty, realny `window.devicePixelRatio=2`, Interactive buffer scale 1.25. Widoczny canvas, zdrowy WebGL, niezerowy buffer; widoczne prostokąty DOM HUD bez kolizji. Nie obejmuje to testu kolizji wszystkich sprite'ów i etykiet w WebGL.
- Eksport DPR2: CSS 456.296875×554.6875, Interactive buffer 570×693, PNG 912×1109, powrót do 570×693; ten sam node canvas, kontekst zdrowy. Wszystkie trzy warianty eksportu potwierdziły ten powrót. Opaque: 1011408 pikseli alpha=255; transparent bez oznaczeń: 797613 pikseli alpha=0 i 213795 widocznych pikseli geometrii. Zmiana oznaczeń: 91082 piksele.
- PNG z wąskiego canvasa zapisano w katalogu wizualizacji zadania jako `viewport_layout_dpr1-Mocha-480x320.png`, `viewport_layout_dpr1-Latte-480x320.png`, `viewport_layout_dpr2-Mocha-480x320.png`, `viewport_layout_dpr2-Latte-480x320.png`. Po oględzinach jasnego wariantu liczby podziałki otrzymały kolor primary i font weight 700, niezależnie od koloru kresek. Ta późniejsza poprawka wymaga nowego obrazu; powyższe PNG są dowodem stanu sprzed niej.
- Pierwsza próba tej macierzy `6f57a333bc6f48b2b173e1e33e064cde` zatrzymała się na kalibracji rozmiaru, bez błędów strony/HTTP/WebGL. Korekta kalibracji używa zmierzonego nachylenia rozmiaru canvasa względem okna; nie obniżono docelowych wymiarów ani tolerancji.
- Ponowny produkcyjny typecheck po warunku pustej ramki: nadal pięć tych samych błędów bazowych, exit 1. ESLint nowych helperów/runnera i poprawki tekstu: exit 0. AST trzech plików wrapper/reconcile/regresje: passed. Testów jednostkowych nie wykonano ani nie skompilowano.

Do opt-in przygotowano helper małej sceny pól, ograniczony do istniejącej sesji z jedynym obiektem `qa-offset-film-mvgw65uf`/`QA offset film`. Source review potwierdził kontrakty scope/revision/ACK/readback i brak replace/reset. Przygotowanie fixture nadal **NOT VERIFIED**; dostępny katalog pól sam w sobie nie będzie dowodem pobrania bajtów ani adopcji w viewporcie.

### Przygotowanie własnego FDM — próby bez solve

- Jawny opt-in `--prepare-viewport-fixture` jest zapisywany w inputs receiptu i środowisku QA; domyślny przebieg pozostaje bez mutacji sceny. Reconciliation korzysta wyłącznie z przypiętej wartości bool; brak pola w historycznych receiptach oznacza false.
- `a621248dee3444d8814c129e0057fd79`: failed-confirmed przed komendami. Materiał, przypisanie, uniform-Y i exchange/demag: pięć zmian ACK/readback, rewizje 1→6. Study ACK revision 7. Kontrola oczekiwała dawnego `per_magnet`; niezależny GET potwierdził kanoniczne `study.fdm.per_object_grid`, poprawny CPU/double, grid i etap relax. Poprawiono konsumenta i pomijanie już zgodnego study; brak automatycznego ponawiania nieznanych zapisów.
- `8032b60a784c4ff7b72f58ea4491c3b5`: bez dodatkowych zapisów authoring. POST mesh_build odrzucony HTTP 422 przed ACK: 4 nm nie dzieli wymiarów 30 i 10 nm. Command intent zachowany w runner-output: `viewport-qa-fixture:0cfb06e58d9e157120c987feaf154be580e702b138ae008106aca54295e477d9:mesh-build`; brak command_id i brak uruchomienia solve. Późniejsza wersja helpera jawnie rozróżnia odmowę 422 od nieznanego wyniku transportowego.
- Fixture dopasowano do istniejącej geometrii przez komórkę [2,2,2] nm, bez zmiany boxa/transform. Identyfikatory komend są deterministyczne z treści fixture, sesji i zachowanej geometrii/transformacji. Kolejna próba wymaga nowego dowodu; nie przedstawiać wcześniejszych odmów jako wykonania mesha/pól.
- Architecture hygiene po aktualnych zmianach: exit 0. ESLint helpera fixture po korekcie kanonicznego pola i komórki: exit 0. Nie wykonano kompilacji ani uruchomienia unitów.

### Blokada accepted-run i zachowany Stop

- `91452d6cff8743dc8f43d3fe5bc68db3`: study grid 2 nm potwierdzony na revision 8. Mesh POST zwrócił 422 z **durable accepted run**, nie ze zwykłą odmową przed zapisem: `run-live-0cc7302699581e9e1c11d5b210107633b74e674f8874d33d64b883ecac0d9084`. Przygotowanie niekompletne: brak resolved region marker. Backend log `2026-10-20T16:53:22.741523Z` potwierdza zachowanie RunIntent do recovery. Nie rozpoczęto solve ani automatycznego retry.
- Read-only GET sceny: `region_name=null`, geometria i transform bez zmian. Helper źródłowo uzupełnia brak regionu publicznym PATCH, ale `13a94176c17242929b9e6bc5fd2e804c` otrzymał 409: accepted run blokuje edycję; draft **nie został zastosowany**. Obecna wersja rozróżnia `accepted-preparation-incomplete`, `rejected-before-ack`, `rejected-no-write` i `outcome-unknown`.
- Publiczny GET `simulation/commands` zezwalał na Stop, chociaż przyciski UI były disabled z komunikatem Runtime is not active. Po ponownym sprawdzeniu dokładnej sesji, runu i readiness wysłano **jeden** Stop z `client_intent_id=viewport-qa-stop:run-live-0cc7302699581e9e1c11d5b210107633b74e674f8874d33d64b883ecac0d9084` i targetem tego runu. ACK: `fm-7824061f-333e-47d5-bf39-d397d5410a1b`, request `fm-c631565e-845d-4316-a145-f1a60479d5b2`.
- Odczyt `2026-10-20T17:03:04.4126619Z`: komenda **accepted**, run **stopping**, brak terminalnego zakończenia. UI pokazuje Breaking. Obraz: `C:/Users/Mateusz/.codex/visualizations/2026/10/20/01a15981-ab31-7ca0-960f-3d1145a8311d/viewport-qa-stop-pending.png`. Nie zmieniano ownera, bazy ani journalu ręcznie; nie restartowano backendu, nie ponawiano Stop i nie obchodzono blokady edycji.
- Przygotowanie pól FDM i przejście do FEM pozostają zablokowane do prawidłowego terminalnego rozliczenia tego własnego runu. Wymagany następny krok: obserwacja/naprawa obsługiwanej ścieżki accepted Stop/recovery, z zachowaniem run identity i dzienników. Sam screenshot bryły nie zastępuje tej bramki.

### Zapisane etapy

- `a81ad772749e0f84c658eee9bfdf0885a6ca3482`: ochrona pustej ramki i mocniejsze liczby podziałki; lint/diff passed, regresje źródłowe bez wykonania unitów.
- `3cae01857b630eb2825e4b22782307bf467034b7`: rozszerzone managed browser QA, diagnostyka i reconciliation. Hook React Doctor: sześć ostrzeżeń o kolejności await w narzędziach QA, framework-neutral only; niezależne odczyty kontrolek poprawiane, fences identity/revision pozostają sekwencyjne. Nie jest to pełny React proof ani zielona kwalifikacja całego planu.

### Kamera — wykryte rozbieżności R5

- `81651d30e804467e97f13e89113765ca`: scenariusz kamery nie rozpoczął mutacji; helper szukał dialogu po `3D camera parameters`, natomiast dostępna nazwa z Radix DialogTitle to **Camera Parameters**. CUA potwierdziło otwarcie przez widoczną command palette. Poprawiono selektor i opis dowodu odtworzenia, aby brak mutacji nie był nazywany odtworzeniem przez dialog.
- CUA pokazało dodatkowy realny błąd: dialog czytał `commandState.camera` (pozycja [2,1.4,2] µm, cel zero), podczas gdy aktywna scena po Fit miała pozycję około [93.082,42.619,80.582] nm i cel [20,-10,7.5] nm. Module przekazuje teraz do dialogu `sceneProps.cameraState`, zachowując routing zapisu current→cameraRegistry / saved→patchSavedCamera. Review źródłowe tej poprawki: bez potwierdzonej regresji własności.
- `1b21a88971d642748f23267e9bec502c`: próba zatrzymana przed przeglądarką przez timeout publicznego loopback probe podczas HMR. Kontener frontendu pozostał healthy, OOMKilled=false. Nie jest to wynik scenariusza kamery i nie pominięto probe.
- Review ujawnił istniejącą niespójność FOV: dialog przechowuje `cameraResource.fov_degrees`, renderer używa stałych 42°. Poprawka połączenia FOV z rendererem/Fit jest w toku. Wymagany dowód: rzeczywista zmiana PNG przy stałym position/target, dwa poprawne FOV, zależny od FOV Fit i odtworzenie parametrów. Sam odczyt formularza nie dowodzi działania FOV.
- Produkcyjny typecheck po zmianie źródła dialogu: exit 1, te same pięć błędów bazowych poza zmienionym viewportem. ESLint Module/helpera: exit 0.

### Macierz V01–V15 — stan cząstkowy

| ID | Stan | Aktualna granica dowodu |
|---|---|---|
| V01 pusta scena | NOT VERIFIED | Warunek pustej ramki w źródłach; brak nowego PNG pustej sceny po poprawce |
| V02 bryła z otworem | NOT VERIFIED | Referencja użytkownika; brak odtworzonej, przypiętej sceny runtime |
| V03 przesunięcie i origin | PARTIAL | Offset box, zmiana world/frame-center i obrazu; bez pełnej kontroli Lx/Ly/Lz |
| V04 cienkie/wydłużone domeny | NOT VERIFIED | Box 40×30×10 nm nie zastępuje skrajnie cienkiego filmu |
| V05 projekcje i osiowe | PARTIAL | Perspective/ortho, FOV35/70, Fit i restore potwierdzone; pełne widoki osiowe/ViewCube nadal niewykazane |
| V06 orbit/ćwiartki/spód | NOT VERIFIED | Pozy przez dialog nie są dowodem płynnej orbity ani ViewCube |
| V07 motywy/DPR | PARTIAL | Mocha/Latte × DPR1/2 wykonane; liczbowy kontrast wszystkich etykiet niezmierzony |
| V08 rozmiary/HUD | PARTIAL | Canvas 1200×800/480×320 ±3 px; DOM HUD bez kolizji; sprite'y poza tym checkiem |
| V09 materiały | PARTIAL | Primitive geometry preview; FDM fields i FEM zablokowane |
| V10 kolory danych | NOT VERIFIED | Źródłowo unlit i ochrona efektów; brak ilościowego RGB na danych runtime |
| V11 invalidation | PARTIAL | Zmiana tła bez żądań pola/topologii na geometry preview; brak sceny załadowanego pola |
| V12 idle/interakcje | PARTIAL | Idle [0,0,0] i brak wzrostu zasobów na małej scenie; bez budżetu dużego FEM |
| V13 churn 20× | PARTIAL | Zasoby i canvas po 20 cyklach sprawdzone; cały flow czerwony przez błędy zasobów 2D |
| V14 reload/identity | PARTIAL | Preferencje reload i stabilna sesja; nowe dataset/saved identity niekwalifikowane |
| V15 capture | PARTIAL | Pobrane opaque/transparent/annotations i DPR2 restore; błąd capture nieprzetestowany runtime |

PARTIAL nie oznacza zaliczenia całego kryterium. R8 pozostaje niezrealizowane; worktree i dowody trzeba zachować.

### Retencja po próbach QA

Kontrola `2026-10-20T17:21:28.6806606Z`: host C ma 93605904384 B wolnego miejsca (pomiar hosta, nie wolnego miejsca wewnątrz silnika Docker). W grupie zadania działają tylko zdrowe backend/frontend; jednorazowe helpery zakończonych prób zostały rozliczone przez launcher. Brak autoryzowanego kandydata do usunięcia: zachować control volume z receiptami/logami/runner-output, żywe named volumes i cache, własny projekt oraz accepted run/journal wymagający recovery. Worktree jest aktywnie bind-mountowane, więc cleanup jest niedozwolony. Ponowna ocena po terminalnym rozliczeniu runu i zakończeniu kwalifikacji; żadnego prune ani usuwania wyników.

Zakaz testów został później uchylony wyłącznie w zakresie opisanym niżej. Nie wykonywać merge ani cleanup worktree przed wymaganymi dowodami całej macierzy. R8 integracja: NOT STARTED. Kod nie jest przedstawiany jako ukończona realizacja planu.

### Kontynuacja R7: FOV, clipping i zasoby frontendu

Uzgodnione między zadaniami okno bez zapisów zostało zachowane i jawnie zwolnione po synchronizacji `fullmag-master`. Nie zmieniano głównego checkoutu, jego HEAD/indeksu ani kontenerów. Dalsze zapisy dotyczą wyłącznie worktree tego zadania.

WIP kamery przekazuje FOV właściciela current/saved do renderera i dialogu, normalizuje zakres `0 < FOV < 180`, uwzględnia aspekt viewportu przy perspektywicznym Fit i aktualizuje samą macierz projekcji przy zmianie FOV. Review wykrył dodatkowy błąd: near wyliczany z hipotetycznego fit przy FOV 0.1° odcinał model bez zmiany pozy. Poprawiono near względem rzeczywistej głębokości sfery bounds; far uwzględnia również jej rzeczywistą głębokość. Ortho zachowuje parametry fit 42°/aspect 1. Niezależny przegląd źródeł tego fragmentu nie znalazł dalszego blockera. Dodane regresje projekcji dla FOV 0.1/42/179 i targetu poza modelem pozostają **nieuruchomione i nieskompilowane**.

Ponowiony szeroki lint z limitem heap 4 GiB zatrzymano celowo przez SIGTERM wyłącznie procesu ESLint tego zadania: Next.js zajmował około 4.4 GiB RSS, a łączna pamięć kontenera osiągnęła limit 6 GiB. To nie jest zielony wynik lint. Pierwszy GET workspace przekroczył 45 s, po zwolnieniu pamięci następny zwrócił HTTP 200. Syntax check nowego helpera kamery oraz lint runnera i helpera kamery zakończyły się kodem 0, bez ostrzeżeń. Pełny typecheck nowych zmian FOV nadal **NOT VERIFIED**.

Zarządzana próba `4ea4e1adf2474862ada0b177b6caab5b` zakończyła się `failed-confirmed`: timeout download PNG w scenariuszu eksportu, przed scenariuszem kamery. Canvas pozostał WebGL2/context-lost=false/buffer 712×554; UI zgłaszało `Resource load deadline exceeded`. Zarejestrowano 6 HTTP 400/404 dla frozen_spins i frequency-response, bez page errors i transport failures. Częściowy proof appearance ponownie wykazał gradient (258078 zmienionych pikseli), world/frame-center (9224 piksele), reload preferencji i przywrócenie ustawień. Nie jest to dowód działania FOV ani zaliczenia eksportu. Launcher rozliczył helpery bez ręcznego zwalniania lease.

Scenariusz kamery przeniesiono przed eksport, zachowując wszystkie wymagane sprawdzenia i czerwony wynik całości przy błędzie. Kolejna próba trwa; jej wynik wymaga odczytu receiptu i pełnego runner-output. Nie wykonywano Solve, resetu ownera, restartu backendu ani modyfikacji accepted run/journal.

Próba `6abe8332caeb48feb3e68ed89ae2cb86` została rozliczona jako `failed-confirmed` z powodu błędów HTTP, ale dotarła do końca macierzy. `viewport_camera.state=passed`: rzeczywisty dialog zgadzał się z pozycją/targetem renderera w SI; przełączenia perspective→ortho→perspective, pięć zadanych ujęć (w tym od spodu), FOV 35/70 przy stałej pozycji (84626 zmienionych pikseli), odmienna odległość Fit dla obu FOV oraz końcowe przywrócenie kamery i tego samego canvasa potwierdzone. Ujęcia przez dialog nie dowodzą płynnej orbity ani interakcji ViewCube. FOV 0.1 i 179 pozostają wyłącznie źródłami nieuruchomionych regresji clippingu.

W tej samej próbie ukończono oba eksporty DPR1/DPR2, układy Mocha/Latte DPR1/DPR2 i lifecycle. Nie zaciera to wcześniejszego timeoutu eksportu ani nie dowodzi braku awarii pod obciążeniem. Całość czerwona: 32 zarejestrowane HTTP errors/console errors, page errors=0, transport failures=0. Unikalne ścieżki: frozen_spins (400), frequency-domain response/progress (404), planar-default meta bez danych pola (422). Zrzut `viewport-camera-initial-6abe8332.png` zapisano w katalogu wizualizacji zadania i obejrzano: gradient, bryła, skala i baselines widoczne; brak danych pola.

Produkcyjny typecheck z heap 1 GiB wykrył brak `camera-fov` w typie diagnostyki; po jego uzupełnieniu ponowiony wynik zawiera wyłącznie pięć wcześniej wskazanych błędów bazowych w primitiveSurfaceColor, FieldMapModule i ObjectRegionMagneticParametersPanel. Cały typecheck ma exit 1, nie jest zieloną bramką. Nowe źródła kamery nie generują w tym przebiegu diagnostyk TypeScript. Nie kompilowano testów jednostkowych.

### Ograniczony wyjątek dla regresji viewportu i pierwsze wyniki

Użytkownik odpowiedział jawnie: **„Tak, tylko regresje viewportu”** na pytanie o odwołanie zakazu wyłącznie dla wymaganych regresji tej refaktoryzacji w grupie Docker worktree. Od tej odpowiedzi wolno kompilować/wykonywać ten zakres; wcześniejsze stwierdzenia o zakazie opisują historię. Pozostałe testy pozostają objęte zakazem. Nie zmieniono AGENTS.md ani globalnej konfiguracji.

Wąskie linty Scene/Types/FOV, runnera/helpera oraz dialogu/saved-camera/CameraControls zakończyły się kodem 0 bez ostrzeżeń po poprawieniu zależności memo i Orbit size. Szeroki lint Model+komponenty przy heap 1280 MiB zakończył się OOM; pozostaje otwartą bramką, nie zielonym wynikiem.

Usunięto błędne memo zależne od indeksowanych tuple i pomijanego FOV. Stabilny fallback sceny służy pierwszemu renderowi; Controller i Orbit otrzymują surowy stan właściciela. Dla początkowego domyślnego źródła Controller wykonuje Fit aktualnym FOV/aspect, a Orbit przyjmuje target dopiero gdy pozycja dokładnie odpowiada temu Fit. Nie nadpisuje targetu kamery autorskiej ani pozycji przesuniętej gestem. Review źródeł nie znalazł dalszego defektu w tym bounded fragmencie; ponowny runtime po tej zmianie nadal wymagany.

Pierwsze 5 grup regresji ujawniło 6 failures. Raport v2 po kolejnych zmianach: **250 testów, 243 passed, 7 failed**. Dowody: `/state/development/test-evidence/viewport-visual-quality/camera-regressions-v2.json` i `.log` w technicznym wolumenie tej grupy. Dwa failures dotyczą asercji tekstowych CameraControls/Scene, które nie śledziły rozszerzonego bloku sync i przeniesienia flagi do PostProcessingLayer; skorygowano zakres asercji bez usuwania sprawdzanej ochrony. Pozostałe 5 w SceneModel (Airbox key, retention, render fixed point, catalog gating) jest badane; nie uznano ich za bazowe bez dowodu wykonania. Raport v3 dla 4 grup kamery trwa, szersza bramka nie jest zamknięta.

### Aktualny wynik R7 — 84% realizacji, integracja otwarta

Najnowszy wynik każdego sprawdzonego pliku: **26 plików / 594 testy / 594 passed / 0 failed / 0 pending**. Zestawienie obejmuje raporty `camera-regressions-v3`, `appearance-core-v1`, `capture-primitive-v2`, `scene-model-v3`, `scene-module-manifest-v1`, `module-v2`, `material-hud-v1`, `colors-fdm-v2` w `/state/development/test-evidence/viewport-visual-quality/` (JSON + log, techniczny wolumen frontendu). Późniejszy raport dla danego pliku zastępuje wcześniejszy czerwony wynik; nie sumowano wielokrotnych wykonań jako różnych testów. Nie ponawiano zielonych niezmienionych grup dla samej deklaracji zakończenia.

SceneModel: 158/158 po korekcie dwóch nieaktualnych asercji tekstowych i trzech fixture'ów. Oczekiwana rewizja `top-1` wymaga rzeczywistej `carrierRevision`/`meshTopologyRevision`; hash nie jest rewizją. Nie zmieniono produkcyjnej retencji. Module: 72/72 po korekcie wyszukiwania otwierającego tagu, które urywało blok na `=>` handlera. Capture/primitive: 28/28 po wykorzystaniu istniejącego fake document i uwzględnieniu przypisań koloru. Colors/FDM: 58/58 po uwzględnieniu tokenów gradientu/palety i Basic/Lambert przy zachowaniu asercji własności materiału. Niezależny przegląd źródeł tych zmian nie znalazł blockera ani osłabienia tożsamości/retencji.

Ponowiona po poprawce Orbit próba browser **`67555cc24d794e7e8f9300ae4df32cf2`**: wszystkie siedem części macierzy zapisane; kamera `passed`, FOV35/70 zmienił 84626 pikseli przy stałej pozycji, Fit zależny od FOV i restore tego samego canvasa potwierdzone. Całość **failed-confirmed** przez 32 zarejestrowane błędy HTTP/console (frozen_spins400, frequency response/progress404, planar-default meta422), bez page errors i transport failures. Oryginalne raporty pozostają w control volume. Nie filtrowano tych błędów, nie uznano całego browser QA za zaliczony i nie resetowano zablokowanego accepted runu.

Nadal otwarte: pełny lint dużych plików (OOM), całkowicie zielony typecheck (5 błędów bazowych), API hygiene, pozostała macierz R0/R7 dla pustej sceny/otworu/skrajnie cienkiej geometrii, rzeczywistych pól FDM/FEM i ilościowego koloru, ViewCube/płynnej orbity oraz dużej sceny. Przygotowanie pól blokuje istniejący accepted run w stanie stopping; nie wolno zastąpić recovery resetem ownera ani usunięciem journalu. R8 push/PR/merge/cleanup nie rozpoczęto. Zgłoszenie z równoległego odbioru master3198 o niedostępnych diagnostics przed resolved discretization zapisano do dalszego rozpoznania; nie jest własnym dowodem runtime tego worktree i nie wykonano na tej podstawie zmiany mastera.

Fragment R5/R7 zapisano w commicie **`d87d42ed78a4267d9d9ad064d2c04f6c2c14543c`** (23 pliki; FOV, fit/clipping, właściciel dialogu, browser helper i regresje). Przed commitem sprawdzono osobno staged names, staged diff i whitespace. Hook zakończył się kodem 0, ale React Doctor zgłosił 8 ostrzeżeń (framework rules gated off na repo root; wynik nie kwalifikuje całej aplikacji React). Niezależne odczyty formularza i trzech składowych wektora zrównoleglono po commicie; ich lint ma exit 0 bez ostrzeżeń. Pozostawione pętle wykonują sekwencję zmian projekcji/FOV/pozy i pola kontrolowanego formularza; równoległe mutacje tego samego UI mogłyby naruszyć kolejność i restoration. Nie wyciszano reguł. Najnowszy browser proof dotyczy helpera sprzed tej zmiany wyłącznie kolejności odczytów; nie deklaruje się nowego pełnego PASS dla zmienionego harnessu.

### Diagnostyka blokady runu — odczyt 18:24–18:30 UTC

HEAD po uporządkowaniu odczytów QA: `5867accc9a60ed4c9abdd64817c9c463a4f7c009`; worktree był czysty. Hook drugiego commita zakończył się kodem 0 i pozostawił 4 ostrzeżenia o sekwencyjnych pętlach mutacji UI; niezależne odczyty nie były już zgłaszane. Rejestr właściciela został zaktualizowany zarządzanym `fullmag_storage.py register`, z zachowaniem bazy i celu R0–R8.

Publiczny odczyt `2026-10-20T18:24:59.0847643Z`: dokładny run `run-live-0cc7302699581e9e1c11d5b210107633b74e674f8874d33d64b883ecac0d9084` nadal `stopping`, revision 8; komenda Stop `fm-7824061f-333e-47d5-bf39-d397d5410a1b` nadal `accepted`. Nie ponawiano komendy.

Konfiguracja własnego kontenera i jego procesów API/runtime wskazuje `/opt/fullmag/runtime-control/runtime-service/docker-all.json`, `runtime_service_config.v2`, `store_root=/state/runs/docker-all/session-store`. Publiczny `/v2/platform/openapi.json` nadal publikuje binding `0d68a6bc4fcfc7e892f948de50821e1de9d237596a74bda3d44a014010848dda`. Obliczenie według `accepted_store::store_binding` dla tego samego katalogu z końcowym separatorem (wynik `canonicalize(...).join(empty)` w `writable_product_state_path`) daje dokładnie ten binding. Sam hash ścieżki bez separatora był inny; nie uznano tego za drugi store.

Odczytany bez modyfikacji `runs/<run_id>/run_catalog.json` ma SHA256 `633a3dadbdca1c4485a9c03f165826f4f94436d2641cbb30beedf20e81a699bf`; jedyny task `task-235b85b4778fcb3a7ac16b3d20ff56cda9d3ddfdd6f8be28cd84664babab4b83` ma lifecycle **cancelled**. W katalogu runu istnieją tylko `run_intent.json` i `run_catalog.json`; **`artifact_catalog.json` nie istnieje**. Nie jest to dowód braku każdego procesu ani upoważnienie do restartu lub zwolnienia ownera.

Źródłowy mechanizm rozbieżności: `live_accepted_projection::load_durable_projection` po odczycie run catalog wymaga `read_artifact_catalog`; przy `None` zwraca `Ok(None)` przed obliczeniem `accepted_projection_status`. `catalog_status` potrafi mapować task Cancelled na run cancelled, lecz ten przypadek nie dochodzi do mapowania. Publiczne `get_current_run/get_run_by_id` zwracają bieżący read-model sesji, więc nie naprawiają tej rozbieżności samym GET. To konkretna diagnoza source+durable readback, bez patchowania backendu, tworzenia pustego katalogu artefaktów, modyfikacji journalu ani resetu UI.

Zapytano użytkownika o upoważnienie do jednej wiadomości z tą diagnozą do istniejącego czatu „Przywróć wizualizacje FEM i FDM”, który zajmuje się recovery. Do otrzymania odpowiedzi nie wysyłać wiadomości; samo otrzymanie wiadomości z innego zadania nie udziela zgody na odpowiedź. Ewentualna naprawa backendu wymaga rozstrzygnięcia zakresu i jego osobnych bramek; wyjątek od zakazu testów dotyczy wyłącznie regresji viewportu. Kontrole API wymagają brakującego `rg` w obrazach obu usług; nie instalowano narzędzi na hoście ani w działającym runtime, nie uruchamiano testów API poza udzielonym wyjątkiem.

### Widoki osiowe i niezależne kontrole — R7, 85%

Zarządzana próba **`63bbf8679c9f4a84b4016ff4c63a2d28`** objęła dodatkowo sześć kierunków ±X/±Y/±Z. Wszystkie 11 zadanych pozycji, projection toggle, FOV i restore mają `viewport_camera.state=passed`; restore potwierdza ten sam canvas/context. Obraz `viewport-axis-z-positive-63bbf867.png` zapisano w katalogu wizualizacji zadania i obejrzano: widoczna powierzchnia bryły, skala XY i orientacja +Z; brak danych pola. Osiowe ustawienia dialogiem nie dowodzą obsługi kliknięć ViewCube ani ciągłej orbity. Wszystkie siedem części runnera ma proof, ale całość nadal **failed-confirmed** przez 32 HTTP/console errors, page errors=0 i transport failures=0. Harness po zmianie równoległości odczytów został w tej próbie faktycznie wykonany; lint nowej macierzy ma exit0.

Architecture hygiene wykonano w usłudze frontend grupy worktree: **exit0 / passed**. Cztery kontrole źródeł z `check-api-hygiene.mjs` sprawdzono dostępnym hostowym `rg` na dokładnym worktree: brak direct fetch poza kernel API, brak legacy imports/state models, brak ręcznych endpointów v2 poza API/generated. Czwarty wzorzec pobrano z `api-hygiene-rules.mjs`; jedyny match to kanoniczny `PLATFORM_COMPUTE_PREVIEW_PATH`. Wynik przepuszczono przez rzeczywiste `filterCanonicalComputePreviewMatchLines` i `shouldFailSearchCheck` uruchomione Node w frontendzie tej grupy: filtered_matches pusty, failed=false, exit0. To source checks, bez buildu/instalacji na hoście; pełnej recepty z testami API poza wyjątkiem nie uruchomiono.

Read-only przegląd launchera potwierdził brak obsługiwanej trasy restartu wyłącznie działającego frontendu lub zmiany jego `mem_limit:6g` bez backendu/config CAS. `resume-volume` pozwala jedynie wznowić zatrzymany frontend; `restart-idle` zatrzymuje także backend i wymaga jego idle. Nie wykonano ręcznego restartu ani `docker update` w celu obejścia tej granicy. Szeroki lint pozostaje otwarty.

Master odczytany jako `42d92610312871d591db16a5b60a8f7a6d6339b5` zawiera poprawki wszystkich pięciu bazowych błędów TypeScript. Wspólna baza z branchem zadania nadal `88a9b68…`; zmiany obejmują również pliki viewportu. Podczas próby QA nie zmieniano bazy. Przed kolejną pełną kwalifikacją można zaktualizować wyłącznie własny branch do tego przypiętego commita, zachowując obie implementacje i ponownie sprawdzając zmienione kontrakty. Nie jest to merge zadania do mastera, R8 ani zgoda na kopiowanie dirty zmian mastera. Nowe okno bez zapisów mastera respektowane; QA3218 i task worktree są odrębne.

### Aktualizacja bazy i ponowna kwalifikacja źródeł — R7, 85%

W branchu zadania rozpoczęto merge przypiętego `42d92610312871d591db16a5b60a8f7a6d6339b5`, bez fetch/pull i bez kopiowania dirty zmian głównego checkoutu. Rozwiązano sześć konfliktów: cztery testy viewportu, plan i allowlistę faz helpera. Helper zachowuje zarówno upstream `iteration`, jak i własne `browser-qa`, obok `activation`; nie poluzowano walidacji komendy, namespace, obrazu ani mountów. Plan zachowuje kryteria odbioru i aktualny status. AST helpera poprawny; nie wykonywano testów backendu ani API poza wyjątkiem.

Pięć wcześniejszych błędów TypeScript zniknęło po aktualizacji bazy. Dwie nowe niespójności deklaracji naprawiono bez zmiany runtime: `ButtonProps` uwzględnia `ref` przekazywany istniejącym spreadem props w React 19, a `RibbonSessionStatus.resources` ujawnia opcjonalne rewizje topologii/siatki/domeny, które rzeczywisty selector już dostarcza. Nie usunięto fokusu przycisku ani bramek resolved discretization. Produkcyjny **TypeScript exit0**; ESLint obu zmienionych plików **exit0, zero ostrzeżeń**.

Raport `post-merge-viewport-v1.json`: **26 plików, 594 testy, 593 passed, 1 failed**. Jedyna porażka to asercja tekstowa oczekująca starego źródła `fdmLaneActive`; upstream rozdzielił adapter podglądu opublikowanej topologii od strict resolved lane pól. Asercję dopasowano do `viewportDataDiscretization` i dodano kontrolę `resolveSessionTopologyDiscretization`, zachowując sprawdzenia statusów FEM/FDM. Ponowienie tylko dotkniętego pliku, `post-merge-scene-model-v2.json`: **158/158 passed**. Najnowszy wynik każdego z 26 plików: **594/594 passed**. Raporty JSON i logi pozostają w technicznym wolumenie frontendu, `/state/development/test-evidence/viewport-visual-quality/`; nie sumowano powtórzeń jako dodatkowych testów.

Nowa zarządzana próba browser `4ebefe6e64084ebdbdde6b367c685f54` zakończyła się **failed-confirmed przed uruchomieniem scenariuszy**: `Host-published frontend loopback probe failed`. Nie zastępuje to runtime dowodów sprzed merge. Frontend był running/healthy, OOMKilled=false; kontrola zasobów pokazała 5.239 GiB/6 GiB w trakcie przebudowy HMR. Nie pominięto probe ani nie restartowano backendu z accepted runem w stopping. Nowe okno synchronizacji głównego checkoutu respektowane: bez zapisów master/HEAD/index.

Zwykły staged whitespace check zgłasza końcowe CR w odziedziczonym, niezmienionym względem `42d926…` pliku `ObjectRegionsPanel.test.ts`; kontrola z `core.whitespace=cr-at-eol` ma exit0. Nie normalizowano cudzych plików jako skutku ubocznego merge.

Merge zapisano jako **`e3fe72b1e4e4ad02c5f3840ba63e501c8dc79a57`**, rodzice `7c96ebca02b1c87cc4f18cfa442dbfc9620e046a` i `42d92610312871d591db16a5b60a8f7a6d6339b5`; ancestry przypiętej bazy potwierdzona. Niezależny review obu stron konfliktów i dwóch poprawek typów: brak actionable findings, zachowane asercje retencji i tożsamości. Hook commita exit0; 9 ostrzeżeń React Doctor dotyczy odziedziczonych zmian smoke-inspector, SimulationPreparationLog i ObjectRegionMagneticParametersPanel. Framework rules nadal gated off; nie jest to pełna kwalifikacja React. Nie uruchamiano zalecanych przez output publikacji ani wiadomości zewnętrznych.

Dodatkowa regresja granic podglądu po merge, `post-merge-preview-boundaries-v1.json`: **5 plików / 211 testów / 211 passed**. Zakres: ObjectMoveInteraction, field-domain compatibility, render model, resources oraz bezpośrednio używany przez viewport resolver sessionDiscretization. Łącznie najnowsze wyniki **31 różnych plików / 805 różnych testów / 805 passed / 0 failed**; bez testów backendu ani szerszego API. Powtórzone kontrole architektury mają exit0. Ponowione cztery kontrole źródeł API: trzy rg exit1 (brak matches), czwarty wyłącznie kanoniczna definicja preview; rzeczywisty filtr reguł w Node frontendu zwrócił `filtered="", failed=false`, exit0. Pełnego skryptu API uruchamiającego dodatkowe unit tests nie wykonywano.

Ograniczenie browser po merge potwierdzono osobno: hostowy GET timeout45s oraz GET wewnątrz frontendu timeout20s po redirect do strony workspace. Next pozostaje procesem żywym; odczyt VmRSS 5920856 kB i cgroup `memory.events: max=114816, oom=0, oom_kill=0`, ze znacznym swap/refault. To dowód presji pamięci, nie potwierdzona jedyna przyczyna timeoutu. Nie powtarzano całej próby browser bez odzyskania odpowiedzi strony, nie uruchamiano ręcznego restartu, nie zwiększano limitu i nie resetowano accepted runu. Rejestr worktree zaktualizowano do commita merge; status active, R8 nadal nie rozpoczęto.

### R7 — przywrócenie interakcji HUD po wydzieleniu warstw

Po odzyskaniu HTTP200 na własnym frontendzie wykonano próbę `9149256878b94dd3933374b51f3e8246` na źródłach po merge. Wszystkie siedem części runnera zapisane; kamera, oba układy i lifecycle passed. FOV35/70 nadal zmienia 84626 pikseli, restoration kamery verified. Całość failed-confirmed przez 23 HTTP/console errors: frequency-domain response/progress404 i planar-default meta422. Frozen spins400 nie wystąpiło po upstream gatingu. Page errors=0, transport failures=0. Jest to nowy dowód po merge, bez pełnego zaliczenia macierzy.

Przy analizie brakującego V06 wykryto błąd refaktoryzacji: OrientationHudLayer przypisuje obiekty do warstwy31, podczas gdy osobny natywny raycaster ViewCube pozostał na domyślnej warstwie0. Korekta wcześniejszej diagnozy: shared raycaster zdarzeń R3F miał już bit31 włączany przez PostProcessingLayer; nie był przyczyną tego braku trafienia. Próba na rzeczywistej zainstalowanej bibliotece Three.js dała 0 trafień domyślnego raycastera w bryłę HUD i 2 po ustawieniu warstwy31. Następnie browser baseline `592706e7473b4423a5a72e406ee3c810`, przed poprawką, faktycznie kliknął środek ViewCube z ujęcia bliskiego+X: publiczna poza pozostała niezmieniona i upłynął timeout oczekiwanego snap+X. Ten wynik potwierdza defekt interakcji; runner nie zachował wtedy partialProof helpera przy wyjątku, więc brak trwałego dowodu restoration tego konkretnego przebiegu.

Poprawka: natywny raycaster jest tworzony wyłącznie dla HUD31; widoczny ViewCube włącza dodatkowy bit31 shared raycastera. Cleanup usuwa wyłącznie bit dodany przez tego właściciela, zachowuje layer0, custom layers i bit31 wcześniej obecny. Cztery nowe wykonywalne regresje korzystają z rzeczywistych obiektów Three.js i sprawdzają trafienie, odrzucenie geometrii sceny oraz własność maski. Dwie kontrole źródłowe sprawdzają podłączenie do komponentów. `hud-raycasting-v1.json`: 14/14 passed; najnowsze wyniki wszystkich różnych plików: **33 pliki / 817 testów / 817 passed / 0 failed**.

Helper kamery sprawdza teraz rzeczywisty klik+X oraz ciągły drag myszy z pięcioma próbkami żywej kamery, zachowaniem targetu/promienia i końcowym stabilnym commitem przez500ms. Kontrole finite, SI, target/radius/projection/up obejmują również commit; readonly diagnostyka nie steruje kamerą. Pointer-up ma finally, całość nadal przywraca kamerę przez istniejący dialog. Runner zachowuje failed partialProof kamery, po czym ponownie rzuca błąd; nie zamienia wyjątku w sukces. Lint produkcyjnej poprawki i helperów exit0 bez ostrzeżeń. Niezależny review bez blockera; wcześniejsze P2 końcowej walidacji commitu zamknięte źródłowo. Runtime kliknięcia po poprawce nadal wymaga nowej próby.

Użytkownik jawnie upoważnił do jednej wiadomości z diagnozą cancelled task / brak artifact_catalog. Wysłano ją do czatu „Przywróć wizualizacje FEM i FDM”, ID `01a15476-ae72-7923-b659-2d0cce6d8956`; narzędzie potwierdziło wysłanie. Tamten czat przejął wąską poprawkę live_accepted_projection w masterze. Nie dublować jej, nie rozszerzać zgody na kolejne wiadomości ani mutacje backendu. Grupa3218 i run0cc pozostały nietknięte. Sourcefreeze głównego checkoutu został jawnie zwolniony przez jego właściciela; w tym zadaniu nadal nie zapisano mastera.

### R7 — potwierdzona naprawa ViewCube i orbity, 86%

Poprawkę zapisano w **14a94c9980c50a0d68f5b63b9ebba4fe6e452802**. Produkcyjny TypeScript exit0, lint zmienionych plików i helperów exit0, wymagane 14 regresji HUD passed. Hook exit0 z sześcioma ostrzeżeniami: pięć sekwencyjnych pętli interakcji/próbkowania formularza w QA oraz istniejący index key statycznej, nieprzestawianej listy COMPASS_RIM_POINTS. Nie wykonywano zaleceń publikacji z outputu hooka i nie wyciszano reguł.

Próba po poprawce **6a3744282ccc4b68876efcc4668cabdc**: camera passed, ViewCube+X passed, ciągły drag myszy passed. Kliknięcie ustawiło pozycję z [1.3483481059979242e-7,1.483481059979242e-9,1.8983481059979243e-8] na [1.3597747367484777e-7,-1e-8,7.500000000000001e-9] przy target [2e-8,-1e-8,7.5e-9] m. Pięć kolejnych próbek żywej kamery jest różnych; target i promień zachowane. Końcowa poza była stabilna przez co najmniej500ms; finite/projection/up/target/radius sprawdzone. Restore kamery przez dialog verified, ten sam canvas i kontekst, errors puste. Pozostałe 11 póz, projekcje i FOV nadal passed. To częściowe zamknięcie V05/V06: jeden snap i jeden ciągły gest, nie wszystkie trafienia ViewCube ani pełny test ACK race.

Wszystkie siedem części macierzy ponownie zapisane, lecz całość **failed-confirmed** przez26HTTP errors; page errors=0. Nie utożsamiać passed gestów z zielonym całym browser QA. Backend nadal722c, frontendHMR źródła14a; source HEAD i worktree sprawdzono po przebiegu. SHA256 istotnych plików frontendowych: viewport3dHudLayer.ts 7921aeb1cdb1963f858a2cc6a1ee7e2103733168b5a1c43713a06de516ca5e4b; OrientationHudLayer.tsx 8a7493b336590f1403e8338b55da28d85018ae1cf4ac3fa500e827e3a967a587; ViewCube3DBox.tsx 369ae8f99b3c86277d8779f57c7e92c59d8c7d2579c02703b6ba83c25272fdec; camera helper db30904bdb23dfa348bf595ebb43f956e017253751ff5250e549e94998287aac; runner7bbd325b946ab5edc0a23393f4242e1127c0c7dcc28a47a28b500e897d68e0b7.

Z rzeczywistego payloadu6a wyodrębniono bez transformacji dwa nowe PNG480x320: viewport-before-contrast-Latte-6a374428.png SHA939de727f882fb56b99690efb57b6c669accd231ff53dd96735472e316638e6a oraz Mocha SHA d7ba0eac8626588e0d848a48e70dd9be6a941ac6e44d82793d5e494f4677d363. Pliki w katalogu wizualizacji zadania. Pomiar starszych obrazów wskazał problem koloru osi w Latte: lokalne pary rasterowe X4.08, Y2.47, Z3.57; jednostki4.81/4.83/5.48. Mocha osie5.00/6.78/5.77. To próbki pikseli po AA z ręcznych cropów i mediany sąsiedztwa obejmującego halo, nie formalna kwalifikacja WCAG. Krytycznej klasy linii nie udało się jednoznacznie wydzielić; próg3:1 dla linii nadal NOT VERIFIED. Nowe PNG służą odświeżeniu pomiaru przed zmianą tokenów.

Uruchomiono osobny scenariusz światła geometrii: Studio0/2 musi zmienić obraz, Flat musi pozostać identyczny przy zmianie zachowanej intensywności Studio, a kontrolki Flat mają być disabled. Helper rozszerza snapshot i końcową weryfikację odtworzenia trybu/intensywności oraz storage. Lint exit0; runtime trwa. Nie zmienia pól, geometrii ani kamery. Ten dowód nie zastąpi ilościowych kolorów FDM/FEM.

### R7 — światło i kontrast Latte, kolejne ograniczone próby

Próby `849c3f02c24b41b8899bfa43a3a1ebc8` i `21a2d561b9024670a00da0bcfb211a61`: `geometry_lighting.state=passed`, Studio0/2 zmienia **45918 pikseli**, Flat0/2 **0 pikseli**, kontrolki Flat disabled. Original controls i storage restored/verified; camera passed z restoration verified. Obie próby kończą wszystkie siedem części runnera, ale pozostają failed-confirmed przez odpowiednio26 i24HTTP errors, page errors=0. To geometry preview, bez kwalifikacji danych pola ani działania AO w tej konfiguracji przeglądarki.

Wariant21a2 używał pierwszej korekty lightHUD tokens: X#a80c2e,Y#26601a,Z#1852c4,label#3c3f54,ticktextprimary. Rzeczywiste próbki z nowego PNG: X FG(172,32,61), BG(225,228,235), ratio5.45; Y FG(69,117,62), BG(227,230,236), ratio4.34; Z FG(47,97,200), BG(222,225,232), ratio4.38. ROI włącznie: X(327..340,212..226), Y(118..131,240..255), Z(64..78,163..177). Położenie osi przesunęło się o13–14px względem6a, więc cropy dopasowano do znaków, bez zmiany pikseli. Te same cropy w Mocha:4.89/7.39/5.98. To lokalne rdzenie znaków po AA i mediana pierścienia3px poza ROI; nie pełna kwalifikacja WCAG ani wszystkich etykiet.

PNG bez transformacji: `viewport-after-contrast-Latte-21a2d561.png`, SHA256 ec6f96e0fecb21363dad8ffd1137a4c7e4aec2fa179ec85933c0c8ff39bed767; Mocha16ee5eb3e313736e5d7cf231bfdcafe9efd1be0f5ddd67964628bdd315c5c610. Pliki w katalogu wizualizacji zadania. Y/Z nadal poniżej celu próbki4.5:1, dlatego kolejny wariant przyciemnia je do **Y#1e4d15,Z#1443a0**. Nie uznano go za potwierdzony na podstawie samych tokenów; czeka na nowy obraz. Colormaps danych i tokeny Mocha nietknięte. Regresje konsumentów colors/dimension frame11/11 passed, lint helpera exit0.

Dalszy przegląd znalazł nakładanie właścicieli shared raycastera: PostProcessingLayer już od wcześniejszego etapu włączał HUD31. Usunięto dodatkowy effect z OrientationHudLayer, zachowując poprawkę osobnego native raycastera. PostProcessingLayer pozostaje jedynym właścicielem: korzysta teraz z helpera cleanup usuwającego własny bit, zamiast odtwarzania całej historycznej maski i cofania późniejszych zmian innych warstw. Cztery testy rzeczywistego raycastera zachowane; wiring kontroluje istniejący test Scene zamiast dodatkowego testu Orientation. `hud-owner-v2.json`:59/59 passed. Liczba przypadków spada o jeden przez usunięcie zdublowanej asercji wiring, nie utratę wykonywalnego testu własności maski. Niezależny review potwierdził bezwarunkowy mount PostProcessingLayer i brak drugiego właściciela po tym przeniesieniu. Lint produkcyjnej zmiany exit0; nowy runtime po przeniesieniu właściciela pozostaje wymagany.
