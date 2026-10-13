# P8-53BE — Compute po odtworzeniu workspace

Status: **OPEN**, checkpoint 13.10.2026. Kontynuacja P8-53 po zamknięciu
[P8-53BD](53bd-incomplete-physics-project-persistence.md).

Najnowszy stan: build H zakończył się exit 0. Próba F→H
`11caba0f12ac4e7c8ba39ca7ee4ae342` potwierdziła odtworzenie sceny i dokumentu,
oba normalne Grid, wykonanie Run 1 ps i zachowanie timestampu sesji przy
starcie child. Brakuje kompletnego command/stage/execution provenance;
status po zakończeniu etapu błędnie przedstawia interaktywną sesję jako
tombstone. Normalnego zamknięcia child nie zaliczono; próbę zakończono
kontrolowanym cancel z terminalnym wait wszystkich procesów. Szczegóły
i granice dowodów w [checkpointcie BG](53bg-acquisition-refusal-diagnostics.md).

## Synchronizacja modelu — kolejny wykryty blocker

Próba browser `52a8ef28d5f44de689a58879ef962ee9` zakończyła się
**failed, exit 1**. Zachowała rzeczywistą scenę revision 10: geometria,
region, materiał, jawna anizotropia oraz skończony Run 1 ps.
Nie wykonała Grid, replacement ani Compute; nie jest dowodem kwalifikacji.
Scratch używał dla POST model/syncs tego samego limitu 1 s co odczyty statusu.
Utrata odpowiedzi uruchamiała błędne zgłoszenie niepoprawnego modelu.

Poprawka źródeł rozdziela limit tego żądania (45 s) od krótkich odczytów.
API render/rewrite korzystają z istniejącego helpera ograniczonego do 30 s,
z kontrolą wielkości logów i zakończenia procesu. Utrata transportu,
nieczytelna odpowiedź oraz HTTP 5xx zachowują nieznany wynik: supervisor
nie ponawia zapisu, nie uruchamia child i nie potwierdza idle do jawnego
odzyskania workspace. HTTP 5xx nie dowodzi zakończenia helpera.
Zmiana została przygotowana po diagnozie; runtime regresja nadal **NOT VERIFIED**.

13.10.2026 uruchomiono zarządzany native build finalnego kodu:
`native-build-61cc793f80324a4bb055e566ebc70758.log`, profil backend-dev,
prywatny port próby 3258. Nie zmieniono konfiguracji storage ani sesji
użytkownika na 3197. Końcowy wynik buildu oraz Grid → restore → Compute
muszą zostać dopisane na podstawie terminalnych receipts.

Źródła `scratch_runtime.rs` i `script.rs` są byte-equal z frozen snapshot
`eb52257d12175b44c3b2ae84206375e99e471be6a7ef636f33b7da2ea453736b`.
Scoped review poprawki oraz pause/stop i cleanup helpera: bez nowych findings.
Review nie zastępuje runtime proof. Podczas kontroli build pozostawał aktywny:
zarządzany launcher wykonywał `compiler_inputs.py materialize` dla tego
snapshotu. Nie uruchomiono drugiego buildu ani nie zwolniono jego blokad.

Finalny build 13.10.2026 zakończył się **exit 0** (odebrany proces
zarządzanej recepty). Manifest:
`792b174ba289a8f9d95ac11550cb320c9770f583ae6111b923a7471649ae0d20`,
backend identity:
`60ff3410a4cc1fc0f8b3d2595c7b37bc4dcbdeb05fe8724e25459f7384ce2b24`.
Snapshot pozostaje `eb52257d12175b44c3b2ae84206375e99e471be6a7ef636f33b7da2ea453736b`;
inventory `f0524fd00b8f49463801faec19b52271d155b0546f012671b8c9f014c84450a4`.
Uruchomiono nową zarządzaną próbę browser
`25b8fb06696c4ebcb7d4a96cfb35629b`; jej wynik pozostaje otwarty.

### Wynik próby 25b8 i eksport anizotropii

Próba `25b8fb06696c4ebcb7d4a96cfb35629b` zakończyła się **failed, exit 1**.
UI utworzyło nowy projekt; rzeczywistą scenę z poprzedniej próby odtworzono
normalną transakcją `replace_scene` z base_revision, zachowując nowe ID projektu
i jego outputs. Pełny zapis: `fixture-scene-replay.json` w katalogu próby.
Viewport był widoczny, context_lost=false, drawing buffer 575 × 281.
Żądanie Build Grid otrzymało HTTP 500; nie wystartował scratch child.
Supervisor prawidłowo zachował unknown i nie ponawiał synchronizacji.

Diagnostyczny helper zakończył się normalnym wait, exit 1 i
`IncompletePhysicsError`. Scena zawierała włączoną anizotropię obiektu
ku1=1000 J/m³, axis=(0,0,1), lecz bootstrap eksportu przekazywał wyłącznie
parametry materiału, pomijając ten jawny physics_stack przed capture stage.
Kontrakt pozostaje istniejący: [anizotropia jednoosiowa](../../../../../physics/0402-uniaxial-anisotropy.md).
Naprawa bootstrapu korzysta z tych samych normalizerów co renderer końcowy;
nie dodaje domyślnych oddziaływań ani nie osłabia walidacji pustego modelu.

Managed regresja przed poprawką `c77f8306db0340478dd2ca7247801b8d`:
156 kontroli, jeden odtworzony błąd. Po poprawce
`97f8c84e2ff9469a9636ca5156a4be77`: **completed, exit 0, 156/156 PASS**.
Nowe kontrole sprawdzają rzeczywisty helper i ponowne wczytanie wygenerowanego
skryptu z dokładnymi Ku1/axis bez globalnych energy terms oraz odmowę przy
wyłączonej anizotropii. Rust unit tests nie były kompilowane.

Własne API nieudanej próby zatrzymano po sprawdzeniu PID i dokładnego EXE;
nie było aktywnego solvera ani scratch child. Zapis końcowy posiada normalny
odbiór wszystkich ośmiu procesów, w tym API exit -1 i CLI exit 1.
Nie jest to dowód graceful API shutdown ani Compute. Następna bramka:
pakiet zawierający poprawkę Python oraz pełny Grid → restore → Compute.

Poprawka eksportu i dwie regresje zapisane jako spójny commit na master:
`27c43be1315bb70018a24b42aa15eec3cec6bc3e` (wyłącznie script_builder.py
i test_windows_development_scene_render_incomplete.py). Scoped review bez
findings, managed 156/156 PASS dla niezmienionych źródeł. Nowy build pakietu:
`native-build-b5ff76c94cfe478d9252d8959b6c0e07.log`: **completed, exit 0**.
Manifest SHA-256 `9e8e0d5f95aa47dd0fdb35db28c7779e15be7ff70e3280b47adb467e7a4d7832`;
frozen snapshot `fb462628e27197c2ff283646b7e1a03887fa8f7e82c00dcbed4b135c23f27d06`,
inventory `d8f2a1cce435d724c03b17e5c62369d274b87bda121f7468980dd9dd1a151663`.
script_builder.py, scratch_runtime.rs i API script.rs są byte-equal z frozen
source. Kompilacja CLI/API i desktopu PASS; nie jest to jeszcze dowód
Grid, odtworzenia workspace ani Compute po restore.

Kolejna rzeczywista próba `0aec17ea7b3c40b9900e92d70948ba85`:
**failed, exit 1**. Typecheck i lint strony testowej PASS. Odtworzono
wcześniej autoryzowany model przez revision-checked model transaction,
z zachowaniem nowej tożsamości projektu i jego outputs; zapisano
`fixture-scene-replay.json`. Eksport Python i materializacja ProblemIR
przeszły, więc poprzedni IncompletePhysicsError nie wystąpił.
Grid child PID 51080, komenda `fm-4a85e8dd-d89b-4c9b-8b56-da8b891553f4`,
został odebrany normalnym wait, exit 1, kill_requested=false.
Planner odmówił modelu zawierającego wyłącznie jawną anizotropię:
`the current executable FDM path requires at least one of Exchange, Demag,
Zeeman, StaticFieldMap, or RotatedInterfacialDmi`.
Źródło: `crates/fullmag-plan/src/fdm.rs::plan_fdm`, warunek poprzedzający
walidację open magnetic boundary. FDM CPU ma realizację lokalnego pola
i energii anizotropii w `cpu/fields/anisotropy.rs`, a plan przekazuje
parametry materiałowe. Jest to rozbieżność wymagająca osobnej kontroli
legality/qualification; nie dodano sztucznego Exchange ani Zeeman do fixture.
Restore i Compute pozostają NOT VERIFIED. Dokładnie przypięte własne API
zatrzymano po terminalnym odbiorze Grid child, aby verifier zakończył
sprzątanie; nie restartowano workspace użytkownika na 3197.
Receipt potwierdza terminalny wait wszystkich dziewięciu procesów i frontendu.
API exit -1 jest kontrolowanym zatrzymaniem, nie graceful shutdown.
Próba zamknięcia własnej karty po zatrzymaniu frontendu została odrzucona
przez browser URL policy dla automatycznej strony błędu `data:`;
nie obchodzono ograniczenia. Nie zmienia to terminalnego stanu procesów.

Przygotowano poprawkę admission w `fdm.rs::has_referenced_material_anisotropy`:
single-grid i multilayer liczą niezerowe skalarne współczynniki anizotropii
wyłącznie materiałów przypisanych do magnesów. Uniaxial wymaga obecnego
Ku1, zgodnie z istniejącą konstrukcją runtime; sam Ku2 bez Ku1 nie rozszerza
tej realizacji. Nie dodano energii globalnych ani cichego fallbacku.
Regresje źródłowe w `crates/fullmag-plan/tests/fdm_material_anisotropy.rs`
obejmują Ku1 dodatnie/ujemne, Ku2 z jawnym Ku1=0, cubic oraz odmowę dla
braku, zerowych parametrów i nieużywanego materiału. **Rust tests NOT RUN**,
zgodnie z zakazem kompilowania testów. Zmienione źródła wymagają nowego
managed builda i odrębnej próby runtime; wcześniejszy pakiet nie zalicza
tej poprawki. Istniejące noty 0402 i 0403 zachowują definicje fizyczne;
zmiana dotyczy pominiętego warunku obecności już realizowanego local term.
Po source review warunek dodatkowo wymaga skończonych współczynników
i poprawnych osi; uniaxial zachowuje domyślną oś Z, cubic X/Y. Jawne osie
zerowe, niefinitywne lub równoległe osie cubic nie spełniają nowej bramki.
Regresje uwzględniają również wcześniejszą odmowę na poziomie IR.
Parser/format check przez rustfmt PASS; nie zastępuje wykonania regresji.
Przed kolejnym buildem sprawdzono około 4 GB wolnego C: i 313 MiB trwałego
snapshotu poprzedniego builda. Nie usunięto Cargo target, cache ani artefaktów
nieudanych prób. Brak odrębnego dowodu kwalifikacji naukowej czterech lane'ów.
Ponowne scoped review po poprawkach: brak actionable findings. Pełna
walidacja wszystkich współistniejących lokalnych interakcji pozostaje poza
zakresem helpera obecności energii; brak promocji statusu naukowego.
Żądanie `just windows-workspace-build dev dev 3258 true`, session 51935,
zakończyło się terminalnie exit 1: bounded wait 120 s na heavy slot wygasł
przed rozpoczęciem kompilacji. W chwili sprawdzenia działający owner process
PID 123836 uruchamiał zarządzany build z checkoutu
`C:\git\fullmag\worktrees\multi-project-hpc-r2-20261005`; nie zatrzymano go
i nie wywnioskowano tożsamości rozmowy z samej ścieżki. Następna próba
dopiero po potwierdzonym zwolnieniu zasobu. Poprawka pozostaje WIP,
bez zaliczenia managed buildu, Grid/restore/Compute ani całego P8-53BE.

Po potwierdzonym zakończeniu obcego procesu uruchomiono własny build
session 23783, log `native-build-512469b6d89f42708b86926e2f540f2e.log`.
Frozen snapshot `378934228842e9998fa25a96bd0b6b73622d22cdf45e1f0d6789f3666a1737fb`;
planner byte-equal, SHA-256
`b71f03126564ea732d2c11023c3856f52841c3585c890d6e95286459bc53e5e2`.
CLI/API i desktop skompilowane; cały build **completed, exit 0**.
Manifest `fe245a03ab381c0d6a8eea5560a157fe4ca2e20fd2915b514487833e6eb9f730`,
inventory `35bddbf5d30607525923d0af0046502c77854388e79b85ad103f3538f6afe38e`.

Browser verifier otrzymał osobną bramkę
`check_material_anisotropy_plans`: produkcyjne `example-ir` i
`plan-json --execution-plan`, dziesięć scenariuszy dopuszczenia/odmowy
na jednej komórce, z CPU/double/strict i bez startu solvera. Każdy proces
ma ograniczony czas/log i actual wait; niepotwierdzony cleanup zachowuje
`unknown`. Dopisane dwie interpretowane regresje błędu odczytu logu
i niepotwierdzonego wait. Scoped review cleanup bez findings, syntax PASS.
Zarządzane handoff checks odmówiły startu przy blokadzie własnego buildu;
Po zakończeniu buildu managed receipt
`80afe98f862447cca0045d1706fe05c1`: **completed, exit 0, 158 testów PASS**,
w tym dwie nowe regresje custody. Produkcyjne scenariusze `plan-json`
i końcowe Grid/restore/Compute wymagają odrębnej próby runtime.
Wersja verifiera z poprawionym cleanup powstała po zamrożeniu źródeł tego
buildu: jest osobnym narzędziem weryfikacji, nie zmianą skompilowanego plannera.

Receipt `523affb9b5dd4a13820b33e52171b550`: dziesięć produkcyjnych
przypadków plannera PASS i real Grid 4×4×1, normalny wait exit 0.
Przed restartem zachowano scenę revision 1 i dirty document revision 2.
Acquisition została jednak odrzucona przed handoff; aktualny odczyt
`status.lifecycle` wykazał awaiting_command/disconnected/forbidden.
Nie znamy pierwszej odmawiającej bramki z ogólnej odpowiedzi prywatnego
kontrolera. Odczyty zapisano w `acquisition-refusal-observation.json`.
Publiczny restart, restore i Compute nie są zaliczone. Cała próba **failed,
exit 1**; własna karta zamknięta, API i frontend zatrzymane po sprawdzeniu
tożsamości, native owner odebrał EOF i wykonał cleanup. **20/20 procesów
i frontend waited**, bez niepotwierdzonych custody records.

Osobny zweryfikowany przyrost plannera zapisano i wypchnięto na master:
`c5ea6a74119b69ce529cee6911815302db7f004c`.
[P8-53BF](53bf-fdm-material-anisotropy-admission.md) rozdziela ten zakres
od otwartego P8-53BE i od kwalifikacji multilayer/GPU/nauki.
Następny krok: prześledzić, dlaczego po terminalnym Grid scratch workspace
traci connectivity, oraz zachować admission i source/contract fencing;
nie ustawiać ręcznie connected ani nie omijać odmowy restartu.

## Aktualny checkpoint — grid-only i dowody procesów

Po numeric prerequisite zaimplementowano wykonanie `fdm_grid_refresh` przez
scratch runtime. Odbiornik pobiera wyłącznie przypiętą komendę Grid; późniejszy
Solve pozostaje w kolejce. Grid używa istniejącego manual remesh, publikuje
jedynie mesh_workspace/engine_log i kończy proces bez uruchamiania solvera.
Osobny storage przygotowania Zarr nie rezerwuje authored OutputStorage.
Następny child jest dopuszczony dopiero po normalnym wait i zgodnym terminalnym
ledger receipt. Nieznany wynik lub obcy session scope zachowują custody.

Produkcyjny managed build F zakończył się exit 0:
`native-build-bf08b996dbce40868bef6d01d4d24961.log`, manifest
`b99b9af6fa2ebf18272e82ec137c5264e533fb9d62ccc0b8cbb0c9be08e1ba9b`.
Siedem zmienionych plików core było byte-equal z frozen source. Dodana później
inicjalizacja scratch w prywatnym browser probe wymaga kolejnego builda H;
nie jest zaliczona na podstawie F. Review końcowego incrementu bez findings.
Rust unit tests pozostają **NOT RUN**.

Build H zakończył się **completed, exit 0** o 11:58:04 UTC:
`native-build-dc11ce22ccae45e19ea39fdb3ac36843.log`, manifest
`97a09bf39eea40a68ece3c528b22140f66c78767156910f8eda2298b5f98c10a`,
backend source
`4293418afc62956228645c358c1ce5f1f69096c163a2d0091af6990cd47e2e30`.
Wszystkie osiem zmienionych plików core/probe jest byte-equal z frozen source
`13b8ce1b32a6ab7905b5beeb91ecaab28308013e27f2f9da4a294f9a55162932`.
CLI/API build: 45,93 s; desktop: 55,89 s. Build obejmuje także snapshot,
przygotowanie zależności i weryfikację pakietu; nie jest to czas całej recepty.
Zweryfikowany mechanizm archiwizacji pakietu został osobno zapisany i wysłany
na master: `008ea9ca3d0465eeee225f1ea435d15c0d2cc15e`.

Managed interpreted handoff `34f25d27bbdd424283cdbfea0ef30a36`:
**completed, exit 0, 151/151 PASS**, bez skipów. Obejmuje exact parser
start/wait scratch child, nonce, API/session scope, duplikaty i odmowy unknown
wait. Wymagany jest zaobserwowany API pin; błąd protokołu unieważnia custody.
To dowód parsera, nie wykonania Grid ani solvera.

Managed API/archive `45e1ec45441a47eda950e2e0ea57f7b3`:
**completed, exit 0, 33 kontrole PASS** dla manifestu
`9bc4ac651427ef3c0a07ebd1b3410b11f50e16a4aea944ff1cb10cc08dbd4b9c`.
Zachowano zweryfikowany pakiet A
`19e7dfca9d77464da8aeb9bc4d515adb` z 13 binariami do kolejnego testu A → B.
Nie aktywowano pakietu ani nie restartowano workspace 3197. Receipt obejmuje
końcowe sprawdzenie manifestu, EXE, frozen źródeł i terminalnych procesów.

Próba runtime Grid → wait → capture → restart → Grid → Compute i terminalny
solver pozostaje **NOT VERIFIED**. Publiczny restart nadal wyłączony;
procentów całego planu nie zwiększono. Poniższe historyczne checkpointy
opisują poprzednie próby i nie zastępują tej bramki.

### Próba H i korekta procedury terminalnej

Browser `453611f757e1491e8993115074e25971` zakończył się **failed, exit 1**:
wyczerpano 600 s prywatnego native probe podczas ręcznego authoringu.
Brak replacement API i brak dowodu Compute. Osiem własnych procesów ma
terminalny wait; frontend również odebrany. Typecheck i lint staged fixture:
PASS. Scena testowa miała obiekt, region, materiał, magnetyzację i Run 1 ps;
nie zaliczać zlecenia Apply Grid ani jego preview jako wykonanej siatki.

Niezależny review wykrył błąd procedury weryfikacji: interaktywny CLI po
ukończeniu finite Run przechodzi do awaiting_command. Normalny terminalny
wait i completed run wymagają jawnej komendy `close`, nie oczekiwania na
samoistny exit ani zabicia childa. Prywatna fixture dodaje Close completed
solver: najpierw potwierdza rzeczywisty ukończony etap, dodatnie kroki i
awaiting_command przez read-only bramkę, następnie wysyła zwykłą typowaną
komendę Close. Jej gotowość zwraca verified=false; dopiero osobna końcowa
bramka wymaga completed run i normalnego wait. Unknown ACK nie uprawnia
do ponowienia Close. Prywatny budżet ręcznego testu zwiększono do 1800 s;
timeouty API, acquisition i cleanup pozostają bez zmian.

Publiczna epoka zasobu sesji może legalnie zmienić się podczas bootstrapu
Compute i terminalnego tombstone. Bramka zachowuje API pin, session_id,
liczbową epokę backendu i request_scope; każde dziecko jest związane z
zakresem sprzed startu, a końcowa epoka zasobu jest zapisana oddzielnie.
Dokładna zgodność sceny i dirty dokumentu nie została osłabiona.

Managed handoff po dodaniu read-only execution gate:
`ee10b3fa70fe4ce38b2b5d66912f5376`, completed, exit 0, **151/151 PASS**.
React Doctor changed-source: `555ad5107a8e457aa0efdcd9fc1877e3`, passed,
6 plików, bez findings. Późniejsza poprawka Close wymaga ponownej weryfikacji;
trzy nowe interpreted checks oczekują zwolnienia locka własnego native buildu.
Nie dodano kolejnego katalogu target ani nie zatrzymano workspace 3197.

## Warunek docelowy

Po kontrolowanej wymianie backendu użytkownik może uruchomić rzeczywiste
obliczenia na odtworzonym modelu. Dla pierwszej bramki wybieramy istniejący
legalny FDM CPU, strict, double; nie dowodzi to pozostałych lane'ów ani
kwalifikacji fizyki. Model ma jawnie przypisany materiał, magnetyzację,
oddziaływanie oraz ograniczony etap obliczeń. Dowód musi pochodzić z
normalnego Compute Study w rzeczywistym workspace, po restore.

Wymagane dowody:

1. Przed restartem i po nim identyczna kanoniczna scena oraz dirty dokument;
   świeża instancja API, sesja i scope po odtworzeniu.
2. Normalne przygotowanie FDM przez Build Grid; bez ręcznej podmiany
   ProblemIR, wymuszenia capability lub zastępczego solvera.
3. ACK `solve` z command_id przypiętym do odtworzonej sesji, następnie
   rzeczywisty postęp solvera i ukończony etap tej samej komendy.
4. Terminalny sukces komendy i etapu; failed/rejected/cancelled/skipped
   nie spełniają bramki sukcesu.
5. Requested/resolved provenance FDM CPU strict double.
6. Jawna tożsamość i terminalny wait wszystkich własnych procesów, w tym
   dziecka scratch_runtime. Brak procesu na liście OS nie zastępuje wait.
7. Widoczny canvas, contextLost=false, niezerowy drawing buffer.

## Ustalenia z bieżących źródeł

Baza master: `1ee35b19e4a0e28da31ed5b9e52097d8b01919f8`.

- `studyRuntimeCommandContributions.ts` rejestruje `study.run` jako `solve`
  i kieruje normalne żądanie przez typowaną fasadę komend.
- `development_restart.rs` po restore uruchamia scratch_runtime przypięty
  do zastępczego API. `scratch_runtime.rs` wykrywa pending compute,
  synchronizuje scenę i uruchamia rzeczywiste `fullmag --interactive`.
- Istniejąca fixture `native-workspace-restart-page.tsx` kończy proof na
  tożsamości, scenie, dokumentach i viewportcie. Nie wymaga udanego Compute.
- `smoke-compute-performance.mjs` sprawdza rozpoczęcie wykonania, lecz jego
  terminalny cleanup dopuszcza także nieudane stany. Nie jest gotowym
  dowodem terminalnego sukcesu tej bramki.
- `verify_workspace_browser.py` rejestruje CLI/API/helpery; dotychczasowy
  protokół nie przekazuje jawnego PID i wyniku wait dziecka scratch_runtime.
  Produkcyjny owner posiada Child i obsługuje wait, ale sama kontrola źródeł
  nie dowodzi rzeczywistego terminalnego odbioru w konkretnej próbie.

Read-only przegląd niezależnego agenta potwierdził te granice; żadnej z
powyższych luk nie uznano za PASS. Rust testy jednostkowe pozostają NOT RUN.

## Bieżąca próba

Zarządzany browser korzysta z osobnego frontendu 3258 i własnych API.
Workspace użytkownika 3197 nie jest restartowany. Pierwszy start odmówił
na blokadzie storage; niczego nie usunięto ani nie zatrzymano. Ponowienie
tej samej recepty uzyskało dostęp i działa pod istniejącym uchwytem procesu.
Wynik oraz wykryte problemy zostaną dopisane po terminalnym odbiorze.
Nie podniesiono procentów P0–P8, nie udostępniono publicznego restartu.

## Próba diagnostyczna i odtworzone blokery

Receipt `bb551f895a854177939cd55e9fc1f54f`: **FAILED**, exit 1,
8/8 procesów oraz frontend odebrane, brak replacement API. Model utworzono
przez rzeczywiste UI: FDM CPU strict double, Box 20 × 20 × 10 nm,
region, Ms=8e5 A/m, A=1.3e-11 J/m, alpha=0.01, anizotropia Ku1=1e4 J/m³,
magnetyzacja uniform, pole zewnętrzne (0,0,0.01) T oraz cell 5 nm.
Nie zalicza to wykonania solvera ani walidacji fizyki.

Save stages dla Run until=2e-12 s odmówił:
`invalid scene patch payload: invalid type: floating point 2e-12, expected a string`.
Przyczyna jest w serde SceneStudyState.stages używającym tekstowego
ScriptBuilderStageState. UI prawidłowo wysyła liczbę. Analogicznie narażone
są fixed_timestep i max_steps Relax. Zakres poprawki: osobny typ sceny,
liczbowe canonical writes, nazwany reader legacy tekstu i adapter do
tekstowego buildera. Nie stringyfikować UI ani podmieniać solvera.

Po odrzuceniu szkicu etapu zapisano baseline sceny revision 8 i podjęto
restart. Native stderr zachowuje dodatkową odmowę:
`invalid development API acquisition response: unknown field reason`.
Nie było replacement ani Compute. Osobno należy sprawdzić pending
fdm_grid_refresh/quiescence oraz przekazanie diagnostyki refusal; nie
uznawać nieudanego restartu za dowód prawidłowego odtworzenia.

Nowa zarządzana regresja HTTP w windows/verify_scene_stage_authoring.py
wymaga udanego numeric Run/Relax round-trip, canonicalizacji legacy tekstu,
zachowania extra keys oraz odmowy bool/object/array/null i niepoprawnych
u64 step budgets bez mutacji. Observer jest utrwalony i hashowany w receipt.
Przed poprawką i produkcyjnym buildem pozostaje NOT RUN.

## Diagnoza odmowy acquisition

Niezależny read-only review wskazał, że CLI `development_api_owner::acquire`
dekoduje także legalną ramkę control rejection jako AcquisitionResponse,
który dopuszcza wyłącznie schema/nonce/api_instance_id/workspace. API owner
używa ogólnej odmowy `development_owner_request_rejected`, zawierającej reason.
CLI ma dokładny parser tej odmowy, lecz stosuje go wyłącznie w commit.
Niepoprawna klasyfikacja wyjaśnia komunikat unknown field reason; nie
uprawnia do pominięcia acquisition ani przymusowego restartu.

Pending grid może naruszać bramkę quiescence; stdout/stderr nie dowodzą,
który konkretny warunek acquisition odmówił. Coordinator po znanej odmowie
pozostawia attempted_api i nie ponawia próby dla tego samego API. W kolejnym
przyroście potrzebne są rozpoznanie ścisłej ramki odmowy i dowód jawnego
retry dopiero przy potwierdzonym Running/uncommitted starym ownerze.
Unknown/postcommit nie może zwolnić claimu. W tym przebiegu nie naprawiono
jeszcze tych granic; nie zalicza się retry ani Compute jako PASS.

Rozszerzenie numeric DTO obejmuje również jawne kolizje obecnego UI:
torque/energy tolerance, eigen_count, eigen_target_frequency, liczbową
trójkę eigen_k_vector oraz scalary adaptive_timestep. Extra payloady
pozostają lossless JSON. To reprezentacja istniejących żądań, bez dodania
capability, zmiany IR/fizyki lub kwalifikacji modalnej.

## Stan implementacji i dowodów

Rozdzielony DTO sceny, legacy scalar/vector reader, adaptery i fail-closed
export są wdrożone w source. Niezależny review: bez actionable findings.
Rust regression source został przejrzany, lecz **NOT RUN** zgodnie z zakazem
kompilowania testów jednostkowych. Parser AST observera Python PASS.

Pierwszy zarządzany BuildOnly, log
`native-build-cec85996f82d4186aaf9ff3ccd0700d3.log`, zakończył się exit 1
przed Cargo: Origin changed while copying a source file. Wrapper ponawia
capture trzy razy, nie kompiluje zmienionej/torn kopii. Dodano nazwę
konkretnego chronionego pliku do diagnozy wyczerpanych prób. Ponowienie
tego samego profilu nie omija seal/fingerprint/source-identity checks.
To blokada bieżącego snapshotu, nie wynik błędu Rust ani nieudanej fizyki.

### Numeric stage authoring — CLOSED, 07.10.2026

Ponowiony managed `just windows-backend-dev 3197` zakończył się exit 0:
CLI/API oraz desktop zbudowane bez kompilacji testów jednostkowych.
Log `native-build-774c99aba27347cda7e1bbb169cf449e.log`;
manifest `7d87e9c8bdeaf1ad95c9aa8884db6758e4e657f4bb852e90c5995b54a44dd74e`,
backend source `abc815900a993a4b4a7d8abbb96c068ada537e070f9c36d4695e126e9a82d8d8`.
Trzy zmienione pliki fullmag-authoring są byte-equal z frozen source.

Zwykły project-document preflight odmówił po późniejszych zmianach wspólnego
checkoutu (receipt `accc34feda6c41f0839e4b6e64f4bbfe`, blocked, exit 2).
Dodano osobną trasę `just verify-windows-project-document-frozen <manifest SHA>`:
wiąże EXE i Python helpers z tym samym zweryfikowanym snapshotem, zamiast
korzystać z później edytowanego pakietu Python. Niezależny review bez findings.

Pierwsza próba frozen (`cbfcbeb6ad264ca596aeb3e615fe52df`) wykonała 32 kontrole,
lecz zakończyła się failed, exit 1: helper Python dopisał 81 plików `.pyc`
w `__pycache__` sealed źródeł. Kontrola inventory prawidłowo odmówiła PASS.
Zweryfikowano hash i rozmiar każdego oryginalnego pliku oraz brak procesów
tej próby. Wyłącznie dodatkowy bytecode przeniesiono do jej `bytecode-quarantine`,
zachowując ścieżki i inventory hashów. Record i źródła pozostały niezmienione.
Verifier ustawia `PYTHONDONTWRITEBYTECODE=1` dla API i dziedziczących helperów.
Review poprawki bez findings; nie dodano wyjątku do seal checks.

Finalny receipt `0bdb5b739e864f8786433c83aa17ef28`: **completed, exit 0,
32 kontrole PASS**, wszystkie 6 własnych procesów terminalnie odebrane.
Numeric Run/Relax, adaptive scalary, legacy reader, extra preservation,
odmowy nieprawidłowych typów i u64 bez mutacji: PASS przez rzeczywistą
transakcję i odczyt sceny. Canonical OpenAPI identity oraz końcowy manifest,
EXE i frozen source integrity: PASS. Rust unit regression source: NOT RUN.

Zamknięcie dotyczy błędu numeric stage authoring i regresji API/persistence.
Nie dowodzi solvera, Compute po restore ani publicznego restartu. Wymienione
niżej bramki nadal są otwarte; UI użytkownika na 3197 nie restartowano.

## Dalszy blocker Compute — pending FDM grid

Read-only tracing potwierdził ścieżkę blokady świeżego workspace:
StudyInspectorPanel Apply Grid kolejkuje `fdm_grid_refresh`; whitelist
`pending_compute_command` scratch_runtime ignoruje ten rodzaj. Solve nie
uruchomi wykonawcy, ponieważ API odmawia Compute przy aktywnej komendzie
meshu. Acquisition również odmawia przy pending grid. Obserwacja tego
przebiegu oraz tracing określają następny konieczny krok, nie stan PASS.

Runner już klasyfikuje grid refresh jako Remesh i obsługuje go wewnątrz
wait_for_solve bez rozpoczęcia symulacji. Naprawa musi podłączyć ten rodzaj
do istniejącego wykonawcy oraz zapewnić terminalny odbiór grid-only child
przed restartem. Samo rozszerzenie whitelisty nie zamyka quiescence,
bo scratch pause nadal wymaga child.is_none(). Nie omijać admission ani
nie zaliczać braku widocznego PID jako wait.

## Checkpoint po zamknięciu numeric prerequisite

Numeric fix jest na lokalnym i remote master:
`2102e64c040ddeecb5dba6b454154081769c1e42`. Frozen build D i receipt
32/32 dotyczą tej poprawki, nie późniejszych zmian restartu.

Przygotowano osobny **WIP source** acquisition w development_api_owner.rs:
exact rejection parser i typowana odmowa przed handoff. Source tests dodane,
**NOT RUN**; brak native/runtime kwalifikacji tego przyrostu.
Nie zaliczać go na podstawie wcześniejszego builda D.

Wariant retry pump został wycofany po niezależnym review. Rzeczywisty
transport zachowuje immutable slot starego API i odrzuca inne request_id
HTTP 409; samo dopuszczenie nowej próby w pump jest nieosiągalne.
Ponadto wykorzystany readiness_candidate pozostawia memo tej samej identity
i blokuje ponowne przygotowanie. Potrzebny jest kontrolowany następnik
slotu po dokładnie potwierdzonej odmowie przed handoff, zachowanie historycznych
request/result oraz poprawny cykl ponownej walidacji candidate. Ogólne Failed,
Unknown i niepotwierdzona publikacja nie mogą uprawniać do następnej próby.
Unit test samego predykatu retry nie dowodzi tych granic. Rozpoznanie
acquisition rejection przeszło source review bez findings; retry pozostaje OPEN.

Review grid-only custody wskazał wymagany kontrakt przed implementacją:

- Lokalne przygotowanie przez istniejący manual remesh bez asynchronicznego
  publishera. Bootstrap nie może utworzyć sztucznego run/live/stage ani
  zastąpić authoring identity. Końcowy payload dopuszcza mesh_workspace
  i opcjonalnie engine_log; pola wykonania i flagi wymiany pozostają puste.
- Odbiornik pobiera wyłącznie przypięty Grid ID i kończy polling przed
  opublikowaniem terminalnego wyniku. Obecny poller pobiera komendy z API
  przed lokalnym odbiorem; samo zatrzymanie na końcu może zgubić późniejsze
  Solve. Inne kolejkujące się komendy muszą pozostać w API.
- Synchroniczny ACK publikacji oraz exact command ledger confirmation:
  ID/kind/API/session scope, completion i timestamp. 404/unavailable
  oznacza unknown. Następny child dopiero po normalnym wait i potwierdzeniu.
- Prep failure i scene/session drift wymagają scoped failure/reconciliation;
  nie publikować sztucznego failed run ani usuwać custody przez sam kill.

Wstępny eksperyment whitelist/early exit został wycofany przed buildem:
nie spełniał wszystkich powyższych granic. Scratch runtime, orchestrator
i live publisher nie mają zmian z tego eksperymentu. Grid i końcowe Compute
po restore nadal są **OPEN**, bez zmiany procentów P0–P8.

## Aktualizacja 13.10.2026 — rzeczywisty Grid i refusal

Powyższa notatka o wycofanym eksperymencie jest historyczna. Późniejsza
implementacja przypiętego Grid-only child uzyskała rzeczywisty dowód:
próba browserowa `9ee08c8889f7486eab618f288474a90f`, Grid 4×4×1,
16 aktywnych komórek, normalny wait child exit 0, ledger completed.
Cała próba zakończyła się failed z pełnym terminalnym custody, ponieważ
API A odmówiło acquisition scratch po zapisaniu wygenerowanego skryptu.
Restore i Compute po restore nadal nie są potwierdzone.

Aktualna diagnoza i WIP korekty canonical scratch path, jednorazowej
publikacji Grid bez runner heartbeat oraz terminalnego observera są w
[P8-53BG](53bg-acquisition-refusal-diagnostics.md). Production build tych
korekt został uruchomiony zarządzaną receptą, sesja 75802; wynik jeszcze
nie jest dowodem ukończenia. Publiczny restart pozostaje wyłączony.
