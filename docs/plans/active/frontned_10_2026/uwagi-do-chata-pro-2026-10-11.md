# Uwagi do dokumentacji refaktoryzacji frontendu Fullmag

Materiał do przekazania do Chata Pro po przeglądzie pakietu `fullmag_frontend_audit_2026-10-11`. Data przeglądu: 11 października 2026.

## Ocena gotowości do implementacji

Rozumiem kierunek refaktoryzacji i potrafię wskazać punkty rozpoczęcia: naprawa baseline i konfliktów formularza, historia oraz ogrodzenie sesji dla Move, wspólna sesja edycji, wspólna ocena aktualności artefaktów, a następnie narzędzia i import. Dokumentacja dobrze oddziela model zatwierdzony, draft, preview i artefakt oraz uczciwie opisuje ograniczenia dowodów.

Nie wszystko jest jednak jednoznaczne. Pakiet pozwala rozpocząć wąskie poprawki A1–A3 po odtworzeniu problemów w produkcyjnych modułach. Nie wystarcza jeszcze do samodzielnego wykonania całego B–G bez podejmowania nowych decyzji produktowych i kontraktowych. Część tych decyzji autor jawnie wymienia w D07, sekcja 4. Poniższe uwagi wskazują także dodatkowe luki i konkretne rozbieżności.

Pakiet dotyczy przede wszystkim modelowania geometrii, transformacji, importu i meshu. Nie jest kompletnym planem refaktoryzacji całego Control Room, obejmującym również wszystkie moduły wyników, wykresów, Field Map, startu, uruchamiania i automatyzacji. To granica zakresu, a nie zarzut braku audytu obszarów wyłączonych ze zlecenia.

## Podstawa przeglądu

Przeczytano README, wszystkie dziesięć rozdziałów Markdown, cztery źródła diagramów DOT, kod i zapisane wyniki reprodukcji oraz materiały JSON. Obejrzano arkusz wszystkich siedmiu makiet. Sprawdzono wskazane niżej fragmenty bieżącego kodu oraz kontrakty repozytorium. To przegląd dokumentacji z celowanym sprawdzeniem kodu, bez pełnego audytu implementacji, wykonania aplikacji, WebGL, meshera ani nowych pomiarów. Reprodukcji nie uruchamiano ponownie; ich skrypt nadpisuje własny `results.json`, a zapisane wyniki dotyczą izolowanych modeli starego zachowania.

Główny checkout: `C:/git/fullmag/fullmag`, branch `master`, HEAD `2a3c6becb9c7e111ae1497ec0cd9ac9576acba95`, zgodny ze snapshotem pakietu. Checkout zawiera liczne cudze zmiany i pliki niewersjonowane, a sam pakiet jest niewersjonowany. Zwykły `git status --short` nie odczytał submodułu `external_solvers/3` z powodu odmowy dostępu; stan głównego drzewa sprawdzono z `--ignore-submodules`. Żaden z 24 plików z `sources.json` nie wykazał różnicy względem HEAD. Backendowy handler authoringu spoza tej listy ma lokalne zmiany; obecność opisanej niżej transakcji geometry+transform potwierdzono również bezpośrednio w wersji HEAD.

Kontrola pakietu: 45 z 45 wpisów manifestu ma zgodny SHA256; 28 ustaleń i 24 źródła odpowiadają zadeklarowanym licznościom; nie znaleziono brakujących lokalnych plików wskazanych linkami dziesięciu rozdziałów Markdown. Nie sprawdzano dostępności zewnętrznych stron bibliografii ani renderowania galerii HTML w przeglądarce.

SHA256 `manifest.json`: `d635a2619655b71f66685ad86f8069988d12020410f3269764af9688cbe9b3d0`.

Skróty źródeł dokumentacji używane dalej:

| Skrót | Rozdział |
|---|---|
| D01 | [Źródła i metodyka](fullmag_frontend_audit_2026-10-11/docs/01_ZRODLA_I_METODYKA.md) |
| D02 | [Rejestr ustaleń](fullmag_frontend_audit_2026-10-11/docs/02_REJESTR_USTALEN.md) |
| D03 | [Stan obecny i workflow](fullmag_frontend_audit_2026-10-11/docs/03_STAN_OBECNY_I_WORKFLOW.md) |
| D04 | [Architektura i transformacje](fullmag_frontend_audit_2026-10-11/docs/04_ARCHITEKTURA_DOCELOWA_I_TRANSFORMACJE.md) |
| D05 | [Specyfikacja UI i Inspectorów](fullmag_frontend_audit_2026-10-11/docs/05_SPECYFIKACJA_UI_I_INSPEKTOROW.md) |
| D06 | [Workflow i jakość meshu](fullmag_frontend_audit_2026-10-11/docs/06_MESH_WORKFLOW_I_JAKOSC.md) |
| D07 | [Plan wdrożenia](fullmag_frontend_audit_2026-10-11/docs/07_PLAN_WDROZENIA.md) |
| D08 | [Testy i reprodukcje](fullmag_frontend_audit_2026-10-11/docs/08_TESTY_I_REPRODUKCJE.md) |
| D09 | [Wzorce i decyzje projektowe](fullmag_frontend_audit_2026-10-11/docs/09_BENCHMARKI_I_DECYZJE_PROJEKTOWE.md) |
| D10 | [Makiety i schematy](fullmag_frontend_audit_2026-10-11/docs/10_MAKIETY_I_SCHEMATY.md) |

Numery linii odnoszą się do pakietu o powyższym manifeście. Priorytety pytań opisują gotowość planu: **wymagane przed danym etapem** oraz **uzupełnienie planu**. Nie są nową klasyfikacją defektów P0/P1/P2.

## Pytania wymagające rozstrzygnięcia przed odpowiednim etapem

### Q01 Zakres refaktoryzacji i pierwszy użyteczny release

**Podstawa:** D03:7, 86–88; D07:23–38, 50–64; D05:142.

Plan łączy poprawki istniejącego zachowania z nowymi funkcjami: Rotate/Scale, importem, workplanes, align, wieloselekcją, diagnostyką i rozbudową inspekcji. Nie wszystkie mają osobny pakiet i test odbioru. Hierarchia obiektów pojawia się w matematyce, a Boolean pozostaje disabled. Bez granicy release nie wiadomo, co ma być ukończone w pierwszej dostawie.

**Pytanie do Pro:** Czy ten plan obejmuje tylko geometry/mesh authoring, czy ma być bazą refaktoryzacji całego frontendu? Podziel go na: naprawy spójności, rozszerzenie authoringu i funkcje odłożone. Dla każdej funkcji wskaż release, zależności i kryterium odbioru. Jawnie zakwalifikuj multi-selection, align, workplanes, parametryczne wyrażenia, CSG i hierarchię obiektów.

### Q02 Czy zakończenie gestu zapisuje model, czy tylko draft

**Podstawa:** D04:48–50; D05:68–78; D07:28; D08:T02/T18; makieta M02 pokazuje `1 intent on Apply`.

Opis narzędzia przewiduje commit przy pointerup. Inspector i makieta przewidują wspólny draft oraz `Apply Changes`. Przy niezapisanej zmianie promienia i następnym przesunięciu walca nie wiadomo, czy gest zapisuje promień i pozycję, tylko pozycję, czy nic do czasu Apply. Każdy wariant daje inną historię i zachowanie Revert.

**Pytanie do Pro:** Opisz dokładnie scenariusz „zmieniam wymiar, przeciągam, kończę gest, naciskam Revert/Apply”. Wybierz jedną granicę transakcji dla pierwszego release. Jeżeli dopuszczasz kilka trybów, zdefiniuj ich nazwy, reguły przełączania, payload i liczbę wpisów historii. Uzgodnij tekst, diagram i makietę.

### Q03 Atomowy zapis geometrii i transformu częściowo już istnieje

**Podstawa:** D02:F03, linie 80–88; D07:B1/C1; kod `AuthoringTransactionRequest::PatchObjectGeometry` i `apply_object_geometry_patch`.

W [schemas/authoring.rs](../../../../crates/fullmag-api/src/schemas/authoring.rs), linie 1503–1511, `PatchObjectGeometry` ma `geometry`, opcjonalny `transform` i jeden `base_revision`. W [handlers/model/authoring.rs](../../../../crates/fullmag-api/src/router_v2/handlers/model/authoring.rs), symbol `apply_object_geometry_patch` (lokalnie 3952–3976), oba pola są zmieniane na tej samej scenie; dispatcher wykonuje następnie commit. Taką strukturę potwierdzono również na przypiętym HEAD. Frontendowy `ObjectGeometryPatchRequest` również posiada `transform`.

To dowód istniejącej ścieżki źródłowej, bez kwalifikacji współbieżności i pełnej walidacji runtime. Zmniejsza jednak niepewność zdania „jeśli backend obsługuje atomowy batch”.

**Pytanie do Pro:** Czy B1 może wykorzystać istniejący `patch_object_geometry` z transformem? Prześledź jego walidację, zapis, odpowiedź, historię i konkurujące requesty. Wskaż konkretne ograniczenia zamiast zakładać potrzebę nowego endpointu lub ogólnego batcha. Wieloobiektowy commit to osobny kontrakt.

### Q04 TRS istnieje w scenie lecz nie jest domknięte w realizacji

**Podstawa:** D04:62–74; D07:C1; D02:F10.

[scene.rs](../../../../crates/fullmag-authoring/src/scene.rs), `Transform3D`, linie 167–175, już definiuje `translation`, `rotation_quat`, `scale` i `pivot`. [adapters.rs](../../../../crates/fullmag-authoring/src/adapters.rs), linie 186–192, odmawia obrotu/skali w kanonicznym FDM owner-frame lowering. Taką odmowę ma również Python [runtime/scene_document.py](../../../../packages/fullmag-py/src/fullmag/runtime/scene_document.py), `_owner_frame_translation`, linie 1971–1983. To ograniczenie konkretnej realizacji, nie dowód braku wszystkich pól transformu w modelu.

**Pytanie do Pro:** Dodaj mapę istniejących i brakujących części: SceneDocument → transakcja → walidacja → Python → ProblemIR → eksport → evaluator → FDM membership/FEM realization. Które pola reużywamy, które zmieniają semantykę, a które wymagają migracji? Rozpisz wsparcie dla czterech realizacji FDM CPU/GPU i FEM CPU/GPU, z jawnymi stanami planned/unsupported/qualified.

### Q05 Własność wspólnej sesji edycji i cykl życia

**Podstawa:** D04:13–36; D07:B1 i linia 42; kontrakt modułów frontend-v2.

Obecny `InspectorEditSession` jest mechanizmem rejestracji akcji panelu, nie kompletnym współdzielonym magazynem draftu. Nowy `ObjectEditSession` ma być czytany przez Inspector i viewport, ale dokumentacja nie wskazuje właściciela, publicznej granicy ani lifetime. Viewport nie może importować prywatnego store modułu Inspector.

**Pytanie do Pro:** Wskaż docelowe pliki, usługę/kernel API, selektory, adapter InspectorEditSession i właściciela preview. Co dzieje się przy zmianie panelu, aktywnej zakładki centralnej, wejściu na Start, zamknięciu viewportu, zmianie sesji i usunięciu obiektu? Który stan przetrwa unmount, a które zasoby trzeba zwolnić? Uwzględnij zgodność pierwszego renderu klienta z SSR.

### Q06 Tożsamość obiektu szkicu i operacji

**Podstawa:** D04:23–33, 40–42; D02:F26; D05:35–37, 100–102.

Identyfikator kanonicznego obiektu musi być oddzielony od nazwy, typu prezentacyjnego i identyfikatora draftu. Dokumentacja nie domyka mapowania `object_id` do `SceneDocument.objects[].id`, zachowania przy reimport/duplikacji oraz zakresu identyfikatorów operacji. Przykładowy `CommitOutcome` zawiera `operationId`, ale bieżąca odpowiedź `AuthoringTransactionResponse` zwraca rodzaj transakcji, rewizję i scenę.

**Pytanie do Pro:** Zdefiniuj tabelę identyfikatorów: kto je nadaje, zakres unikalności, trwałość i obecność w request/response. Oddziel `gestureId`, lokalny `operationId`, serwerowy identyfikator komendy i `client_intent_id`. Reimport powinien mieć jawną regułę zachowania object ID, a duplikat regułę utworzenia nowego ID.

### Q07 Zachowanie wpisywania i pending podczas zapisu

**Podstawa:** D04:38–42; D05:60, 68–70; D08:T01/T05/T06; `.agents/instructions/frontend.md`, reguła stabilnego Inspectora.

D04 opisuje dwie możliwości: blokadę wpisywania oraz zachowanie dalszych zmian. Nie wybiera pierwszej implementacji. Wymóg repozytorium zabrania jednego target-wide pending, który blokuje lub przyciemnia niespokrewnione kontrolki. Blokada kolejnego gestu nie rozstrzyga dostępności wszystkich pól.

**Pytanie do Pro:** Określ, które pola i akcje są zablokowane dla danej transakcji oraz jak zachować rawText wpisany po submit. Dopisz regresję przeglądarkową dla Object i Airbox, gdzie dotyczy: stały root panelu, zachowany focus/scroll/draft, brak zmian opacity i disabled w innych kontrolkach, ograniczona liczba renderów i requestów.

### Q08 Reguły rebase oraz trybu absolute i delta

**Podstawa:** D02:F08, linie 170–178; D04:90–94; D07:B1.

„Scalaj rozłączne ścieżki” nie wystarcza dla radius/diameter, pełnego deskryptora geometrii, quaternionu, zmiany typu i względnej translacji. Tekst nie ustala też, do którego baseline przypisana jest delta i co się dzieje po zdalnej zmianie pozycji.

**Pytanie do Pro:** Dodaj tabelę base/local/remote/result dla co najmniej: rozłącznych wymiarów, tej samej wielkości przez radius i diameter, transformu absolute, transformu delta, zmiany typu oraz usunięcia obiektu. Quaternion traktuj zgodnie z jego semantyką, bez bezrefleksyjnego scalania czterech liczb. Konflikt wymaga jawnego wyboru; podmiana samej rewizji nie jest scaleniem.

### Q09 Nieznany wynik zwykłej mutacji i gwarancje historii

**Podstawa:** D02:F07/F22/F27; D04:29–33, 104–108; diagram D02.

Recovery po `client_intent_id` jest opisane głównie dla budowy meshu. Diagram stosuje lookup do edycji obiektu, ale plan nie wskazuje serwerowego kontraktu idempotencji/reconciliation zwykłych transakcji. Jednocześnie „jeden wpis historii” współistnieje z best-effort historią i możliwością jej utraty.

**Pytanie do Pro:** Jak rozstrzygnąć utracony ACK dla Create/Apply/Move, także po reloadzie? Określ deduplikację, retencję identyfikatora intencji, wynik lookupu i warunek bezpiecznego ponowienia. Zdefiniuj gwarancję historii w pierwszym release: trwała czy best-effort z `history-degraded`. Potwierdzenie już wykonanego zapisu nie może powodować drugiej mutacji lub dwóch wpisów Undo.

### Q10 Pivot oraz interpretacja Position

**Podstawa:** D04:62–94; D05:74–78; D07:52.

Wzór transformu z pivotem jest konkretny, ale tekst nadal pozostawia decyzję, czy pivot jest kanoniczny, czy narzędziowy. Z niego wynika, że pozycja pivotu w przestrzeni rodzica to `t+p`, nie zawsze samo `t`. Wartość Position Absolute jest opisana jako pozycja wybranego punktu odniesienia, bez dokładnego mapowania na translację.

Ponadto [geometry.rs](../../../../crates/fullmag-authoring/src/geometry.rs), `derive_object_bounds`, linie 959–979, wylicza narożniki przez scale → rotation → translation i w tym fragmencie nie używa pivotu. Nowa semantyka wymaga przeglądu istniejących konsumentów, a nie tylko dodania kontrolki.

**Pytanie do Pro:** Wybierz model pivotu i zdefiniuj Position dla center, bottom-center, world origin i custom anchor. Podaj liczbowy przykład z niezerowym pivotem, rotacją i skalą, expected matrix, punktami kontrolnymi oraz AABB. Ustal dokładną kolejność Eulera, politykę normalizacji quaternionu i czy hierarchia obiektów jest w zakresie.

### Q11 Transformacje a fizyka aktywnego modelu

**Podstawa:** D04:96–102; D06:87–89; D07:52.

Autor poprawnie wskazuje tę decyzję jako otwartą. Bez niej nie można bezpiecznie aktywować nowych transformacji: material axes, tekstura magnetyzacji, laboratoryjne pola i stan aktywnego solvera mają różne znaczenie.

**Pytanie do Pro:** Dopisz scenariusze do przyszłego ADR: obrót obiektu z lokalną osią anizotropii, obrót z polem world, zmiana rozmiaru, remesh i edycja podczas aktywnego runu. Czy operacja jest blokowana, tworzy model dla następnego runu, czy wymaga zatrzymania? Na pierwszy etap zachowaj deklarowaną reinicjalizację, jeśli projekcja magnetyzacji nie jest wdrożona i zakwalifikowana. Wskaż właściciela noty naukowej i mapowanie Python/IR.

### Q12 Kanoniczna tożsamość i aktualność artefaktu

**Podstawa:** D06:9–26, 30–53; D02:F19–F21; D07:E1.

Przykładowy `MeshProvenanceVNext` nie zawiera wszystkich pól wymienionych w opisie, w tym session/project identity. `object-context` nie rozstrzyga, czy chodzi o lokalną siatkę, wybraną wspólną domenę czy tylko miejsce uruchomienia komendy. FDM ma odrębne fingerprint i membership. W tekście występują różne zestawy stanów aktualności.

**Pytanie do Pro:** Zdefiniuj jeden kontrakt z wariantami FEM/FDM, oddzielając kontekst selekcji od faktycznego zakresu artefaktu. Opisz źródło i kanonizację digestów oraz tabelę wspólnego resolvera `current/stale/incompatible/unknown/loading/inconsistent`. Czy zmiana samej nazwy przy wyższej sceneRevision wymaga remeshu? Jak działa przejściowy resolver przed wdrożeniem serwerowych digestów? Wszystkie panele i Run gating muszą konsumować ten sam wynik.

### Q13 Atomowa publikacja i referencja elementu

**Podstawa:** D06:26, 83–87, 101; D05:126–128; D02:F21.

Publikacja zgodnego zestawu jest opisana jako propozycja. Nie określono markeru aktywacji, wymaganych zasobów ani statusu opcjonalnej per-element quality. `elementId` i ordinal wymagają jawnego rozróżnienia.

**Pytanie do Pro:** Kto aktywuje generację i jaki marker gwarantuje kompletność? Rozpisz obowiązkowe manifest/topology/region membership oraz opcjonalne diagnostics/quality dla obu rodzin. Zdefiniuj wspólny `ElementRef` przenoszony przez selection, highlight, quality i refinement. Nowa generacja nie może przejąć starego indeksu; brak opcjonalnej metryki nie powinien automatycznie udawać awarii poprawnej topologii.

### Q14 Pierwszy build oraz rzeczywisty zakres Build Selected

**Podstawa:** D06:55–79; D05:110–120; D02:F28; D07:52.

Opis legalnego `absent` nie wybiera konkretnej reprezentacji API i resource hooks. „Build Selected” nadal pozostaje otwartą decyzją. Apply & Build obejmuje zapis i późniejszy job, więc odmowa drugiego kroku może nastąpić po poprawnym zatwierdzeniu polityki.

**Pytanie do Pro:** Ustal kontrakt pustych summary/latest/manifest i różnicę między not-built, not-found oraz awarią odczytu. Opisz zakres pracy FEM i właściciela planu FDM. Dopisz stany „policy saved, build rejected”, zmianę sceny pomiędzy Apply i Build, double click, utratę ACK oraz bezpieczne wznowienie. Nie obiecuj atomowości zapisu i długiego jobu, jeśli jej nie zapewnia backend.

### Q15 Import oraz reimport jako kontrakt projektu

**Podstawa:** D05:84–102; D07:D1/D2 i linia 48; diagram D04.

Workflow jest zrozumiały, ale backend `assets.rs` był sprawdzony jako parser summary, a nie kompletna ścieżka importu. Nadal brakuje zasobów staged asset/upload/checks, stanu asynchronicznej walidacji, limitów oraz persistencji samowystarczalnego projektu.

**Pytanie do Pro:** Rozpisz istniejące i nowe zasoby v2, capability, operacje, binarny transport preview i format asset reference w Python/IR. Określ, które checks są wymagane do construction-only, FEM volume i FDM occupancy. Dopisz limit pliku/trójkątów, cancel/reload, referencje i retencję uploadu. Czy zapis projektu zawiera oryginalny asset, czy tylko ścieżkę? Przy reimport wskaż wersjonowanie, konflikt równoległej edycji oraz zgłoszenie i naprawę osieroconych regionów bez mapowania po ordinalach.

### Q16 Capability oraz pełna droga zmiany API

**Podstawa:** D07:B2/C1/D1/E1/E2; D04:36; kontrakt resource-first.

„Jeden model capabilities” nie powinien oznaczać drugiego, lokalnego registry prawdy. Repo rozdziela capability procesu, aktywnej sesji i meshing policy. `FieldProblem`, lookup intencji, digesty i rozszerzone transakcje muszą mieć zdefiniowaną granicę transportu.

**Pytanie do Pro:** Dla każdej nowej kontrolki wskaż capability owner, pole i powód disabled. Dla każdego nowego pola/zasobu podaj ścieżkę: backend schema → OpenAPI → generator → typowany facade → resource hook/cache key → invalidation/event → konsumenci. Wskaż kompatybilność starego klienta/projektu i brak cichego fallbacku GPU→CPU. JSON pozostaje cienkim control plane; topologia i ciężkie preview używają data plane.

## Uzupełnienia wymagane do wykonalnego planu

### Q17 Tabela przejść i spójność z testami

**Podstawa:** D04:19–21, 40–50; diagram D02; D08:T18.

Diagram nie jest kompletną tabelą przejść: pomija m.in. odrzucenie invalid draft, target-missing i zachowanie dalszej edycji podczas ACK. T18 oczekuje aktywnego gestu B podczas ACK A, chociaż pierwsze wdrożenie blokuje nowy gest do ACK.

**Prośba do Pro:** Dodaj tabelę state/event/guard/next/effects. Rozdziel test pierwszego release, w którym B nie może wystartować, od testu przyszłego trybu dopuszczającego nakładanie operacji. Uzgodnij stany pomiędzy typami, diagramami, makietami i testami.

### Q18 Numery parser tolerancje i snap

**Podstawa:** D04:54–58; D02:F09/F16; D07:A2/A3; D08:T08–T10/T24.

Dokument nakazuje jedną politykę przecinka, ale jej nie wybiera. Podobnie nie ustala tolerancji no-op, kroku snap, rotacji ani obsługi jednostek dla niekompletnego tekstu.

**Prośba do Pro:** Zdefiniuj gramatykę liczb/jednostek, separator dziesiętny, `um/µm`, scientific notation, empty/incomplete/invalid oraz zmianę jednostki podczas edycji. Podaj wzór tolerancji no-op z SI, uzasadnienie i test subnanometrowego ruchu. Rozdziel próg rozpoczęcia gestu w pikselach od rzeczywistej zmiany modelu. Snap nie może kumulować dryfu ani niejawnie zmieniać discretization.

### Q19 Mapa węzłów Explorer i Inspectorów

**Podstawa:** D05:13–37, 66, 140–142; D07:F1.

Docelowe drzewo i dwanaście Inspectorów nie są jeszcze mapą istniejącego `Selection` i registry. Węzły Geometry/Placement/Regions/Mesh Policy wymagają własnej semantyki i view, zgodnie z regułami repo.

**Prośba do Pro:** Dodaj tabelę node kind → Selection → Inspector view → manifest/slot → resource owner → komendy. Wyjaśnij działanie dirty guard przy przejściu Geometry→Mesh Policy i do innego obiektu. Zachowaj jeden shell, jeden viewport i istniejący navbar; makiety nie są oddzielną aplikacją ani obowiązkiem skopiowania ich CSS.

### Q20 Zakres Build Geometry i nowych akcji jakości

**Podstawa:** D05:46, 126–128; D06:33, 99–103; D07:F1/G1.

`Build Geometry`, dowolna płaszczyzna przekroju, kolorowanie per-element, refinement i porównanie zbieżności pojawiają się w opisie, ale nie mają pełnej mapy komend, danych i pakietów pracy. Nie należy zakładać, że realizacja geometrii i build meshu są tym samym.

**Prośba do Pro:** Dopisz owner i zakres każdej akcji, wejście/wyjście, lifecycle oraz warunek capability. Dla quality określ metrykę, zakres, jednostkę, orientation i invalid elements; dla refinementu zmianę recepty, nie lokalną podmianę topologii. Dopisz test rzeczywistego przekroju i jawnie odłóż funkcje bez kontraktu.

### Q21 Powiązanie pakietów z testami i bramkami repo

**Podstawa:** D07:23–38; D08:30–40, 46–97; `AGENTS.md` i `.agents/instructions/frontend.md`.

50 scenariuszy jest dobrym początkiem, ale nie ma mapy pakiet→test→fixture→oracle→recepta→dowód. Nie podano w tym zestawie wszystkich obowiązkowych bramek frontendu, m.in. lint bez ostrzeżeń, architecture/API hygiene i adekwatnego React Doctor. Repo tymczasowo zabrania kompilowania testów jednostkowych; plan powinien rozróżniać dozwolone testy lekkie od zakazanej kompilacji, bez samodzielnego uchylania reguły.

**Prośba do Pro:** Dodaj wykonawczą macierz i zależności środowiska. Dla viewportu wymagaj widocznego canvas, `isContextLost() === false` i niezerowego drawing buffer. Oddziel fixture browser od realnego backendu, managed runtime i kwalifikacji fizycznej. Dla T14/T16/T45 określ dane i tolerancje. Sam zielony typecheck lub izolowany port JS nie zamyka ryzyk integracji.

### Q22 Mierzalne wymagania wydajności

**Podstawa:** D06:103; D02:F25; D08:T49; D09.

„Brak regresji CPU/GPU/network” jest celem, ale bez baseline, sprzętu, rozmiarów modelu i metody pomiaru nie daje kryterium odbioru. D09 opisuje wzorce z produktów, a nie benchmark wydajności Fullmaga.

**Prośba do Pro:** Wprowadź etap pomiaru baseline i dopiero potem zatwierdzenie budżetów: latencja wpisywania i drag, liczba requestów/renderów, import mały/duży, czas przekroju, pamięć po cyklu create/delete/switch i cleanup. Nie wpisuj fikcyjnych FPS ani limitów bez pomiaru. Optymalizacja ma domyślnie zachować jakość wizualizacji; niższy LOD/budżet jest jawnym fallbackiem.

### Q23 Migracja i małe dostawy

**Podstawa:** D07:7–19, 25–38, 64; reguły integracji repo.

Diagram A→B→C/D/E jest zbyt ogólny, by wyznaczyć wszystkie zależności. Naprawy first-build/freshness nie zawsze muszą czekać na całe B. A1 wprowadza reducer, a B1 ponownie przebudowuje własność draftu; trzeba zaplanować reuse. Brakuje sposobu wyłączenia nowego narzędzia przy problemach oraz warunku usunięcia adapterów przejściowych.

**Prośba do Pro:** Rozpisz małe PR-y z właścicielem plików, wejściowym kontraktem, kryteriami odbioru i zależnościami. Oddziel poprawki od nowych funkcji. Wskaż punkty migracji starego UI, compatibility shim owner/removal i bezpieczne wycofanie. Operacyjnie odwołaj się do obowiązującego rejestru/worktree/storage i bramek integracji zamiast tworzyć konkurencyjną procedurę.

### Q24 Spójna aktualizacja całego pakietu

**Podstawa:** README, D01/D02/D07/D08/D10, `findings.json`, `sources.json`, `index.html`, diagramy i manifest.

**Prośba do Pro:** Po zmianie decyzji zsynchronizuj Markdown, diagramy, makiety, backlog JSON i galerię HTML oraz przelicz manifest. Zachowaj klasy C/L/R/G i rozdzielenie ryzyka od potwierdzonego błędu. Dodaj nowe źródła backend/Python, stabilne symbole i zakresy, zwłaszcza istniejący Transform3D, odmowę lowering i geometry+transform transaction. Nie zmieniaj historycznych reprodukcji tak, aby udawały testy poprawionej produkcji.

## Jak realizowałbym plan po doprecyzowaniu

1. Potwierdzić reprodukcje F01/F02/F04–F09/F16/F18 na odpowiednich produkcyjnych funkcjach i konsumentach. Minimalnie naprawić baseline/ACK/conflict, session fence, no-op, obsługę błędów i historię Move. Zachować prawidłowy cleanup gestów.
2. Rozstrzygnąć Q02, Q05–Q09 i zbudować kernelową granicę wspólnej edycji z adapterem istniejącej stopki. Wykorzystać istniejącą transakcję geometry+transform tam, gdzie kontrakt to potwierdzi. Dołożyć preview istniejącego obiektu i stabilny Inspector.
3. Naprawić niezależne first-build/freshness/selection, następnie migrować konsumentów na wspólną tożsamość i resolver artefaktów. Zachować obecne confirmation, observation i brak duplikacji budowy.
4. Po ADR i kontraktach cross-layer domknąć transformacje oraz import przez Python/IR/OpenAPI/evaluators i realizacje. Dopiero wtedy włączać capabilities Rotate/Scale/Import oraz rozbudowane narzędzia.
5. Porządkować komponenty i ekrany na stabilnych kontraktach, w istniejącym shellu. Zamknąć przypisane testy frontend/API/browser/runtime i wymagane dowody fizyczne osobno.

To kolejność proponowana do uzupełnionego planu, nie autoryzacja ani deklaracja rozpoczęcia implementacji.

## Instrukcja do przekazania do Chata Pro

Przepracuj dokumentację `fullmag_frontend_audit_2026-10-11` na podstawie pytań Q01–Q24. Zachowaj zakres i źródła potwierdzone w audycie. Najpierw odpowiedz na decyzje blokujące poszczególne etapy, następnie zaktualizuj spójnie rozdziały architektury, UI, meshu, planu i testów. Jeśli decyzja wymaga właściciela produktu albo kwalifikacji naukowej, podaj warianty, rekomendację i wpływ na implementację; nie zapisuj jej jako już uzgodnionej.

Najważniejsze korekty: ustalić commit przy pointerup versus wspólne Apply, wykorzystać istniejący geometry+transform payload, rozdzielić obecne pola TRS od braków end-to-end lowering, wskazać kernelowego właściciela draftu, opisać recovery zwykłej mutacji i ujednolicić identity/freshness/publication. Oczekiwany wynik to wykonywalny plan z tabelami kontraktów, stanów, plików, migracji i testów, który ogranicza potrzebę podejmowania przez implementera nieuzgodnionych decyzji.

## Dodatkowa tożsamość sprawdzonych źródeł

| Źródło | SHA256 |
|---|---|
| `GeometryObjectPanel.tsx` | `f1869de20ef1491616f2a7ad216f61a6fd6c80961a8b72427024586219aaaf80` |
| `crates/fullmag-authoring/src/scene.rs` | `b42379e8ec2d1ce68249ef9939e488c9820d1957191a549122a215314d118749` |
| `crates/fullmag-authoring/src/adapters.rs` | `ee0998417033d23d38c4311c69162bc36de0abe33bad3ed0c5ca5cad8c718c03` |
| `packages/fullmag-py/src/fullmag/runtime/scene_document.py` | `a1990e085e54ef4852f2d35868b31f2b985b6d880638bf2bde52399e59d3698f` |

Weryfikacja dokumentacji nie jest wykonaniem refaktoryzacji ani certyfikatem runtime lub wydania. Oryginalnego pakietu, źródeł aplikacji i cudzych zmian nie modyfikowano. Utworzono wyłącznie ten osobny materiał uwag.
