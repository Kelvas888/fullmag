# P8-53CC — fixtures kontraktów ownera i inventory

Data: 14.10.2026. Zakres: wyłącznie moduły `cfg(test)` w
`compute_node_snapshot.rs` i `host_resource_ledger.rs`.

CI `rust-contracts`, job `115726863344`, zakończyło serię 302 PASS / 13 FAIL.
Analiza wskazała fixtures niespójne z aktualnymi kontraktami:

- Próbka zmieniająca wyłącznie capabilities zachowuje poprzednie ograniczenie
  CPU, aby nie zmieniać jednocześnie inventory.
- Próbki V2 mają rzeczywisty `runtime_owner_id` danego ledgeru.
- Mutacja partition GPU przelicza inventory digest, zamiast tworzyć uszkodzony
  snapshot przed badaniem unknown partition.
- Syntetyczny ledger dla release proof używa bieżącego schema V3 i node policy,
  żeby test docierał do docelowej walidacji dowodu zwolnienia.

Nie zmieniono produkcyjnego owner fencing, walidatora, algorytmu digest ani
revision. Asercje zachowano. Review diffu, parser Rust bez zapisu i
`git diff --check`: PASS. **Lokalnych Rust unit tests nie kompilowano ani
nie wykonywano; wykonanie poprawionych regresji w CI: NOT VERIFIED.**

To naprawa wejść testowych, nie dowód poprawnego runtime ani nauki.
P8 i cały plan pozostają IN PROGRESS.
