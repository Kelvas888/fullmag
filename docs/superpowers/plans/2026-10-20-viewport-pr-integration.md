# Viewport 3D — integracja PR

Status: przygotowanie PR do mastera na jawne polecenie użytkownika. R7 pozostaje niezaliczone; samo zlecenie merge nie jest dowodem brakujących kontroli ani odwołaniem zakazu kompilowania pozostałych testów.

## Źródła i synchronizacja

- Branch `codex/viewport-visual-quality-20261020`, worktree `C:\git\fullmag\worktrees\viewport-visual-quality-20261020`.
- HEAD przed synchronizacją `cb7eb74d96a06531ddf9550f54eeb3883cd8ca12`.
- Zweryfikowany remote `https://github.com/MateuszZelent/fullmag.git`, master `03b90c82797f976a6237fd910dd8baf81ad193c1`; lokalny master i origin/master wskazywały ten sam commit.
- Merge mastera do własnego brancha: dwa konflikty. RibbonSessionStatus ma identyczną semantykę typów, przyjęto formatowanie upstream. Test modelu sceny zachowuje silniejszą asercję resolvera dyskretyzacji i wszystkie nowe poprawki upstream.
- Zachowano oryginalne zakończenia linii niezmienionych fragmentów dużego testu; bez masowego churn. Polecenie stagingu miało jednorazowe core.autocrlf=false, bez zapisywania konfiguracji repo.

## Weryfikacja po synchronizacji

- 34 przypisane pliki regresji viewportu: 827/827 passed, zero błędów suites. Raport w technicznym wolumenie frontendu `test-evidence/viewport-visual-quality/integration-master-03b90-v1.json`; numTotalTestSuites obejmuje też describe, nie liczbę plików.
- Wrapper browser QA: 23/23 unittest w frontend tej samej grupy. Pierwsza próba ujawniła fixture zwracające str zamiast bytes dla active fence; poprawiono wyłącznie fixture. Produkcyjny CAS i odmowy pozostają bez zmian.
- Produkcyjny typecheck exit0, GOMEMLIMIT=768MiB/GOMAXPROCS=2 w frontend grupy tego worktree.
- Diff zmian PR względem przypiętego mastera bez whitespace errors. W pełnym merge pojawiają się tylko istniejące upstreamowe dwuspacje Markdown w mx3.md; nie zmieniano ich przy integracji.
- Wcześniejsze źródłowe review i narrow lint zachowują zakres dla niezmienionego kodu. Pełny lint dużego modelu pozostaje NOT VERIFIED/OOM; review nie zastępuje runtime.

## Publikacja i bramki merge

Workflow bootstrap uruchamia na pull_request kompilację testów Rust/native spoza wyjątku viewportu. Automatyczna kontrola odrzuciła próbę commita z [skip ci] jako nieautoryzowane pominięcie kontroli; commit nie powstał. Nie zastosowano znacznika ani obejścia. Użytkownik następnie jawnie odpowiedział „Tak, pozwól na CI tego PR”. To odwołuje zakaz wyłącznie dla automatycznego CI tego konkretnego PR; publikacja może uruchomić normalne kontrole. PR pozostaje draft do czasu brakujących bramek.

Brak ochrony brancha i brak repo rulesets nie unieważniają wymogów AGENTS.md: dowodu przeglądarkowego zmienionego viewportu i bramek pełnego planu. Backend3218 nadal unhealthy, failed_outcome_retained, api_shutdown/owner unknown; brak zgody na recovery. Nowe baselines2CSSpx nie mają aktualnego runtime proof. Historyczne próby browser miały globalne404/422. [Macierz V01–V15](../../audits/2026-10-20-viewport-r7-acceptance-evidence.md) nadal określa brakujące sceny FDM/FEM, RGB, AO, lifecycle i capture failure.

Dozwolone teraz: zapis zweryfikowanej synchronizacji, push brancha i publikacja PR ze standardowym CI. Dalszy merge czeka na wymagane dowody i wyniki CI. Nie ustawiamy auto-merge, nie wymuszamy merge i nie kasujemy aktywnego worktree. Główny checkout pozostaje niezmieniony; kontenery nadal mountują worktree.
