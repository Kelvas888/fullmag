# Checkpoint wdrożenia korekt U01–U12

Zlecenie użytkownika: realizacja wszystkich korekt z `audit-and-correction-plan.md`. Audyt i `source-identity.json` zachowują historyczny stan HEAD `f2eb8f100e706343fe379e9928c589530529bd94`; ten plik opisuje późniejszą implementację.

Worktree: `simulation-mode-consistency-20261013`, branch `codex/simulation-mode-consistency-20261013`, PR #155. Główny dirty checkout pozostaje chroniony.

## Decyzje i zakres etapów

- U01/U02: authored method z zaakceptowanej sceny; resolved execution i operation capabilities niezależne. Brak capabilities nie blokuje edycji modelu. Jawny brak/conflict nie korzysta z zachowanej siatki. Source pointer w statusie jest zgodny ze źródłem.
- U05/U08/U09: serwerowa lista readiness poszerzona o method/domain/execution oraz target pierwszego obiektu z brakującym przypisaniem. Manual bounds blokują build/run, dopuszczając naprawę modelu. Efektywna polityka `study.universe_mesh` ma pierwszeństwo. ADR 0053 zapisuje decyzję.
- U03/U04/U06/U07/U10/U12: przewodnik i ustawienia domeny wdrażane w istniejących modułach, przez resource hooks, selection guards i Apply/Revert.
- U11: nowe regresje źródłowe i browser fixture będą wykonane w CI. Realny backend oraz osobne FEM/FDM CPU/GPU receipts wymagają aktualnych źródeł i managed execution; obecnie **NOT VERIFIED**.

## Dotychczasowa kontrola nowych zmian

- `git diff --check`: PASS.
- `node scripts/check-api-hygiene.mjs` i `node scripts/check-architecture-hygiene.mjs` uruchomione z `apps/control-room`: PASS.
- `python scripts/check_repo_consistency.py`: PASS.
- Niezależny source review ROOT: comparator absent authored → authored null wymagał korekty; naprawiony i objęty regresjami. Manual Universe dociera do backendowych bramek admission.
- Nowe unit/DOM/Rust testy: przygotowane; lokalnie nieuruchamiane zgodnie z zakazem kompilacji testów. Wynik poprzedniego HEAD nie obejmuje nowych zmian.

## Wykonanie i retencja

Read-only `local_runner_cli.py container-status`: exit 1, `Container profile allow-list mismatch`. Nie zmieniono konfiguracji runnera ani profilu i nie zastosowano zastępczej trasy FEM. Ocena przed buildem: dla tego nowego etapu brak zakończonych execution/staging/runtime do usunięcia. Zachowane wcześniejsze evidence `storage/evidence/simulation-mode-consistency-20261013/f2eb8f100`, cache przyrostowy i runtime użytkownika. Storage rozwiązuje resolver do `C:/git/fullmag/storage`; na 2026-10-13 dostępne około 25 GB. Retencja globalna nie jest obsługiwana jako scoped plan tego etapu, zatem nie wykonano kasowania.

## Pozostałe kroki

Dokończenie i review UI, nowy CI, browser proof, próba realnego authoring z zarządzanego Windows workspace oraz osobna ocena managed FEM, integracja PR, fast-forward chronionego mastera i cleanup dokładnego worktree. Całe R0/R1 D07 i kwalifikacja wydania nie są zamknięte.

## Etap P0 zapisany i CI

Commit `3d8a1b1ac2290ebe9f39ee8cd05521e0be5971e0`: authored method, readiness, manual admission i ADR 0053. GitHub Actions run `38424872870`, attempt 2: wszystkie osiem bramek SUCCESS, w tym Rust i browser. Cztery nowe API regresje były zielone już w attempt 1; niezmieniony `session_recovery_is_scoped_to_current_session` zwrócił 500 zamiast 200. Powtórzono wyłącznie tę bramkę bez osłabienia asercji. Nie ustalono przyczyny pierwotnego 500. React Doctor run `38424872996`: SUCCESS; wynik advisory nie dowodzi braku całego istniejącego długu.

Nowe UI obejmuje przewodnik, wspólny trwały host NewProblemDialog, potwierdzenie session collection przed nawigacją, Universe i SI. Review wykrył rozjazd SI JSON i wybranej jednostki nm; poprawka i regresja są częścią następnego etapu. Browser fixture prowadzi do Material Assignment i Universe oraz zapisuje WebGL proof. CI rozszerzono o wykonanie `fullmag-authoring manual_universe`, ponieważ wcześniejszy filtr rotated nie wykonywał tych nowych testów.

### Runner i retencja przed buildem

Rozwiązano blokadę klienta: konfiguracja hosta zawiera zatwierdzony profil runtime-v2, którego stary klient zadania nie rozpoznaje. Zweryfikowany istniejący klient `fem-script-launch-20261013` (HEAD `e0d64ca97af68e7c125fa79aaf5c3014b63a0c8d`, pliki klienta czyste) z jawnym `--worktree` tego zadania zwrócił health.ok=true, worker_alive=true, accepting_jobs=true, pustą kolejkę i brak aktywnych jobów. Konfiguracji ani źródeł obcego zadania nie zmieniono.

Na odczycie preflight dostępne 23 258 718 208 bajtów. Nie ma zakończonych danych nowego etapu wykazanych jako zbędne; cache przyrostowy, runtime użytkownika, logi i evidence pozostają zachowane. Zarządzany fem-cpu-release buduje target native `fullmag_fem`, nie targety testowe, i produkcyjny CLI/API oraz static web; lokalny zakaz kompilowania testów pozostaje w mocy. Build i realny happy path nadal NOT VERIFIED do terminalnego receiptu i obserwacji.

Finalny source review UI: brak kolejnych konkretnych P1/P2; poprawiono JSON SI → aktualna jednostka kontrolki i dodano nm round-trip regression. Odczyt runnera `/storage` zwrócił magic `1021997` (9p), poza allowlistą session persistence w managed-browser launcherze. Dlatego realna trwała sesja FEM na tej bind-mounted trasie pozostaje blokowana; nie obniżono allowlisty. Listing własnych jobów zwrócił HTTP 500; przed zleceniem builda należy ponownie sprawdzić zdrowie koordynatora.
