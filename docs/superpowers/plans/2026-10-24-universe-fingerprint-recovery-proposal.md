# Universe: poprawka tożsamości siatki i odzyskanie własnej grupy 3203

Status: propozycja do decyzji użytkownika. Patch bramek nie został zastosowany.
Build kandydata i natywny preview nie zostały wykonane. E1–E12 nadal otwarte.

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
