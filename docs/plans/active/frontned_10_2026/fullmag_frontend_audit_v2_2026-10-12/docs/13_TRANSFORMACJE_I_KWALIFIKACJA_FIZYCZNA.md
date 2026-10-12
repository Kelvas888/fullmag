# TRS, pivot, migracja i kwalifikacja realizacji

ADR-03/04 — rekomendacja do akceptacji geometry/IR ownera i właściciela noty naukowej. Część „Stan źródłowy” jest potwierdzona kodem; część matematyczna wyprowadza proponowaną semantykę i oracle. Nie jest certyfikatem nowej fizyki ani działających evaluatorów.

## 1. Stan źródłowy a potrzebne zmiany

| Warstwa | Dowód / stan | Reuse | Brak do domknięcia |
|---|---|---|---|
| SceneDocument | S27: Transform3D ma translation, rotation_quat `[x,y,z,w]`, scale, pivot | Zachować pola i kolejność quaternionu | Jawna wersja semantyki pivotu, walidacja/migracja |
| Transakcja | S25/S26: PatchObjectGeometry przyjmuje geometry+transform | Ten sam endpoint i pełny replace payload | Receipt/CAS qualification; nie gubić nieedytowanych pól |
| Walidacja geometry | S30: derive bounds sprawdza finite i quaternion; bounds stosuje scale→rotate→translate | Reuse walidacji liczb i descriptorów | Pivot nie jest użyty w odczytanej funkcji; pełny przegląd konsumentów |
| Rust adapter | S28: nieidentyczna rotation/scale powoduje `owner_transform_rotation_scale_unsupported` | Translation lowering | Brak kompletnego TRS; guard nie jest tutaj warunkowany odczytanym lane |
| Python scene runtime | S29: `_owner_frame_translation` odmawia rotation/scale | Translation, finite validation | TRS i pivot-aware lowering, q≡−q |
| ProblemIR | Nie odczytano wszystkich pól i ścieżek w tej rewizji | Jeden istniejący publiczny IR, nie alternatywny frontend IR | PR13 mapuje canonical geometry do istniejącego ProblemIR/DTO; PR14 kwalifikuje lane consumers; brak dowodu nie oznacza braku wszystkich transformów |
| Eksport Python / load | Wymagany kontrakt repo: jeden edytowalny DSL | Istniejący exporter, schema versioning | Round-trip pełnego transformu/asset ref bez utraty semantyki |
| Evaluator geometry | Brak pełnej kwalifikacji w V2 | Przenoszenie obecnych descriptorów | Inverse transform, normal rules, predicates, local/world frames |
| FDM membership / FEM realization | Nie wykonano CPU/GPU runtime | Wspólne geometry intent | Parity geometrii i dyskretyzacji; osobne capability evidence |

Nie należy uruchamiać Rotate przez samo usunięcie `disabled`. Rozszerzenie edytora może ujawnić istniejące limity lowering i odmienną interpretację pivotu, nawet gdy JSON został poprawnie zapisany.

## 2. Cztery realizacje — status nie jest wspólną etykietą

| Realizacja | Translation | Rotation/scale przez odczytany owner-frame lowering | Pivot-v1 | Warunek `qualified` |
|---|---|---|---|---|
| FDM CPU | Istnieje źródłowa ścieżka; nie kwalifikowano w V2 | unsupported na odczytanej drodze | planned | Python/IR parity, occupancy i region mapping, runtime fixture |
| FDM GPU | Źródłowo współdzielony input; nie kwalifikowano execution | unsupported na odczytanej drodze; brak dowodu alternatywy | planned | GPU kernel/predicate parity, requested/resolved device, precision |
| FEM CPU | Istnieje input; nie kwalifikowano pełnej ścieżki | Odczytany wspólny adapter odmawia; właściwa trasa FEM wymaga mapy | planned | Geometry realization, Gmsh/supported mesher, boundary mapping, runtime |
| FEM GPU | Nie kwalifikowano | Jak wyżej, bez deklaracji działającego GPU fallback | planned | Jak FEM CPU + rzeczywisty GPU solver/provenance/precision |

`planned` opisuje zamiar; `unsupported` — wykazaną odmowę konkretnej drogi; `qualified` wymaga versioned evidence dla geometry family/device/precision i fixture. Żaden wiersz nie ma tutaj statusu qualified. FDM/FEM mogą używać wspólnego przygotowania na CPU, lecz to musi być jawna część requested/resolved execution, nie cicha zamiana solvera GPU na CPU.

## 3. Wersjonowana semantyka i macierz

R2-T: kolumnowe wektory, aktywna transformacja prawoskrętna, skala dodatnia. Pivot p jest kanonicznym punktem lokalnym w metrach. Parent hierarchy wyłączona w R1/R2.

\[
A=R(q)\operatorname{diag}(s),\qquad
x_w=t+p+A(x_l-p)=Ax_l+b,\quad b=t+(I-A)p.
\]

\(M=T(t)T(p)R(q)S(s)T(-p)\). Translation t nie jest ogólnie world position pivota: \(x_w(p)=t+p\). Normalne: normalize(A^{-T}n). Dla positive scale determinant A>0; negative/zero scale i mirror odrzucane do odrębnej kwalifikacji. Warunek fizyczny normy magnetyzacji nie jest tym samym co transform normalnych powierzchni.

Quaternion: wire `[x,y,z,w]`. Wymagane finite i niezerowa norma. Normalizować skalowanym algorytmem (najpierw dzielenie przez max abs component), żeby unikać overflow/underflow; q i −q reprezentują tę samą orientację. Canonical sign: w>0, a przy w=0 pierwszy niezerowy element w kolejności z,y,x dodatni. Nie odrzucać poprawnego −identity wyłącznie przez porównanie tablicy do `[0,0,0,1]`. Zmieniona normalizacja ma być zgłoszona w DTO/feedbacku, nie magicznym filtrem.

Euler UI: **extrinsic XYZ**, rotacje wokół stałych osi X, potem Y, potem Z, więc `R = Rz(gamma) Ry(beta) Rx(alpha)`. Stopnie w UI, radiany w obliczeniach. Nie opisywać tego jednocześnie jako intrinsic XYZ. Przy osobliwości beta=±90° zachować ciągły raw Euler użytkownika i kanoniczny q; nie przeskakiwać pól przy każdym renderze. Bezpośredni edytor q może być advanced view.

## 4. Position i anchors

| Wybór source anchor a | Definicja lokalna | Wyświetlane Position | Zapis przy żądanej world position v |
|---|---|---|---|
| Center | Środek lokalnego geometry AABB | `t+p+A(a-p)` | `t=v-p-A(a-p)` |
| Bottom center | Środek X/Y, lokalne minZ | Ten sam wzór | Ten sam wzór; nie world bbox minZ po obrocie |
| Object origin | a=[0,0,0] | `t+(I-A)p` | `t=v-(I-A)p` |
| Pivot | a=p | `t+p` | `t=v-p` |
| Custom anchor | Jawne local SI coordinates + source version | Ten sam wzór | Ten sam wzór; unresolved po utracie source |
| World origin | To **cel v=[0,0,0]**, nie ruchomy source anchor | Polecenie „Place selected anchor at world origin” | Wzór dla wybranego source anchor |

Zmiana dropdown anchor bez polecenia place zmienia interpretację prezentacji Position, nie przesuwa modelu. Local delta oznacza osie z uchwyconego R, bez mnożenia dystansu przez scale; world delta jest bezpośrednia. Zmiana frame w trakcie drag wymaga zakończenia/cancel gestu.

Pivot-only: przy p→p' utrzymujemy A i b, więc `t'=t+(I-A)(p-p')`. To zmiana parametrów tej samej geometrii world, nie reset położenia. Jeżeli backend digestuje evaluated affine, pivot-only nie wymaga remeshu. Legacy revision adapter nie musi umieć tego wykazać i wtedy jest konserwatywny.

### Fixture TRS-01 — liczby w nm dla czytelności

`t=[100,200,300]`, `p=[10,20,30]`, `s=[2,3,1]`, `q=[0,0,sqrt(1/2),sqrt(1/2)]` (Rz=90°). Box lokalny: min=[−10,−20,−5], max=[10,20,5].

\[
A=\begin{bmatrix}0&-3&0\\2&0&0\\0&0&1\end{bmatrix},\quad
b=\begin{bmatrix}170\\200\\300\end{bmatrix}\mathrm{nm},\quad
M=\begin{bmatrix}0&-3&0&170\\2&0&0&200\\0&0&1&300\\0&0&0&1\end{bmatrix}.
\]

Ostatnia kolumna w powyższej prezentacji jest w nm; w JSON SI wynosi [170e−9,200e−9,300e−9]. Punkty kontrolne: local origin→[170,200,300]; pivot→[110,220,330]; bottom-center [0,0,−5]→[170,200,295]. World AABB: min=[110,180,295], max=[230,220,305] nm. Zmiana pivot na zero wymaga t'=[170,200,300]nm; wszystkie world points pozostają bez zmian. Podstawa w `fixtures/transform_oracles.json`; liczby sprawdza niezależny skrypt, nie kod Fullmaga.

AABB ośmiu transformowanych narożników lokalnego bounding box jest dokładne dla Box. Dla walca/kuli jest konserwatywnym bounds po obrocie/skali, nie zawsze ciasnym AABB; jeśli UI obiecuje dokładne wymiary światowe bryły, wymagany jest shape-specific oracle. Nie używać bbox jako podmiany powierzchni fizycznej.

## 5. Migracja legacy

Proponowane nowe pole/version capability `transform_semantics='pivot-v1'` w versioned SceneDocument schema. Dokładny placement pola należy do schema review; nie udajemy, że już istnieje. Brak pola oznacza legacy semantics, nie dowolne nowe zachowanie.

Legacy p=0: migracja do pivot-v1 nie zmienia macierzy. Legacy p≠0: odczytany bounds ignoruje pivot, lecz innych konsumentów nie przejrzano w całości. Wymagany migration review; nie przeliczać takiego projektu automatycznie jako pewnego. Zalecany wybór po potwierdzeniu, że stara geometria miała `x=Ax+t_old`: preserve-origin-matrix, `t_new=t_old-(I-A)p`; zapisuje zarówno oryginalny raw transform, jak i decyzję migracji. Alternatywa interpretacji starego p jako aktywnego pivota zmieni world geometry i musi mieć preview/diff oraz jawną zgodę.

Stary klient nie może cicho zapisać pivot-v1 jako origin-v0. Serwer wymaga feature/version handshake i odmówi unsupported write. Plain serialization defaults nie stanowi migracji. Nowy klient otwiera nieobsługiwane projekty read-only zamiast usuwać nieznane pola.

Hierarchia obiektów: R3. Test T16 w R1/R2 oczekuje **odmowy** parent transform, nie cichego flatteningu. Przykład shear-risk dla przyszłego kontraktu: `diag(2,1,1)*Rz(45°)` ma nieortogonalne kolumny, dot(c1,c2)=−1.5; nie wolno bezrefleksyjnie rozłożyć tego na czyste pojedyncze R i diagonal S w odwrotnej kolejności.

## 6. Transformacje i fizyka — wariant do noty naukowej

Właściciel: micromagnetics/physics maintainer wraz z Python/IR i backend maintainers. Notę umieścić w `docs/physics/` zgodnie ze skill `scientific-documentation-contract` repozytorium przed wdrożeniem zmiany numerics. Ten rozdział formułuje wymagania i scenariusze, nie zastępuje tej noty ani akceptacji naukowej.

| Scenariusz | Rekomendowana semantyka | Co wymaga dowodu |
|---|---|---|
| Obrót geometrii z osią anizotropii object-local | Oś world=R·u_local; skala nie mnoży normy osi | Frame przenoszony Python→IR→coefficients; test energii |
| Obrót geometrii z B_ext world | B_ext pozostaje w laboratoryjnej ramie | Nie obracać globalnego pola przy samym gizmo |
| Initial texture object-local | `m_world(x)=R·m_local(M^{-1}x)` dla proper rotation | Sample frame/normalizacja i porównanie source texture; współczynniki Ms nie skalowane geometry scale |
| Initial texture world | Pole w world pozostaje world; geometry zmienia domenę próbkowania | Wyraźny frame w assignment; brak automatycznego założenia |
| Zmiana rozmiaru | Zmienia fizyczną geometrię i sampling; nie skaluje automatycznie Ms/A/Ku | Nowa dyskretyzacja i kwalifikacja material fields |
| Remesh / Build Grid | Jawna reinicjalizacja z authored initial state | Stary dynamical m nie jest automatycznie projektowany; zachować jego wynik jako snapshot |
| Aktywny run | Commit/attach/remesh geometry blocked podczas queued/preparing/running/cancelling; draft local dozwolony | Backend admission i race run-start vs Apply; nie force-stop bez polecenia |
| Nieznany stan runtime | Commit i Run fail-closed | Jawny komunikat, odzyskanie statusu; visualization pozostaje dostępna |

Tensory, DMI frames, magnetoelastic fields, mirror/pseudowektory i transfer stanu po remeshu nie mogą zostać objęte uproszczeniem bez noty. Tam gdzie bieżący materiał nie ma informacji frame, nie zgadywać object-local: zostawić istniejące znaczenie, oznaczyć migration required przed aktywacją body-attached rotation.

Kwalifikacja geometrii to points/bounds/occupancy/topology. Kwalifikacja fizyki obejmuje invariance pod wspólnym obrotem modelu i odpowiednio obracanych lokalnych danych (gdy prawo jest izotropowe), kontrolowaną zmianę przy stałym polu world i zbieżność po dyskretyzacji. Tolerancje wynikają z danej skali/precision/metody; nie przenosić f64 tolerance z oracle macierzy bezpośrednio na wynik LLG lub energię mesha.
