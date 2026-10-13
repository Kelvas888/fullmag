# P8-53BG — diagnostyka odmowy acquisition

Stan 13.10.2026: **OPEN**. P8-53BE oraz publiczny restart nie są zamknięte.

Aktualny checkpoint: produkcyjny build C zakończony PASS (manifest
`7e9039806e8ce9046cd26c816bcb9d0727e93ea515d59482dad0eb21f82130d7`),
archiwizacja C zakończona PASS (33 kontrole). Restore/Compute NOT VERIFIED.
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

## Archiwum C PASS i kolejny kandydat

Sesja 52054 zakończyła się kodem 0. Receipt
`b375b399786841888a5d07a55f0de293`: completed, 33 checks PASS,
wszystkie procesy waited, zakończenie `2026-10-13T10:24:36.265888+00:00`.
Archiwum owner A:
`17477dc817fa49aab39b8108b69967fd`, manifest C i hashe CLI/API jak wyżej.
Kontrole obejmowały project document, authoring i zachowanie archiwum;
nie obejmowały restartu, browser hydration ani wykonania fizyki.

Checkpoint dowodów zapisano i wypchnięto na master:
`becaf9e8f183b80413f02d181d5a56763e925c57`, tylko ten plik Markdown.
Źródła poprawek pozostają WIP do ich odrębnego zakresowego commita.
Uruchomiono kolejny managed build dla kandydata D, który zawiera dodatkową
diagnostykę statycznej przyczyny. Po jego terminalnym odbiorze użyć
archiwum `17477dc817fa49aab39b8108b69967fd` do pełnej próby browserowej.

Build D: żywa sesja `22425`, log
`native-build-373c1850ee1446e5a886f2b4fbffc89c.log`, managed recipe
`windows-workspace-build dev dev 3258 true`. Ostatnia obserwacja nadal
przygotowywała snapshot; nie zgłaszać kompilacji lub gotowego pakietu.
Osobny `git ls-remote origin refs/heads/master` potwierdził dokładnie
`becaf9e8f183b80413f02d181d5a56763e925c57` jako remote master.

## Odbiór D i rozpoczęcie próby browserowej

Sesja 22425 zakończyła się kodem 0. Kanoniczny build-status potwierdza
`completed`, execution mode `windows-workspace-build`, profil
`windows-native-fdm-cpu-dev`, zakończenie `2026-10-13T10:35:08.091950+00:00`.
Manifest D:
`e8d540e47135da58f44642047cd1efd4f214b8d6720b4521a1f2edc4c26225d1`.
CLI SHA `4261c2889befbb06bbd83cf1204c79f16fff2d2d6735315e7b67e4760fcd3df9`;
API SHA `9f2e732fc9bef10b986c5faa86c294e81c8652a2df2bd14566cfa8ac35abd7f6`.
Produkcyjny build CLI/API i desktopu PASS; testów jednostkowych Rust nie
kompilowano. Runtime/restore/Compute nie wynikają z tego dowodu.

Snapshot D `369ed852734c37e32cfc2884dd1e93be4a0f5e15f9db180876130c4a6694cc31`
zawiera także cudze zmiany `compute_resources.py`, `scene_document.py`,
`scene_document_ir.py` i `script_builder.py`. Nie cofano ich ani nie
przypisywano do własnego zadania. Odczytowe porównanie obydwu zamrożonych
wersji Python dla dokładnej sceny z receipt `9ee08c8889f7486eab618f288474a90f`
dało exit 0 i ten sam canonical builder SHA:
`b504110e7c9913508980598876d18de37d8dcaa2f4d537f364d345bf71bb191f`.
To dowód zgodności semantyki buildera tego fixture, nie wszystkich nowych
funkcji ComputeResources ani uruchomienia solvera.

Uruchomiono kanoniczny `verify-windows-development-workspace-browser`
z archiwum A `17477dc817fa49aab39b8108b69967fd`; sesja 76723,
receipt `f6765443de694de9899daef400434b56`, własny port 3258.
W chwili zapisu proces jest żywy i przygotowuje runtime. Nie zgłaszać PASS
próby przed terminalnym receipt oraz właściwym dowodem browser/Compute.

## Rzeczywisty restore C→D i kolejna ujawniona blokada Compute

W próbie `f6765443de694de9899daef400434b56` scoped frontend typecheck/lint
zakończyły się kodem 0. Własna karta testowa 5, port 3258; nie restartowano
sesji użytkownika na 3197. Scenę regresyjną odtworzono przez revision-checked
`replace_scene`, zachowując świeżą tożsamość oraz własne output/temp.
Payload i ACK zapisane w `scene-replay-evidence.json` przy receipt.

Pierwszy Grid: `fm-7db98dcb-b0be-4a6a-b789-ed90bcdcf945`, dziecko 117632,
waited, exit 0, kill_requested=false. Status rzeczywistego API pozostał
`connected`, `awaiting_command`, solver idle, run null. Acquisition i restart
następnie przeszły; stare API 89924 waited exit 0, wszyscy sześciu pomocnicy
waited exit 0. Nowe API 132124:
`731cf156-1956-40cd-b665-451ca497b70b`, sesja
`session-18de10e63f0c029c0002041c`, scope
`731cf156-1956-40cd-b665-451ca497b70b:1`.

Po normalnym `Check restart` UI zmieniło pin, generation=1, paused=false.
Dokument `project-03ede1ec4c6a45d48aec5bbeaf221baf`, revision=2, dirty=true
zachował hash archiwum
`f78ac01f600dcc0855051e71d65b10c486331f229ebebf3c7b538eb4b5ab22dc`
i sceny `972af012da6f17a438220ed6e4c85f03f3b91612fc96c863085417dcba369a40`.
Obiekt, region i materiał pozostały. Canvas widoczny, context_lost=false,
drawing buffer 629×297.

Drugi rzeczywisty Grid: `fm-bfd1f0d4-16e8-4ac0-b31b-af0cacd1513f`,
dziecko 133384 waited exit 0, kill_requested=false, 4×4×1 i 16 aktywnych
komórek; ledger completed. Normalny przycisk Compute Study zakończył się
odmową `Mesh out of date - build mesh before compute` w logu komend UI.
Run pozostał null, brak dziecka Compute. Nie przedstawiać samego enabled
przycisku Close/Finish ani udanego Grid jako wykonania solvera.

Diagnoza źródeł: `prepare_fdm_grid_refresh` publikuje `source_scene_revision`
w historii, ale pomija ją w `last_build_summary`. API
`successful_mesh_build_source_scene_revision` czyta podsumowanie; bez tego
pola nie uruchamia `clear_mesh_dirty_tags_for_built_scene`. Przy `mesh:dirty`
`geometry_blocks_solver_run` poprawnie odrzuca Compute. Dodano brakujące pole
w podsumowaniu z tej samej intencji `opts`, bez osłabienia guardu rewizji.
Scoped diff check PASS; poprawka nie jest jeszcze zbudowana ani sprawdzona
w runtime. P8-53BE pozostaje OPEN. Zrzut:
`p8-53bg-restored-compute-refusal.png`.

Sesja 76723 w chwili zapisu nadal żywa; API D i frontend są własnymi zasobami
tej próby. Brak terminalnego receipt — custody całej próby nadal pending.
Nie rozpoczynać kopii tej próby ani ogłaszać całości PASS. Następny krok:
kontrolowane zakończenie własnej próby, build poprawki i ponowny rzeczywisty
Grid→Compute po restore.

## Przerwanie próby — brak potwierdzonego terminalnego custody

Sesja narzędzia 76723 zakończyła się kodem 1, pozostawiając żywy verifier
Python 129672. Po kontroli exact command line i bundle A zamknięto ten
własny verifier. CLI 120716 otrzymał EOF; późniejsza kontrola wykazała brak
CLI i API 132124, ale nie odzyskano ich exit codes ani terminalnej ramki.
Zweryfikowano i zamknięto własne procesy Next 111552/120416. Porty 3258
i 57867 nie nasłuchują; 3197 nie zmieniano.

Oryginalnego receipt nie nadpisano. Oddzielny `interruption-recovery.json`
przy receipt rejestruje niepotwierdzoną oryginalną custody i późniejszy
brak procesów. To nie jest PASS cleanup ani restore→Compute.

Archiwizacja D przez `archive-windows-native-build`: sesja 64968,
receipt `538ef5c0774846e8abe4e82fc788ce62`, ostatnia obserwacja running.
Po jej terminalnym odbiorze przygotować build brakującej rewizji w
`last_build_summary`. Następna regresja nadal wymaga rzeczywistego solvera,
zgodnej sceny i provenance oraz terminalnej kontroli procesów.

Archiwizacja D zakończyła się terminalnie: sesja 64968 exit 0, receipt
`538ef5c0774846e8abe4e82fc788ce62`, completed, 33 checks PASS,
koniec `2026-10-13T12:58:45.649085+02:00`. Brak procesów z waited=false.
Archiwum `da3fb23a4fdf49b380ffcdeebfd7049e` zawiera zweryfikowane 13 plików,
CLI/API i manifest D wskazane wyżej. To archiwum jest punktem wyjścia A
dla kolejnej próby, nie dowodem Compute.

Rozpoczęto managed build E z poprawką rewizji Grid:
`windows-workspace-build dev dev 3258 true`, sesja 82028, log
`native-build-30c25ea415ac46958655b4613ab7d5fd.log`. Nie uruchamiano raw
Cargo ani kompilacji testów jednostkowych. Terminalny manifest i ponowna
regresja browser/runtime pozostają wymagane przed zamknięciem poprawki.

Preflight E zarejestrował aktualny wspólny HEAD
`9112d38880f45ff85db2bbd82dd5da67b778cb40` (merge PR #150), a nie
wcześniejszy `becaf9e8…`. Współdzielony index w chwili kontroli zawiera
liczne zmiany innych prac oraz omawianą poprawkę i starszy checkpoint.
Nie stage'owano, nie resetowano indexu ani nie wykonano commita tego zbioru.
Nowe dopiski checkpointu są lokalne. Build musi być oceniany według własnego
utrwalonego snapshotu; nie przypisywać mu automatycznie dowodów wcześniejszych
HEAD-ów lub nowego bieżącego checkoutu.

E utrwalił snapshot
`943032b59eb9ee78abd1a0e189d4d326616114aa34577fb73a8c69954ac9bf72`.
Odczyt tego snapshotu potwierdził pole `source_scene_revision` w
`prepare_fdm_grid_refresh.last_build_summary`; SHA pliku
`70bb1440c682691a743d0ba2305e6fb92524b469f201351e523e65d8de17ffc8`.
Wersja E `0.1.0-dev.20261013.g9112d38880f4.dirty.s8134b7f3f1ad+9782`.
Zależności pnpm przygotowane z cache, frozen lockfile, exit bez błędu;
ostatnia obserwacja sesji 82028 nadal running. Nie przypisywać tej obserwacji
terminalnego manifestu, udanej kompilacji ani wykonania solvera.

## E failed: nowy compute-node snapshot i poprawka ograniczenia Serde

Sesja 82028 zakończyła się exit 1. Kanoniczny build-status rejestruje
exit 1 i koniec `2026-10-13T11:07:29.717316+00:00`; Cargo exit 101.
Nie powstał zatwierdzony pakiet E ani dowód runtime dla rewizji Grid.
Zamrożony snapshot E zawierał nowy, niezacommitowany moduł
`fullmag-session/src/compute_node_snapshot.rs`. Kompilator zgłosił 12
E0277 dla `Reported<CpuQuota>`, `Reported<CpuTopology>`,
`Reported<GpuPartition>` i `Reported<GpuTopology>`: automatycznie wywiedzione
`Deserialize` wymagało `T: Default` przy opcjonalnym `last_known`.

Do bieżącego modułu dodano wyłącznie jawne Serde bound
`T: Deserialize<'de>` oraz źródłową regresję z typem bez Default. Test
sprawdza available, unavailable bez last_known, retained last_known oraz
odmowę available bez value. Zachowano resztę cudzej implementacji;
porównanie z zamrożonym E wykazuje tylko ten zakres. Rustfmt parser exit 0;
test Rust NOT COMPILED / NOT RUN zgodnie z obowiązującą regułą.

Powtórny managed build F: sesja 97293,
`windows-workspace-build dev dev 3258 true`, log
`native-build-4464a454f32449e28875128cbdfd85ce.log`.
Ostatnia obserwacja: żywy proces utrwala źródła. Archiwum D
`da3fb23a4fdf49b380ffcdeebfd7049e` pozostaje punktem wyjścia przyszłej
próby; build i restore→Compute nadal wymagają terminalnych dowodów.

Rozpoznano również brak wygodnego anulowania prywatnej próby z zachowaniem
jej terminalnego custody. W tym etapie nie zmieniono verifiera ani UI
anulowania; pierwszeństwo ma usunięcie konkretnej blokady kompilacji.

## F: potwierdzony snapshot i kontrolowane anulowanie prywatnej próby

Żywa sesja 97293 utrwaliła snapshot
`3d2d67766d66b7c3f6b778418057c50248561feb9c7e4f50905bde22e5f9fe1e`.
Odczyt zamrożonych plików potwierdził jawny bound Serde oraz
`source_scene_revision` w podsumowaniu Grid. Kompilacja przeszła moduł
fullmag-session i doszła do fullmag-cli/fullmag-api; terminalny wynik
całego builda pozostaje niepotwierdzony. Nie uruchomiono drugiego buildu.

Do prywatnego verifiera dodano `/cancel`: dokładny schema/nonce oraz
istniejąca kontrola origin, osobny event anulowania i odmowa finish po
anulowaniu. Pętla obserwatora przechodzi do istniejącego cleanup przez EOF,
z odbiorem terminalnych ramek i wyników procesów. Anulowanie nie ustawia
finished ani browser PASS, nie dotyczy publicznego UI i nie zabija sesji 3197.
22 interpretowane kontrole skryptu przeszły (exit 0), w tym błędny scope,
odmowa anulowania po finish i odmowa finish po anulowaniu. Diff check PASS.
Rzeczywista próba anulowania z procesami pozostaje NOT VERIFIED;
bramka restore→Compute nadal OPEN.

## F completed i nowa próba D→F

Sesja 97293 zakończyła się exit 0; build-status `completed`, zakończenie
`2026-10-13T11:22:38.801210+00:00`. Manifest F SHA256
`a3aaab8a14c82ceaf31cf9dd3f9faaf1475953cdf64a811c4efc793bdfd61e2f`
zweryfikowany bezpośrednio z pliku; backend source SHA256
`499ebdccf714fba3ff94fc2923b10bb3a8f0f9394e07a59f7f2ddcc04be9a1cd`.
CLI/API build 3m47s, desktop 1m12s. Jest to dowód produkcyjnej kompilacji,
nie wykonania Compute ani zamknięcia publicznego restartu.

Interpretowana regresja HTTP anulowania wykazała Windows connection reset
przy odmowie origin bez odbioru bounded request body. Handler odbiera teraz
body w istniejącym limicie przed oceną origin; odmowa nadal poprzedza parsing
i każdą mutację. 23/23 kontroli PASS, exit 0, w tym rzeczywisty lokalny
HTTP: obcy origin 409 bez cancel, właściwy origin 200 z cancel bez finish.
Nie zastępuje to terminalnego custody realnego native ownera.

Uruchomiono managed browser proof D→F: sesja 89785, receipt
`864d2e68606c4b1caa259f93e8556e22`, stan running. Stary owner D
`da3fb23a4fdf49b380ffcdeebfd7049e`. User workspace 3197 nietknięty.
Współdzielony checkout przeszedł na HEAD
`a227bea56dc94109edb6b72826d55e65e8e19e6d`; nie przypisywać temu HEAD
frozen builda F, którego recorded head pozostaje 9112d38880f4.

## D→F odmowa na typecheck przed browserem

Sesja 89785 terminal exit 1; recipe exit 2, receipt
`864d2e68606c4b1caa259f93e8556e22` failed. Typecheck exit 2:
trzy TS2339 (`failure_policy`) i jeden TS2367 (`stopped`) w
projectBatchResources.ts / ProjectBatchesSection.tsx. Każdy proces receipt
ma terminalny wait; CLI/API zakończyły się exit 1, helpery exit 0.
Próba nie doszła do rzeczywistej sceny/browsera ani Compute.

Backend ProjectBatchSummaryResource ma failure_policy, a session expansion
obsługuje Stopped; obecny generated OpenAPI JSON i types nie zawierają
tych elementów. Nie zmieniono guards ani ręcznie wygenerowanych typów.
Rozpoczęto managed `archive-windows-native-build` dla manifestu F,
sesja 41147, w celu uzyskania kanonicznego eksportu z receipt. Następnie
wymagana jest regeneracja i weryfikacja typów oraz nowy zgodny frozen
pakiet frontendu. Restore→Compute i publiczny restart pozostają OPEN.
