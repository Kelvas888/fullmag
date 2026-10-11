# Anteny mikrofalowe — działania po niezależnej recenzji PRO

## Zakres i wiarygodność

Ten checkpoint rejestruje uwagi, podział pracy i dowody; nie zastępuje not fizycznych ani nie certyfikuje solvera. Recenzja dotyczy commita `426d1974bf4801f87e34024a81c21b0789605817` na branchu `codex/microwave-antenna-latest-20260909`.

Oryginalną recenzję zachowano w [archiwum audytu](../specs/2026-10-11-microwave-antenna-independent-pro-review.md), bez zmian merytorycznych. Porównanie z załącznikiem po normalizacji CRLF do LF potwierdziło identyczność tekstu. SHA-256 oryginalnego załącznika: `614eb100bc2b1e725cf5dac4fea59c40ef8f0669ccec846f5d8950f7ef558234`. Historyczne oceny audytu pozostają przypisane do badanego commita, nawet po poprawkach.

## Koordynacja

Użytkownik upoważnił do uzgadniania prac z wątkiem `01a12a56-002e-7660-8424-c7e07fb0907a` — „Zaimplementuj anteny i transport”. Wątek potwierdził następujący podział:

| Obszar | Właściciel i granica |
|---|---|
| Ograniczenie wieloportowych definicji w UI | Ten worktree: command, composer, Inspector i wspólna funkcja capability. Bez zmiany Rust/Python/ABI. |
| Transport, planner/binder/materialization, geometria i meshing | Równoległy worktree `antenna-transport-e2e-20261011`; duży sprzężony WIP. Nie edytujemy jego checkoutu. |
| B-02: compiler i zależności kolejności | Tutaj najpierw proposal i odczyt kodu; implementacja dopiero po porównaniu z równoległym WIP. |
| Runner, operator i scena na 3197 | Bez restartu i bez zmiany sceny w ramach tej poprawki. |

Przed integracją potrzebny jest osobny SHA poprawki UI i porównanie z aktualnymi zmianami drugiego wątku. Uzgodnienie zakresu nie jest dowodem zgodności runtime.

## Rejestr uwag i bramek

| Uwaga | Stan po odczycie kodu | Następny weryfikowalny rezultat |
|---|---|---|
| B-01: baza łączy dwa solve | Potwierdzone w legacy ścieżce. RT0 udostępnia wspólny potencjał, lecz to nie wystarcza. Otwarte. | V, J, H i podpisany prąd odniesienia z jednego źródła, pełna tożsamość mesh/current/certificate; odwrócenie prądu i normalizacja H/I potwierdzone numerycznie. |
| B-02: brak produkcyjnego producenta accepted Study | Compilation zachowuje drzewo i wykonania, nie produkuje kompletnego StudyPlan/catalog. Otwarte. | Jedno lowering aplikacyjne; rzeczywiste zależności danych i oddzielne bariery zakończenia; kwalifikacja scheduler/worker/replay. |
| B-03: raw inspection nie zasila LLG/FFT | Odmowa jest zamierzonym zabezpieczeniem, nie naprawą przez jej usunięcie. Otwarte. | Kwalifikowana baza i projekcja na target; waveform używa bazy bez solve w każdym kroku; źródłowe FFT odrębne od odpowiedzi magnetyzacji. |
| R-01: brak wygenerowanych kontraktów frontend API | Otwarte. | Generacja z przypiętego, zaufanego backendu, typowany klient i consumer durable result; bez ręcznego dopisywania generated paths. |
| R-02: koszt GET/ETag/Range | Otwarte. | Ograniczony cache/index z deduplikacją, pełną tożsamością ownership/attempt i kontrolą integralności; testy współbieżności oraz 304/Range. |
| R-03: UI obiecuje niewspieraną selekcję | Poprawka źródłowa przygotowana; lint i noEmit typowanie przeszły. Regresje runtime niepotwierdzone. | UI odmawia definicji z liczbą portów różną od 1; jednoportowy przepływ pozostaje dostępny; browser public-flow bez mutacji przy odmowie. |
| R-04: ekstrakcja artefaktów | Otwarte. | Golden parity formatu, przypadki odrzucenia i build odpowiednich features; przeniesienie kodu nie dowodzi usunięcia walidacji. |
| S-01: alreadyAdded a disabled | Otwarte. | Czytelny komunikat o wyłączonym kroku/przodku; deduplikacja nie włącza niczego automatycznie. |

W R-03 wybrano uczciwą odmowę zamiast rozszerzenia kontraktu: publiczny Python i raw planner wymagają singleton definicji. Sam wybór jednego portu z wieloportowej definicji nie czyni jej wykonywalną. Nie usuwamy portów z modelu ani nie aktywujemy innej fizyki. Wsparcie pełnej definicji wieloportowej pozostaje osobnym, otwartym zadaniem cross-layer.

## B-02 — proposal przed implementacją

Poniższe punkty są projektem, a nie istniejącym API:

1. Zachować jedno miejsce ekspansji: `crates/fullmag-application/src/script_pipeline_compilation.rs::materialize_script_pipeline_with_output_policy_bounded` już wywołuje istniejącego właściciela materializacji tylko raz. Kolejny adapter powinien konsumować jego wynik, nie ponownie odtwarzać macro/payload.
2. Wyprowadzać typed StudyPlan i immutable inputs z rzeczywistych `CompiledScriptExecution`, zachowując authored ID, expansion index, enablement przodków, requested execution i tożsamość całego inputu. Wykorzystać `crates/fullmag-application/src/study_execution_materialization.rs::materialize_study_execution`; nie traktować samej listy wykonanych etapów jako gotowego accepted catalog.
3. Rozdzielić przekazanie danych od kolejności: `crates/fullmag-authoring/src/study_contract.rs::StudyStep` zawiera `inputs`, lecz brak osobnej bariery zakończenia. `StudyPlan::topological_order` wyprowadza krawędzie z grup i StepOutput. Nie dodawać fikcyjnego artifact input do raw anteny tylko po to, by serializować wykonanie.
4. Przed zmianą publicznego kontraktu ustalić wersjonowanie i migrację starego JSON. Osobne completion dependencies muszą przejść walidację unknown/self/duplicate/cycle/disabled; wspólny graf uwzględnia również realne zależności danych. Nie wymuszać globalnej sekwencyjności niezależnych etapów poza zamierzoną semantyką authored pipeline.
5. Przenieść barierę do lowered plan i immutable run identity. `crates/fullmag-plan/src/study_lowering.rs::StudyStepExecutionPlan` obecnie przechowuje inputs oraz outputs. Kolejność w `topological_order` nie jest sama w sobie barierą wykonania.
6. Kontrolować barierę przed queue, admission, Prepare oraz replay. `crates/fullmag-runtime-control/src/scheduler.rs::inputs_are_automatically_resolvable` obecnie sprawdza powodzenie required StepOutput; pusta lista inputs nie tworzy bariery. `crates/fullmag-runtime-control/src/study.rs` ponownie wiąże źródła z bieżącym successful attempt — tego zabezpieczenia nie wolno osłabić.
7. Nie utożsamiać ukończenia raw solve z przydatnością jego H do LLG. Completion dependency mówi wyłącznie „poprzednik zakończył się sukcesem”; baza→projekcja→LLG potrzebuje oddzielnego, kwalifikowanego kontraktu artefaktu i adaptera konsumenta.
8. Przed wdrożeniem uzgodnić diff z właścicielem równoległego planner/binder WIP. Bramy: dwa niezależne kroki mogą działać równolegle; krok zależny czeka; failed/cancelled poprzednik nie uruchamia następcy; restart/retry nie używa starego attempt; cykl mieszany data/completion zostaje odrzucony; UI/Python round-trip zachowuje semantykę.

## B-02 — minimalny zestaw źródłowy do przeniesienia kompilatora

Odczyt porównuje źródło `426d1974bf4801f87e34024a81c21b0789605817` z worktree `antenna-transport-e2e-20261011`, którego zaobserwowany HEAD to `147d8b1f723135229cfff0a90e8b2a8bb18cfd9d`. Numer kapsuły koordynatora nie jest SHA checkoutu. Docelowy worktree zawiera aktywny WIP, również w dwóch plikach poniżej; nie wolno zastępować ich całymi plikami ze źródła. Ta sekcja jest propozycją przeniesienia, nie wykonaną integracją ani potwierdzeniem kompilacji.

### Minimum produkcyjne: cztery pliki, wybrane hunki

| Plik względem repo | Dokładny zakres do przeniesienia | Dlaczego jest konieczny |
|---|---|---|
| `crates/fullmag-application/src/script_stage_contract.rs` | Dodać `ScriptStageProvenance` z authored ID, expansion index, ancestor IDs, label/notes/source; `ResolvedScriptStage.provenance: Option<ScriptStageProvenance>`; inicjalizować `None` w `solver` i `synthetic`. | Kompilator odczytuje provenance każdego wykonania. W docelowym kontrakcie tego pola i typu jeszcze nie ma. Nie zmieniać wariantów closed-loop dodanych przez drugi wątek. |
| `crates/fullmag-application/src/script_stage_materialization.rs` | Import typu i `BTreeSet`; preflight `validate_pipeline_node_ids` przed mutacją/ekspansją, także dla wyłączonych poddrzew; rozszerzyć `walk_study_pipeline_nodes` o ancestor IDs, przekazywać `&[]` z korzenia i osobną kopię ścieżki dla grupy; oznaczać wynik primitive indeksem 0, a macro przez enumerate, zachowując label/notes/source. | Bez tego wyniki mają `None`, a kompilator odmawia. Duplikaty ID nie mogą zostać nadpisane w mapie ownerów; ścieżka grup nie może przenikać do rodzeństwa. Ekspansja i kolejność mutacji pozostają własnością istniejącego materializera. |
| `crates/fullmag-application/src/script_pipeline_compilation.rs` | Przenieść nowy moduł ze wskazanego SHA: inventory drzewa, wspólny hash, jednorazowa materializacja, walidacja provenance, przenośne `script-execution-<sha256>`. | W docelowym checkoutcie plik nie istnieje. Nie używać wcześniejszego ID z dwukropkiem, nie dodawać alternatywnej ekspansji ani automatycznego StudyPlan. |
| `crates/fullmag-application/src/lib.rs` | Dodać `mod script_pipeline_compilation;` i wyłącznie jego `pub use`: bounded materializer oraz cztery typy wyniku. | Udostępnia moduł konsumentom aplikacji. Nie kopiować całego bloku eksportów, bo zawiera inne zmiany artefaktów i planowania anteny. |

W źródle moduł kończy się `#[cfg(test)]` wskazującym `script_pipeline_compilation_tests.rs`. Zestaw gotowy do późniejszego budowania testów potrzebuje również tego pliku, ale jego pierwszy test wymaga osobnej decyzji opisanej niżej. Nie usuwać testowego include tylko po to, aby pozornie domknąć zależności.

Istniejące zależności wystarczające w docelowym źródle: `anyhow`, `serde_json`, standardowe `BTreeMap/BTreeSet`, `fullmag_ir::canonical_ir_json_sha256` (definicja w `crates/fullmag-ir/src/execution_profile.rs`, eksport przez `lib.rs`), publiczny `StageOutputPolicy` i `materialize_script_stages_with_output_policy_bounded`. Dla tego minimum **nie potrzeba** zmian Cargo.toml/lock, crate `fullmag-antenna-artifacts`, native ABI, runnera, Python ani completion dependencies. Dodanie pola do Rust typu nie zmienia wire JSON `StudyPipelineDocument`, ponieważ `ResolvedScriptStage` nie ma tu serde derive; zmienia natomiast wewnętrzny kontrakt konstruktora.

Odczyt `rg` konstrukcji `ResolvedScriptStage {` w docelowym `crates/` znalazł definicję, impl i funkcję zwracającą ten typ w testach CLI, nie dodatkowy literal wymagający pola. Przy przeniesieniu sprawdzić ponownie aktualny WIP oraz consumerów; ten odczyt nie zastępuje compiler gate. Docelowy materializer już zwraca pusty wynik dla authored empty/all-disabled pipeline, więc nie wymaga ponownej implementacji tej naprawy.

### Regresje i granica standalone anteny

`crates/fullmag-application/src/script_pipeline_compilation_tests.rs` ma dziewięć testów: osiem używa lokalnego `config()` i istniejących run/relax/set_current, a jeden `standalone_antenna_pipeline_replans_without_conflating_authored_and_physical_ids` odczytuje brakujący w docelowym worktree `tests/fixtures/runtime/antenna-standalone-pipeline.json`. Osiem testów ogólnych obejmuje drzewo/mutatory, deterministic ID, portable ID, duplicate/missing pipeline, empty/disabled, expansion budget, primitive-after-macro i ambiguous explicit/pipeline. Potrzebne są też hunki regresji provenance i duplicate IDs przy materializerze. Nie uruchomiono ich w tej iteracji.

Przeniesienie całego test suite bez adaptacji wymaga nie tylko fixture, ale również zgodnego standalone StudyIR i wyboru stage/port w fizycznym input. W diffie materializera występują związane z tym `standalone_antenna_study`, `resolve_script_until_seconds`, `normalize_stage_sampling`, flat/pipeline antenna action binding i helper walidacji referencji portu. **Nie należą do minimum kompilatora.** Należy kwalifikować je jako osobny pakiet antenowy z właścicielem planner/IR WIP. Alternatywa: wydzielić test fixture do osobnego pakietu kwalifikacyjnego, zachowując go jako otwartą bramkę, i przenieść osiem testów ogólnych wraz z minimum. Nie deklarować wtedy przejścia standalone anteny.

### Kolejność bez kopiowania historii

1. Zamrozić uzgodniony snapshot docelowego WIP i ponownie porównać hunki. Zaobserwowane SHA-256 bajtów docelowych plików: contract `8d438b3c9cd1a8faec7f0a1b65a09e134a3f1f3f33f5e82aebf393e4d5400a86`, materialization `cc0bbbf43737c92c8620160bc3abc45de2b29f3025b392fdf96077093e6dbaad`; są to identyfikatory odczytu, nie gwarancja niezmienności późniejszego WIP.
2. Przenieść wybrane hunki provenance/identity i nowy moduł/eksport w jednym spójnym commicie. Bez cherry-pick całego checkpointu `426d…`, bez kopiowania Cargo zmian, bez checkout nad dirty plikami. Odczyt source module SHA-256: `cde4dcd969499665cd3cec933a2e86e498bd2dcf31738193c5e9a69294083b2a`.
3. Przygotować regresje ogólne i jawnie rozstrzygnąć test standalone; nie zmieniać oczekiwań tak, by akceptowały brak provenance. Zakaz kompilacji unit tests nadal obowiązuje. Build produkcyjny, jeżeli zlecony, wyłącznie przez uzgodnionego runnera; source review nie jest jego zamiennikiem.
4. Dopiero osobno projektować typed accepted compiler i completion contract. Minimalny transfer powyżej nie zamyka B-02, ponieważ nadal brak producenta kompletnego StudyPlan/catalog i barier zakończenia.

## B-01 — różnica gałęzi po koordynacji

W równoległym worktree potwierdzono `crates/fullmag-runner/src/native_fem/charge_transport.rs::require_legacy_charge_only_publication`, dodany w `5d8b3721ac7a1eff9c2003a69406042c64f3e3b8`. `execute_native_fem_charge_transport` wywołuje go dla całego przygotowanego batcha przed native solve; odrzuca conservative current view, powiązane źródło Oersteda lub request bazy anteny. Jest to źródłowe zabezpieczenie przed publikacją mieszanych ownerów, nie realizacja wspólnej bazy. Nie uruchomiono tu native regresji. Historyczna B-01 w recenzji `426d…` pozostaje prawidłowo przypisana do tamtej gałęzi; nie wolno przenosić jej oceny bez sprawdzenia na nowszy WIP ani nazywać blokady ukończeniem reusable H/I.

## Dowody i ograniczenia tej iteracji

- `git diff --check` zmian kodu: exit 0. Staged archiwum ma sześć oryginalnych Markdown hard-breaks (dwie końcowe spacje w metadanych), zgłaszanych przez domyślne `diff --check`. Zachowano je świadomie, aby nie zmieniać tekstu audytu. Checkpoint nie ma takich wyjątków.
- ESLint sześciu zmienionych plików frontendowych, `--max-warnings=0`: exit 0.
- TypeScript `--noEmit --incremental false --project tsconfig.typecheck.json`: exit 0.
- Zapisano regresje komendy i composera DOM: odmowa multiport także przy jawnym wyborze portu, bez mutacji modelu i bez wysłania komendy; valid singleton nadal sprawdza pending/ACK. Testów nie uruchomiono: obowiązuje tymczasowy zakaz kompilacji testów jednostkowych.
- Odczyt UI `http://localhost:3197/workspace`: sesja „Simulation 2026-10-09 003546”, Objects 0, Study 0 stages. Nie zmieniano modelu i nie klikano Build backend. Nie ma na tej scenie materiału do regresji inspektora anteny. Browser qualification R-03: **NOT VERIFIED**.
- Raportowane w recenzji statusy CI badanego SHA nie zostały w tej iteracji niezależnie odtworzone. Brak dostępnego `gh`, a próba odczytu API nie dała wiarygodnego wyniku. Nie przypisujemy przyczyny awarii bez logów.
- Nie wykonano nowego native buildu, naukowego solve ani kwalifikacji LLG/FFT. Nie zamknięto żadnej pełnej bramki T00–T18 na podstawie tej poprawki.

Kolejność pozostaje M0→M6 z recenzji: wiarygodny pinned build, accepted compiler, durable V/J/H oraz UI, wspólne źródło podpisanej bazy, projekcja i LLG, źródłowe FFT, pełna kwalifikacja przeglądarkowa i release. Równoległe zadania nie mogą ukryć zależności między tymi bramkami.
