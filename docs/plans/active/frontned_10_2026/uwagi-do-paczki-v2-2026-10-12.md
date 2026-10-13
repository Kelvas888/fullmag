# Przegląd poprawionej paczki geometria/mesh v2 — 12.10.2026

## Ocena

**Kierunek refaktoryzacji jest teraz zrozumiały.** V2 zawiera odpowiedzi na wszystkie Q01–Q24, wyraźnie oddziela istniejący kod od propozycji, rozpisuje 20 PR-ów i 72 planowane scenariusze. Najważniejsza sprzeczność v1 została usunięta: w docelowym R1 pointerup kończy gest w draftcie, a wspólne Apply zapisuje geometrię i pełny transform jednego obiektu.

Potrafię na tej podstawie zaplanować wykonanie. Przed rozliczaniem poszczególnych PR-ów należy poprawić poniższe powiązania i doprecyzować scenariusze graniczne. Nie ma potrzeby ponownego otwierania wszystkich 24 pytań ani przepisywania całej dokumentacji.

Proponowane ADR-y pozostają propozycjami. Przesłanie paczki jest kontynuacją przeglądu; nie traktuję go jako zatwierdzenia nowych zachowań produktu, wdrożenia ani operacji Git. Przed implementacją potrzebne będą decyzje właściwe dla uruchamianego etapu, aktualna mapa konsumentów i dowody zgodne z obowiązującymi regułami repozytorium.

## Co zostało rozstrzygnięte

| Obszar poprzednich uwag | Odpowiedź v2 | Ocena dokumentacji |
|---|---|---|
| Granica gest/Apply i zakres dostawy | Wewnętrzny R0 zachowuje obecny zapis; R1 wprowadza staged draft i jedno Apply; TRS/import/quality mają osobne R2 | Jasne; skorygować testy R0 opisane niżej |
| Atomowa edycja | Reuse istniejącego PatchObjectGeometry z geometrią i pełnym Transform3D; brak nowego ogólnego batcha | Poprawna korekta v1; CAS/trwałość wymagają kwalifikacji |
| Własność draftu, ACK, rebase, zmiana widoków | Kernel objectEdits, Inspector jako adapter, identyfikatory epoki/intencji, zachowanie post-submit edits, trzystronne scalanie | Wystarczająco konkretne do implementacji po decyzji produktowej |
| API i recovery | Osobne receipt dla ordinary mutations, brak ślepego ponawiania unknown, jawnie zdegradowana historia | Jasne; proponowanego API nie przedstawiono jako istniejącego |
| TRS/pivot/Python/IR/fizyka | Istniejące pola nie oznaczają istniejącego lowering; pivot-v1, kolejność rotacji, round-trip, world/local frames i cztery realizacje | Dobry kontrakt docelowy; nie jest dowodem działających evaluatorów |
| Mesh/grid i generacje | Osobne presence/delivery/assessment, legacy adapter, serwerowe digesty, marker aktywacji, ElementRef i jawny Build Selected scope | Jasne; brak optional quality nie udaje błędu topologii |
| Import/reimport | Stage oddzielny od obiektu, limits/lease, logical asset refs, wersjonowanie źródeł i osierocone region bindings | Wyraźne granice i wymagane punkty integracji |
| Wydajność i odbiór | Baseline przed budżetami, fixtures, SHA i środowisko, browser/WebGL/runtime/physics jako osobne dowody | Prawidłowo zachowano NOT VERIFIED dla niewykonanych bramek |

## Pozostałe uwagi do poprawienia przez Chat Pro

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

- Paczkę bezpiecznie rozpakowano do nowego katalogu fullmag_frontend_audit_v2_2026-10-12. V1 i zawartość v2 pozostawiono bez zmian. Niniejszy raport jest oddzielnym plikiem.
- Manifest: 76/76 wpisów zgodnych po normalizacji separatorów; bez różnic inventory i hashy. Powiązania PR↔test mają zgodne referencje w obu kierunkach. Ta kontrola sprawdza strukturę, nie poprawność znaczenia przypisań V2-01/V2-02.
- Dostarczony check_package.py: FAIL na Windows wyłącznie dla inventory separators; pozostałe jego kontrole nie zgłosiły błędów. Dostarczony check_spec_oracles.py: PASS, exit 0, dziesięć kontroli niezależnej algebry i reguł dokumentacji.
- Nie uruchomiono aplikacji Fullmag, testów produkcyjnych, WebGL, meshera ani kwalifikacji fizyki. Nie kompilowano unit tests. Wyniki oracle nie zamykają żadnego Txx wymagającego produkcji.
- Dokumenty v2 opisują snapshot 2a3c6becb9c7e111ae1497ec0cd9ac9576acba95. To przegląd poprawionej specyfikacji i jej powiązań, nie pełny ponowny audyt aktualnego dirty checkoutu ani potwierdzenie wszystkich proponowanych ścieżek backendu.

## Tekst do przekazania Chat Pro

Paczka v2 rozwiązuje główne problemy wcześniejszego przeglądu; kierunek i zakres refaktoryzacji są jasne. Proszę o małą rewizję v2.1, bez przepisywania całego planu:

1. Rozdziel odbiór PR03/R0 immediate commit od staged R1: T25 i pozostałe wspólne testy muszą mieć jawne warianty etapowe.
2. Napraw przypisania numerów PR: encoder/digesty w D06:58 oraz TRS→ProblemIR w D13:14, zgodnie z kartami D07 i backlog.json.
3. Napraw fixture T56: przypadek 1 pm/no-op jest w numeric_oracles.json.
4. Dopisz wykonywalne sekwencje odbioru A→B→A z nową epoką i usunięcia targetu podczas pending; deklaracja session_ABA już istnieje, potrzebuje zdarzeń i wyników.
5. Napraw walidator manifestu na Windows przez as_posix(); obecne FAIL wynika z separatorów, a niezależna kontrola 76 hashy jest zgodna.
6. Wyjaśnij relację czystego resolvera ArtifactAssessment w shared/domain do resource ownera/selectorów w kernel.

Zachowaj status proposed ADR, planned_not_run dla testów produkcyjnych oraz rozdzielenie oracle dokumentacji od runtime/browser/physics. Po poprawkach podaj krótką tabelę ID uwagi → zmienione pliki → kontrola; zaktualizuj manifest po ostatecznych edycjach. Nie przedstawiaj tej rewizji jako implementacji ani kwalifikacji Fullmaga.
