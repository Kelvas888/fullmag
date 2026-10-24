# Universe: poprawka tożsamości siatki i odzyskanie własnej grupy 3203

Status: zatwierdzony recovery wykonany, natywny Solve wystartował i zakończył
się błędem limitu liści całkowania. Nie opublikowano wyniku H Universe. API zostało
zatrzymane przez nadzorcę po wtórnym błędzie heartbeat. E1–E12 nadal otwarte.

## Stan rzeczywisty

Zatwierdzone wznowienie 7fe211454fea49e3b54ff7937f347de4 zakończyło build i start API.
Wysłano jeden publiczny Solve Universe. Przygotowanie zakończyło się exit0, ale
scheduler odrzucił zadanie przed uruchomieniem solvera: niestabilny fingerprint.
Nadzorca zakończył API/runtime; backend pozostaje running/unhealthy. Nie ma
nowego V/J/H Universe ani dowodu wizualizacji.

24 odczytowe planowania tych samych zaakceptowanych danych dały dwa digests
siatki, 13 i 11 razy. Przyczyną jest surowa serializacja HashMap metadanych
jakości dwóch domen. Minimalna poprawka MeshIR w źródłach sortuje tylko tę mapę
po numerycznych kluczach. Trzy regresje źródłowe i niezależny review są gotowe;
parser rustfmt PASS, testów Rust nie kompilowano. Nie zmieniono schematu
fingerprintu ani ścisłego porównania przez scheduler.

Wszystkie 70 wcześniejszych plików wyniku, pięć historycznych katalogów i
zapisany FMS Universe ponownie sprawdzono hashami: identyczne.

## Konkretny pakiet do zgody

Połączony patch ośmiu plików:
`6ce99bd5c18ce667c9a617c5b4908b08df06785b025d1efcc4ebf54e24c24a1a`.
Artefakt w wolumenie kontrolnym tej grupy:
`verification/universe-volume-policy-20261023/consolidated-fingerprint-recovery/v1/proposal.patch`.
Manifest z hashami każdego pliku przed/po: `manifest.json` w tym samym katalogu.

Składniki: authority resume
`a114637fd1f079eab4d5387dfa8dbb6a4853141e17eee0d7af5282b5a5e378a5`
oraz awaryjny preclaim Cancel
`ebe93f2bd88ee103e5a7977434ed0b0f3ac360a74ce0f3210d19d232c81a228e`.
Dotychczasowy kontroler wybiera przestarzały development/verified; nowa jawna
para pinów wskazuje potwierdzony resume i jego rodzica. Zachowane są wszystkie
kontrole konfiguracji, środowiska, cache, kontenera, procesu i OWNER. Nie ma
wyboru automatycznie najnowszego zapisu ani przepisywania historii.

Nowa natywna komenda jest przypięta wyłącznie do Run
`run-live-a64208b634566c8860f02400cb9b0a7f78c0a5a2d116c94a7629e613b7ee223f`.
Katalog rev2 SHA256:
`ea1b868f78d35d7fdbcf839d212eb58c97e12d7e0b84299f063df81fbc1dce19`.
Request anulowania, jeszcze niewykonany:
`9b3b67399e5d5175224009f543b8715198c546d60fca86d635bb118f85965845`,
`verification/universe-volume-policy-20261023/preclaim-cancel-proposal/request.json`.

## Kolejność wykonania po zgodzie

1. Zastosować dokładny patch i dodać do indeksu Git wyłącznie jego nowe pliki,
   potrzebne do snapshotu. Zachować istniejącą poprawkę MeshIR oraz cudzy FMS.
   Wykonać kontrole i zapisać spójny commit zadania przed capture do buildu.
2. Zbudować kandydata przez istniejący `just docker-dev-recovery-build` w stałym
   backendzie grupy, z jawnym resume 7fe211… i terminal SHA256
   `29f7074f38834bf0d924a4baf1f75ad1e5a5c7629e213d7996747d479c2c4d67`.
   Niezmienione obrazy zależności i cache pozostają do wykorzystania.
3. Przed promocją/restartem sprawdzić kompletny pakiet oraz rzeczywisty native
   preview z przypiętym requestem. Powtórne odczyty muszą dawać jeden stabilny
   fingerprint; sprawdzenia odmów wykonuje się wyłącznie w trybie verify-only.
4. Jeżeli poprawiony fingerprint pasuje do zapisanego, zachować ten sam Run.
   Apply anulowania sam odmawia w tym przypadku. Zarządzane wznowienie może
   przydzielić wykonanie już przyjętemu zadaniu; nie wysyłać drugiego Solve.
5. Wyłącznie przy potwierdzonej niezgodności: zastosować opisany request Cancel
   istniejącymi natywnymi prymitywami intent/projection. Wymagane: brak attempt,
   wykonania, Start, aktywnych leases i niezwolnionych rezerwacji. Zmienia się
   lifecycle i revision tylko tego katalogu; przygotowanie, input_fingerprint,
   RunIntent, CAS i wyniki pozostają. OWNER zostaje Failed do istniejącego recovery.
6. Opublikować zweryfikowany kandydat i przywrócić wyłącznie grupę 3203 przez
   zarządzane recepty stop-failed/recreate z zachowaniem state (fresh_state=false),
   pełnymi aktualnymi pinami oraz kontrolami native drain/recovery. Inne grupy
   pozostają poza zakresem. Odtworzyć własną scenę z zachowanego kanonicznego
   skryptu; nie dopasowywać fingerprintów ani zastępować modelu fizycznego.
7. Tylko w wariancie z kroku 5: uruchomić JEDNO nowe publiczne Solve tej samej
   niemagnetycznej anteny i Universe, z profilem volume_inspection_v1. Odczytać
   durable Run także przy timeout HTTP; bez automatycznego ponawiania Solve.
8. Zweryfikować V/J/H, prawdziwy globalny nośnik H i obwiednię otaczającą źródło,
   jednostki, wspólne provenance i budżety. Udostępnienie pola w UI nie zastępuje
   dowodu WebGL; aktualna ścieżka przeglądarki nadal jest zablokowana.

## Blokady i zgodność

Native bierze startup/launch/owner oraz host→store writer locks; sprawdza
przypięte receipty, PID/boot/namespace i pełne inventory Run. Nie tworzy
fikcyjnego solver claimu. Częściowo zapisany intent zachowuje się jako prawdziwy
stan; nieudane apply bez potwierdzenia pozostawia operation unknown i wymaga
odczytu dowodów, bez automatycznego retry. Zmiana pinów, źródeł lub stanu
powoduje odmowę, nie pominięcie kontroli. Anulowania nie cofamy.

Zgoda obejmuje powyższą warunkową procedurę, zastosowanie dokładnego patcha,
build/preview i istniejącą promocję/restart własnej grupy oraz najwyżej jedno
nowe Solve tylko wtedy, gdy wcześniejszy Run musiał zostać anulowany. Nie jest
to kwalifikacja naukowa ani odbiór E1–E12. Wyniki pozostają inspection-only.

## Dowody i granice weryfikacji

Połączony pakiet: 13 testów interpretowanych PASS, sześć izolowanych prób fixed
argv preview/apply i odmów PASS, bash -n PASS, parser just1.58 PASS,
git apply --check --whitespace=error PASS. Authority sprawdzono także na
rzeczywistych receiptach, konfiguracji i mountach istniejącego kontenera.
Przeglądy obu składników i minimalnej poprawki MeshIR: brak pozostałych blockerów.
Testy Rust — źródła, bez kompilacji. Poprawiony pakiet, rzeczywisty native
preview, terminalizacja, restart i Solve pozostają NOT VERIFIED do wykonania.

## Dlaczego wymagana jest decyzja

§8 AGENTS.md przekazanego przez użytkownika w rozmowie wymaga pytania, gdy:
“The change touches something you've been told is load-bearing, versioned,
or has a migration path.” Ten pakiet rozszerza bramkę wyboru potwierdzonego
uruchomienia oraz dodaje natywną ścieżkę zmiany stanu zadania. Wcześniejsza zgoda
dotyczyła innego patcha i została już wykonana. Obecna propozycja nie została
zablokowana przez automatyczny review; decyzja wynika z instrukcji użytkownika.


## Zgoda i rozpoczęcie wykonania — 24.10.2026

Użytkownik zatwierdził opisaną warunkową procedurę („akceptuje”). Dokładny
patch 6ce99bd5… został zastosowany po sprawdzeniu wszystkich hashy bazowych
i końcowych. Nie zmieniono jeszcze katalogu Run ani stanu runtime. Następny
krok: sprawdzenia źródeł, commit oraz zarządzany build kandydata.


## Wykonanie po zgodzie — 24.10.2026, stan podczas obliczeń

Zastosowany patch zapisano w 7008afd9eab3ecb6b9e17bccb1a02fee802e2d02.
Pierwszy build ujawnił użycie prywatnego reject_link. Minimalna poprawka
7501800a074b89c73990185a388427b954f1a24a używa istniejącego publicznego
checked_path, zachowując kontrolę linków i containment. Następny build
b6a0da22261443b8a8f63a31ab5afac2 przeszedł, bez błędów kompilatora.
Receipt pakietu: d1e628a2a25aadf99faa309149705fa297e29cdcbfa02830f7361febf38f39f9.

Preview przed promocją odmówił: nowy commit binarny nie zgadzał się ze starym
kanonicznym provenance. Nie wyłączono tej kontroli. Promocja bez startu runtime
87ebf6014f484bf08d4a787fb163c999 przeszła, po czym kontroler otrzymał jawny
wybór published: tylko PACKAGE_ROOT, kompletne inventory, dokładny receipt
oraz powiązane provenance pod dotychczasową build lock. Nie zmieniono natywnych
warunków anulowania. Sześć lekkich testów opcji, parser Bash/just oraz niezależny
review wiring przeszły. Testów Rust nie kompilowano.

Dwa rzeczywiste preview dały identyczny poprawiony fingerprint
2ece71556b96d660c424f104a6367fcf596e4ebe9a64550db4f509f0eab9f843,
różny od zapisanego 2118aec25de60892d810e3e4999bc6365b1d4cf43695d3c336fcc8332cc32899.
Negatywne verify-only z błędnym OWNER SHA i przestrzenią PID odmówiły.
Zatwierdzony apply f08c6c11acad4769bf5c5d4853c19cd4 zakończył wyłącznie a642…:
Cancelled rev4, hash katalogu 3f193d206c4a020358964db3410cd0d0e2b5a80f66545578fbb15aa650e272c7.
Input fingerprint, przygotowanie i CAS nie zostały przepisane.

Zarządzane stop-failed i recreate zachowały state/cache. Pierwszy start odmówił
z powodu chwilowego kontenera, którego po odmowie nie było już w Dockerze.
Istniejący CLI resume-recreation wystawiono przez ścisłą recepturę just;
nie zmieniono bramek lifecycle ani nie powtórzono usuwania usług.
Start 8b881fa8d50746e8aca521a1b6618f72 zakończył się succeeded, port 3203,
config ff12a3b0e4d89aa23997f6a2f0062ee03b53b2e1fc49734697f44cd10a5ded17.
Toolchain/images były cache hit; aplikacja przebudowała swój pakiet w backendzie.

Publiczny import skryptu potwierdził round-trip. Osobne przygotowanie Mesh Build
zakończyło się poprawnie, a jego nieuruchomioną obserwację b29… zamknięto publicznym
Stop, zachowując siatkę. To terminalizowało sesję; Solve dostał jawne HTTP409
session_cancelled_read_only bez utworzenia zadania. Ten sam kanoniczny model
przywrócono do nowej sesji, a Solve sam przygotował domenę. Nie ponawiano Solve
po timeout transportu: trwały katalog potwierdził przyjęcie i uruchomienie.

Jedyny przyjęty zastępczy Solve:
- sesja session-18e14e039f9aa74a00000a85;
- Run run-live-8d181b0e7ac898ebbc0cb6e8b6a7b958219a6f8ccea0943e7e5d5704824bb331;
- task task-3151e003704f28bd5eabf7936ee5248af7446c9150d261a8c2301c057c476cc0;
- attempt attempt-7c35a45efffb4389ad7435ef83ebbd98;
- komenda fm-a32e38b8-a217-4486-b183-04c7b11f7a0b.

Przygotowanie native potwierdziło 678 węzłów i 1863 Tet4 przewodnika,
zero niepoprawnych komórek. Istnieje worker_execution_started; trwały lifecycle
Running, aktywny worker widoczny w procesach kontenera. To dowód rzeczywistego
wykonania, jeszcze nie poprawnego V/J/H. Nie ma zgody na kolejne przyjęte Solve.
Po recovery ponownie potwierdzono 70 wcześniejszych plików, pięć katalogów i FMS
jako identyczne. Dowody: approved-new-solve/ oraz preclaim-cancel-proposal/
w verification/universe-volume-policy-20261023 w wolumenie kontrolnym grupy.


## Wynik wykonania i granica dalszej zgody — 24.10.2026

Natywny worker 8d181… zakończył się exit1. Potwierdzony błąd:
final_leaf_budget_exceeded przy target_m=(0,-4.6176898829131121e-12,-1e-7).
Estymata błędu 11.056035818905203 A/m przekroczyła tolerancję
2.4709319136549057 A/m; roundoff indicator 2.4305242514006608e-10 A/m.
Liczba liści na ten punkt osiągnęła 1000000. Końcówka reason jest ucięta;
nie wolno interpretować urwanego kernel_evaluations=353 jako pełnego licznika.
Limit wynika z DirectTetraQuadrature::maximum_final_leaves_per_target w
backends/fem/cpu/mfem/interactions/oersted/direct_tetra_quadrature.hpp,
a odmowa z evaluate_target w odpowiadającym .cpp. To limit na jeden target,
nie liczba par źródło-target ani przydział CPU/RAM kontenera.

Następnie scheduler odmówił reconcile final worker-acknowledged resource heartbeat:
worker exited with an unacknowledged heartbeat command. OWNER przeszedł w Failed,
nadzorca zreapował API (exit -15) oraz runtime. Katalog pozostał Running/reconciling
rev52, zero artifact_ids; nie jest to aktywne obliczenie ani zaakceptowany wynik.
Istnieje trwały worker process exit receipt. Globalny mesh CAS ma 1157 węzłów
i 6498 elementów; jego istnienie nie dowodzi obliczenia pola.

Nie zwiększono limitów, nie zmieniono tolerancji i nie wysłano kolejnego Solve.
Dalsza terminalizacja tej nowej próby i zwolnienie jej rezerwacji wymagają
odrębnego, przypiętego requestu/preflight do decyzji użytkownika. Zgoda na a642…
nie obejmuje zmiany nowego Running task 8d181… . Numerykę trzeba zbadać przed
proponowaniem większego limitu; samo jego zwiększenie nie dowodzi zbieżności.
Dowód pełnego bieżącego logu zachowano jako approved-new-solve/failed-compute-log.json.


## Nowy request po awarii 8d181 — gotowy do decyzji

### Odzyskanie po nieudanym Universe Solve 8d181 — decyzja operatora

Status: request przygotowany; rzeczywisty native verify-only PASS. Apply,
zwolnienie zasobów i restart NIE zostały wykonane. Nie ma wyniku H Universe.

#### Dokładny zakres

Run: run-live-8d181b0e7ac898ebbc0cb6e8b6a7b958219a6f8ccea0943e7e5d5704824bb331.
Task: task-3151e003704f28bd5eabf7936ee5248af7446c9150d261a8c2301c057c476cc0.
Attempt: attempt-7c35a45efffb4389ad7435ef83ebbd98; ownership epoch 1.
Katalog pozostaje Running/reconciling rev52, bez opublikowanych artefaktów.
Worker zakończył się exit1 po final_leaf_budget_exceeded. API i runtime
zostały zakończone przez nadzorcę; nie działają żadne obliczenia tej próby.

Request: request.json w tym katalogu.
SHA256: 550a170177411ff23c2996ca5be7de19899e6e69f35d43462b90529059ec328d.
Request zawiera wrażliwe tożsamości procesu; jego treści nie publikujemy.

#### Zmiany po zgodzie

1. Ponownie sprawdzić dokładne piny i wykonać istniejący native preflight.
2. Zastosować wyłącznie przypięty --fail-reaped-worker: kanoniczny Failed,
   nieretrywalny event, DoNotRetry, zwolnienie wyłącznie tej rezerwacji CPU,
   archiwizacja przypiętego slotu. Zachować exit receipt, journal, inbox,
   przygotowanie, CAS i całą historię. Bez ręcznej edycji katalogu/ledgera.
3. Potwierdzić końcowe receipty, brak aktywnego lease i zachowanie danych.
4. Przywrócić wyłącznie naszą grupę 3203 przez managed just stop-failed i
   recreate/resume z zachowaniem state/cache (fresh_state=false), wraz z
   potrzebnym buildem w jej stałym backendzie. Przywrócić ten sam model
   authoring przez publiczne API. Nie zatrzymywać cudzych grup ani WSL/Dockera.
5. Nie ponawiać Solve, nie zwiększać limitów całkowania ani CPU/RAM, nie
   zmieniać tolerancji. Diagnostyka numeryczna pozostaje osobnym zadaniem.

Zmiana któregokolwiek pina, nowy proces lub niejednoznaczny wynik przerywa
procedurę. Unknown nie oznacza zgody na ponowienie. Nie cofamy Failed ani
DoNotRetry. Sam restart nie będzie przedstawiany jako poprawne obliczenie H.

#### Dowody

verify-only.stdout: verified_reaped_worker_failure; mutations_applied=false,
solve_replayed=false; exit0, stderr puste. Natywna kontrola sprawdziła tożsamości
hosta/boot/PID, Failed OWNER, dokładne Start i exit, lease/rezerwację, journal
24 komendy / 23 zdarzenia, pojedynczy niepotwierdzony ogon heartbeat, brak
pending effect oraz archiwizowalność przypiętego slotu. Jest to odrębna,
niesymulacyjna kontrola istniejącego CLI wewnątrz własnego backendu; nie bramka
FEM ani nowy Solve. Nie ma receptury just dla tego read-only CLI.

Po preview ponownie sprawdzono: 70 historycznych plików, pięć katalogów, FMS
identyczne; nowy Run nadal bez zmian rev52. Tryb verify-only może aktualizować
diagnostyczne WRITER.owner.json przy blokadach; nie zmienia biznesowego stanu
Run, rezerwacji ani retry. Testów Rust nie kompilowano.

#### Dlaczego nowa zgoda

Poprzednia decyzja wskazywała a642… i jeden zastępczy Solve. Nie obejmowała
terminalizacji nowego Running task 8d181… . AGENTS.md przekazany w rozmowie,
§8, wymaga decyzji przy zmianie elementu load-bearing lub wersjonowanego.
Zgoda dotyczy wyłącznie opisanej terminalizacji i przywrócenia naszej grupy,
bez następnego obliczenia i bez zmiany polityki numerycznej.


## Audyt geometrii i ograniczenie wniosków po awarii 8d181

Status: audyt tylko do odczytu. Nie zmieniono metody, tolerancji, polityki,
siatek ani stanu runtime; nie uruchomiono kolejnego Solve. Ponowny odczyt
indeksu preflightu potwierdza apply_invoked=false. Wniosek o terminalizację
8d181 pozostaje osobną, oczekującą decyzją; wcześniejsze „akceptuje” dotyczyło
wykonanej już procedury a642 i pojedynczego zastępczego Solve.

### Dowód geometryczny

Zweryfikowany katalog CAS:
32ad3f04cfb8fc3e9912f2d2ad1bf906d7a6789206c456e458aa872785f78861.
Źródło: 678 węzłów / 1863 Tet4. Universe: 1157 węzłów / 6498 Tet4.
Dokładny target z błędu jest globalnym węzłem 52:
(0, -4.6176898829131121e-12, -1e-7) m. Najbliższy source vertex 48:
(0, -2.220446049250313e-22, -1e-7) m; odległość
4.617689882691067e-12 m, około 4,6 pm.

Diagnostyka geometrii umieszcza target na krawędzi komórek źródła
234, 1481 i 1484. Dwie współrzędne barycentryczne wynoszą zero; dwie
pozostałe około 3.0784599218e-5 i 0.9999692154. Nie wykazała dodatnich
podkomórek Duffy o względnej objętości mniejszej niż 1e-10. To nie jest dowód
natywnego przebiegu kwadratury: Python fsum ma inny porządek zaokrągleń niż
wyrażenia C++; raport jawnie ma same_algorithm_as_native=false oraz
physics_qualified=false. Nie obliczano prądu ani pola.

Dowód w wolumenie kontrolnym grupy:
verification/universe-volume-policy-20261023/failed-target-geometry-audit.json.
Bliskość do wierzchołka jest wskazówką do regresji, nie potwierdzoną przyczyną
wyczerpania miliona liści. Brakuje rozkładu błędu po elementach i głębokościach
oraz zachowanych współczynników RT0 z nieudanej próby; atomowa publikacja
nie pozostawiła zaakceptowanego V/J/H tej próby.

### Dwa odrębne nośniki są obecną realizacją kontraktu

| Źródło: ścieżka + symbol | Zaobserwowane zachowanie |
|---|---|
| packages/fullmag-py/src/fullmag/runtime/antenna_coincident_materialization.py::materialize_antenna_coincident_loops | independent_workflow usuwa domain_mesh_source/domain_region_markers/domain_object_region_markers; buduje przewodnik bez study_universe i podmienia fem_mesh_assets, zachowując globalny asset. |
| packages/fullmag-py/src/fullmag/meshing/_antenna_coincident_cut.py::realize_antenna_coincident_loop_mesh oraz prepare_antenna_coincident_loop | Osobna pełna siatka 3D i sourcecut z własnymi stable IDs. |
| crates/fullmag-plan/src/antenna_field_solve.rs::load_object_mesh oraz resolve_field_sampling | Niezależny asset przewodnika i odrębny fem_domain_mesh_asset dla globalnego samplingu. |
| crates/fullmag-plan/src/antenna_current_source.rs::materialize_antenna_closed_loop_current_input | Pełny oryginalny właściciel, ordynały oraz source.mesh_digest są częścią przypiętego wejścia. |
| docs/physics/0950-quasistatic-microwave-antenna-field-basis-and-k-selective-excitation.md: parametr AntennaFieldSolveStage.conductor_mesh_policy oraz anchor antenna-universe-inspection-carrier | authored_shared_domain zachowuje publiczny default pełnej 3D Tet4; sampling ma własne rzeczywiste xyz i connectivity, przypięte do signature. |

Nie znaleziono obietnicy, że source mesh musi być wycięciem Universe.
Nazwa tokenu jest mniej precyzyjna niż realizacja; nie upoważnia do zmiany
zaakceptowanego modelu. Snap punktu, usunięcie trudnych targetów lub zamiana
source na wycinek globalnej siatki zmieniłyby wejście i provenance.

### Granice diagnozy numerycznej

backends/fem/cpu/mfem/interactions/oersted/direct_tetra_quadrature.cpp:

- decompose_target_tetrahedron wybiera podział Duffy dla targetów wewnątrz/na
  Tet; integrate_duffy_once usuwa radialną osobliwość bez fizycznego cutoffu;
- evaluate_leaf porównuje reguły rzędu 4+2*depth i o dwa większego;
- evaluate_target sumuje nieujemne estymaty błędu liści na cały target,
  wybiera dalsze refinements stertą i końcowo przelicza ledger;
- liście osiągające maximum_subdivision_depth nie trafiają ponownie do sterty.
  Bez końcowego rozkładu błędu nie wiadomo, czy pozostały błąd tej próby
  dominował w takich liściach; sam kod nie dowodzi tego scenariusza.

backends/fem/cpu/mfem/interactions/oersted/direct_tetra_quadrature.hpp::
DirectTetraQuadrature określa milion final leaves per target; ResolveWorkLimits
w .cpp daje profilowi volume_inspection_v1 500 mln kernel evaluations i ledger
visits. To odrębne limity. Osiągnięcie pierwszego nie jest dowodem braku RAM.
backends/fem/cpu/mfem/transport/affine_rt0_element.cpp::AffineRt0Element::current_at
wiąże obecną kwadraturę z rzeczywistym afinnym prądem RT0; bez jego
współczynników nie przedstawiamy diagnozy samej geometrii jako odtworzenia pola.

Najwęższy następny eksperyment numeryczny powinien zachować dokładne wejście,
source view, target i tolerancje, a zebrać ograniczony rozkład błędu według
source element/depth i klasyfikacji inside/edge/near. Najpierw należy ustalić,
czy można odtworzyć ten sam zamrożony prąd, a następnie przygotować kanoniczną
regresję i dowód z zarządzanej ścieżki. Ten eksperyment nie został wykonany;
nie stanowi zgody na kolejny Solve ani na zmianę wersjonowanej metody.
Nie publikujemy nowego operatora ani twierdzenia o zbieżności.

Weryfikacja tego etapu: niezależny odczytowy audyt źródeł i CAS, kontrola
istnienia ścieżek/symboli oraz git diff --check. Brak zmian terminalnej noty
naukowej lub kodu, brak buildu, Rust unit tests i dowodu browser/WebGL.
