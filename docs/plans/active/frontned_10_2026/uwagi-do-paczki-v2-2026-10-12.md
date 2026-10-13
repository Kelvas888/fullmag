# Przegląd poprawionej paczki geometria/mesh v2 — 12.10.2026

## Ocena

**Kierunek refaktoryzacji pozostaje zrozumiały.** V2 odpowiada na Q01–Q24, oddziela stan kodu od propozycji, rozpisuje 20 PR-ów i 72 planowane scenariusze. W tym task worktree doprecyzowano rozjazdy przypisań i scenariusze graniczne wskazane w pierwszym przeglądzie; zmiany nie są implementacją produktu.

Po tych korektach można przejść do realizacji R0/R1 zgodnie z D07. Pozostałe propozycje ADR nadal wymagają decyzji właściwych dla etapów, a kwalifikacja musi opierać się na osobnych dowodach.

Proponowane ADR-y pozostają propozycjami. Przesłanie paczki jest kontynuacją przeglądu; nie traktuję go jako zatwierdzenia nowych zachowań produktu, wdrożenia ani operacji Git. Przed implementacją potrzebne będą decyzje właściwe dla uruchamianego etapu, aktualna mapa konsumentów i dowody zgodne z obowiązującymi regułami repozytorium.

## Co zostało rozstrzygnięte

| Obszar poprzednich uwag | Odpowiedź v2 | Ocena dokumentacji |
|---|---|---|
| Granica gest/Apply i zakres dostawy | Wewnętrzny R0 zachowuje obecny zapis; R1 wprowadza staged draft i jedno Apply; TRS/import/quality mają osobne R2 | Testy R0/R1 są jawnie rozdzielone w D07/D08 |
| Atomowa edycja | Reuse istniejącego PatchObjectGeometry z geometrią i pełnym Transform3D; brak nowego ogólnego batcha | Poprawna korekta v1; CAS/trwałość wymagają kwalifikacji |
| Własność draftu, ACK, rebase, zmiana widoków | Kernel objectEdits, Inspector jako adapter, identyfikatory epoki/intencji, zachowanie post-submit edits, trzystronne scalanie | Wystarczająco konkretne do implementacji po decyzji produktowej |
| API i recovery | Osobne receipt dla ordinary mutations, brak ślepego ponawiania unknown, jawnie zdegradowana historia | Jasne; proponowanego API nie przedstawiono jako istniejącego |
| TRS/pivot/Python/IR/fizyka | Istniejące pola nie oznaczają istniejącego lowering; pivot-v1, kolejność rotacji, round-trip, world/local frames i cztery realizacje | Dobry kontrakt docelowy; nie jest dowodem działających evaluatorów |
| Mesh/grid i generacje | Osobne presence/delivery/assessment, legacy adapter, serwerowe digesty, marker aktywacji, ElementRef i jawny Build Selected scope | Jasne; brak optional quality nie udaje błędu topologii |
| Import/reimport | Stage oddzielny od obiektu, limits/lease, logical asset refs, wersjonowanie źródeł i osierocone region bindings | Wyraźne granice i wymagane punkty integracji |
| Wydajność i odbiór | Baseline przed budżetami, fixtures, SHA i środowisko, browser/WebGL/runtime/physics jako osobne dowody | Prawidłowo zachowano NOT VERIFIED dla niewykonanych bramek |

## Ustalenia przeglądu v2 przed korektą

Poniższe V2-01–V2-05 zachowują zapis pierwotnych obserwacji i próśb z pierwszego przeglądu. Stan ich realizacji w task worktree podsumowano w końcowej tabeli.

### V2-01 — rozdzielić bramki R0 i R1 [P2]

**Dowód:** [D07:99–109](fullmag_frontend_audit_v2_2026-10-12/docs/07_PLAN_WDROZENIA.md#pr03--zabezpieczenie-obecnego-move--r0) opisuje PR03 jako wewnętrzny hotfix zachowujący istniejące zakończenie gestu. Jego odbiór w linii 107 wskazuje jednak T25. [T25 w tests.json, od linii 729](fullmag_frontend_audit_v2_2026-10-12/tests.json) wymaga „Move draft → Apply → Undo → Redo” i braku wpisu historii na pointerup. To docelowa semantyka PR07/R1, której PR03 sam nie wdraża. T18 także opisuje R1 i wymaga interpretacji etapowej.

**Prośba:** dodać jawne warianty odbioru R0 i R1 albo rozdzielić identyfikatory testów. Dla R0 sprawdzić serializację, fence, no-op, obsługę błędów i historię przy obecnym immediate commit. Dla R1 sprawdzić pointerup bez zapisu i jedno Apply. Zsynchronizować D02/D07/D08, backlog.json i tests.json.

**Oczekiwany rezultat:** PR03 można odebrać bez wdrażania PR07; zaliczenie R0 nie oznacza zaliczenia staged R1. Jeden test przypisany do wielu PR-ów musi wskazywać, co jest bramką danego etapu, a co dopiero bramką integracji.

### V2-02 — poprawić przypisania właścicieli do numerów PR [P2]

**Dowód:** [D06, linia 58](fullmag_frontend_audit_v2_2026-10-12/docs/06_MESH_WORKFLOW_I_JAKOSC.md) przypisuje canonical binary encoder do PR08. D07 definiuje PR08 jako pierwszy build i konserwatywny resolver, natomiast PR09 — digesty, generacje i marker aktywacji. [D13, linia 14](fullmag_frontend_audit_v2_2026-10-12/docs/13_TRANSFORMACJE_I_KWALIFIKACJA_FIZYCZNA.md) przypisuje mapowanie ProblemIR/DTO/consumers do PR09, mimo że TRS i lowering przypisano do PR13/PR14.

**Prośba:** wskazać jednoznacznie PR09 dla encodera/digestów oraz właściwego właściciela PR13/PR14 dla TRS→IR. Jeśli rozdział pracy jest celowy, opisać deliverable i zależność w obu kartach PR, zamiast pozostawiać sprzeczne odsyłacze. Przejrzeć wszystkie numery PR po renumeracji.

**Oczekiwany rezultat:** żadna konieczna zmiana nie trafia do niewłaściwego etapu ani nie zostaje pominięta, ponieważ oba zespoły uznają ją za cudzą odpowiedzialność.

### V2-03 — naprawić fixture T56 [P2]

**Dowód:** [D08, linia 98](fullmag_frontend_audit_v2_2026-10-12/docs/08_TESTY_I_REPRODUKCJE.md) i T56 w tests.json wskazują transform_oracles.json dla „1 pm przy 100 nm nie jest no-op”. Konkretne dane tego przypadku i reguła epsilon są w [numeric_oracles.json](fullmag_frontend_audit_v2_2026-10-12/fixtures/numeric_oracles.json), w sekcji no_op. Transform fixture zawiera przykład TRS, nie ten przypadek no-op. D08:116 wskazuje już poprawnie NUM-01 dla parsera/no-op.

**Prośba:** przypisać numeric_oracles.json do T56 lub jawnie wskazać obydwa fixtures z zakresem każdego. Zaktualizować odsyłacze w JSON i Markdown razem.

**Oczekiwany rezultat:** driver T56 otrzymuje rzeczywiste wejście a/b/Lchar/epsilon i może sprawdzić no-op bez samodzielnego odtwarzania danych z prose.

### V2-04 — zamienić deklaracje ABA/usunięcia targetu na sekwencje odbioru [P2]

**Dowód:** D04:56 wymaga ogrodzenia epoki dla A→B→A, a D04:100 opisuje TARGET_DELETED. T06 opisuje zmianę sesji A→B przy tym samym objectId. [authoring_sequences.json:74](fullmag_frontend_audit_v2_2026-10-12/fixtures/authoring_sequences.json) zawiera już deklarację session_ABA, więc nie brakuje tej zasady; brakuje równie konkretnej sekwencji jak dla podstawowej edycji. Nie znalazłem osobnego, jednoznacznego scenariusza odbioru usunięcia targetu podczas pending zapisu.

**Prośba:** rozszerzyć T06 lub dodać scenariusze: submit w A/epoch1 → B → A/epoch2 → późny ACK epoch1; oraz submit → usunięcie targetu przez innego autora → odpowiedź/receipt. Podać kolejność zdarzeń i oczekiwany draft, baseline, selekcję, historię oraz dostępność Apply. Rozróżnić potwierdzony commit sprzed usunięcia od odrzuconego zapisu do już usuniętego obiektu.

**Oczekiwany rezultat:** późny wynik nie wskrzesza targetu ani starego draftu; wykonany wcześniej efekt pozostaje poprawnie rozliczony bez fałszywego sukcesu edytora.

### V2-05 — poprawić przenośność walidatora paczki [P3]

**Dowód odtworzony na Windows:** verification/check_package.py kończy się exit 1 i zgłasza Manifest inventory mismatch. W [linii 67](fullmag_frontend_audit_v2_2026-10-12/verification/check_package.py) używa str(p.relative_to(ROOT)); Windows daje separatory backslash, a manifest używa slash. Niezależne porównanie po normalizacji wykazało zgodność wszystkich 76 plików i ich SHA256. Nie jest to uszkodzenie archiwum.

**Prośba:** zastosować p.relative_to(ROOT).as_posix() dla kluczy manifestu i sprawdzić walidator na Windows oraz Linux. Zachować historię wyników; nie przepisywać nieudanego uruchomienia jako PASS.

**Oczekiwany rezultat:** identyczna paczka przechodzi kontrolę inventory na obu hostach; kontrola zawartości nadal wykrywa rzeczywistą zmianę pliku.

### Doprecyzowanie bez blokowania planu — warstwy ArtifactAssessment

[D06:93](fullmag_frontend_audit_v2_2026-10-12/docs/06_MESH_WORKFLOW_I_JAKOSC.md) podaje kernel/resources/artifactAssessment.ts i selector, natomiast PR08 wskazuje shared/domain/mesh/artifactAssessment.ts. Mogą to być poprawnie rozdzielone warstwy. Dopisać jedno zdanie: shared/domain zawiera czysty resolver, kernel/resources zarządza zasobami i subskrypcją, selector udostępnia wynik konsumentom. Unikniemy dwóch niezależnych implementacji reguł freshness.

## Weryfikacja i ograniczenia

- Pierwotna paczka i V1 pozostają zachowane; korekty v2 znajdują się w wyznaczonym task worktree. Niniejsza notatka pozostaje osobnym plikiem poza manifestem paczki.
- Pierwotny wynik walidatora na Windows wskazywał problem separatorów. Po zastosowaniu ścieżek POSIX i jawnego UTF-8 uruchomiono kontrolę strukturalną oraz pełny walidator; oba aktualne wyniki są zapisane poniżej.
- historyczne pliki verification/package_checks.json i verification/original_archive_check.json nie zostały nadpisane. Manifest odświeżono dla 76 plików paczki; walidator potwierdził inventory, SHA256, referencje i 122 lokalne linki.
- Nie uruchomiono aplikacji Fullmag, testów produkcyjnych, WebGL, meshera, solvera ani kwalifikacji fizyki. Nie kompilowano testów jednostkowych. Wszystkie 72 testy produktu nadal mają status planned_not_run.
- check_spec_oracles.py nie był ponownie uruchamiany w tym tasku. Historyczne wyniki oracle dokumentacji nie zamykają żadnego Txx wymagającego produkcji.
- Dokumenty opisują snapshot 2a3c6becb9c7e111ae1497ec0cd9ac9576acba95; kontrola bieżącego kodu aplikacji ani dirty checkoutu nie była częścią tej korekty dokumentacji.

## Stan korekt w task worktree

| Uwaga | Wprowadzona korekta | Kontrola |
|---|---|---|
| V2-01 | D07, D08, backlog.json, tests.json i findings.json oddzielają immediate Move R0 od staged R1. T18/T19/T20/T26 mają kryteria etapowe; T25 należy do PR07/PR12. | Referencje PR↔test sprawdzone przez check_package.py. |
| V2-02 | D06 przypisuje canonical digest encoder do PR09 i rozdziela czysty resolver ArtifactAssessment od właściciela zasobów. D13/D07 przypisują mapowanie geometry→ProblemIR/DTO do PR13, a konsumentów lane do PR14. | Sekcje D06/D07/D13 zsynchronizowane. |
| V2-03 | T56 jest testem parsera/no-op SI przypisanym do PR04/PR07 z fixtures/numeric_oracles.json; usunięto go z mapowania PR03 i PR15 oraz z testu snap. | Fixture i mapowania JSON/Markdown sprawdzone. |
| V2-04 | T06 i authoring_sequences.json zawierają konkretne A→B→A z późnym ACK oraz osobne gałęzie delete-wins i commit-wins; D04 podaje stany target-missing, draftu, selekcji, historii i Apply. | JSON parsuje się; zachowano identyfikatory testów. |
| V2-05 | verification/check_package.py normalizuje ścieżki przez as_posix() i jawnie odczytuje UTF-8; manifest odświeżony bez zmiany inventory. | Kontrola strukturalna PASS; pełny walidator PASS. |
| ArtifactAssessment | shared/domain zawiera czysty resolver snapshotów; kernel/resources ładuje i subskrybuje zasoby; selector udostępnia stan konsumentom. | Granica opisana w D06 i PR08. |

## Bieżące dowody

- python verification/check_package.py --structural — PASS; 28 findings, 32 sources, 20 PR-ów, 72 testy, 24 pytania, 122 lokalne linki, 4 historyczne reprodukcje bez zmian.
- python verification/check_package.py — PASS; 76 wpisów manifestu, wszystkie inventory/SHA256 i referencje poprawne.
- package_checks.json i original_archive_check.json pozostały bez zmian jako zapis wcześniejszych wyników. PASS z tego tasku pochodzi z nowego uruchomienia walidatora, nie z podmiany historii.
- Żadne testy produktu nie zostały uruchomione. Status wszystkich Txx pozostaje planned_not_run; WebGL, API runtime, mesher, solver i kwalifikacja fizyczna pozostają NOT VERIFIED.

