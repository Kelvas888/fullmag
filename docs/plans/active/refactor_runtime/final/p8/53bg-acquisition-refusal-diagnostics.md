# P8-53BG — diagnostyka odmowy acquisition

Stan 13.10.2026: **OPEN**. P8-53BE oraz publiczny restart nie są zamknięte.

Aktualny checkpoint: produkcyjny build C zakończony PASS (manifest
`7e9039806e8ce9046cd26c816bcb9d0727e93ea515d59482dad0eb21f82130d7`),
archiwizacja w sesji 52054 nadal aktywna. Restore/Compute NOT VERIFIED.
Sekcje poniżej stanowią chronologiczny dziennik; wcześniejsze określenia
„żywa” lub „NOT VERIFIED” opisują stan w chwili danego wpisu. Aktualne
rozstrzygnięcia i pełne hashe są w końcowych wpisach.

## Dowody i granice diagnozy

Receipt `523affb9b5dd4a13820b33e52171b550` zachował odmowę acquisition
po rzeczywistym przygotowaniu Grid zakończonym normalnym wait z kodem 0.
Odczyt statusu starego API wykazał `awaiting_command`, brak run oraz
`connectivity=disconnected`. Wszystkie 20 procesów dowodowych miało
terminalny wait; odmowa pozostaje błędem próby, nie sukcesem restartu.

Log `workspace-browser-fixture/native.stderr.log` tej samej próby zawiera:
`scratch observer identity unavailable: API source/contract mismatch before native service attach`.
To potwierdza brak dołączenia obserwatora w próbie A→B. Nie wolno omijać
kontroli source/contract ani traktować nowego API jako zgodnego ze starym.

Bieżący `main.rs::sync_current_live_frame_update` zapisuje heartbeat po
zaakceptowanej publikacji, także metadata-only Grid. `status.rs` pogarsza
stan po 15 s i przechodzi do disconnected po 45 s od ostatniej publikacji.
Jednorazowe przygotowanie Grid nie jest trwałym runnerem. To wskazuje
problem semantyki liveness, ale nie dowodzi pierwszej bramki odmowy:
acquisition sprawdza mesh workspace przed connectivity.

## Ograniczona zmiana źródeł

W `development_owner_control.rs` rozdzielono błąd admission oraz timeout.
Po uwierzytelnieniu lokalny log zawiera status, kod i komunikat walidatora;
timeout ma osobny stały komunikat. Nie zapisuje sceny ani dokumentu.
Obie gałęzie nadal kończą się istniejącym `reject(stream)`; nie zmieniono
formatu wire, admission, retry, blokad, source fencing ani handoff.

`git diff --check`: PASS. Native kompilacja i runtime tej diagnostyki:
**NOT VERIFIED** do odczytu terminalnego wyniku nowego buildu i reprodukcji.
Nie uruchomiono kompilacji Rust unit tests.

## Następny krok

Zarządzany `just windows-workspace-build dev dev 3258 true` uruchomiono
na lokalnym storage, bez startu UI. Przy ostatniej obserwacji czekał na
hostową blokadę ciężkich buildów. Istniał aktywny łańcuch procesów buildu
worktree `multi-project-hpc-r2-20261005`; nie wyprowadzono z tego właściciela
czatu i nie zatrzymano procesów. Nie tworzyć drugiego targetu ani omijać locka.

Po terminalnym buildzie przygotować zweryfikowany pakiet właściciela
z diagnostyką i odtworzyć Grid→acquisition, zachowując zgodność źródeł.
Oddzielić odmowę pipeline, brak trwałego runnera i odmowę source/contract.
Zmiana liveness musi zachować wykrywanie utraty rzeczywistego runnera;
ustawienie sztucznego `connected` lub pominięcie bramki nie jest naprawą.

## Weryfikacja przechwytywania danych — 13.10.2026

`ProofBridge.capture_before` pobiera teraz status i istniejący zasób
`/v2/sessions/current/meshing/semantics`, pomiędzy dwoma odczytami dokładnego
scope API/sesji. Odrzuca zmianę scope, status innej sesji i zmianę sceny
w trakcie odczytu. Zapisuje `workspace_browser_before` do receipt natychmiast,
przed wysłaniem żądania restartu. Stan disconnected lub aktywny pipeline
pozostaje dowodem; obserwacja nie udziela admission.

Nowe dwa testy w `test_windows_development_admission_observation.py`
potwierdzają zachowanie odmownych stanów oraz odrzucenie danych przekraczających
granicę sesji. Zostały włączone do source identity zarządzanej bramki.
Red przed implementacją: brak `read_admission_observation`; po implementacji
dwa testy PASS. Managed `just verify-windows-development-handoff`:
**160 tests, 0 skipped, exit 0**; receipt
`0a37a98b87c54b3688586977185a1e0b`, source SHA
`cc7c084f3b4d9d3aa3d5bbf5ec9c1423b6217700f69af1b2db1b4e00d7a50bda`.

Zakres tej bramki to `test_*development_*.py`; nie obejmuje całego starszego
`test_windows_workspace_browser.py`. Jego oddzielny przebieg podczas red
ujawnił także istniejące awarie testów frozen-native gate (walidacja scope
przed resolverem oraz wejście z fikcyjnym katalogiem). Nie naprawiano ich
przez osłabienie produkcyjnego preflight; pełna bramka tego pliku pozostaje
FAIL, a native/browser kwalifikacja nadal NOT VERIFIED.

Dwie próby managed native build zakończyły bounded wait przed kompilacją
(recipe raportuje exit 2). Ostatnia sesja narzędzia `83795` jest terminalna.
Aktualna obserwacja potwierdziła nadal aktywny obcy proces wrappera buildu;
brak Cargo w pojedynczym odczycie nie był dowodem zwolnienia zasobu.
Nie uruchomiono trzeciej równoległej próby ani nie zatrzymano obcego procesu.

## Zamknięcie regresji starszego testu frozen scope

Po reprodukcji ustalono, że obie raportowane awarie pochodziły z jednego
nieaktualnego testu. Produkcyjny weryfikator dopuszcza frozen-native ID
z `project_document_only`, co wykorzystuje istniejąca recepta
`archive-windows-native-build`. Test nadal oczekiwał odmowy i przez mock
resolvera dochodził do fikcyjnego katalogu. Zaktualizowano wyłącznie test:
oba legalne scope muszą dojść do preflight, a nielegalne kombinacje nadal
muszą zostać odrzucone przed wywołaniem resolvera. Produkcyjnego weryfikatora
ani jego preflight nie zmieniono w tym przyroście.

`python -B -m unittest discover -s scripts -p test_windows_workspace_browser.py`:
**20 tests PASS**, exit 0. Ta aktualna weryfikacja zastępuje wcześniejszy FAIL
tego pliku; nie jest dowodem browser/runtime. Managed 160-test receipt powyżej
pozostaje oddzielnym wynikiem i nie obejmuje tych 20 testów.

Poprawka starszego testu i checkpoint zostały zapisane na remote master w
`f758f84404713778e1c1f2c0762c83c689bd144a`; exact remote SHA potwierdzono
przez `git ls-remote`. Runtime diagnostyki oraz rozszerzony verifier nadal
pozostają WIP poza tym commitem.

Dodatkowa regresja before-capture sprawdza faktyczny atomowy zapis receipt
w prywatnym katalogu testu oraz brak zapisu i brak `before` po zmianie sceny.
Najnowszy managed wynik: **161 tests PASS**, 0 skipped, exit 0, receipt
`59a32ad19aba4d5cbd8119492174955a`, source SHA
`714f0f64df9c574a0cb699e4c88b13dd219d6f18311e983b2aef1e9492321cd0`.
Nie dodawano kolejnego procesu symulacji ani Rust unit builda.

Po rewalidacji braku poprzedniego łańcucha procesów managed build uzyskał
zasób i rozpoczął capture sources. Aktywna sesja narzędzia: `30784`; log
`native-build-0bfa7a594b1d465592dbbcb8f22488db.log` w istniejącym profilu
`windows-native-fdm-cpu-dev`. Nie uruchamiać duplikatu po samym timeout
obserwacji. Wynik tej kompilacji pozostaje niepotwierdzony do terminalnego
receipt; UI użytkownika na 3197 nie restartowano.

Aktualna obserwacja tej samej sesji potwierdziła snapshot
`561e1f9bde61d2fcda2a39bdf67ba1961ab0585f59292984e78e35d02f1a9411`.
Pliki diagnostyki są byte-equal z bieżącym checkoutem:

- `development_owner_control.rs`:
  `d58245a90b05905ed1942daa7b6009ed63a2789a56821bd5e4410407b9102ab5`;
- `verify_workspace_browser.py`:
  `de890fbc7b6e29ad4225ded9fd4e6ff9593796f751ebe99b3caf4bd781b6d767`.

Build przygotował zależności frontendu i pakiet Python. Przy ostatniej
obserwacji działał własny `compiler_inputs.py materialize` (PID 11724,
rodzic launcher PID 128584); brak Cargo w tym etapie nie oznacza terminalnego
buildu. Nie uruchomiono duplikatu. Dopiero terminalny wynik sesji 30784
i receipt pozwolą zaliczyć kompilację diagnostyki.

## Kompilacja diagnostyki i review źródeł

W tej samej managed sesji 30784 kompilacja CLI/API zakończyła się
`Finished backend-dev` po 3m21s. Potwierdza to kompilowalność nowej diagnostyki
w byte-equal frozen source, bez kompilacji unit tests. Cały build nadal
buduje desktop i nie ma jeszcze potwierdzonego końcowego receipt.

Niezależny bounded review nowego match acquisition, observation helper oraz
before-capture: brak actionable findings. Sprawdzono uwierzytelnienie przed
logiem, stałe komunikaty bez sekretów/dokumentu, zachowanie wire rejection,
zachowanie odmownych stanów oraz odrzucenie drift i fail-closed odpowiedź.
Review dotyczy źródeł; nie potwierdza runtime ani restartu.

Końcowy wynik tego managed buildu: **PASS, exit 0**, `build-status.json`
ma `state=completed`, zakończenie `2026-10-13T09:08:52.885835+00:00`.
Desktop zakończył kompilację po 1m27s. `verified_build_identity` zakończył
pełną walidację pakietu kodem 0:

- manifest SHA:
  `1b7dc8aa1c7f1b0362432662b0f736d0f674a70d0c1cc67701c629c21eb43dc3`;
- backend source SHA:
  `744872bb1acea4d9e0ec73534ad16b69df77f2e070b0f0699821eff72afb7e56`;
- API EXE SHA:
  `e64cd01a9ca4bcbbe43f4cc67043e8b19ff4794c721addb4e32721789075e177`;
- CLI EXE SHA:
  `465a49890fafeb19ea6dc186e05db4fb87c792ec48923977516a4befbdd7fb09`.

Te wyniki zamykają kompilację i integralność pakietu diagnostyki. Nie
zamykają acquisition, restore, Compute ani publicznego restartu. Następny
krok: managed frozen project-document proof i archiwizacja tego pakietu
przed próbą restartu.

Diagnostyka i powyższe dowody są na remote master w commicie
`499c7c902b40ad7a69e3e03108f26caecb28d3ca` (exact remote SHA potwierdzony).
Do tego commita włączono wyłącznie `development_owner_control.rs` i ten
checkpoint. Rozszerzony verifier i nowe testy observation pozostają WIP.

Uruchomiono `just archive-windows-native-build` z dokładnym manifest SHA
`1b7dc8aa1c7f1b0362432662b0f736d0f674a70d0c1cc67701c629c21eb43dc3`.
Ostatnia obserwacja: sesja narzędzia `51052` nadal aktywna, proces managed
verifier PID 134804 potwierdzony. Brak terminalnego receipt archiwizacji;
nie traktować rozpoczęcia zadania jako PASS ani uruchamiać duplikatu.

## Terminalny wynik archiwizacji i następna diagnoza

Sesja 51052 zakończyła się kodem 0. Receipt
`4b12dce356224b99aae4b099d37dfa7a` w profilu
`development-backend-api-checks` zawiera **33 kontrole PASS** oraz archiwum
`32a54ae2137a49dca229728dd4b80206`. Pakiet ma wskazany wyżej manifest
`1b7dc8aa1c7f1b0362432662b0f736d0f674a70d0c1cc67701c629c21eb43dc3`.
Wszystkie procesy próby zostały zebrane; kontrolowane zakończenie API
nie jest dowodem wykonania fizyki. Pakiet stanowi nową bazę A.

W źródłach próby A→B znaleziono niespójność: API przed restartem pochodziło
z zapieczętowanego A, a scratch authoring child z `current_exe()` launchera B.
Kontrola compiled identity przy przyłączaniu odrzuca taką parę.
Próba wybiera teraz `bin/fullmag.exe` z tego samego A co API, po pełnej
walidacji pakietu przez istniejący helper. Nie zmieniono kontroli API ani
protokołu acquisition. Po restarcie istniejąca ścieżka nadal wybiera runtime
z pakietu kandydata B. Kompilacja i rzeczywisty restart tej poprawki pozostają
**NOT VERIFIED** do nowego terminalnego buildu i próby browserowej.

Managed build B uruchomiono przez `just windows-workspace-build dev dev 3258 true`,
sesja `54070`, log `native-build-26e3189e6e4044c195418966ea05f280.log`.
Pierwsza obserwacja potwierdza capture sources; brak terminalnego wyniku.
Niezależny bounded review zmiany wyboru EXE: brak actionable findings,
wyłącznie dowód źródłowy. Wyprowadzona ścieżka jest w uprzednio zweryfikowanym
pakiecie A; źródłowa kontrola compiled identity pozostaje obowiązująca.

Build B zakończył się **PASS, exit 0**: `build-status.json` ma
`state=completed`, czas zakończenia `2026-10-13T09:35:39.303526+00:00`.
CLI/API: 1m53s, desktop: 51,59s. Snapshot
`0bc3b5b3792c85e89b47569dac3ece2bddf9ecdde06e3425254318f7456cd784`
zawiera byte-equal plik próby, SHA
`41ec7264a6f6b32303ae34875e745610ccdcb11a6254c20d3a7b9b475eb7dcf1`.
Manifest B:
`099bf10381fb7b65716ab085b021d03b8d43a95f0732116fe8b4ac8f431d046e`,
backend source B:
`ab5a14e95b2a62ea0a28de0e7d864c543f60cc32dd31755f8af0e3211285e562`.
Kompilacja nie obejmowała unit tests. Próba zarządzana
`just verify-windows-development-workspace-browser 32a54ae2137a49dca229728dd4b80206`
jest aktywna w sesji `75826`; verifier PID 135048 potwierdzono jako żywy.
Nie ma jeszcze wyniku restartu; UI użytkownika 3197 pozostaje nietknięte.

## Rzeczywisty Grid i odmowa po renderze kanonicznego skryptu

Próba `9ee08c8889f7486eab618f288474a90f` wystartowała na 3258 z API
`b59b4a3d-395b-4688-adae-59833c838e64`, port 56181. Nową pustą sesję
utworzono w UI; scenę odtworzono normalnym `replace_scene` z kontrolą
rewizji z receipt `52a8ef28d5f44de689a58879ef962ee9`. Osobny plik
`scene-replay-evidence.json` zapisuje hash payloadu i ACK. Wyniki i TEMP
tej sesji skierowano do jej własnego katalogu próby, bez zapamiętywania
ustawień dla innych sesji.

Grid uruchomiony z UI zrealizował 4×4×1 komórek, 16 aktywnych. Log
potwierdza normalny exit 0 scratch child i nie zawiera poprzedniego
`API source/contract mismatch`. UI pokazało completed command/mesh oraz
cztery FDM pipeline phases done. Before-capture utrwalił scenę, dirty
project document i rzeczywisty admission observation przed odpowiedzią.
Canvas przed restartem: visible, context_lost=false, drawing buffer 610×281.

Restart z UI został odrzucony. Nowa diagnostyka A potwierdziła:
`status=409 Conflict`, `development_restart_not_safe`,
`only an idle scratch workspace or terminal run can be captured`.
Przyczynę zawężono do producer/consumer kontraktu: po kanonicznym renderze
`script.rs::sync_current_live_script_with_request` zapisuje `scene_document.py`
do `session.script_path` uprzednio pustego scratch workspace, natomiast
`development_restart.rs::is_idle_scratch` wymaga pustego pola. Status przed
restartem: solver idle, run null, generated script pod zarządzanym workspace;
lifecycle awaiting_command/degraded/forbidden. Connectivity jest osobną
następną bramką i nie została jeszcze rozstrzygnięta.

Nie rozszerzano admission ani nie wykonywano ponownego requestu po odmowie.
Restore i Compute pozostają **NOT VERIFIED**. Sesja narzędzia 75826 pozostaje
żywa; nie oznaczać receipt jako terminalnego ani uruchamiać duplikatu.
Następny krok: uzgodnić producer/consumer rozróżnienie UI scratch oraz
wygenerowanego artefaktu Python, zachowując kontrolę bezczynności i procesu.

Przygotowano WIP poprawkę `is_idle_scratch`: obok pustej ścieżki dopuszcza
wyłącznie dokładne `<state.current_workspace_root>/scene_document.py`.
Nie zastosowano ogólnego `script_origin=generated`, ponieważ ten predykat
obejmuje szersze zarządzane katalogi. Producer nadal zapisuje ścieżkę potrzebną
przez GET źródła i status. Pozostałe warunki UI/trusted restore, scene identity,
braku run/stage/live, idle runtime oraz wszystkie bramki acquisition pozostają.

Dodano źródło regresji obejmujące pełne `acquire_workspace_for_restart`:
kanoniczny artefakt zachowuje scratch bez run ID; inne zarządzane ścieżki,
busy oraz disconnected są odrzucane. **Rust test NOT RUN/NOT COMPILED** zgodnie
z obowiązującym zakazem. Bounded review: brak actionable findings, źródłowo.
Ta poprawka API powstała po buildzie B i nie jest nim zweryfikowana.
Wymaga kolejnego production buildu i archiwum A zawierającego poprawiony
guard przed następną próbą A→B; nie przypisywać jej dowodów poprzedniego pakietu.

Nowy build poprawki API, sesja `82968`, oczekuje w bounded preflight na
zasób zajęty przez własną próbę browserową `75826`. To nie jest rozpoczęta
kompilacja; nie uruchamiać duplikatu ani usuwać locka. Po wygaśnięciu
bounded próby trzeba potwierdzić jej terminalny receipt i custody procesów,
a następnie dopiero ponowić build po terminalnym wyniku oczekiwania.
UI `Check restart` potwierdziło failed restart i odblokowało publication
host (`paused=false`), zachowując scenę i dirty document. Nie jest to restore.

Oczekiwanie buildu 82968 zakończyło się terminalnie: launcher exit 2,
recipe exit 1, `Bounded wait expired before starting`. Kompilacji nie
rozpoczęto. Próba 75826 nadal pozostaje żywa; nie mylić odmowy admission
z terminalnością całego verifiera. Poprawka API pozostaje niezweryfikowana
przez build/runtime, bez commitowania jako zamkniętego etapu.

## Kontynuacja: terminalność próby po znanym wyniku

Poprzedni przyrost był postępem: production build i Grid dały nowe dowody,
a poprawka klasyfikacji scratch zmieniła źródła. Nie jest to blocker
zewnętrzny; istnieje własna ograniczona czasowo próba z żywą sesją 75826.

Dodano w prywatnym `development_workspace_probe.rs` odczyt terminalnego
wyniku przez istniejące `read_pending_request` i `read_result`: wiązanie
original API, generation, immutable slot, request hash i status token
pozostaje w istniejącym transporcie. Failed kończy failed proof, Unknown
pozostaje unknown, a Ready nie jest utożsamiane z restore. Błąd obserwacji
również pozostaje unknown. Każdy taki wynik przechodzi przez istniejący
`finalize_outcome`, bez skrótu omijającego custody.

Źródło regresji publikuje prawdziwe lokalne rekordy request/result i obejmuje
brak result, obcą generation oraz Failed/Unknown/Ready. Rust tests **NOT RUN**,
bez kompilowania. Zainstalowany rustfmt sparsował i sformatował dwa własne
zmienione pliki, exit 0; `git diff --check` PASS. Source review observera
terminalnego wyniku: brak actionable findings. Produkcyjna kompilacja i
runtime tego observera pozostają **NOT VERIFIED**.

Osobno trwa diagnoza kolejnej bramki: pojedynczy Grid-only snapshot, bez
run/live/stage, uruchamia obecnie heartbeat watchdog w API. Nie zmieniono
`validate_connectivity` ani nie dodano sztucznego heartbeat. Przed nowym
buildem należy rozstrzygnąć producer-side semantykę metadata publication.

## Terminalna próba i wąska korekta heartbeat

Receipt `9ee08c8889f7486eab618f288474a90f` zakończył się 13.10.2026
o `10:07:15.372723+00:00`: failed, exit 1. Sesja narzędzia 75826
potwierdziła terminalny wynik. Wszystkie procesy w receipt mają
`waited=true`; API A exit 1, helpery exit 0, rzeczywisty Grid child exit 0.
Brak API B i restore. Zachowujemy dowód Grid, nie kwalifikujemy restartu.

W `main.rs` przygotowano wyłączenie naliczania runner heartbeat tylko dla
dokładnego mesh-only Snapshot (mesh_workspace i opcjonalny engine_log,
bez manifestu/session status/metadata/run/stage/preparation/live/pól/profilu
solvera i bez flag mutacji pól). Wszystkie pozostałe Snapshot i wszystkie
typed Session/Runtime/Scalars/Fields zachowują dotychczasowe zachowanie;
dedykowany heartbeat endpoint oraz connectivity guard pozostają bez zmian.
To odpowiada jednorazowemu Grid producerowi, który publikuje i kończy proces,
zamiast udawać obecność resident solvera. Review diagnozy wskazało, że
wyłączenie wszystkich Session frames byłoby zbyt szerokie.

Dodano źródło regresji dla mesh-only oraz stateful/field-mutating payloadów.
Rust tests NOT RUN/NOT COMPILED. Zainstalowany rustfmt sparsował `main.rs`
bez nadpisywania cudzych zmian, exit 0; scoped diff check PASS.
Poprawki scratch admission, terminal-result observera i heartbeat wymagają
nowego production buildu oraz rzeczywistej próby runtime.

Source review implementacji heartbeat: brak actionable findings. Build
sesja `75802`, log `native-build-56e4131da7094565adc143e0f71375a1.log`,
utrwalił snapshot
`358167a3aba904d31d9f98fd3dcba1365b0ee881e21d4241cb1b22c3dd40a226`.
Backend source SHA:
`a5b1072211e458335e303abc7c38382a7c20997b65e73a33e94abb50362167a0`;
inventory SHA:
`02a84e139edebef2817d8c3549acf03317f5fc6d51e71e859214b5b10a01f63b`.
Trzy pliki własnych poprawek porównano bajtowo ze snapshotem: zgodne.
To potwierdza wejścia, nie wynik kompilacji. Następny krok: odebrać ten
sam żywy build, zweryfikować pakiet, archiwum poprawionego owner API,
a następnie wykonać odrębną próbę Grid/restart/restore/Compute.

Po utrwaleniu snapshotu C przygotowano dodatkową korektę diagnostyki
prywatnego probe: terminalny stderr zachowuje `ProbeOutcome` reason
oddzielnie od statusu ustalonego przez final custody. Nie zmieniono formatu
result, klasyfikacji Failed/Unknown ani cleanup. Wcześniej stała przyczyna
była gubiona w ogólnym komunikacie o braku pass, co utrudniało rozróżnienie
refusal, timeout i niepotwierdzonej obserwacji. To rzeczywista zmiana kolejnego
kandydata D; nie przypisywać jej dowodów buildu C. Źródło regresji dodane,
unit tests NOT RUN; rustfmt i scoped diff check PASS.

Review dodatkowej diagnostyki nie wykazał actionable findings: status
pozostaje custody-qualified, reason jest statycznym kodem bez payloadów.
Build C potwierdził produkcyjną kompilację CLI/API (1m03s) i desktopu
(52.36s). Sesja 75802 pozostaje jednak żywa podczas finalizacji pakietu;
manifest w chwili kontroli nadal wskazywał poprzedni build
`099bf10381fb7b65716ab085b021d03b8d43a95f0732116fe8b4ac8f431d046e`.
Nie archiwizować go jako C ani przypisywać poprawkom starego manifestu.
Odbiór terminalnego receipt i nowego manifestu jest nadal wymagany.

Build C następnie zakończył się terminalnie, sesja 75802 exit 0. Nowy
manifest SHA:
`7e9039806e8ce9046cd26c816bcb9d0727e93ea515d59482dad0eb21f82130d7`;
CLI EXE SHA:
`1710fd9e6b0c8283feb0b7604459e323b12b789c99c168200b13542cd8208ffa`;
API EXE SHA:
`36ef582a9871ce49db7f52ad216b87dff3df887f00a1c9cc4807ce496513f45e`.
Manifest wiąże wskazany snapshot C i backend source `a5b10722…`.
Uruchomiono `archive-windows-native-build` z pełnym manifest SHA, sesja
52054: oczekujemy odrębnego terminalnego dowodu archiwum przed kolejnym
buildem D. Kompilacja produkcyjna PASS; zachowanie po restore NOT VERIFIED.

Kanoniczny `windows-native-fdm-cpu-dev/build-status.json` potwierdził:
`completed`, exit 0, execution mode `windows-workspace-build`, worktree
`fullmag-0950f4dca4ffe38f`, start `10:11:20.199957+00:00`, koniec
`10:20:04.630417+00:00`, dokładny manifest C wskazany powyżej. Zachowano
ten sam resolver/profile/target/cache i TEMP na R:, bez buildu testów Rust.
