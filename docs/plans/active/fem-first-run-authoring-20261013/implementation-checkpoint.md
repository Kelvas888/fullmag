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
