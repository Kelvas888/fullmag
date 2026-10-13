# Inspector actions and template — checkpoint

## Cel i izolacja

Naprawić routing semantycznych węzłów, rzeczywiste Apply/Revert oraz wspólny
kontrakt wariantów Inspectorów, zachowując wzorzec Visualization i kanoniczne
zasoby. Użytkownik dodatkowo zgłosił dekoracyjne przyciski dolnego paska.

- Worktree: `C:/git/fullmag/worktrees/inspector-actions-template-20261013`.
- Branch: `codex/inspector-actions-template-20261013`.
- Base: `27c43be1315bb70018a24b42aa15eec3cec6bc3e`.
- Rejestr: `storage/index/inspector-actions-template-20261-cece1930e1d3431d.json`.
- Główny dirty checkout chroniony; nie przenoszono cudzych zmian.

## Podział

- Koordynator: shell/footer, semantyczny routing z typed carrier ref,
  wspólne CSS i kontrakt w specyfikacji.
- Worker paneli: kompletna inwentaryzacja trybów i połączenie pominiętych draftów
  z rzeczywistym commit/reset; osobny ledger.
- Worker browser: produkcyjny Shell/Footer w kontrolowanych fixture,
  pending/ACK/rejected/invalid/live/read-only, Object/Airbox, layout i stabilność.

## Kryteria odbioru

Apply wykonuje faktyczny commit tylko w staged, Revert odtwarza baseline,
nieudany zapis zachowuje draft. Live display nie pokazuje Apply, immediate
korzysta z nazwanych operacji panelu, read-only nie ma atrap edycji. Isolate nie
jest reklamowany bez handlera. Fit view odpowiada istniejącemu poleceniu fit.
Unassigned rodzic i część wybierają swoje widoki bez zmiany adresowania mesh.
Brak opacity transitions na sekcjach. Source/lint, browser fixtures i obowiązkowe
CI/review muszą mieć aktualne dowody przed merge. Fixture nie dowodzi backendu.

## Weryfikacja dotychczasowa

`git diff --check`: PASS dla pierwszego fragmentu. Dodano regression checks
selectExplorerNode -> Inspector route -> visualization target; nie uruchamiano
ani nie kompilowano testów jednostkowych zgodnie z zakazem użytkownika.

Lokalne source/browser checks jeszcze NOT VERIFIED: brak zależności w nowym
worktree i w sprawdzonych wcześniejszych namespace storage. Linki storage
przygotowane przez resolver. `fullmag_storage.py run ... pnpm install` odmówiło:
`Container runner owns heavy builds on this host; submit a snapshot through just runner-build`.
`local_runner_cli.py container-status` zgłosiło `Container profile allow-list mismatch`.
Nie obchodzono odmowy, nie uruchamiano backendu ani solverów.

## Pozostało

Dokończyć podłączenia paneli i regression fixture, przejrzeć komplet diff,
wykonać dostępne źródłowe sprawdzenia oraz CI, push/PR, wymagane akceptacje,
merge, bezpieczny fast-forward i cleanup własnego worktree lub jawny blocked.

## Zapisane etapy

- `df85465e1e91c5f28031760176a1d6a523e35286`: semantyczne trasy unassigned
  z zachowanym carrier ref; regresje źródłowe dodane, nie uruchomione.
- `3ea8df7279b241e81b1f4e9afe5548a133877a57`: rzeczywiste tryby dolnego
  paska, widoczne powody blokad, kontrakt wariantów i usunięcie opacity
  disclosure. Niezależny review tego zakresu: brak actionable findings.
- `2b4c147f07b67f121b60d24db15387d2d76285bf`: fixture produkcyjnego
  Shell/Footer/Group oraz job CI ze zrzutami i receipt, jawne type=button
  i zawężone transitions. Browser jeszcze NOT VERIFIED.

Kontrole interpretowane źródeł: architecture hygiene PASS, API hygiene PASS
(exit 0), node --check smoke PASS, Python AST harness PASS, diff whitespace
PASS. Nie kompilowano ani nie uruchamiano testów jednostkowych lokalnie.

## Review paneli przed integracją

Niezależny review roboczego zakresu poza Study wykrył dwa Required P2:

1. Frozen Spins: Preview mask nie może wymagać dirty, bo jest podglądem
   również zapisanej definicji.
2. Frequency Domain display: liveViewport z dirty=false i reset no-op
   pozostawiał Reset display bez rzeczywistej operacji.

Oba są w poprawie przed integracją. Dodatkowy review koordynatora obejmuje
blokadę wszystkich operacji regionów i fence właściciela podformularza po ACK.
Study ma sprawdzaną kolizję właścicieli parent/stage. Nie deklarowano PASS
przeglądarki ani kompletnego zamknięcia paneli na podstawie tego review.

## Zamknięcie review kodu paneli

Commit formularzy: `4f44330331a9835faab10caad3bf5428d4516f28`. Oba Required P2 zamknięte
źródłowo, końcowy zawężony review nie wykazał nowych actionable findings.
Composite Apply przechwytuje callback/dirty przed await i sprawdza owner key;
pending obejmuje także inne operacje regionu. Callback child zapisuje przechwycony
szkic i zachowuje późniejszą edycję po ACK. Dodano regression sources.

Study nie ma aktywnej kolizji parent/stage: InspectorModule renderuje jeden
alternatywny Panel, a katalog rozdziela trasy. Nie zmieniano Study.

Pełna integracja parent->child z rzeczywistym ACK/owner-change/pending pozostaje
NOT VERIFIED; helper tests i DOM child nie zastępują tej ścieżki backendowej.

Commit hook React Doctor: 75/100, 1 warning no-array-index-as-key w
ObjectRegionMagneticParametersPanel. Wskazany key override:index jest taki sam
w bazie 27c43be; hook nie wykrył frameworku w root i ograniczył reguły. Nie jest
to pełny runtime/React proof ani wynik 0 warnings. Bramka CI porówna PR z bazą.

Końcowe interpretowane architecture/API hygiene i whitespace: PASS.
Browser smoke parser: PASS po usunięciu wyścigu publikacji fixture drivera.
W CI wymagane zachowanie receipt i zrzutów (brak artefaktów to błąd).

## Ostatnia poprawka przed PR

`ec8bb243b75eb42d98dc8c7973793a66a19ec2a4` zamyka Required P1
Planar Monitor: zmiana definicji zasobu przy dirty draft nie może zostać
nadpisana przez pełną starą definicję z nową revision. Zachowano szkic,
wprowadzono widoczny konflikt i blokadę obu Apply do Revert. Aktualizacja
samej revision nie blokuje. Zawężony niezależny review: P1 zamknięte źródłowo,
brak nowych actionable; źródła regresji dodane, wykonanie w CI jeszcze pending.

Rejestr rodzin i rzeczywistych handlerów znajduje się w
`docs/reports/2026-10-13/inspector-panel-actions-ledger.md`.

## Poprawki po pierwszym CI PR #150

Pierwszy przebieg na bbc8df331552cbee52d0b93e47ee4a4a6eb55ca6 wykrył
2 błędy TypeScript w mockach testów i 13 nowych przypisań ref.current
podczas renderowania. Poprawiono typowanie oraz przeniesiono synchronizację
refów do useLayoutEffect, zachowując synchroniczne zapisy ze zdarzeń i ACK.

Istniejący browser smoke oczekiwał starej nazwy Focus; selektor aktualizuje się
do Fit view. Nowy smoke wymaga normalizacji absolutnej ścieżki uploadu
artefaktów i drukuje ograniczone logi po błędzie. Dodano kontrolę niezmienionych
disabled/opacity pola, limit commitów React i licznik mutacji API. Fixture używa
syntetycznych callbacków: nie stanowi dowodu rzeczywistego API end-to-end.

Kontrole parserów i git diff --check: PASS. Ponowne CI, browser i pełny
przebieg mutacji z backendem: NOT VERIFIED do uzyskania aktualnych wyników.

## Drugi przebieg CI i aktualny audyt zakresu

Commit a6fe6a1955a617af1be9b6d7f1dbeff6a78e8541 przeszedł typecheck; lint
ujawnił cykliczne odwołania handlerów do callbacków ACK hooka oraz odczyty ref
w renderowaniu. Poprawki zachowują callback ACK uchwycony przy kliknięciu,
synchronizują bridge w layout effect i używają React state w renderowaniu.
Browser fixture brakował Chromium w resolverowym cache; CI ustala teraz
ścieżkę przez fullmag_storage.py. Smoke routingu oczekiwał starego
mesh-part-visualization zamiast naprawionego mesh-unassigned-part.

Commit 9c99346a7dd205e8fd87c721fda98c78b159b9f0 zachowuje bajty pakietu
dokumentacji przez scoped -text oraz aktualizuje SHA/bytes D07. Walidator
manifestu na Windows: PASS (76 wpisów); orakle: PASS (10/10).

Audyt wymagań D07 pozostawia R1 nieukończone: brakuje udowodnionego trwałego
recovery ordinary transactions, pełnej aktywnej generacji/digestu i runtime
receiptów. Root potwierdził limit 8 w reconcileMeshSubmission i dopuszczenie
current/runAllowed na samym source_scene_revision. Te elementy należy
naprawić w kolejnych oddzielnych etapach, bez traktowania PR150 jako pełnego
zakończenia oryginalnego celu R0/R1.

## Aktualne dowody browser CI

Na PR head 2580023c1ca341362008de4d79df7ae8749b1205, run38381032834,
inspector-actions-browser-smoke: PASS. Receipt wskazuje merge-ref
c5173116a0a3fc3d981a6bdb1a0e797659e15bea; jego rodzice to
499c7c902b40ad7a69e3e03108f26caecb28d3ca oraz powyższy PR head.
Source digest before/after identyczny: cd42024878db363c475597c457be3d5a1bfbf44bffef3c6a2fd53d669433bb5a.
Pobrane 11 artefaktów mają zgodne SHA256/size z receipt. Obejrzano zrzuty
Object wide invalid i Airbox narrow live; stopka pokazuje właściwe tryby.
7 scenariuszy PASS, transakcje ACK: 4 i 5 commitów React (limit <32);
0 mutacji API zgodnie z syntetycznym fixture. Backend end-to-end pozostaje
NOT VERIFIED. Owned server terminal=true, source_changed_during_run=false.

control-room-contracts: typecheck i brak błędów ESLint, lecz FAIL przez
4 ostrzeżenia exhaustive-deps najnowszych callbacków regionów. Efekty te
synchronizują refs po każdym commitcie, więc usunięto pozornie stabilne
deps arrays, zachowując semantykę i threshold max-warnings=0.
React Doctor CI: 22 warnings, score84, bez nowych error findings; wynik
advisory nie jest deklaracją zero warnings. Nie tłumiono reguł ani diagnostyk.

## Diagnoza końcowego CI c496af

Run 38381937823 zakończony: oba browser smoke PASS, Python, FDM,
generated-api i API hygiene PASS. control-room-contracts: typecheck i lint
PASS, testy FAIL (29); rust-contracts: 967 PASS, 1 FAIL, 3 ignored w grupie
API — capture resolved_device zwrócił 500 zamiast 200. Diagnoza Rust trwa;
nie uznano tego za flake ani nie osłabiono bramki.

Poprawki konfiguracji testów CrossSection i PlanarMonitorDraft zachowują
oryginalne eksporty KernelContext oraz montują rzeczywiste providery kernela
i sesji Inspectora. Test późniejszej edycji PlanarMonitor używa natywnego
settera i zdarzenia input dla pola tekstowego zamiast zdarzenia select;
dodatkowa asercja potwierdza draft przed ACK. Zachowano wymaganie, że ACK
nie kasuje późniejszej edycji.

Usunięto nieużywane selektory dawnego tooltip wrappera stopki. Kontrakt CSS
sprawdza obecny wrapping kontrolek i osobny wiersz feedbacku, zgodny z
wcześniej zweryfikowanym wąskim fixture. git diff --check PASS; lokalnych
testów/kompilacji nie uruchamiano. Wykonanie poprawionych testów pozostaje
NOT VERIFIED do następnego CI. Pozostałe błędy Frozen Spins/regionów diagnozuje
oddzielny worker; zakres R0/R1 nadal nieukończony.
