# Postęp wdrożenia

## T0 — w toku

- Worktree i branch utworzone z bazy zapisanej w README; rejestr aktywny, własność przypisana do tego chatu.
- Cudze zmiany głównego checkoutu zachowane. App attachment odrzucony: zwykły Git worktree nie jest managed worktree aplikacji; używane są jawne ścieżki.
- `setup_docker.py --check`: PASS konfiguracji WSL, GPU proof niedostępny; runtime NOT VERIFIED.
- Wolne miejsce przed buildem: Docker 375 GiB, WSL 23 GiB. Brak danych zakończonego etapu tego zadania do usunięcia. Obce cache/volumes zachowane.
- Katalog 224 literalnych ID/commandId zapisany w command-inventory.json (referencje statyczne, nie dowód rejestracji). Baseline runtime i screenshot matrix: w przygotowaniu. Historyczne screenshoty audytu nie zastępują pomiaru nowych źródeł.
- T1 delegowany theme_tokens: Button/kontrast/telemetria; T2 chrome_ribbon: fonty/theme startup. Rozłączne pliki, bez stagingu przez workerów.
- Testy jednostkowe nie są kompilowane.

## Etapy T1–T12

Wszystkie nadal wymagają odbioru. Implementacja częściowa nie oznacza zamknięcia etapu.

## Integracja

Commit/PR/merge/aktualizacja master/cleanup: oczekują. Brak kwalifikacji runtime, WebGL i naukowej.

## Checkpoint źródeł fundamentu

- Plan i 224 kandydaty command ID: commit `cb14ad36a7b5748f011748963eee48fe7129c4ce`; JSON, 42 rekomendacje, linki i staged diff: PASS.
- Toolchain: attempt `43ecf25ad0834eee8c2187490f9315f7`, image `sha256:edf2b09890584142aee7e901535f427f4c10a5d7ddc24c59e6512443956761bd`; Compose własnego zadania. Backend nadal kompiluje aplikację, bez testów jednostkowych.
- T3: jeden CSS owner Tabs, Explorer bez własnego klona stylów, role radiogroup zachowane; fallback wejścia klawiaturą przy disabled/missing wyborze. Nowy regression case zapisany; unit tests NIE kompilowano ani NIE wykonano.
- T4: wspólna nawigacja i transport, compact menu, pełny command ID, close bez overlap i Delete z przywróceniem focus.
- Typecheck źródeł aplikacji w stałym frontendzie: PASS przed końcowymi poprawkami T3/T4/T1/T2; wymaga sprawdzenia po ich stabilizacji.
- Browser WIP: `storage/runs/control-room-design-audit-20261026/browser-foundation`, 1440×1000 DPR1, bez JS errors; tylko ekran oczekiwania na API. Pełne Home/workspace NOT VERIFIED.

## T1/T2 — zweryfikowane fragmenty

- T1 commit: `98f1541d0cb8434e0bf9b93240eb2b7d58282686`; źródłowy pomiar kontrastu w kontenerze PASS, targeted ESLint PASS, produkcyjny typecheck PASS. Unit tests niekompilowane. Hook React Doctor wykonał się, lecz parser oxlint zgłosił `Unexpected discriminant 7 for TSTypeName`; analiza INCOMPLETE mimo komunikatu „No issues found”. Nie jest to dowód PASS review.
- T2: lokalne fonty z manifestem SHA256/licencji, prepaint i System. Browser `home-fixture/theme-result.json`: 4 przypadki przed hydratacją + przełączenia System i ręczny wybór, fonty załadowane, zero błędów/hydration warnings. Targeted ESLint oraz typecheck PASS.
- Header fixture: 6 przypadków light/dark × 1440/900/450, menu/keyboard focus/transport hit area PASS, zero mutacji. To dowód UI z mockowanym API, nie wykonania solvera. Home przy450px wymaga korekty układu w T11.
- Grupa DEV gotowa: attempt `605197360d7949edaf565fe7f94aea94`, config `8cab70728cb1b7d89faa96968474eefd1795fbc43fd7025f46e9973897468478`, frontend i backend healthy, port3230. Brak Solve.

## Kontynuacja — implementacja aktywna

- Cel implementacji wznowiony po błędnym powrocie do wcześniejszego zakresu planistycznego. Obowiązuje pełny kontrakt README i etapowe wiadomości.
- T2 commit `566f2876a55121aee81d59375bfe076a6b739dec`; T3 `04413643792d216f392164a356a40639232b596d`; T4 `319ff4deca914a5ee0cf94b8a5d51bb81802c3a2`. Zielone dowody fundamentu pozostają ważne dla niezmienionych źródeł.
- Model QA `examples/airbox_inspector_mixed.py` opublikowano przez `just docker-dev-script`; activation attempt `f0337228f18b4b648a90bd87c1557481`, succeeded. Model czeka na Compute; bez Solve.
- T7: PanelFrame/PanelChrome, stable parent/key podczas dock/float/maximize/hide, retencja bocznych subtree i osobny uchwyt/menu. Inspector zachowuje efekty guardu/pending form; Explorer/dock suspendują efekty Activity po ukryciu. Zapisano ADR0070, doprecyzowano aktywny moduł + jawny companion bez retencji innych rendererów.
- Pierwszy browser `panels/behavior.json`: rzeczywisty Object/Airbox, ta sama tożsamość DOM po float/maximize/hide/dock, ruch/resize klawiaturą, powrót do poprzedniego trybu; canvas widoczny, contextLost=false, buffer617×719. SwiftShader — nie kwalifikacja hardware GPU.
- T8: jeden identity host dla Airbox, Domain policy zamiast powtórnego tytułu, sześć EmptyState zachowuje komunikaty. Browser draftu ujawnił dwa Revert; ObjectGeneral przeniesiono do istniejącego footer bridge. Powtórka oczekuje na frontend.
- T9: kontrolki 3D przeniesione do nazwanego pasa nad canvasem. Renderery/dane/jakość i overlay settings bez zmian; końcowy browser po tej zmianie oczekuje.
- Frontend Next zakończył się V8 heap OOM po długim HMR, docker OOMKilled=false; backend healthy. Nie ponawiano aktywacji ani Solve. Rozpoczęto `just docker-dev` reconcile istniejącej grupy; brak usuwania cache/volumes.
- Produkcyjny typecheck PASS z checkpointu T11 workera przed końcową zmianą ObjectGeneral/T9; wcześniejsze błędy przejściowe w plikach ribbon workera poprawione. Targeted lint PanelFrame/T7/T8 PASS; T9/nowy browser check przerwane przez wyłączenie frontendu, wymagają ponowienia. Unit tests nadal niekompilowane.

## Recovery frontendu — zweryfikowany fragment

- `just docker-dev` wykazał błędną bramkę resume: `Retained start has no admissible terminal outcome` dla wcześniejszego `succeeded`, mimo późniejszej awarii wyłącznie frontendu. Poprawiono dopuszczenie historycznego udanego startu; dalsze kontrole nadal wymagają zgodności projektu/obrazu/source/mountów/ID oraz backend running + frontend stopped.
- Pinned `just docker-dev-resume`: PASS, attempt `9f243df83ae64f2ab1ec554e61e7b525`, ten sam config i grupa. Docker: backend StartedAt nadal `2026-10-26T10:33:29.103180534Z`; frontend `2026-10-26T12:01:23.728005014Z`; oba healthy. Żaden backend restart ani ponowienie modelu/Solve.
- Trzy interpretowane regresje `test_docker_volume_pending_resume.FrontendOnlyResumeTests` w stałym backendzie z `python3 -B`: PASS (0.067s). Udany start wznawia wyłącznie frontend; działający frontend i zatrzymany backend są odrzucane. Bez natywnej lub jednostkowej kompilacji testów.
