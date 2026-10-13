# Sprawdzenie protokołu cancellation HTTP na natywnym API

Data: 07.10.2026. Status: **PASS w opisanym zakresie; pełne E0–E7 nadal w toku**.

## Pakiet i tożsamość

Zarządzana recepta `just windows-workspace-build dev dev 3197 auto` zakończyła
się exit 0. Nie kompilowano testów Rust. Gotowy CLI/API/UI ma wersję
`0.1.0-dev.20261007.gc6b8e4f08be0.dirty.s7068e95de947+9776`.

- commit: `c6b8e4f08be06e39a7e3855bc01f72dcce1a6f26`;
- hash utrwalonej kopii źródeł: `403c858f7dc1d49ad96afac04722b575a87cd32c168b4198e3885b1596d302bb`;
- source snapshot pakietu: `7068e95de947f3c3c024b494f80ee97bd3f14af003f9dd032d4ff39c45c4e265`;
- backend fingerprint: `5ca9731cd0d87d6c06969b71189bceaee9868c13f6818a35bd7156986cb46c0d`;
- manifest SHA-256: `b4f69e4158693a7f1ae05c233baefb7d1a0b3f4aff1eb99a5ccf2284fece40fd`.

Są to różne tożsamości różnych zakresów; nie są zamienne. Walidator
verified_build_identity potwierdził manifest i binaria przed wykonaniem.

## Zakres fixture

Recepta `just verify-compute-cancellation-api <manifest-sha256>` używa existing
managed harness z preflightem, pojedynczym lockiem checkoutu, sealed diagnostic
copy binariów, terminalnym receipt i kanonicznym exportem OpenAPI. Nowy wrapper
przyjmuje tylko tę dokładną receptę Windows i lowercase SHA-256; pierwsza próba
przed dodaniem allowlist została poprawnie odrzucona.

Fixture inicjalizuje nowy scoped store przez produkcyjny CLI, następnie przed
startem własnego API seeduje jawny RunSpec v2 i unclaimed katalog Accepted/Queued.
Nie jest to test Submit ani prawdziwego ProblemIR, siatki, solvera lub scheduler
release. Snapshot definicji/study jest syntetyczną fixture protokołu.

Pierwszy przebieg `bbb6d409b5314a9e89ba8ff384a478db` zakończył się FAILED/0 checks:
initializer odmówił niepełnego managed development context. Fixture poprawiono
przez przekazanie rzeczywistych metadanych gotowego pakietu oraz oddzielnego
diagnostic status path. Nie omijano guardu ani nie modyfikowano realnego watchera.

Końcowy przebieg `15bfd6c4c92046e5b5eac71f6abba5bd`: **completed, exit 0, 19 checks**.

| Kontrola | Rzeczywisty wynik |
|---|---|
| Accepted bez claimu | POST 202 requested, brak command_id; task nadal Accepted |
| Idempotentny retry | POST 200 replayed, pierwotny id/revision/created_at |
| Zmieniona tożsamość | 409 run_task_cancel_identity_conflict; brak nowego zapisu |
| Niepełna para id/revision | 400 bad_request |
| Stara rewizja | 409 run_task_cancel_revision_conflict |
| Prawdziwy writer innego procesu | 409 run_store_busy; fs2/Win32 lock w produkcyjnym store |
| Legacy reason-only na unclaimed | 409 run_task_cancel_rejected, bez fikcyjnego claimu |
| Queued bez claimu | POST 202 requested; lifecycle pozostaje Queued |
| Retry po zmianie rewizji przez inny task | 200 replayed z pierwotnym expected revision i aktualną rewizją catalogu |
| GET readmodel | Zwraca intent; odrzucone prośby nie tworzą rekordów ani ownera |

Własny initializer i lock-holder zakończyły się exit 0. Własne puste API zostało
zatrzymane przez verifier (exit 1); wszystkie trzy procesy zostały wait/reap
i ponowny CIM potwierdził ich brak. To nie jest dowód graceful shutdown solvera.
Domyślny listener produkcyjnego API był 0.0.0.0 na ephemeral porcie; klient fixture
używał loopback. Nie zmieniano publicznego kontraktu sieci ani firewallu.

Kanoniczny OpenAPI export pochodzi z tych samych zweryfikowanych binariów, hash
`4d72e78d6643a5238c3b869a2b829da44ec8a3d043a02a3988d51bf7febf5a9f`.
Zaimportowano go istniejącym generate-openapi-v2.mjs z native receipt oraz
expected commit/snapshot. Types/client regenerated; TypeScript i API hygiene PASS.

## Dowody i otwarte bramki

Receipt: `C:/git/fullmag/storage/builds/fullmag-0950f4dca4ffe38f/development-backend-api-checks/checks/15bfd6c4c92046e5b5eac71f6abba5bd/receipt.json`.
HTTP body evidence: ten sam katalog, `compute-cancellation-http-evidence.json`.
Log buildu: `C:/git/fullmag/storage/builds/fullmag-0950f4dca4ffe38f/windows-native-fdm-cpu-dev/logs/native-build-460bf2ca919748ef9219c2f608163e84.log`.

Terminalne Cancelled, no-spawn/Consumed recovery i resource release przez
prawdziwy scheduler, Submit round-trip, browser cancellation, profile Apply,
OS enforcement, CPU/GPU/physics oraz E5–E7 pozostają **NOT VERIFIED**.
Startup guard v2 zachowano. Ukończony protokół HTTP nie zamyka E4 ani całego celu.
