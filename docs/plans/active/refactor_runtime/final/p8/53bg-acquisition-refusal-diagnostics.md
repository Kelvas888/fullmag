# P8-53BG — diagnostyka odmowy acquisition

Stan 13.10.2026: **OPEN**. P8-53BE oraz publiczny restart nie są zamknięte.

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
