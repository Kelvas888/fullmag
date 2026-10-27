# PR #264 — poprawki regresji i integracja

## Cel i źródła

Zachować zmiany `codex/viz-parity-20261025`, naprawić dwa P1 z review,
zweryfikować wynik z aktualnym `master` i scalić PR #264.
Baza zadania: `55266d541f2f824dfd3b25a670bc846fc42aefd6`.
Master przy rozpoczęciu: `5c5e072314fad6d3037ee064566dd07c7757d6ca`.
Izolacja: `worktrees/viz-parity-fixes-20261027`, owner Codex
`01a17c4c-9f0c-7d91-a8d4-a93507d9135c`. Pierwotne worktree i grupy
innych właścicieli pozostają chronione.

## Etapy i kryteria

1. Naprawić AABB cylindrów i wykazać RED/GREEN dla osi ukośnej,
   osi X/Y/Z oraz osi prawie równoległej do osi świata.
2. Usunąć nakładające się mutable slices z równoległej budowy kernela,
   zachować wartości, znaki, padding i brak alokacji per komórka.
3. Połączyć aktualny master; wykonać review, dozwolone kontrole źródeł,
   build aplikacji w osobnej grupie Compose i wymagane dowody UI/runtime.
4. Zaktualizować PR #264, przejść wymagane kontrole, scalić, potwierdzić
   lokalny master i wykonać cleanup wyłącznie własnego worktree.

Zakaz kompilacji testów jednostkowych Rust pozostaje w mocy.
Brak dowodu runtime, WebGL lub numerycznego nie jest wynikiem pozytywnym.

## Etap 1 — granice cylindrów

`fullmag.meshing.voxelization::_geometry_bounds` sumuje projekcję promienia
oraz połowy wysokości. Norma dwóch poprzecznych składowych osi unika utraty
precyzji w odejmowaniu `1 - a_i^2` przy prawie osiowym cylindrze.

Nowy `test_voxelization_cylinder_bounds.py`: cztery testy, przed poprawką
pięć nieudanych asercji (w tym subtesty), po poprawce wszystkie przechodzą.
Sprawdzono też trzy istniejące testy: pierścień na osi X, maskę cylindra oraz
zgodność fingerprintu Difference/Translate. Razem 7 testów PASS.
Testy użyły publicznego modelu geometrii i rzeczywistej woksylizacji,
bez buildu ani instalowania zależności na hoście. Kontrola diffu PASS.
To dowód geometrii źródłowej, nie kwalifikacja solvera.

## Stan

WIP: poprawka bezpieczeństwa równoległego kernela i bramki integracji w toku.
