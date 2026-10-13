# Inspector actions and template — checkpoint

## Cel i izolacja

Naprawić routing semantycznych węzłów, rzeczywiste Apply/Revert oraz wspólny
kontrakt wariantów Inspectorów, zachowując wzorzec Visualization i kanoniczne
zasoby. Użytkownik dodatkowo zgłosił dekoracyjne przyciski dolnego paska.

- Worktree: `C:/git/fullmag/worktrees/inspector-actions-template-20261013`.
- Branch: `codex/inspector-actions-template-20261013`.
- Base: `27c43be1315bb70018a24b42aa15eec3cec6bc3e`.
- Rejestr: `storage/index/inspector-actions-template-20261-cece1930e1d3431d.json`.
- Główny dirty checkout chroniony; nie przenoszono cudzych zmian.

## Podział

- Koordynator: shell/footer, semantyczny routing z typed carrier ref,
  wspólne CSS i kontrakt w specyfikacji.
- Worker paneli: kompletna inwentaryzacja trybów i połączenie pominiętych draftów
  z rzeczywistym commit/reset; osobny ledger.
- Worker browser: produkcyjny Shell/Footer w kontrolowanych fixture,
  pending/ACK/rejected/invalid/live/read-only, Object/Airbox, layout i stabilność.

## Kryteria odbioru

Apply wykonuje faktyczny commit tylko w staged, Revert odtwarza baseline,
nieudany zapis zachowuje draft. Live display nie pokazuje Apply, immediate
korzysta z nazwanych operacji panelu, read-only nie ma atrap edycji. Isolate nie
jest reklamowany bez handlera. Fit view odpowiada istniejącemu poleceniu fit.
Unassigned rodzic i część wybierają swoje widoki bez zmiany adresowania mesh.
Brak opacity transitions na sekcjach. Source/lint, browser fixtures i obowiązkowe
CI/review muszą mieć aktualne dowody przed merge. Fixture nie dowodzi backendu.

## Weryfikacja dotychczasowa

`git diff --check`: PASS dla pierwszego fragmentu. Dodano regression checks
selectExplorerNode -> Inspector route -> visualization target; nie uruchamiano
ani nie kompilowano testów jednostkowych zgodnie z zakazem użytkownika.

Lokalne source/browser checks jeszcze NOT VERIFIED: brak zależności w nowym
worktree i w sprawdzonych wcześniejszych namespace storage. Linki storage
przygotowane przez resolver. `fullmag_storage.py run ... pnpm install` odmówiło:
`Container runner owns heavy builds on this host; submit a snapshot through just runner-build`.
`local_runner_cli.py container-status` zgłosiło `Container profile allow-list mismatch`.
Nie obchodzono odmowy, nie uruchamiano backendu ani solverów.

## Pozostało

Dokończyć podłączenia paneli i regression fixture, przejrzeć komplet diff,
wykonać dostępne źródłowe sprawdzenia oraz CI, push/PR, wymagane akceptacje,
merge, bezpieczny fast-forward i cleanup własnego worktree lub jawny blocked.
