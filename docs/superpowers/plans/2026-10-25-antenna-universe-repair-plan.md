# Antena: raport stanu i sekwencyjny plan naprawczy Universe

Data: 25.10.2026. Status: plan wykonawczy; pełne zadanie niezakończone.
Branch: `codex/antenna-transport-e2e-20261011`.
Baza pierwszego audytu: `b15ea875191a5a1abf74b36da2b1234ab1350c38` + niezacommitowane zmiany.
Kolejne wykonania i ich tożsamości zapisano w rejestrze poniżej.
Środowisko: worktree WSL Ubuntu, grupa Docker DEV anteny, UI na porcie 3203.

## Cel i zasada prowadzenia pracy

Cel: z publicznego skryptu uzyskać rzeczywiste V i J zamkniętej anteny 3D,
pole H_ant w przestrzennej siatce Universe, a następnie sterować jego
wizualizacją w drzewie Universe/Airbox, również po zapisaniu i ponownym otwarciu.
Nie jest to jeszcze odtworzenie wyników publikacji ani kwalifikacja BORIS.

Kolejne komunikaty mają zaczynać się od `Etap k/5:`. Numer oznacza bramkę
realizacji, nie numer wiadomości. Aktualny etap: **1/5 — geometria i siatka**.
Nie przechodzimy do ciężkich obliczeń następnego etapu, dopóki nie ma dowodu
spełnienia poprzedniej bramki. Istniejące wyniki wykorzystujemy ponownie,
jeżeli odpowiadają dokładnie przypiętym wejściom; nie powtarzamy Solve dla formalności.

To wewnętrzny raport stanu i plan, nie nowa nota fizyczna. Zastosowano
`scientific-documentation-contract`: oddzielono kod, wykonanie runtime,
kwalifikację naukową i UI. Kanonicznym właścicielem fizyki pozostaje nota
[0950](../../physics/0950-quasistatic-microwave-antenna-field-basis-and-k-selective-excitation.md).
Zmiana metody lub tolerancji wymaga aktualizacji tej noty i jej walidacji;
ten raport nie wprowadza nowych równań ani polityki obliczeń.

## Potwierdzony stan i problemy

| ID | Obszar | Fakt / problem | Znaczenie |
|---|---|---|---|
| P1 | Tożsamość domeny | Historyczne H obejmuje 14 węzłów obiektu `sampling`, scope `object`, nie Global Universe. | Tego wyniku nie wolno przedstawiać jako pełnego pola wokół anteny ani przemianować jego metadanych. |
| P2 | Siatka Universe | Przygotowano osobny przypadek 1149 węzłów / 6472 Tet4. Brak kompletnego dowodu jakości i widoku tej siatki w bieżącej obserwacji. | Istnienie danych siatki nie dowodzi, że UI pobiera właściwą topologię. |
| P3 | Drzewo UI | Gałąź Airbox znikała bez rozpoznanej domeny/siatki; ustawienia wizualizacji stawały się niedostępne. | Poprawiono źródła: gałąź prezentacji pozostaje dostępna, brak siatki jest jawny. Browser NOT VERIFIED. |
| P4 | Transport | Istnieją rzeczywiste wyniki V/J/H dla małego przypadku; pełny przypadek ma inne wejście siatkowe. | Dowód małego przypadku nie kwalifikuje transportu na nowej siatce. |
| P5 | Koszt pola | Ostatni benchmark: 354.300 s wobec 346.505 s, +2.2495%; 21 payloadów identycznych bajtowo. | Zgodność wyników PASS, przyspieszenie FAIL. Przyczyna różnicy czasu nieustalona. |
| P6 | Pełne pole | Global Universe pozostaje nieobliczone. | Brak podstaw do oznaczenia żądanego zadania jako wykonanego. |
| P7 | Odtwarzanie | Eksport balanced i pojedynczy import przeszły. Test odczytu potwierdził H dla 14 punktów, lecz całość zakończyła się `HTTP inspection read failed`. | Cold-load V/J/H jako całość nie jest zaliczony; przyczyna HTTP wymaga zawężenia. |
| P8 | Semantyka importu | Publiczny status po imporcie to `completed` z zakazem komend; wcześniejszy test oczekiwał `imported_read_only`. | Poprawiono interpretację testu; nie jest to dowód awarii samego importu. |
| P9 | Typy i quantities | W historii występowały magnetyczne ustawienia dla anteny/Airbox; pełnej kwalifikacji UI nadal brak. | Trzeba sprawdzić cały katalog i routing, nie dopisywać pojedynczych wyjątków dla field ID. |
| P10 | Przeglądarka | Brak zaakceptowanego dowodu widocznego canvasu i pola; wcześniejsza automatyczna kontrola blokowała odczyt karty. | TypeScript i HTTP 200 nie zastępują kontroli wizualnej. |

Ostatni managed build `39541a1e34754eddb244958a48a84897` zakończył się sukcesem.
Nie wynika z tego poprawność całego przepływu naukowego. Pełna kontrola TypeScript
po poprawce drzewa: 0 diagnostyk (6.0.3, 215.509 s); sześć scenariuszy drzewa
oraz focused ESLint przeszły. To dowód źródeł, nie działającego obrazu 3D.

## Etap 1/5: geometria, domena i siatka

**1.1 — przypiąć jeden przypadek referencyjny.** Rozdzielić w rejestrze:
(a) historyczny `sampling` 14 węzłów, (b) nowe Global Universe 1149 węzłów.
Zanotować hash skryptu, geometrii, siatki, współrzędne, jednostki m,
identyfikatory encji i runtime. Skrypt docelowy:
`examples/antenna_universe/fem_antenna_closed_loop_universe_surface.py`;
SHA256 `fcfba6ee532835b75e0e18f029246e8576fd0e8e5de82e5fafd727df848a2bd5`.

**1.2 — wykonać audyt siatki bez Solve.** Sprawdzić granice i padding
Universe względem przewodnika, orientację i dodatnią objętość Tet4,
indeksy, osierocone węzły, zdublowane elementy, połączenia signal/return/mostków,
przekrój źródła i przypisania materiałów. Ustalić jakość elementów według
istniejących kryteriów meshera, a nie arbitralnego nowego progu. Rozdzielić
siatkę przewodnika i siatkę próbkowania pola: powietrze nie otrzymuje
przewodności ani magnetyzacji tylko dlatego, że jest w Universe.

**1.3 — sprawdzić kontrakt topologii i dostęp do zarządzania.** Python
`study.universe.mesh` / `study.build_domain_mesh` → domena Global → artefakt
siatki → API → Explorer/Inspector. Zgodność liczby węzłów, komórek,
identyfikatorów i hashy; brak podmiany na bieżącą siatkę magnetyczną.
Gałąź `Universe → Airbox → Visualization` ma istnieć także przed siatką,
a brak danych ma być opisany. Węzeł Mesh musi odpowiadać rzeczywistemu stanowi.

**Bramka:** raport jakości i tożsamości siatki PASS oraz kontrola siatki
w UI (granice, przewodnik i otoczenie). Bez dostępu do przeglądarki część
wizualna pozostaje NOT VERIFIED; nie oznaczamy całej bramki jako zaliczonej.

## Etap 2/5: potencjał i gęstość prądu

**2.1 — zweryfikować model źródła.** Pełny obwód 3D: signal, return, dwa
mostki, skok potencjału na przekroju wejściowym, jawne przewodności i gauge.
Sprawdzić publiczny skrypt i wynik normalizacji bez aktywowania LLG.

**2.2 — uruchomić lub odczytać transport dla dokładnie siatki z etapu 1.**
Potencjał V w V, gęstość prądu J w A/m². Sprawdzić zbieżność, bilans
prądu na przekrojach, ciągłość przez mostki/źródło i interpretację znaków.
Progi przyjąć z istniejącego kontraktu przed oceną wyniku; brakujący próg
najpierw jawnie zdefiniować i uzasadnić.

**2.3 — kwalifikować źródło pola.** Zapisać zaakceptowany prąd, siatkę,
normalizację portu i provenance. Zweryfikować lokalizację próbek J
(węzły lokalne/elementy), bez traktowania ich jak węzłów Universe.

**Bramka:** transport ukończony, kontrole zachowania prądu i jednostek PASS,
J dostępne przez publiczne API, jednoznaczny zaakceptowany artefakt źródła.

## Etap 3/5: pole Oersteda w Universe

**3.1 — rozwiązać problem kosztu na kontrolowanym benchmarku.** Profilować
operator na przypiętym źródle i targetach, oddzielić przygotowanie,
arytmetykę i publikację; zebrać czas, RSS oraz zasoby w tym samym oknie.
Nie promować obecnego zero-copy jako przyspieszenia. Porównać warianty przy
identycznych danych, tolerancjach i warunkach; zachować wynik negatywny.

**3.2 — potwierdzić poprawność pola.** Sprawdzić kierunek względem prądu,
liniowość amplitudy i odwrócenie znaku, zgodność z niezależnym przypadkiem
referencyjnym oraz zbieżność przestrzenną. Bitowa zgodność dwóch wariantów
tej samej implementacji jest regresją, nie niezależną walidacją fizyki.
H_ant ma jednostkę A/m; nie przedstawiać go jako B w T.

**3.3 — wykonać docelowe Global Universe.** Dopiero po wiarygodnej ocenie
kosztu uruchomić pełną mapę na siatce z etapu 1. Obecny profil ma 1800 s
całości / 90 s na target, limit 4 mln par i 6 GiB RSS. Przypadek ma
2 138 289 par źródło–target. Nie zwiększać limitów ani nie zmniejszać
siatki/tolerancji po cichu. Każde ograniczenie zakresu jawnie odnotować.

**Bramka:** zaakceptowane H_ant dla pełnej docelowej siatki, domena Global,
poprawne liczby próbek, skończone wartości, jednostki i provenance;
zaliczone określone testy fizyczne. Brak wyniku nie jest zerowym polem.

## Etap 4/5: publikacja, API i odtworzenie

**4.1 — zawęzić błąd HTTP.** Odczytać dokładną operację, status/timeout,
czas i log serwera ostatniego testu. Zachować częściowy sukces H i pełny
błąd; nie powtarzać importu ani Solve. Naprawić przyczynę w kanonicznej
warstwie field-store/API/materializacji.

**4.2 — sprawdzić spójność całego wyniku.** V/J na przewodniku, H na Global,
stała tożsamość wykonania i własnej topologii. Błędne/stare locatory muszą
być odrzucane. Żądania ilości niedostępnych dla danej fizyki nie mogą
wynikać z domyślnego ferromagnetycznego szablonu.

**4.3 — zapisać i ponownie otworzyć.** Natywny eksport/import, odczyt
wszystkich wymaganych pól i siatek bez ponownego Solve, zgodność wartości
z zaakceptowanym wynikiem. Zachować ostrzeżenia importu i wyjaśnić ich
znaczenie; nie uznawać samego HTTP 200 za pełne odtworzenie.

**Bramka:** pełny test publicznego odczytu i cold-load PASS, brak
niezdiagnozowanych błędów HTTP oraz zgodne wartości/topologia/provenance.

## Etap 5/5: drzewo, Inspector i obraz 3D

**5.1 — kwalifikować zarządzanie wizualizacją.** Kliknięcie Universe/Airbox
prowadzi do właściwego Inspectora. Selekcja źródła, widoczność, geometria,
przekrój, komponent pola, skala i legenda działają zgodnie z dostępnymi
funkcjami. Brak funkcji lub danych jest jawny. Antena, obiekt magnetyczny
i Airbox nie dziedziczą sobie fizyki; `m`/`frozen_spins` tylko tam, gdzie
wymagany moduł i dane rzeczywiście istnieją.

**5.2 — wykonać rzeczywisty browser/WebGL smoke.** Widoczny canvas,
nieutracony kontekst, niezerowy drawing buffer, prawidłowe granice i strzałki
pola wokół anteny. Sprawdzić osobne klatki: siatka włączona, wyłączona,
pole włączone. Długości i liczba glyphów mają pokazywać przebieg pola;
nie zasłaniać go gęstą plątaniną i nie zmniejszać jakości po cichu.

**5.3 — kwalifikować użycie i trwałość.** Stabilny Inspector podczas
zmian/ACK, brak niepowiązanych requestów magnetycznych, zachowane ustawienia
po ponownym otwarciu; porównać obraz z wartościami API w wybranych punktach.

**Bramka:** użytkownik może otworzyć projekt i samodzielnie włączyć
rzeczywiste pole w Universe; dowód przed/po i regresja browser PASS.

## Mapa odpowiedzialności w kodzie

| Miejsce / symbol | Odpowiedzialność |
|---|---|
| `examples/antenna_universe/fem_antenna_closed_loop_universe_surface.py` — moduł `study`, `study.universe.mesh`, `study.current_transport`, `study.stages.add_antenna_field_solve` | Jedno publiczne wejście geometrii, źródła i Global targetów. |
| `apps/control-room/src/modules/explorer/builders/buildModelTree.ts` — `buildModelTree` | Dostępność gałęzi Universe/Airbox. |
| `apps/control-room/src/modules/explorer/builders/airboxExplorerNodes.ts` — `buildAirboxPresentationNode`, `buildFdmAirboxNode`, `buildFemAirboxNode` | Oddzielenie ustawień prezentacji od dowodu istnienia siatki. |
| `apps/control-room/src/modules/viewport-3d/model/artifactFieldCarrierModel.ts` — `parseArtifactFieldLocator`, `artifactCarrierQueries`, `admitArtifactFieldCarrier` | Spójność pola i jego własnej topologii. |

Przed edycją transportu/operatora/API etap wykonawczy uzupełni mapę o dokładne
symbole danej poprawki. Powyższy plan nie jest kompletną mapą implementacji
noty naukowej i nie zastępuje jej source-map.

## Rejestr dowodów i ograniczeń

Wolumen kontrolny grupy, katalog
`verification/surface-rt0-performance-20261025`:

- `gmp-zero-copy-parity-and-timing.json`: zgodność PASS, wydajność FAIL.
- `accepted-inspection-owned-object-read-result.json`: H 14 próbek, A/m,
  pięć negative pin checks; cały test failed z błędem HTTP. Universe=false.
- `accepted-export-balanced-regression-result.json`: eksport balanced PASS.
- `accepted-export-balanced-after.fms`: 31 902 967 B,
  SHA256 `4aa0d0e08463a6c2f84b6e25d5c681a4f8110770725e37ed71a6e0d21a3faf45`.

Wolumen frontendu: `/state/development/airbox-explorer-typescript.json`:
0 diagnostyk. Regresja źródłowa:
`apps/control-room/scripts/check-airbox-explorer-availability.mjs`, 6 PASS.
Kontekst wykonania i wcześniejsze receipty:
[checkpoint runtime](2026-10-25-terminal-history-recovery-v3.md).

Zakres backendów: niniejsze dowody dotyczą wskazanego FEM CPU. FDM CPU,
FDM GPU i FEM GPU nie są przez ten raport kwalifikowane. Nie wykonano
porównania BORIS ani odtworzenia publikacji w zakresie pełnego Universe.

**Bilans planu: 5 bramek, 15 zadań kontrolnych; 0/5 bramek zaliczonych
w pełnym docelowym przepływie.** Istnieją częściowe dowody i poprawki opisane
powyżej. Nie sumujemy ich jako zakończonego zadania użytkownika.
Pierwsza kolejna praca: audyt i przypięcie siatki, bez uruchamiania Solve.


## Wykonanie etapu 1 — audyt siatki i poprawka jednostek

Przypięty katalog wejściowy CAS:
`2f5f590e280eff04731036a47d2fe53f2b7241efd9a108b6f506fe498343d0a7`.
Global: 1149 węzłów / 6472 Tet4, jedna składowa połączona przez ściany,
zero niedodatnich objętości, osieroconych węzłów, duplikatów i ścian
współdzielonych przez ponad dwa elementy. 346 ścian zewnętrznych i 1224
interfejsowe odpowiadają opublikowanym facets. Padding 0.5 µm z każdej
strony, objętość bbox 1.224e-17 m³ zgodna z sumą elementów.

Przewodnik w Global ma 1725 elementów, osobny przewodnik ze źródłem ma
1861. Objętość obu wynosi 6.08e-19 m³. Wszystkie 13 par zbieżnych
współrzędnych odpowiada jawnie zadanemu przekrojowi napięciowemu:
14 par ścian, 28 ścian brzegowych na z=-0.3 µm. Nie scalać węzłów.
Każdy element ma jedno przypisanie materiałowe. Minimalny det/lmax³
0.01080819605 przekracza istniejący próg 1e-12. Brak publikowanych
wewnętrznych facets w siatce po rozcięciu wynika z konstruktora, który
publikuje exterior; nie dowodzi przerwy w przewodniku. Pierwszy ogólny
raport audytu zachowano wraz z późniejszym wyjaśnieniem kontraktu.

`runtime/antenna_coincident_materialization.py::materialize_antenna_coincident_loops`
jawnie tworzy osobny przewodnik. `crates/fullmag-plan/src/antenna_field_solve.rs`:
`load_object_mesh` wybiera źródło, `resolve_field_sampling` wybiera
Global. Token authored_shared_domain ma odziedziczoną nazwę; nie dowodzi
wspólnej topologii. W tym scenariuszu nie uruchomiono LLG.

Naprawiono rzeczywisty błąd jednostek w
`meshing/_gmsh_occ.py::generate_shared_domain_mesh_via_occ`: raporty
volume_min/max/mean/std i element_volume zachowywały skalę Gmsh mimo
konwersji węzłów do metrów. Istniejący helper `_quality_volumes_in_si`
przeniesiono z `_gmsh_swept.py` do `_gmsh_infra.py` i zastosowano
w OCC do raportu globalnego i każdej domeny. Geometria, topologia
i metryki bezwymiarowe pozostają niezmienione. Starych artefaktów nie
przepisano; nowa konwersja działa przy ponownym przygotowaniu.

Regresja realnego Gmsh przed poprawką: błąd jednostek w 1035/1035
elementach o czynnik 1e18. Po poprawce PASS. Dodatkowo PASS: swept ring
200 nm, swept ring 400 nm i swept cylinder. Pytest nie był zainstalowany;
zachowano błąd i wykonano funkcje regresji bezpośrednio przez Python,
z ich asercjami NumPy i prawdziwym Gmsh, w stałym backendzie Docker.
To cztery kontrole rzeczywistego meshera, nie wynik pytest ani pełnego
builda/API. Nie kompilowano testów natywnych i nie uruchomiono Solve.

Nadal otwarte: ocena niskiego SICN około 0.00677 w otoczeniu; brak
wykazanej bramki minimalnego SICN; utrata raportu jakości w
`split_coincident_sourcecut`; konwersja jakości raw przewodnika;
ogólne skalowanie `_scale_mesh_nodes` (anizotropia wymaga również
oceny metryk kształtu); publiczne przygotowanie docelowej sceny
i kontrola UI. Pełna bramka 1/5 nadal otwarta.

Dowody w wolumenie kontrolnym grupy:
`verification/antenna-universe-mesh-audit-20261025/`: audit_mesh.py,
mesh-structure-report.json, audit_sourcecut_contract.py,
sourcecut-contract-report.json, run_occ_quality_check.py,
occ-quality-red-direct.json, occ-quality-green-direct.json,
quality-scaling-regression.json.

### Dalsza naprawa etapu 1: jakość przewodnika i przekroju źródła

W `realize_antenna_coincident_loop_mesh` przeliczono objętości raportu
jakości globalnego i domenowego wraz z węzłami na SI.
`split_coincident_sourcecut` zachowuje teraz oba raporty: rozcięcie zmienia
identyfikatory węzłów przekroju, ale nie zmienia współrzędnych żadnego
elementu, jego kolejności ani przypisania materiałowego.

Regresje przed poprawką wykazały błędne jednostki wszystkich 1869
elementów nowej testowej siatki oraz `prepared.quality is None`.
Pierwsza wersja drugiego testu miała błędne wywołanie publicznego wrappera
z argumentem raw_mesh; poprawiono test na istniejącą wewnętrzną funkcję
przygotowania. Zachowano pierwotny błąd oraz osobny dowód faktycznej
utraty jakości. Po poprawce pełny interpretowany unittest
`test_antenna_coincident_cut`: 15/15 PASS, bez pominięć, w stałym
backendzie Docker. Obejmuje rzeczywisty Gmsh, jednostki, zachowanie
raportów i bajtów geometrii, kolejność elementów oraz odrzucanie
nieprawidłowych przekrojów. Nie wykonano nowego Solve.

Dowody: conductor-quality-red.log, conductor-quality-loss-red.log,
conductor-quality-suite-green.log w tym samym katalogu kontrolnym audytu.
Kontrola kodu `model/problem.py::_fem_mesh_cache_key` i
`_fem_cache_contract_identity` potwierdza uwzględnienie
FULLMAG_SOURCE_SNAPSHOT_SHA256 w kluczu cache przewodnika. Wdrożenie
wymaga nowego zweryfikowanego snapshotu launchera i sprawdzenia
publicznego przygotowania; ten etap nie został jeszcze wykonany.
Dodatkowe syntetyczne sprawdzenie kluczy nie wystartowało, ponieważ
automatyczny przegląd uprawnień przekroczył limit czasu. Nie traktujemy
go jako dowodu PASS. Cache i historyczne wyniki pozostały zachowane.


### Odblokowanie recept WSL — 25.10.2026

Zainstalowany `just 1.42.4` odrzucał cały justfile na złączonym zamknięciu
wyrażenia warunkowego i interpolacji. Minimalny reproducer potwierdził błąd
przed zmianą oraz poprawne parsowanie po rozdzieleniu nawiasów spacją.
Rozważono rozdzielenie delimitera, ujęcie wyrażeń w nawiasy, wydzielenie
zmiennych i aktualizację just. Wybrano wyłącznie whitespace zgodny z
https://just.systems/man/en/conditional-expressions.html — bez zmiany
wspólnej instalacji, komend, argumentów, polityki ani bramek restartu.

Weryfikacja: pełny plik parsuje 645 recept; dry-run docker-dev z pustymi
oraz jawnymi argumentami i przypiętego docker-dev-restart-idle zakończyły
się kodem 0. `git diff --check` przeszedł. To kontrola składni i rozwinięcia
poleceń, nie dowód buildu ani uruchomienia Universe. Pierwotny błąd wystąpił
przed wykonaniem recepty, więc nie zatrzymał usług i nie rozpoczął buildu.


### Publiczne przygotowanie po poprawkach — wynik niezaliczony

Managed restart `edb6b26336d1409e844e77e0d09f876f` zakończył się
`succeeded`, kompilacja exit 0 (309345 ms), API i frontend zostały
uruchomione w tej samej grupie 3203. Commit
`66db3c86a5ee3f3f87ced3d6dcd3b25e5439da9e`, snapshot
`8c9f767c6bbdeae1568a7c6e572829c21406fe904d9ca32a1a81f06b562f2e78`.
Cache zachowany; brak usuwania danych. Nie kwalifikuje to retencji,
przeglądarki ani obliczenia pola.

Jedna aktywacja `8beaabccc9f8463eae1cc19a24ae5ea2`, request
`antenna-universe-mesh-si-20261025-01`, zakończyła się `succeeded`.
Publiczne preparation=ready, run=waiting_for_solve, solver=awaiting_command.
Run: `run-live-36bd51495b58e60c056a8c8503bec76065e6fa53159e33d74bc3e58034f577b6`.
Nowy katalog CAS: `e460871f733b18f6cb5976d7b7616222f52177ae4c853541ed3bae9e8a9208e0`.
Nie uruchomiono Solve, LLG ani nowego importu.

**P11 — błędny nośnik publicznej domeny.** Katalog zawiera Global
1149 węzłów / 6472 Tet4 i przewodnik 677 / 1861. API
`/v2/sessions/current/meshing/meshes/shared-domain/manifest` zwraca
jednak przewodnik 677 / 1861, z jedną częścią conductor. Raport
shared-domain ma mesh_statistics=null, a quality Universe i anteny
są puste. Przyczyna wyboru topologii potwierdzona w kodzie:
`live_scene_preparation.rs::prepared_fem_mesh` wywołuje
`StageFemMeshAsset::build_from_antenna_field_only_plan`, które zawsze
bierze `plan.source_mesh`. `resolve_field_sampling` zachowuje punkty
i connectivity Global, lecz pomija markery, facets i raport budowy.
Nie wolno naprawić tego przez przemianowanie siatki źródła lub
przepisanie nośników V/J na Global. Następna poprawka musi publikować
rzeczywistą domenę z przypiętego modelu, zachowując osobny nośnik prądu.

**P12 — stare jednostki mimo poprawionych źródeł.** Nowy katalog
zachowuje poprawną geometrię, ale raporty objętości Global oraz
przewodnika nadal mają skalę większą o 1e18. Niezależne porównanie
z determinantami elementów nie przeszło. Przywrócenie raportów
przewodnika działa (są cztery markery), lecz nie kwalifikuje ich jednostek.
Poprawione pliki Python w `/build/workspace` są bajtowo zgodne
z checkoutem. Proces API ma cache `/build/cache/fem-mesh`, lecz
nie ma FULLMAG_SOURCE_SNAPSHOT_SHA256; helper klucza cache zwraca
wtedy brak tożsamości źródeł. Ponowne użycie starych metadanych jest
hipotezą wymagającą potwierdzenia, nie jeszcze zakończoną naprawą.
Następny krok: prześledzić przekazanie zweryfikowanej tożsamości
do Python oraz cache hit/miss, zachowując stare wpisy.

Diagnostyka kształtu: 16 elementów powietrza i 25 przewodnika
w Global ma SICN poniżej 0.1; p5 odpowiednio 0.37419 i 0.47795.
Minimalna gamma jest poniżej istniejącego progu diagnostycznego 0.08.
To progi statystyk inspekcyjnych, nie nowa bramka solvera ani dowód
zbieżności. Nie zmieniono siatki i tolerancji.

Dowody w wolumenie kontrolnym:
`verification/antenna-universe-mesh-audit-20261025/shape-quality-diagnostic.json`
oraz `public-prepare-si/`: zapisane odpowiedzi preparation/run/solver,
manifest, raporty i `result.json` z niezaliczonymi kontrolami.
**Bramka 1/5 nadal otwarta: dwie potwierdzone rozbieżności publicznego
przepływu oraz kontrola UI NOT VERIFIED.** Pełne pole Universe nadal
nieobliczone.

### P12 — przekazanie tożsamości źródeł do runtime

Potwierdzono brak trzech zmiennych tożsamości w `_serve`, mimo ich
przekazania do kompilacji przez `_build_environment`. Poprawka w
`docker/all-in-one/backend_dev.py::_serve` bierze commit, hash snapshotu
oraz stan dirty ze zweryfikowanego receiptu pakietu. Sprawdza zgodność
rekordu source, native_source_identity i jego hasha przed uruchomieniem API;
wartość odziedziczona z procesu nie może zastąpić tożsamości pakietu.
Aktualny receipt działającej grupy zawiera wymagane pola. Poprawka nie
usuwa cache ani nie zmienia równań, tolerancji lub formatu siatki.

Regresja przed zmianą: brak hasha oraz odziedziczony obcy hash przechodziły
do handoffu; niespójność receiptu nie była odrzucana. Po zmianie 5/5 testów
interpretowanego Pythona przeszło w stałym backendzie grupy (0.397 s).
Zakres: brak/obcy hash, niespójny receipt, istniejący start Compose,
uszkodzony manifest i odrębny storage probe. Handoff procesu i delegacja
cgroup były mockowane; nie uruchamiano ani nie zatrzymywano usługi.
Dowody: `verification/antenna-universe-mesh-audit-20261025/cache-source-identity/`
(`red.log`, `green.log`) w wolumenie kontrolnym.

**Wdrożenie i skutek dla publicznego przygotowania: NOT VERIFIED.**
Helper należy do obrazu; wymaga zarządzanej aktualizacji obrazu grupy,
a następnie sprawdzenia środowiska API i metryk nowej siatki. Nie wolno
uznać tych testów za dowód usunięcia błędu jednostek w działającej sesji.
