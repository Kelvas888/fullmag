# Checkpoint anteny po restarcie WSL — 28.10.2026

## Cel i bieżący wynik

Celem pozostaje pełny zakres E0–E12 z pierwotnego zlecenia, w tym rzeczywiste
V/J/H anteny, zapis i cold-load, poprawne Inspectory, wizualizacja pola w Universe,
kwalifikowana baza i jej konsumenci. Ten checkpoint dotyczy naprawy środowiska;
nie oznacza zakończenia anten ani kwalifikacji naukowej zapisanego wyniku.

Backend i frontend naszej grupy są zatrzymane. Nie uruchomiono nowego Solve.
Zapisany wynik pozostaje Failed / unassessed. Historyczny poprawny odczyt API
nie zastępuje ponownego odczytu po przywróceniu usług ani odbioru WebGL.

## Odtworzenie Git bez zmiany historii

Po restarcie znaleziono trzy puste loose objects i dwa wyzerowane końce reflogów.
Odtworzenie surowych payloadów z indeksu i znanych metadanych dało identyczne SHA-1:

- commit `0b85a73357aadcd8caaf0943f0d038bd0c35b274`;
- drzewo scripts `51cc6704b2fc94181cc0addb9a737a1e229826c1`;
- drzewo główne `d787c971393243689f34461c83ee7d1963d7766c`.

Przed zapisem zachowano pełny common Git i chroniony FMS w wolumenie kontrolnym.
Archiwum: 2 337 832 960 B, SHA256
`e7e7ba2c7b1ee96931ae492c2862ff1bf42f7e144d3e354d77c5e8703629d901`.
Pełny `git fsck --full --no-dangling` zakończył się kodem 0, bez komunikatów.
Indeks i FMS zachowały swoje SHA256. Nie wykonano reset, prune ani zmiany refs.
Dowody: `verification/git-repair-after-wsl-restart-20261028/`.

Commity `f08d22c227b3020aa3f07b04f38853ff7f81fad9` i
`0b85a73357aadcd8caaf0943f0d038bd0c35b274` wypchnięto na branch PR #247.
Nie zapisano bezpośrednio do mastera.

## Potwierdzenie błędu osieroconego resume

Nowy jawny schemat `fullmag.docker-resume-interrupted.v1` uzupełnia dotychczasowy
`fullmag.docker-development-interrupted.v1`. Stary kontrakt pozostaje zachowany.
Receptura: `just docker-dev-reconcile-resume <request> <SHA256> <source_root> [apply]`.
Domyślnie wykonuje preview; zapis wymaga `apply=true`.

Zakres jest ograniczony do resume zakończonego błędem gotowości frontendu,
którego backend jest teraz Exited255/PID0 po innym uruchomieniu WSL, a oryginalny
helper już nie istnieje. Kontrolowane są dokładne kontenery, obraz, stan, Compose,
base receipt, package/provenance, log, źródła kontrolerów, wolumeny, helper absence,
blokada i brak aktywnych konsumentów. Publication nie jest ponownie kwalifikowana.
Wolumen zasiany i rzeczywiście zamontowany są rozróżnione w wyniku.

Po restarcie numer urządzenia katalogu storage zmienił się z 2096 na 2128;
inode 241587, root, engine i ext4 pozostały zgodne. Nowy request jawnie przypina
oba numery wyłącznie do potwierdzenia błędu operacji. Certyfikat i jego owner
nie są zmieniane. Zwykła bramka admission nadal odmawia starego device;
regresja wywołuje tę rzeczywistą bramkę i sprawdza odmowę.

Końcowe 21 testów interpretowanych: PASS, 0 failures/errors/skips, w zarządzanym
helperze tej grupy, bez Rust compilation. Testy wykonują też rzeczywistą
transakcję shell na odizolowanych plikach fixture: preview, publikację, częściowe
ponowienie, błędne piny i zajętą blokadę. Niezależny source review: 0 Required.

Canonical preview przeszedł, a następnie zastosowano dokładny request:

- request SHA256: `bbf9e8d3b0edda70bff363db44855cca19e9262f62612e534ca9201c33f99441`;
- kontroler SHA256: `49d0bae5b2a3e07c81a30f8efd7167816fe6c6f2498b9af03218dc773e1e02c4`;
- operacja: `42c26e8726dd472780391b98cde2a33b`, stan `failed-confirmed`;
- terminal SHA256: `8abe83c4318bea3b890558149442b9421d8989a39f713d80085a49a4f05b558c`;
- osierocony active został zwolniony pod blokadą kontrolera;
- wszystkie 15 919 plików store, 537 825 914 B: identyczne przed i po;
- natywne OWNER, LAUNCH i process-tree: identyczne przed i po;
- obserwowane certyfikaty i markery storage: identyczne przed i po;
- zero startów usług i zero ponowień Solve.

Dowody: `verification/resume-interrupted-20261028/`, w tym
`apply-49d0bae5b2a3-1c78bbf7.json`, snapshot i log oraz
`final-source-tests/tests.json`. Potwierdzenie błędu operacji nie jest odzyskaniem
natywnego ownera ani dopuszczeniem storage do uruchomienia.

## Native v4 — źródła przygotowane, runtime niezweryfikowany

Osobny `runtime_service_container_recovery_request.v4` zachowuje pełny,
rozłączny inventory terminal history i nigdy niewypuszczonych manual runs.
Obecny store ma 43 runy: 41 terminalnych i dwa held. Nie wystarczy przypiąć
trzech ostatnich runów. v1–v3 nie akceptują held jako terminal evidence.

Held mają osobne intent/catalog/evidence SHA256, canonical manual policy i brak
release/admission/lease solvera. Zakończone przygotowanie pozostaje zachowane
oraz weryfikowane istniejącymi lease→launch→exit→host-release fences.
STARTUP/LAUNCH/OWNER, host-before-store, quiescence, archiwizacja i idempotencja
pozostają wspólne. V4 wymaga Exited attestation; nie rozszerza NamespaceAbsent.

Agregat v4 wynosi jawnie 256 MiB; v1–v3 pozostają przy 128 MiB.
Pomiar bezpośrednich CAS referencji: 119 548 414 B, plus około 30,8 MB intentów.
Read-only CLI `runtime service-inspect-held-manual-run` produkuje nowy pin;
nie tworzy start release ani nie uruchamia zadania.

Osiem nowych regresji Rust jest w źródłach; zgodnie z ograniczeniem lokalnym
nie kompilowano ani nie uruchamiano testów Rust. Source review nie wykazał
Required/Blocker. Parser rustfmt w helperze własnej grupy poprawnie odczytał
osiem zmienionych plików; to kontrola składni, bez kompilacji i testów. Dowód:
`verification/mixed-history-native-v4-20261028/rust-syntax.json`. CI pełnego
`fullmag-session` obejmuje nowe regresje; dodano także jawne sprawdzenie CLI
`cargo check -p fullmag-cli --bin fullmag` na GitHub. Wynik CI pozostaje wymagany.
Nadal wymagane są CI, managed build i rzeczywisty preflight
wszystkich historycznych runów. Obecny binarny pakiet nie obsługuje v4.

## Następne bramki

1. Zarządzana ponowna kwalifikacja storage po zmianie device, z zachowaniem
   oryginalnych certyfikatów i historii; bez ręcznego resetu ownera.
2. Build nowego pakietu wyłącznie we własnym kontenerze backend przez just.
   Istniejący recovery-build wymaga Running + Failed/Unknown i nie jest jeszcze
   bootstrapem dla Exited255 + Ready. Zwykły start może zatrzymać się przy
   diagnostic API; nie wolno zakładać, że sam zakończy PID1 po odmowie ownera.
3. Pełny mixed-history native preview, następnie autoryzowane recovery;
   żadnego syntetycznego shutdown_unknown, drainu ani pomijania starych runów.
4. Przywrócenie UI i saved inspection z prawdziwym ownerem rozwiązania.
5. Odbiór H w Universe w rzeczywistym WebGL: canvas, wektory, jednostki, skala,
   Inspector, poprawny brak danych i screenshoty; bez nowego Solve przy zmianie widoku.
6. Pozostałe wymagania E0–E12 oraz testy/CI i integracja PR. Ten checkpoint nie
   zastępuje odbioru end-to-end ani odtworzenia wyników publikacji.


## Przygotowanie storage po restarcie WSL — kontroler i regresje

Nowy kontrakt `fullmag.linux-native-device-readmission-preparation.v1` przypina
pięć surowych plików admission, engine, root/inode, dawny i obecny device oraz
istniejące image/source/binary binding. Kandydat zmienia wyłącznie `host_device`
i `restart_verified=False`. Nie daje namespace admission; dotychczasowe bramki
`reuse_certificate`, retained storage i rzeczywisty guest probe pozostają zachowane.

Kontroler `scripts/docker_linux_native_readmission.py` udostępnia jawny request
`fullmag.docker-linux-device-readmission.v1` przez receptę
`just docker-dev-readmit-linux-storage <request> <SHA256> <source_root> <image_id> [apply]`.
Domyślne preview nie zmienia certyfikatu ani ownera. Zarządzany helper własnej grupy
trzyma operation/STARTUP/LAUNCH/OWNER oraz host-before-store writer locks na
rzeczywistych inode. Dwa kontenery muszą pozostać w dokładnie przypiętym stopped
state; aktywny konsument lub rezerwacja oznaczają odmowę. Nie zatrzymuje usług.

Archiwum w prywatnym control volume zachowuje bezstratne surowe bajty i kandydata
przed pierwszą zmianą hosta. Publikacja zachowuje inode certyfikatu bind-mountu.
Replay korzysta z archiwum i obsługuje wyłącznie pary old/old, marker-new/cert-old
oraz new/new; nieznane lub torn bytes wymagają osobnego recovery. Helper nie
wykonuje żadnej mutacji Dockera ani admission, a EOF zwalnia blokady. Dlatego
kontroler stosuje istniejący wzorzec transakcji recovery, bez nowej operacji buildu
ani trwałego active; archiwum i zwykłe bramki blokują niejawne dopuszczenie po awarii.

Weryfikacja w interpretowanym Pythonie we własnym zarządzanym helperze:
13 regresji core i 8 regresji wrappera: PASS, bez failures/errors/skips.
Wrapper uruchamia rzeczywisty protokół na prywatnych fixture i sprawdza wszystkie
blokady, przerwanie po EOF, odmowę przy aktywnej operacji/rezerwacji, zmianę danych,
nieczytelny katalog oraz historię większą niż 64 pliki. Dowody:
`verification/linux-native-readmission-20261028/core-tests.log` i
`verification/linux-native-readmission-20261028/wrapper-tests.log`.
Niezależny przegląd core: brak Required; dwa Required wrappera (serializacja raw
archiwum i jawna odmowa błędu enumeracji) zostały poprawione przed użyciem.

W chwili zapisu pierwszego fragmentu rzeczywiste preview/apply były niewykonane;
wynik późniejszego wznowienia v2 opisano poniżej. Nowy probe w docelowym backendzie,
managed build, native mixed-history recovery i odbiór H w WebGL pozostają niewykonane.
Wynik symulacji zachowuje Failed/unassessed. Nie powtarzano Solve.


## Weryfikacja rzeczywistej trasy i jawne wznowienie archiwum v2

Commit `25a3b800558e3dd2ac642a12b28c7d28a5a4c147` zachował pierwszy fragment.
Rzeczywiste preview wykazało jeszcze brak zamkniętej trasy w
`just_storage_shell.sh`, nieprawidłowy import resolvera oraz różnicę pomiędzy
ścieżkami hosta i aliasami bindów Docker Desktop. Trasa jest teraz jawna przed
hostowym preflight; regresja wykonuje pełną powłokę na prywatnym fixture.
Wybrany source/state są potwierdzane istniejącą funkcją samefile. Dla żywych
aliasów podkatalogów kernelowe TARGET/FSROOT i inode muszą dowodzić rozłączności.
Stary runner Windows pozostaje nietknięty: dwa jego bindy zostały sprawdzone
natywnym, odczytowym dowodem stałego NTFS/ReFS bez reparse ancestors.

Pełny final preview requestu
`5dfa89641cca925359bfdafadb44a566086b06356a869dc55c83338b83d2588d`
przeszedł: 15 919 plików, 537 825 914 B, snapshot
`a7def36ae039208a98f6bce55f254afab818bf407528c38af8312765e5fceb41`.
Ledger SHA: `ba6628a5d510d66e40dff31888a68730f0d09e40aa3ef2cdf8ef9638d1e85d8a`.
Nie uruchomiono usług ani Solve.

Apply tego requestu zatrzymał się po publikacji markera, przed certyfikatem.
Przyczyną był błąd nowego kodu: canonical archive sortował klucze candidate dict,
a publisher serializował dict zamiast przypiętych candidate_raw. Semantycznie
zmieniły się tylko host_device i restart_verified, ale raw readback prawidłowo
odmówił kontynuacji. Certyfikat zachował oryginalny SHA
`b9dfce5d6be9ed857b8468f27fcb8be99fe3ad9674e61ca0e3d46f4d7f116c6f`;
marker ma dokładny archive-order SHA
`48ceccfaf51b515b7d48e896f77e502f21645e48d60f29e1dd5402c5f9e1f089`.
Docelowe candidate_raw mają SHA
`954b615bd9006972afffd7405209c37b9d91acdcbfa752b591659d4f66f8ab62`.

Publisher używa teraz dokładnych candidate_raw; bound certificate odtwarza
kolejność z tych samych bajtów. Osobny request
`fullmag.docker-linux-device-readmission.v2` wymaga SHA starego requestu,
oryginalnego przygotowania oraz dokładnego deterministycznego wariantu markera.
Boot/engine/container/storage/native pins pozostają identyczne. Archiwum jest
kopiowane jako surowe bytes; normalizacja markera musi osiągnąć zwykłą fazę
marker-published przed zapisem certyfikatu. V1 i domyślne wywołania core nadal
odrzucają archive-order marker; nie ma ogólnej równoważności JSON.

Końcowe 28 regresji interpretowanych: PASS, zero failures/errors/skips.
Obejmują rzeczywiste canonical archive → restore → publish, jawne wznowienie
częściowej publikacji i odmowę compact/foreign/reversed bytes oraz błędnych CAS
lub zmienionych authority pins. Niezależny review: zero Required po poprawkach.
Dowody: `verification/linux-native-readmission-20261028/v2-source-tests.json`
i `v2-source-tests.log`. Nie kompilowano lokalnie testów Rust.

V2 preview i apply wykonano poprawnie z commita
`1df80cd630e6f7dd58fa8b3c3ddb9aaa9af3b2c3`, przez zarządzaną receptę just.
Request SHA256: `95dc7f5d476f943e63fa011f9829a404e2ff0cbb27a22bf181443c874ac49fa5`.
Wynik: **prepared-not-admitted**, `namespace_admitted=false`.
Niezależna weryfikacja końcowa potwierdziła:

- certyfikat i marker mają dokładnie docelowe bytes/SHA `954b615b…`;
- zmieniły się wyłącznie host_device i restart_verified;
- inode i metadane certyfikatu bind-mountu zostały zachowane;
- probe, sentinel i restart pozostają identyczne;
- wszystkie 15 919 plików / 537 825 914 B i ledger mają te same hashe jak
  przed nieudaną próbą i przed wznowieniem;
- natywne OWNER, LAUNCH i process-tree pozostają identyczne;
- obie usługi pozostały w dokładnie tym samym stopped state, active nie istnieje;
- plik FMS użytkownika pozostał identyczny; brak nowego Solve.

Dowody w prywatnym control volume:
`verification/linux-native-readmission-20261028/v2-preview-preservation.json`,
`v2-apply.log` oraz `final-verification.json`. Oryginalny request, przygotowanie
z surowymi bajtami i historia nieudanej próby pozostają zachowane.

Storage nie jest jeszcze namespace-admitted. Nadal wymagane: nowy build w tym
samym backendzie, rzeczywisty storage probe tej inkarnacji, pełne native v4
mixed-history recovery oraz odbiór H w UI. Rzeczywisty kod starego obrazu różni
się od checkoutu: backend_dev.py SHA `dcea3be09d4be564b406eb9c3287b0ae642c09baeb8aad1fc4286fe1158e9ce2`,
entrypoint.py SHA `55a97db9c023a4324695364a030464f5be2cd67d09593333b17add0e862d300c`.
Sprawdzony kod obrazu publikuje pakiet przed Linux admission i cgroup gate;
nie można zastąpić tej weryfikacji samym odczytem nowego checkoutu.
