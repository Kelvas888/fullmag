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
