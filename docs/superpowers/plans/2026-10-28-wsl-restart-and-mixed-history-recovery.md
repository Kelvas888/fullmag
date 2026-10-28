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
