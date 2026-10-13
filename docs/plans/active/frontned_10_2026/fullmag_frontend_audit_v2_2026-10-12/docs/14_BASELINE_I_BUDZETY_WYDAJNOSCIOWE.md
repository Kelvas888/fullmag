# Baseline i budżety wydajnościowe — Q22

## 1. Stan dowodów

**Nie przeprowadzono pomiaru Fullmaga w tej rewizji.** `fixtures/performance_scenarios.json` zawiera protokół i wartości `null` dla hardware, measurements i approved_budgets. Liczba scenariuszy ani przegląd kodu nie pozwala podać FPS, MB/s lub maksymalnej liczby elementów jako faktu. Wielkości 10k/1M trójkątów są proponowanymi punktami testu, nie deklaracją zdolności importera. Ograniczenie admission w D12 nie zastępuje kwalifikacji pamięci.

## 2. Profil pomiarowy PR01

Zapisuje się pełny SHA, stan dirty, build mode (production/dev nieporównywalne bez oznaczenia), wersje Node/pnpm/browser/React/Three z rzeczywistego środowiska, OS, CPU, RAM, GPU, driver, dostępny VRAM, ustawienia energii, DPR i viewport, rozdzielczość canvas, local/remote API RTT, wersję backendu/meshera, lane i precision requested/resolved. Dla managed runtime profil i storage resolver muszą pochodzić z rejestru projektu. Pomiar z software WebGL/SwiftShader nie jest wynikiem sprzętowego GPU.

Każdy model ma materializowany fixture hash, liczbę obiektów, rzeczywistych elementów, wierzchołków, wyświetlanych elementów/glyphs, ustawienia quality/LOD/wireframe/clipping. Porównanie wersji używa tego samego profilu i tych samych danych. Osobno cold load (pusty cache) i warm interaction; nie czyścić współdzielonego cache użytkownika — użyć własnego kontrolowanego kontekstu testu.

Protokół propozycji: 5 warmups, 30 powtórzeń scenariusza, 60 s idle i 50 cykli create/delete/switch. Właściciel PR01 może dostosować liczbę po pomiarze wariancji, zapisując zmianę protokołu. Dla p99 z tak małej próby raportować ograniczoną wiarygodność, nie prezentować precyzyjnego estymatora ogona bez większej liczby obserwacji. Bootstrap/confidence intervals są diagnostyką, nie zamiennikiem identycznego środowiska.

## 3. Co i jak mierzyć

| Scenariusz | Punkt start/stop i miary | Stałe warunki | Oracle jakości |
|---|---|---|---|
| Wpisywanie w Geometry/Placement | Input event→DOM z właściwym rawText→paint; p50/p95, longest task, React commit count | Ten sam target, 20 znaków, z/bez request in flight | Tekst/focus/selection range/scroll nie zmienia się przez ACK |
| Move drag | Pointer event→preview frame; event backlog, frame intervals, rejected ray samples | Ta sama camera, path i DPR; bez body mutation do Apply | Geometria pokrywa oracle trajektorii; zero model writes podczas gestu |
| Apply | Click→submit→receipt→baseline publication→paint, liczba write/GET/refetch | Kontrolowany RTT/fault profile | Jeden efekt, brak utraty post-submit rawText |
| Import mały/duży | Upload/checks/preview time osobno; peak JS heap/RSS/worker allocations; bytes | 10k i 1M triangles, wersja checkera, jakość preview jawna | Brak pominiętych checks albo silent decimation |
| Slice | Plane change→zgodny generation-bound wynik; CPU/GPU upload bytes | Tetra oracle oraz qualified real mesh | Rzeczywiste przecięcie, nie projekcja/bbox |
| Mesh rebuild | Submit→compute→publish→viewer delivery osobno | Ta sama recepta, seed gdy dostępny, mesher version | Generation/provenance i zachowanie retained artifact |
| Idle | CPU time main/worker/backend, request count, rendering activity | 60s bez input/run; event/status exceptions opisane | Brak zawsze włączonego renderowania bez potrzeby |
| Create/delete/switch | Retained heap/GPU resources/listeners po każdym cyklu i po settle | 50 cykli, cache policy jawna | Zwolnienie zasobów usuniętego obiektu, nie usunięcie żywego shared cache |

Pomiary JS heap z GC nie porównują bezpośrednio VRAM. Liczba Three geometries/textures jest useful allocation proxy, nie pomiarem liczby bajtów w GPU driverze. Oznaczyć dostępne API i ograniczenia przy raportowaniu. Renderer musi mieć znanego właściciela; jednorazowe warm cache plateau odróżniać od monotonicznego wzrostu po usuwaniu nieużywanych obiektów.

## 4. Budżet jest zatwierdzany po baseline

PR01 zapisuje `baseline.json` i proponuje `budget_profile.json` z miarą, centralnym wynikiem, wariancją, tolerancją/uzasadnieniem, ownerem i stanem approval. PR12 nie może zamienić `null` na arbitralny próg 60 FPS lub 100 ms. Dopuszczalna regresja musi być jawnie zatwierdzona przez właściciela release na podstawie pomiarów i odczuwalnej jakości; brak porównywalnego baseline oznacza blocked performance qualification.

Przykładowy kontrakt budżetu (schemat, nie liczby pomiaru): `{metric, scenario, profile_id, baseline_artifact, threshold:null, comparison, confidence_method, sample_count, rationale, approver:null, status:'pending-baseline'}`. Dla pamięci porównywać steady-state po cyklu z baseline i trendem, nie bezwarunkowo wymagać zera zajętej pamięci. Nowa funkcja bez starego odpowiednika dostaje własny usability baseline, nie zmyślony regression ratio.

Są również twarde **invariants funkcjonalne** niewymagające arbitralnego limitu czasu: zero scene writes na typing/pointermove/pointerup R1, zero duplicate effects na intent replay, zero build na Retry Loading i na display-only change, zero unrelated disabled/opacity changes, brak zgubionego canvas/context. Te warunki należy sprawdzać od pierwszej poprawki.

## 5. Kolejność optymalizacji i fallback

Najpierw eliminować redundantne subskrypcje/requesty, stabilizować selektory/identity, cache generation-keyed, ograniczyć niepotrzebne render/update, następnie przenieść ciężkie parsowanie/triangulację do właściciela worker/data plane. Bufory topologii nie trafiają do status ani state całego React tree. Cleanup zwalnia tylko zasoby owned, nie współdzielone pomiędzy aktywnymi views.

Niższy LOD, rzadsze glyphs i uproszczona topologia są osobno wybieranym fallbackiem, z legendą pokazującą poziom uproszczenia. Nie wolno uzyskać zielonego wyniku PR przez ciche zmniejszenie jakości domyślnej. Wyniki qualification Fullmaga i porównanie wzorców COMSOL/3ds Max w D09 to różne rzeczy.
