# Viewport 3D — checkpoint implementacji

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

- Obowiązuje zakaz budowania testów jednostkowych; nie uruchamiano ich.
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
- Managed browser QA `faa969d54b3f482f885d01b5b8f97626`: **w toku**, rozpoczęto pobranie oficjalnego przypiętego obrazu Playwright. Wyniku testu nie ma jeszcze w tym checkpointcie. Testy regresyjne wrappera są przygotowywane; nie są wykonywane ani kompilowane.

V01–V15 z planu: **NOT VERIFIED w przeglądarce**. Harness appearance jest podłączony do zarządzanego runnera; jego obecność nie jest dowodem wykonania. Brakuje obrazu/PNG, DPR/motywów, FDM/FEM/primitive, pomiaru kontrastu/RGB, idle/network i churn 20 przełączeń. Nie ma zgody na pominięcie tych bramek.

Testy jednostkowe pozostają zablokowane jawnym zakazem użytkownika. Nie wykonywać merge ani cleanup worktree przed wymaganymi dowodami i rozstrzygnięciem tej bramki. R8 integracja: NOT STARTED. Kod nie jest przedstawiany jako ukończona realizacja planu.
