# Fullmag — instrukcje dla agentów

## Zakres i sposób pracy

Instrukcje dotyczą GPT-Astra, GPT-Sol, GPT-Luna oraz innych agentów pracujących w tym repozytorium. Zachowuj model i poziom rozumowania wybrane przez użytkownika lub hosta; nie zmieniaj ich na podstawie liczby plików.

- W granicach instrukcji systemowych i deweloperskich wykonuj intencję użytkownika. Jawne polecenia użytkownika mają pierwszeństwo przed wskazówkami skilli. Niniejszy plik określa zasady pracy; dokumenty naukowe określają zamierzoną fizykę, a bieżący kod i wyniki weryfikacji dowodzą stanu implementacji.
- Doprowadź autoryzowane zadanie do końca. Rutynowe, odwracalne decyzje rozstrzygaj na podstawie kodu i kontekstu. Pytaj, gdy brakująca odpowiedź istotnie zmienia zakres, publiczne zachowanie, bezpieczeństwo danych lub wcześniejszą decyzję użytkownika. Kontynuuj niezależne części pracy.
- Audyt lub plan bez zlecenia implementacji pozostaje tylko do odczytu. Jeżeli użytkownik zlecił również poprawki, nie zatrzymuj pracy na oddaniu planu ani na ponownym pytaniu o wykonanie.
- Przed edycją przeczytaj zmieniane pliki i ich istotnych konsumentów. Dla złożonej pracy podaj krótki plan z kryteriami weryfikacji. Dopasuj się do istniejących wzorców; poprawiaj przyczynę problemu, zachowując zakres zadania.
- Po powtarzającym się niepowodzeniu zmień hipotezę na podstawie dowodów. Sięgnij do aktualnej dokumentacji, gdy problem zależy od nieznanego narzędzia. Nie powtarzaj ślepo poleceń, nie wymagaj „100% pewności” ani resetu sesji jako rutynowej procedury.
- Raporty, plany, audyty i podsumowania artefaktów pisz po polsku. Komentarze kodu, nazwy zmiennych i komunikaty commitów pozostają po angielsku. Podawaj wynik, dowody i istotne ograniczenia bez pochwał, powtórzeń i ceremonialnych zakończeń.

## Ochrona pracy i uprawnienia

- Sprawdź tożsamość checkoutu i `git status --short`. Zachowaj cudze zmiany. Użyj izolacji dla szerokiej implementacji; jeżeli zadanie dotyczy aktywnej konfiguracji, edytuj wskazane pliki z kopią i kontrolą zmian.
- Dla zadania implementacyjnego w worktree użytkownik ustanawia domyślną autoryzację cyklu opisanego poniżej: commit, push brancha zadania, PR do `master`, merge i usunięcie wyłącznie zweryfikowanego worktree tego zadania. Jawne ograniczenie zadania (np. audyt, plan, tylko lokalnie, bez push/merge) ma pierwszeństwo. Pozostałe usuwanie danych, force-push i wiadomości zewnętrzne wymagają odrębnej autoryzacji. Nie obchodź sandboxa, branch protection ani automatycznej kontroli uprawnień.
- Przed każdym commitem w współdzielonym checkoutcie sprawdź `git diff --cached --name-only` w osobnym poleceniu. Rozwijaj skrócone identyfikatory przez `git rev-parse`. Nie wnioskuj o właścicielu worktree lub procesu wyłącznie z jego ścieżki.
- Nie usuwaj współdzielonych cache ani worktree bez sprawdzenia aktywnych użytkowników, procesów i mountów. Przed kasowaniem Cargo target uzyskaj aktualne potwierdzenie od każdego korzystającego agenta. Nigdy nie usuwaj worktree `target/`, gdy kontener bind-mountuje ten checkout.
- Nie zmieniaj tych instrukcji automatycznie po każdym błędzie. Dodawaj trwałe reguły na zlecenie użytkownika albo przy zmianie kontraktu w zakresie zadania; usuwaj duplikaty zamiast dopisywać kolejne ogólne zakazy.

## Obowiązkowy cykl pracy w worktree

- Przed implementacją odczytaj [pełną procedurę](docs/guides/fullmag-build-storage-governance.md#cykl-integracji-zadania) oraz skill `using-git-worktrees`. Ustal główny checkout przez Git; użyj lub utwórz jedno `worktrees/<task-id>` obok niego, branch `codex/<task-id>`, i zapisz właściciela, bazowy commit oraz cel w rejestrze. Buildy kieruj przez resolver do `storage/builds/<worktree-id>/<profile-id>`.
- Zakończenie implementacji uruchamia `finishing-a-development-branch`: wymagane testy i review → commit zmian zadania → push brancha → PR do `master` → wymagane kontrole i akceptacje PR → merge PR → przejście do głównego checkoutu na `master` i aktualizacja fast-forward → weryfikacja integracji → usunięcie worktree zadania przez `git worktree remove` → końcowy wpis w rejestrze. Nie kończ na „kod gotowy” ani na samym otwarciu PR, jeżeli pozostałe kroki są wykonalne.
- Nie wykonuj drugiego lokalnego merge po scaleniu PR. Zachowaj cudze zmiany w głównym checkoutcie. Przed usunięciem potwierdź scalenie PR, czysty worktree, brak unikalnej niezintegrowanej pracy i brak korzystających procesów/kontenerów/mountów. Nie stosuj `--force`, zbiorczego prune ani usuwania cache lub wyników jako skutku ubocznego.
- Merge na remote nie kończy lokalnego cyklu: po potwierdzeniu wynikowego commita przełącz lokalny główny checkout na `master`; jeżeli główny checkout jest niedostępny, możesz ustawić pierwotny worktree na wynikowy ref do weryfikacji, ale cleanup musi wykonać inny zachowany checkout. Z dostępnego cleanup executora usuń najpierw dokładnie ten zweryfikowany worktree, a dopiero potem lokalny zmergowany branch zadania. Jeżeli nie ma surviving cleanup executora albo aktywny proces, kontener, mount, dirty/untracked pliki lub obcy właściciel blokują cleanup, zapisz `blocked` z pełną przyczyną i nie przedstawiaj zadania jako zakończonego.
- Jeżeli CI, review, uprawnienia, dirty checkout lub aktywne zasoby blokują cykl, zapisz `blocked`/`review` z dokładną ścieżką, branchem, HEAD, linkiem PR, przyczyną i następnym krokiem. Zgłoś niedokończoną integrację; nie porzucaj worktree bez wpisu i nie oznaczaj całego zadania jako ukończonego.

### Commity w trakcie implementacji

- Commituj na branchu zadania po każdym ukończonym, spójnym fragmencie, który przeszedł adekwatną weryfikację; nie odkładaj wszystkich commitów do końca zadania. Jeden commit obejmuje jeden logiczny cel wraz z potrzebnymi testami i dokumentacją. Granicę wyznacza działający etap, nie liczba plików ani upływ czasu. Zmiany zależne, które osobno łamią build lub kontrakt, pozostają razem.
- Przed każdym commitem przejrzyj diff i wyniki kontroli, stage'uj wyłącznie zmiany tego fragmentu, a następnie w osobnym poleceniu sprawdź `git diff --cached --name-only` oraz staged diff. Nie dołączaj cudzych zmian, sekretów ani artefaktów builda. Komunikat po angielsku opisuje cel zmiany; w checkpointcie zadania zapisz pełny hash, zakres i dowody weryfikacji.
- Dla poprawki zachowania użyj odpowiednich testów; dla dokumentacji wystarczy adekwatna kontrola tekstu/linków/parsera. Nie powtarzaj niezmienionych zielonych testów wyłącznie z powodu commita. Zielony test fragmentu pozwala zapisać fragment, ale nie zastępuje wymaganych bramek integracji, runtime ani nauki przed merge. Nie nazywaj nieweryfikowanego WIP ukończonym etapem.
- Ta sama autoryzacja zadania obejmuje kolejne commity etapów; nie pytaj o każdy osobno. Commit etapu nie uruchamia osobnego merge ani usunięcia worktree: PR i integracja dotyczą całego uzgodnionego zadania. Jawne polecenie „bez commitów” ma pierwszeństwo.

## Kontrakt Fullmag

- Jeden publiczny Python DSL w `packages/fullmag-py`, jeden `ProblemIR`, wspólne jednostki SI, semantyka i provenance. UI musi eksportować kanoniczny, edytowalny skrypt.
- Oddzielaj cztery realizacje: FDM CPU, FDM GPU, FEM CPU, FEM GPU. Zachowuj requested intent i resolved execution. Wymuszone GPU nie może mieć cichego fallbacku CPU. `auto` nie może znikać z provenance.
- `docs/physics/` opisuje fizykę; `docs/specs/` i `docs/adr/` kontrakty aplikacji. `docs/architecture/backend-golden-masterplan.md` określa architekturę backendów. Sprzeczność dokumentów zgłoś i rozstrzygnij w jej zakresie; dokument planu nie jest dowodem działającego runtime.
- Przed dodaniem lub zmianą fizyki/numerics uzupełnij notę naukową. Dla tworzenia, zmiany, przeglądu lub publikacji dokumentacji naukowej agenci MUST use `scientific-documentation-contract`. Zachowaj równania, jednostki, parametry, Python→IR, mapy źródeł i bramki walidacji.
- Encje sceny mają oddzielne niezmienne `object_id`, nazwę użytkownika `name`, prezentacyjny `type` i jawnie zadane moduły fizyki. Nazwa lub typ nie aktywują fizyki.
- Control Room ma jeden workspace, jeden viewport, jeden klient typowany i warstwę resource hooks. JSON control plane jest cienki i revision-driven; pola i topologia używają binary data plane. Komponenty nie tworzą własnych endpointów ani osobnych drzew FDM/FEM.

## Build i dowody

- Tymczasowo nie buduj testów jednostkowych ani nie uruchamiaj zadań, których celem jest ich kompilacja; zakaz obowiązuje do odwołania przez użytkownika.
- Codzienny development Fullmaga wykonuj wyłącznie przez bezpośrednią ścieżkę Docker Compose: `python -B scripts/setup_docker.py`, `just docker-dev-toolchain`, `just docker-dev` oraz `just docker-dev-build`. Ta ścieżka używa natywnego Windows Python/PowerShell, Docker Desktop z silnikiem Linux i zarejestrowanego checkoutu jako bind mountu. Nie kieruj developmentu do `Fullmag_build_runner`, hostowego `cargo`/`cmake`, natywnego launchera Windows ani ręcznego Docker; wybór, storage, lock, provenance i końcowy receipt muszą przejść przez istniejący launcher oraz resolver. Jawne bramki release, GitHub CI/self-hosted i kwalifikacja naukowa zachowują własne, osobno udokumentowane zarządzane recepty.
- Dla Docker dev jawnie wybierz zarejestrowany checkout/worktree przez `--source-root` lub argument `just docker-dev`; launcher wyprowadza źródła i storage przez resolver, bez cichego fallbacku. Dla osobnych bramek release/CI/naukowych jawnie przypnij `snapshot` albo pełny SHA commita i użyj właściwej udokumentowanej recepty. Nie zamieniaj żądanego GPU na CPU. Testy lekkie i odrębne bramki runtime/nauki zachowują swoje recepty; sukces buildu nie zastępuje ich dowodów.

- Nowy worktree na tym samym hoście nie potrzebuje własnego `.env`: resolver ustala główny checkout przez Git i czyta jego plik. Instrukcja i `.env.example` są wersjonowane; wartości hosta pozostają lokalne. Dla nowego klona na innym hoście przed pierwszym buildem skonfiguruj `.env` głównego checkoutu według `.env.example`, zachowując istniejące ustawienia. Jeśli lokalizacja storage nie została określona, uzyskaj ją od użytkownika; nie kopiuj ścieżki z innego hosta ani nie traktuj fallbacku resolvera jako konfiguracji operatora.

- Fizyczną lokalizację storage hosta deklaruj przez `FULLMAG_PROJECT_STORAGE_ROOT` w lokalnym `.env` głównego checkoutu (szablon: `.env.example`). Worktree korzystają z tej samej konfiguracji przez resolver. Nie wpisuj stałych ścieżek Windows/Linux do instrukcji ani skilli i nie kopiuj całego `.env` do worktree. Buildy są podkatalogami rozwiązanego storage; jawne zmienne procesu, w tym mapowanie kontenera, mają pierwszeństwo i podlegają tej samej walidacji.

- Przed wyborem polecenia builda czytaj `justfile`. Docker dev używa `just docker-dev-toolchain`, `just docker-dev` i `just docker-dev-build`; natywne FEM/MFEM/CUDA/hypre/libCEED pozostają container-backed i używają właściwej zarządzanej recepty wyłącznie dla jawnych bramek release/naukowych. Hostowe `cargo`, `cmake`, bezpośrednie binaria i ręczny Docker nie są ścieżką kwalifikacji.
- Docker dev uruchamiaj z natywnego Windows PowerShell przez Docker Desktop w trybie kontenerów Linux; WSL może czytać i edytować checkout, ale nie uruchamia `scripts/docker_dev.py` ani `scripts/setup_docker.py` jako ścieżki startu. Wszystkie nowe kontrolowane dane kieruj do kanonicznego `storage` projektu; `FULLMAG_WINDOWS_*_ROOT` pozostaje wyłącznie zwalidowanym adapterem zgodności i nie może tworzyć alternatywnych rootów poza konfiguracją.
- Przed buildem, uruchomieniem lub porządkowaniem storage przeczytaj [reguły backendu i wykonania](.agents/instructions/backend.md), w tym dokładne ścieżki Linux/Windows. Linuxowy runner nigdy nie buduje bezpośrednio na CIFS. Prune jest domyślnie tylko dry-run przez `FULLMAG_RUNTIME_DRY_RUN=1`; usunięcie wymaga autoryzacji.
- Obowiązująca polityka worktree, profili buildów, `justfile`, cache, runów i sprzątania znajduje się w [Fullmag build-storage governance](docs/guides/fullmag-build-storage-governance.md). Resolver wyprowadza project root ze wspólnego katalogu Git głównego checkoutu; `storage` i `worktrees` są jego rodzeństwem. Przed utworzeniem worktree sprawdź rejestr i użyj istniejącej izolacji; bez automatycznego `fetch`/`pull`/bootstrapu.
- Każdy build/run z `justfile`, również ręczny, musi wykonać preflight ścieżek i zarejestrować stan końcowy przed zgłoszeniem zgodności. Instrukcje dokumentują kontrakt, lecz wrapper, preflight i sandbox są właściwą granicą techniczną; brak podpięcia danej recepty oznacz `NOT VERIFIED`.
- Dobierz testy do zmiany i wykonaj obowiązkowe bramki projektu. Dla błędu nietrywialnego zachowaj wykonywalny regression check. Dla zmiany tekstu lub formatowania stosuj adekwatny diff/parser/render check zamiast testu powtarzającego implementację.
- Odczytaj wynik i exit code. Ponawiaj lub rozszerzaj zielone testy tylko po istotnej zmianie, awarii albo nierozstrzygniętej obawie. Wynik pozostaje dowodem dla niezmienionych źródeł, wejść i warunków; nie trzeba uruchamiać go ponownie w każdej wiadomości.
- Rozdzielaj testy źródeł/kontraktów, managed runtime, browser/WebGL, walidację fizyki i kwalifikację wydania. Brakująca wymagana ścieżka to `NOT VERIFIED`. Testy lokalne, zbudowana siatka i wykryte GPU nie dowodzą wykonania ani parytetu.
- Zmiany viewportu wymagają dowodu z przeglądarki: widoczny canvas, niezagubiony kontekst WebGL i niezerowy drawing buffer. Zmiany mutacji Inspectora wymagają stabilności panelu i kontroli Object/Airbox opisanych w regułach frontendowych.

### Docker Compose — jedyna ścieżka codziennego developmentu

Na nowym hoście uruchom z natywnego PowerShella `python -B scripts/setup_docker.py`.
Kreator zapisuje wybrany `FULLMAG_PROJECT_STORAGE_ROOT`, checkout źródeł i port
frontendu do lokalnego `.env` głównego checkoutu; nie buduje, nie uruchamia i nie
usuwa kontenerów. Sprawdzenie bez zapisu wykonuje `python -B scripts/setup_docker.py --check`.

Po konfiguracji używaj:

```powershell
just docker-dev-toolchain
just docker-dev "<absolutny-checkout-lub-worktree>" 3197
```

`just docker-dev` buduje backend w usłudze Compose i uruchamia prywatną grupę
`backend`/`frontend`. Wybrany checkout jest zarejestrowany w Git, montowany
readonly do obu usług i pozostaje źródłem HMR frontendu. `just docker-dev-build`
wykonuje kolejną jawną kompilację backendu z cache, bez restartu aktywnej grupy
ani symulacji. Zmiana backendu nie uruchamia builda automatycznie; zastosowanie
nowego pakietu wymaga kontrolowanego, jawnego startu po bezpiecznym zatrzymaniu.

Bez `just` użyj natywnego Pythona: `python -B <main>\scripts\bootstrap_docker_toolchain.py --repo-root <main> --direct-development`, następnie `python -B <main>\scripts\docker_dev.py --repo-root <main> up --source-root <worktree> --port <port>` (start), `python -B <main>\scripts\docker_dev.py --repo-root <main> build --source-root <worktree>` (sam cache build) albo `python -B <main>\scripts\docker_dev.py --repo-root <main> up --source-root <worktree> --port <port> --script <script>` (start ze skryptem). Główna grupa Compose to `fullmag-master`, worktree otrzymuje `fullmag-worktree-<worktree_id>`; port wybiera operator i musi być unikalny, launcher go nie dobiera automatycznie.

Frontend publikuje wyłącznie wybrany port loopback hosta, a backend jest dostępny
tylko jako `backend:8081` w prywatnej sieci tej grupy. Projekt Compose, sieć,
port i `workspace.db` są izolowane per checkout; sesje, wyniki, logi, cache i
receipty pozostają w resolverze storage. Launcher odrzuca kolizję portu lub
aktywną grupę i nie wykonuje automatycznego restartu, przejęcia ani resetu.

Skrypt startowy jest opcjonalnym argumentem trzecim `just docker-dev` i jest
rozwiązywany względem wybranego checkoutu:

```powershell
just docker-dev "<absolutny-worktree>" 3197 "examples/fem_relax_gpu_smoke.py"
```

Walidacja ścieżki, hasha, provenance i odpowiedzi API pozostaje fail-closed.
Skrypt z `study.wait_for_solve(True)` (przykład:
`examples/fem_de_smoke_numeric.py`) kończy aktywację w stanie oczekiwania na
Compute; nie jest to cichy fallback ani dowód wykonania GPU. WSL służy tu do
edycji i diagnostyki źródeł; start, build i konfigurację Docker dev wykonuj
z natywnego Windows PowerShella.

Profil `dev` używa `backend-dev`, `live-shadow-v1`, trwałego cache i bind mountu
źródeł. Profil `release`/`frozen` jest osobną, przypiętą ścieżką archiwum i
kwalifikacji; nie używaj go do codziennej iteracji. Piny toolchaina są źródłowo
w `docker/fem-gpu/Dockerfile`, `rust-toolchain.toml`, manifestach Cargo,
repozytoryjnym `Cargo.lock`, `packages/fullmag-py/pyproject.toml` oraz
`apps/control-room/package.json` z repozytoryjnym `pnpm-lock.yaml`;
`docker-dev-toolchain` korzysta z tych deklaracji w kontenerze.

Szczegółowy kontrakt znajduje się w
[Docker development architecture](docs/guides/docker-development-architecture.md).

## Sprzątanie danych po etapie deweloperskim

- Po zakończeniu etapu (także błędem lub anulowaniem) i przed kolejnym ciężkim buildem oceń dane wygenerowane przez ten etap. Użyj skilla `fullmag-build-stage-cleanup`; jeżeli nie jest dostępny, zastosuj reguły retencji z build-storage governance i zgłoś brak skilla.
- Najpierw kwalifikuj zakończone `execution`, następnie zbędny staging i kopie źródeł, a potem zastąpione pakiety runtime. Przestarzałość oznacza wykazaną zbędność: sam wiek, rozmiar lub nowszy commit nie wystarczają. Zachowaj używany cache przyrostowy, ostatni zweryfikowany pakiet i dane referencjonowane przez wyniki, projekty, sesje lub rollback.
- Przed wykonaniem autoryzowanego planu ponownie sprawdź stan jobów, aktywne procesy, kontenery, mounty, lease oraz dokładne cele w rozwiązanym storage. Zachowaj wyniki, logi, receipty, manifesty i provenance. Nie rozszerzaj zgody na inne katalogi ani nie używaj globalnego prune.
- W checkpointcie etapu zapisz decyzję dla każdego kandydata, dowód zbędności, zachowywane dane, plan/receipt i pomiar wolnego miejsca. Dla pozostawionych danych podaj warunek ponownej oceny. Preview ani zapis skilla nie dowodzą wykonania lub wdrożenia automatycznego sprzątania.

## Szczegółowe reguły — ładuj według zakresu

Poniższe pliki są wiążącym rozwinięciem tego AGENTS.md. Przed zmianą lub oceną danego obszaru przeczytaj właściwe sekcje; nie ładuj całego zestawu dla każdego zadania. Ścieżki kodu zapisane w backtickach są względem repozytorium.

| Zakres zadania | Reguły do odczytu |
|---|---|
| Architektura, publiczny Python/IR, runtime, planowanie, cross-layer refaktor, kryteria ukończenia | [Kontrakty aplikacji](.agents/instructions/contracts.md) — sekcje właściwe dla zmiany |
| Backend, FEM/FDM, siatka, relaksacja, integratory, eigensolve, build, launcher, storage | [Backend i wykonanie](.agents/instructions/backend.md) |
| `apps/control-room`, API v2, resource hooks, workspace, Inspector, wykresy, viewport | [Frontend i API](.agents/instructions/frontend.md) |
| Fizyka, metody numeryczne, dokumentacja naukowa, publiczne przykłady i referencje | [Publikacje i przykłady](.agents/instructions/scientific.md) oraz właściwy skill domenowy |

W `.agents/skills` wybierz skill pasujący do konkretnej czynności. Dla backendów używaj `backend-golden-masterplan`, dla obecnego FEM również `fem-native-backend-architecture`; dla API/workspace `resource-first-api-check` i tylko właściwe `frontend-v2-*`; dla Python/IR odpowiednio `python-api-class` i `problem-ir-design`.

## Kontekst, delegacja i review

- Czytaj skill wskazany przez użytkownika lub istotny dla zadania. Nie ładuj go ponownie bez zmiany treści ani równocześnie z jego duplikatem pluginowym. Referencje w skillu ładuj, gdy konkretny krok ich potrzebuje; nie uruchamiaj łańcucha wszystkich workflow.
- Jeśli skill rzeczywiście powoduje zatrzymanie lub dodatkowe pytanie, wskaż dokładny plik i regułę oraz wyjaśnij ich zastosowanie. Nie interpretuj sugestii jako dodatkowego wymogu zatwierdzenia.
- Preferuj `rg`, ograniczone odczyty i wspólne wykonanie niezależnych wyszukiwań. Zachowuj pełny istotny błąd, ale nie drukuj całych katalogów, sekretów i niepowiązanych logów. Narzędzia dostępne w sesji są źródłem prawdy o możliwościach hosta.
- Deleguj istotne, niezależne podzadanie, gdy host pozwala i podział oszczędza czas lub poprawia jakość. Nie twórz agentów dla formalności. Przekaż zakres, ograniczenia, pliki i wymagane dowody; koordynuj wspólne zapisy, staging i zasoby builda. Zachowaj ustawienia modeli użytkownika.
- Długą pracę kontynuuj z krótkiego checkpointu: cel, decyzje, zakończone kroki, dowody i pozostałe zadania. Nie powtarzaj ukończonej pracy po kompakcji.
- Dla review, PR, commit description i odpowiedzi na review używaj `google-eng-review-practices`. Sprawdź poprawność, zakres, kontrakty i dowody. Rozmiar pliku jest sygnałem do review, nie automatycznym nakazem podziału.
