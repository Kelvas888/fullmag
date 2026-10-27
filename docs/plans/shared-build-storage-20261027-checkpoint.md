# Checkpoint: shared build storage, 2026-10-27

- Worktree: `/home/kkingstoun/git/fullmag/worktrees/shared-build-storage-20261027`.
- Branch: `codex/shared-build-storage-20261027`.
- Base: `38ffb49bf4f8dabfdf2b4921903c88183bb9f84e`.
- Registry worktree ID: `shared-build-storage-20261027-254985687c4b4591`.
- Owner: `codex-01a17d5e-2692-7540-95ab-b5ff7a441faf`.

## Commity etapów

1. `98cf116532f6e4ab16d32e9ddc673a89b9c0a9cb` — shared pnpm store, prywatne
   node_modules i Next, blokada instalacji powiązana z proofem końca procesów.
   Weryfikacja: 60 interpreted frontend tests; review diffu i lifecycle.

## Dowody przed integracją

- 247 tests w szerszej bramce kontraktowej: PASS, 2 platform-dependent skips.
- 88 interpreted backend tests: PASS po ostatnim marker-last cleanup.
- 19 shared store/integration/recovery tests: PASS, w tym single publisher,
  GC zachowujący current/rollback, przerwanie restore/cleanup/GC,
  recovery ready publisher/cache-hit bez fikcyjnego Make attempt.
- Root initializer: 8 tests, 1 UID65532 probe skipped na hoście nie-root.
- Zarządzane obrazy helperów: build PASS, backend image
  `sha256:f4f97860f4ee6563cd860e6ddd4cdf7175d7020cee512d5eaade48667ce834d1`.
  Obraz poprzedza ostatnie poprawki crash recovery; wymaga refresh przed
  pełnym testem startu aplikacji.
- Niezależne review wykryło ctime/link races i recovery building/ready/cleanup;
  poprawki i regresje dodane. Sam review nie jest qualification runtime.
- Docker UID/mount/concurrent helper proof: IN PROGRESS.
- Pełny build/start backend+frontend na finalnym źródle: NOT VERIFIED.
- FDM/FEM CPU/GPU scientific qualification: poza zakresem tej zmiany.

## Kontrakt i ograniczenia

Zobacz [shared build storage](../guides/shared-build-storage.md). Nowe grupy
używają współdzielonych cache; zachowane stare grupy nie są samoczynnie migrowane.
Retencja jest jawną operacją poza startupem. Nie ma globalnego quota Docker ani
automatycznego usuwania danych nieznanych/starych grup. Zachować cudze dirty
submodules w głównym checkoutcie. PR, merge, fast-forward i cleanup własnego
worktree pozostają wymaganymi krokami domknięcia.
