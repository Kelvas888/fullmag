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

## Aktualny checkpoint po wznowieniu implementacji

Użytkownik ponownie zlecił implementację po kontroli planistycznej. Kontynuacja korzysta z tego samego zarejestrowanego worktree i grupy Compose, bez resetowania WIP.

| Zakres | Commit źródeł | Dowód / pozostałe bramki |
|---|---|---|
| T7, rama paneli | `42bfffd90be98e20e9fe4cf4603d9e8a609445da` | browser `panels/behavior.json`: zachowany draft i DOM przez float/maximize/hide/dock, move/resize keyboard, fokus inputa po Hide/Restore, drawer 900 px |
| T8 i T9, Inspector i viewport chrome | `1dc7493c167fb8b84ed93c7785cd293c78755c4d` | Object draft/Revert, jedna tożsamość read-only Airbox; canvas widoczny, contextLost=false, buffer1176×605. T8/T9 zapisane w jednym logicznie powiązanym commicie; brak zmian solvera lub jakości |
| T10, dock/telemetria/status | `19c61e8f76938eb4badd55d8f782a8c956f7544a` | wysokość metrics-grid 99 px przy scrollHeight136; osobne osie statusu i jednostki; browser scroll PASS |
| T5/T6, ribbon | `e3d0b6397f8fe48e74cdef7bf3a7f9c188a97d98` | `ribbon/result.json`: 240 przypadków: 10 kart × 3 gęstości × 4 szerokości × 2 theme, nazwane toolbars, min. hit target24 px, overflow/Escape, Ctrl+F1; ten sam canvas, contextLost=false, buffer733×575 |
| T11, Home | WIP, niecommitowane | `home-fixture/result.json`: 6 przypadków light/dark ×1440/900/450, Settings Details Sheet, Escape/fokus, resize do desktop, brak mutacji API; pełny Copy ID i selected item w końcowej kontroli |

- Managed canvas/Home round trip: PASS attempt `79117d2f9f424c449801d003dc2f0404`; canvas_only=true, 0 console/page errors. To SwiftShader/browser proof, nie sprzętowe GPU ani nauka.
- Pełny `pnpm lint` w stałym frontendzie: PASS, exit0. Produkcyjny `pnpm typecheck`: PASS, exit0. Późniejsza poprawka nagłówka wymaga adekwatnej kontroli źródeł i regresji zoomu.
- Ręczny test ribbonu z wcześniejszym `--use-angle=swiftshader` zatrzymano po nadmiernym obciążeniu własnego procesu GPU; brak PASS dla tej próby. Kanoniczne flagi `--use-angle=swiftshader-webgl --use-gl=angle` pozwoliły zakończyć pełne 240 przypadków bez zmniejszenia jakości.
- Review niezależne znalazło zbyt wysoką siatkę metryk, niefunkcjonalne uchwyty drawer i przechwytywanie fokusu portaled menuitem. Przyczyny poprawione, source/browser PASS. Końcowy reviewer czyta pozostały T11 i ribbon; nie dubluje zakończonego przeglądu.
- React Doctor: historyczny parser oxlint INCOMPLETE; w shadow brak Git metadata dla changed scan. Nie zgłaszamy PASS. Hook staged zgłaszał także istniejące w bazie ostrzeżenia (index keys i nested interactive).
- Zakaz kompilacji unit tests nadal obowiązuje; wysłano pytanie o wyjątek dla obowiązkowej bramki frontendu. CI PR zawiera ponadto testy natywne; bez rozstrzygnięcia ich zakresu nie uruchamiamy niezgodnego workflow.
- Integracja PR/master i cleanup pozostają niewykonane. Niniejszy checkpoint nie oznacza ukończenia wdrożenia.

## T11 — zapisany fragment i końcowe regresje

- Commit `1bc72df1ab02255a36d452d1628d6409b7341224`: Home bez pustej prawej kolumny, Details Sheet do1180 px, rail do760 px, Copy pełnego host ID, jawne locale i zachowana pomoc/kontekst sekcji.
- Końcowy review T11 wykrył utratę opcji przygotowanego skryptu przy zmianie kolumny na Sheet. Root przeniósł draft opcji do istniejącego store przygotowania, pod niezmiennym host ticket. Dismiss/reset i zmiana ticketu usuwają ten draft; brak localStorage, brak zmiany intent do backendu.
- `ScriptRunPanel.test.tsx`: RED (as_authored zamiast cpu po remount) → GREEN, 13/13. Browser `script-options-red/resize.json` odtworzył reset Device/waitForSolve/results; `script-options-green/result.json` potwierdza zachowanie wszystkich trzech opcji przez resize, Escape/reopen i powrót do desktop. Most desktop jest jawnie syntetyczny; `script_run` nie został wywołany.
- `extra/result.json`: natywny zoom Chromium 2.0 przez izolowane MV3 i chrome.tabs.getZoom; innerWidth1440→720, DPR1→2. Długa nazwa sesji początkowo powodowała scrollWidth722 przy width720; ograniczenie szerokości brandu i ellipsis z pełną podpowiedzią daje720/720. To rzeczywisty zoom przeglądarki, nie CSS zoom ani samo DPR.
- Ten sam harness: ArrowLeft/Right/Home/End w toolbarze; density po reload; pełny Copy host ID przez stub schowka; embedded instance bez stripu i z osiągalnym Home. Zwykłe POST visualization/client-acks są zapisane osobno od komend; brak Solve/Compute Fields.
- `inspector-ack-scroll/result.json`: rzeczywisty Object Name Apply→ACK→przywrócenie nazwy, oba PATCH HTTP200. Ten sam Inspector DOM, fokus Notes, scroll90→90, pola enabled i opacity1, zero opacity animations. Liczby requestów i receipty zachowane. Airbox read-only pozostaje pokryty osobnym browserem paneli; nie symulowano mutacji zasobu read-only.

## T12 — aktualizacja bramek i kontrola integracji

- Użytkownik dopuścił testy frontendu oraz obowiązkowe automatyczne CI dla tego PR; nie rozszerzono tego na lokalne natywne testy.
- Pierwszy pełny Vitest: 840 plików PASS, 14 failed; 8786 testów PASS,30 failed,1 skipped. Naprawiono brakujący token przez użycie istniejącego radius-pill. Testy dostosowano do centralnego Apply, nowych nazw i prawidłowego ownership komend; żadnego nowego skip ani osłabienia gate.
- Końcowy pełny Vitest w stałym frontendzie, maxWorkers2: 855 plików,854 z raportowanym statusem passed,1 failed; 8816 testów PASS,1 failed,1 istniejący skipped. Jedyny failure: dotychczasowy rootowy next.config.test.ts oczekuje .next/(dev/)types, a DEV zapisuje .next-control-room-8080/dev/types. Nie zmieniono ani nie pominięto tej asercji; pełna kanoniczna bramka CI pozostaje wymagana przed merge.
- Cross-app kontrakt apps/web/dev-server.mjs czytany przez jawne FULLMAG_TEST_SOURCE_ROOT=/opt/fullmag/source: zarejestrowany readonly checkout, bez host builda i bez rozszerzania cienia źródeł aplikacji.
- Punktowe regresje: ribbon118/118, rootowe source guards i ObjectGeneral24/24, fonty/polityki27/27 przed dodatkowym przypadkiem unresolved FEM. Architecture hygiene oraz idle performance PASS. Produkcyjny typecheck PASS po T11. Pełny lint PASS przed testowymi korektami; późniejsze owned paths ESLint PASS, końcowy pełny lint w toku.
- Reviewer pokrył najważniejsze produkcyjne ścieżki paneli/Inspectora/viewportu/footer oraz pozostałe Home/ribbon i konsumentów. Trzy wcześniejsze findings i końcowy reset opcji skryptu poprawione z dowodami. Testy/QA/dokumentacja były oceniane selektywnie, nie deklarujemy pełnego niezależnego line-by-line review każdego pliku.
- Ruling: odłożone R9/R17/R26/R36 pozostają odłożone zgodnie ze skorygowanym audytem. Nie wprowadzamy ogólnego refaktoru dużych plików, usuwania wszystkich literałów, zmiany domyślnych nakładek/scientific colormaps ani obniżenia jakości renderu.

## Incydent przygotowania środowiska testów — zachowany ślad

Ręczna synchronizacja rootowego pliku testu do chronionego shadow była błędem root-agenta: supervisor wykrył zmianę seed i zatrzymał tylko frontend. Wycofano wyłącznie własny regex edit w źródle; odzyskano pierwotne bajty z immutable frozen copy i sprawdzono ich zgodność z aktualnym readonly checkoutem oraz oczekiwanym SHA256 `333d72d4b2f7b2d3886632552e58ba40de6c5ed8daa9efb48cd971bda321f883`. Naprawiono wyłącznie tę kopię techniczną i jej tryb0644/właściciela; nie zmieniono manifestu, expected hash ani walidatora. Kontroler ponownie zweryfikował całość.

Managed resume `008a8f5b5a97423384dd8dd341ec4b88`: succeeded, ten sam config/grupa. Frontend healthy; backend StartedAt nadal `2026-10-26T10:33:29.103180534Z`. Kolejna faza iteration komendy up zakończyła się osobnym `Current activation is not a failed accepted-then-cancelled terminal` (`447411b9aa804114a0230b1634a745a8`); nie ponawiano aktywacji, Solve ani recovery ownera. Nie przedstawiamy całej komendy up jako PASS. Zachowano cache, model, receipty i niezmienionego właściciela.

PR/CI, merge, lokalne FF oraz cleanup nadal oczekują. Żaden z powyższych wyników nie jest dowodem sprzętowego GPU, solvera lub naukowej kwalifikacji.

## Checkpoint przed PR

Końcowy pełny `pnpm lint`: PASS, exit0. Produkcyjny typecheck: PASS. Po korekcie helperów i oczekiwań pełny Vitest nadal ma dokładnie jeden wyżej opisany mismatch generated route types w DEV, bez dodatkowych failing assertions. Żaden test nie został wyłączony z przebiegu. Wymagane kanoniczne CI po push/PR rozstrzyga gotowość do merge; PR nie będzie scalony przy czerwonych wymaganych kontrolach.

Wykonywalne regresje zapisane w repo: check-design-audit-browser.mjs, check-ribbon-design-browser.mjs, check-panel-design-browser.mjs, check-design-interactions-browser.mjs, check-script-options-browser.mjs i check-inspector-ack-browser.mjs. Ich output kierowany wyłącznie do zarejestrowanego katalogu run zadania. Profile native zoom, fonty, clipboard stub i fixture hosta mają jawny zakres dowodu.

## Uzupełnienie T4/T12 — rzeczywisty header z sesją

Końcowe oględziny PNG wykryły przyciętą markę przy1440 px: header miał scrollWidth1518, a fokus menu powodował scroll całego slotu i left=-78. Fixture bez sesji nie obejmował tego przypadku. Nowa regresja active header odtworzyła RED. Root zachował elastyczną nazwę, przesunął próg etykiet quick actions do1800 px, szczegółów statusu do1600 px i zamiany menubar na compact menu do1440 px. Kontrolki transportu nadal są dostępne bez zmiany karty.

`check-header-session-browser.mjs`: GREEN28 przypadków (2 theme × workspace/Home z sesją ×1920/1600/1440/1366/1180/900/450). Asercje obejmują scrollWidth, left/right całego nagłówka i położenie każdej z czterech kontrolek transportu. `header-active-green/result.json` potwierdza także brak overflow1440 oraz natywny zoom200%. Wcześniejsza uwaga o naprawie samego720 px nie zastępowała tego dowodu.

`final-screens/result.json`: powrót 3D→2D→3D zachowuje position/target/up/projection kamery; po powrocie canvas widoczny, contextLost=false, buffer617×413, zero page errors. Zrzuty dotyczą rzeczywistego, oczekującego modelu QA; komunikat o niedostępnych danych pola pozostaje widoczny, bez udawania wykonania solvera.

Dodatkowy stress test długiego projektu wykrył przepełnienie przy1600/450 px. Root dodał min-width0 grupy akcji, ograniczył wizualną nazwę projektu i rozdzielił nazwę od stałego tekstu `· unsaved`. Pełna nazwa/ścieżka pozostają w DOM i title; dirty marker nie podlega ellipsis. Osobny presenter ma2/2 testów SSR. Macierz nagłówka rozszerzona do84 wariantów: normalny stan oraz jawne DOM fixtures długiej nazwy clean/dirty. To pomiar długości prezentacji, nie dowód zapisania projektu w backendzie. Native przyciski statusu połączenia i readiness mają teraz min-height28 px; kontrola hit targetów obejmuje wszystkie native buttons nagłówka.

Końcowy `header-matrix-final/result.json`: PASS84 wariantów, z kontrolą granic headera, pełnego transportu, native hit targets≥24 px i widoczności dirty marker. Targeted ESLint nowych plików PASS; ProjectDocumentStatus/AppMenuBar14/14 PASS. Poprzedni pełny lint pozostaje dowodem dla niezmienionych ścieżek; ostatni fragment ma własną kontrolę. Pełne CI nadal wymagane.
