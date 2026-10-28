# Recovery input identity — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans for the bounded implementation tasks below.

**Cel:** recovery odtwarza dokładny authored input zapisany w RunIntent, dzięki czemu terminalny Stop zamyka się w tym samym dzienniku i UI. Zachować aktywne sesje, wyniki oraz wszystkie grupy innych zadań.

**Architektura:** nowy RunIntent zachowuje authored SceneDocument w definicji projektu, a wyprowadzony execution profile pozostaje w niezmiennym Study/ExecutionPlan. Historyczny dokument z automatycznie dopisanym dokładnym profilem `legacy_live_execution_profile()` może zostać odtworzony bez tego pola wyłącznie wtedy, gdy pełny versioned input identity staje się identyczny z pinem RunIntent. Bez wyłączania digestów, scene/session/run fence ani ręcznej edycji katalogów i dzienników.

**Technologie:** istniejące Rust API/SessionStore, Docker Compose, HTTP v2 oraz przeglądarka Control Room. Bez zmiany schematu OpenAPI ani fizyki.

**Specyfikacja:** bezpośrednie polecenie użytkownika oraz operacyjny raport `recovery/master-20261028/stop-diagnosis.md`; kontrakty `docs/specs/command-lifecycle-v1.md` i SceneExecutionInputIdentity.

## Ograniczenia

- Jeden branch `codex/recovery-input-identity-20261028`; aplikacja narzuca managed ext4 worktree `/home/kkingstoun/.codex/worktrees/recovery-input-identity-20261028/fullmag`.
- Żadnego zatrzymywania innych grup ani implicit Solve/Compute. Build aplikacji wyłącznie w grupie wybranego checkoutu.
- Nie kompilować lokalnie testów jednostkowych. Regression cases pozostają wykonywalne; dotychczasowa autoryzowana bramka GitHub CI oddzielona od lokalnego buildu aplikacji.
- Nie zmieniać istniejących RunIntent/CAS/dzienników w miejscu. Bieżącej sesji mastera nie zastępować testowym modelem.

## Ryzyka do review

- Jawnie zadany profil domyślny musi pozostać jawny, jeśli zgadza się z pinem.
- Zmieniona geometria, materiał, stage/runtime/output albo dowolny inny input nadal musi być odrzucony.
- Historyczne sceny bez versioned identity nadal wymagają dokładnej revision; nie wolno zgadywać ich authored input.
- Nieprawidłowy schema/digest nie otwiera ścieżki kompatybilności.
- Projekcja Stop nadal wymaga dokładnego run/session i dowodów anulowania wszystkich zadań; nie omijać naukowych guardów.

## Kroki

- [ ] Zapis źródłowego authored SceneDocument zamiast effective clone w nowo materializowanym projekcie.
- [ ] Wspólny helper recovery: najpierw dokładna walidacja, potem jedyna dopuszczona rekonstrukcja historyczna z pełnym porównaniem digestu. Wywołanie przy odczycie niezmiennej definicji przed publikacją API.
- [ ] Regression cases: nowa scena, profil migrowany, profil jawny/custom, zmiana fizyki, malformed pin, legacy revision; odzyskany input przechodzi istniejący terminalny Stop projector i journal completion.
- [ ] Review diffu, adekwatna weryfikacja źródłowa i CI, commit → PR → wymagane kontrole → merge → FF master.
- [ ] Bezpieczne wdrożenie zarządzaną ścieżką z zachowaniem istniejącej sesji i wyników; weryfikacja Stop w izolowanej kopii/teście bez mutacji naukowych mastera.
- [ ] Niezależna kontrola FDM H_demag w powietrzu: najpierw istniejące dane i Ms=0/full-domain, potem screenshot/WebGL; żadnego obliczania bez potrzeby.
- [ ] Receipty, raport i kwalifikowany cleanup własnych zasobów. Jeżeli app blokuje archiwizację aktywnego primary worktree, zachować go i opisać konkretny powód.
