# P8-53BV — lokalny drain helpera po zamknięciu API

Data: 14.10.2026. Baza `e0a69c483e068da818584bf703497ab46d3299d9`.
Status: **IN PROGRESS**. Dotyczy kontrolnej próby, nie promocji publicznego
restartu ani zmiany solvera.

## Obserwacja runtime

Próba `0fb5bed74c2743e28de9b5009a626d4b`, pakiet b08a5648,
owner bundle `12984ba740244e5e86d8878814069155`, zakończyła się failed,
zero checks. Native reason `restart_pump_outcome_unconfirmed` wystąpił przed
browser-ready i przed replacement API. Zarejestrowano start helpera 157744,
lecz jego wait brakował w terminalnym wyniku. API 127232 ma exit 1, frontend
128868 waited/exit 1. Brak obecnego PID helpera nie jest dowodem historycznego
wait; starego receiptu nie poprawiano ani nie zaliczano.

## Przyczyna utraconego cleanupu

`finalize_outcome` zamyka owned API przed drain pompy. Dotychczasowy drain
wywoływał `step_observed`, który może odczytać consumer status, wznowić attach
lub komunikować się z API. Po shutdown taka zależność może zawieść przed
anulowaniem helpera. Bounded review potwierdziło P1 tej ścieżki.

Nowe `NativeRestartPump::drain_candidate_preparation_for_probe` wywołuje
wyłącznie istniejący cancel/drain posiadanego helpera. Bounded pętla probe
nie odnawia readiness, nie wznawia obserwatora i nie korzysta z zamkniętego
API. Wciąż wymaga rzeczywistych terminalnych danych; unknown pozostaje
unknown. Review bieżącej poprawki: brak P0/P1. Rustfmt/parser i diff PASS.

Pierwotny błąd pompy był dotąd sprowadzany do is_err. Probe zachowuje teraz
error contexts w stderr, bez serializacji requestu, UI payloadu ani tokena.
To ma ustalić pierwotną przyczynę niedostępności readiness; sama poprawka
cleanupu jej nie dowodzi.

## Odbiór

Nowy managed native build-only wystartował; rezultat i następną rzeczywistą
próbę należy odczytać z ich terminalnych rekordów. Nie uruchamiać duplikatu
po timeout obserwacji. Testy jednostkowe Rust/TS nie są kompilowane.
Ramka v2, pełny przebieg browser i A→B→C pozostają NOT VERIFIED runtime.
Publiczny restart pozostaje zablokowany; 3197 nie jest zatrzymywane.
