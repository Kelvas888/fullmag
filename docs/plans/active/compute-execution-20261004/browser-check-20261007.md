# Ograniczone sprawdzenie Start i Settings w przeglądarce

Data: 07.10.2026. Status: **częściowy dowód UI, bez kwalifikacji wykonania**.

Sprawdzono działający frontend `http://127.0.0.1:3258/workspace` przez Codex
In-app Browser, tab 2. Był to istniejący workspace innego zadania
(P8-53BD restart compute), backend oznaczony w UI jako
`0.1.0-dev.20261006.g42dcb7b5eb9b.dirty.s69a71c3485dd+9775`. Nie przełączano
sesji, nie zmieniano modelu, nie uruchamiano solve ani buildu z UI.

| Sprawdzenie | Obserwacja | Granica dowodu |
|---|---|---|
| Start → Compute environment | CPU 48 threads; GPU telemetry unavailable | Inventory, nie przydział ani wykonanie GPU |
| Configure compute → Settings | CPU/GPU i cztery lane FDM/FEM CPU/GPU | Runtime lanes miały Not reported; brak deklaracji kwalifikacji |
| Execution profiles | 0 saved versions, catalogue revision 0 | Istniejący store; nie tworzono trwałego profilu testowego |
| Create profile | Inherit dla backend/device/precision/mode, osobne CPU threads per task, Apply i Cancel | Render i szkic, bez zapisu |
| Edycja szkicu | Profile ID compute-draft-check, CPU threads 4 | Tylko lokalny draft |
| Cancel | Formularz znika; katalog pozostaje 0 versions/revision 0 | Odrzucenie draftu; Apply nie sprawdzono |

Zaobserwowano mylący opis Inspectora Settings: „Changes apply immediately”.
Zmieniono go w ProjectInspector.tsx na opis jawnego Apply, nowych wersji profilu
i niezmiennych accepted settings działających runów. Ta ostatnia zmiana tekstu
nie została ponownie obejrzana: owner zamknął frontend, a port 3258 zaczął
odmawiać połączenia. Nie restartowano cudzych procesów i nie obchodzono strony
błędu przeglądarki. Screenshot widoku po Cancel został pokazany w wyniku narzędzia;
nie jest trwałym plikiem artefaktu w repozytorium.

Anulowanie Accepted/Queued przez publiczny endpoint i panel Saved project runs,
Apply profilu, pełny round-trip UI→Python→IR, host ledger fault injection,
CPU/GPU execution oraz E5–E7 pozostają **NOT VERIFIED**. Powyższe obserwacje
nie zastępują tych bramek.
