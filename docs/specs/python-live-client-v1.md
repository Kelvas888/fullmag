# Tryb `live` DSL i klient Pythona — specyfikacja v1

- Status: **przyjęta** (decyzje ADR 0068 z 22.10.2026); runtime NOT IMPLEMENTED.
- Data: 2026-10-22.
- Decyzja: [ADR 0068](../adr/0068-python-live-session-client.md).
- Kontrakty nadrzędne: [`session-run-api-v1.md`](session-run-api-v1.md),
  [`resource-first-control-room-api-v2.md`](resource-first-control-room-api-v2.md),
  [`scene-document-authoring-v1.md`](scene-document-authoring-v1.md),
  ADR 0053 (FMVP), ADR 0067 (grupy DEV).

## 1. Cel i zakres

Zwykły skrypt Pythona z `import fullmag as fm`, uruchomiony przez
`python skrypt.py`, w interpreterze interaktywnym albo komórka po komórce w
Jupyterze, programuje symulację w działającej instancji Fullmaga, tak jak
skrypt z `NetSocks.py` programuje działającego Borisa. Każde wywołanie DSL:

- buduje lub zmienia scenę: obiekty, materiały, regiony, couplingi, napędy,
  etapy;
- wysyła komendy runtime i czeka na ich wynik;
- odczytuje pola, skalary i tabele jako tablice numpy.

Skrypt może też subskrybować zdarzenia sesji, a stan sesji eksportuje się do
kanonicznego skryptu Pythona.

Poza zakresem v1: wykonanie zdalnego kodu, synchroniczny callback po każdym
kroku solvera (faza F7), komendy `step{n}` i long-poll, wiele sesji w jednym
procesie API.

## 2. Tryby wykonania DSL

| Tryb | Jak się włącza | Co robi |
|---|---|---|
| `capture` | `fullmag skrypt.py` | przechwytuje skrypt do ProblemIR; Rust planuje i wykonuje całość z provenance (bez zmian) |
| `eager` | `python skrypt.py` bez `fm.connect()` i bez `FULLMAG_URL` | liczy w procesie Pythona przez PyO3 (bez zmian) |
| `live` (nowy) | `fm.connect(url=None)` albo zmienna `FULLMAG_URL` | każde wywołanie DSL działa na żywej sesji działającej instancji |

`fm.connect()` bez argumentu używa `FULLMAG_URL`, a bez niej
`http://127.0.0.1:<domyślny port frontendu>`. Wywołanie `fm.connect()` w
trybie `capture` zgłasza `RuntimeError`: skrypt przechwytywany nie steruje
sesją, a sandbox przechwytywania i tak blokuje gniazda.

## 3. Odwzorowanie Boris → Fullmag

| Boris (`NetSocks.py`) | Fullmag, tryb `live` |
|---|---|
| `ns = NSClient()` | `fm.connect()` albo `FULLMAG_URL` |
| `ns.default()` | `fm.reset()` → `replace_scene` pustą sceną |
| `ns.cellsize(...)`, `ns.cuda(1)` | `fm.cell(...)`, `fm.device("cuda:0")` → transakcje |
| `ns.addmesh(...)`, `ns.Ferromagnet(rect, cellsize)` | `layer = fm.geometry(fm.Box(...), name="py")` → `create_object` |
| `mesh.param.damping.setparam(0.01)` | `layer.alpha = 0.01` → `patch_material` |
| `ns.setfield(...)` | `fm.b_ext(...)` → transakcja napędu pola |
| `ns.setstages([...])`, `ns.addstage(...)` | `study.stages.add_relax(...)` → `merge_patch` na `study.stages` |
| `ns.Run()` (blokujące) | `fm.relax()`, `fm.run(1e-9)` → komenda + oczekiwanie |
| `ns.stop()`, `ns.runstage(i)` | `fm.stop()`, `fm.run_stage(i)` → komendy z `target` |
| `bufferCommand=True` + `runcommbuffer` | `with fm.transaction(): …` → jedna transakcja |
| `mesh.quant.M.getvalue(...)`, OVF2 | `fm.m.to_numpy()` / `fm.field("m").to_numpy()` (FMVP) |
| `Get_Data_Columns(file)` | `fm.table(id).to_numpy()` / `.to_pandas()` |
| `Run(callback)` (embedded) | `fm.on(...)`, `fm.run_until(predicate, chunk_steps=N)` |
| `NSMultiClient(ports=[...])` | `fm.sweep(fn, points, groups=[url1, url2, …])` |

## 4. Warstwa niska `fullmag.client`

### 4.1 Transport

- Wyłącznie biblioteka standardowa (`http.client`), bez nowych zależności
  runtime: `fm.connect()` działa w każdym środowisku z pakietem `fullmag`,
  także w obrazie Docker. API jest synchroniczne (`fullmag.client.Client`).
- Jedno trwałe połączenie HTTP/1.1 na wątek, więc synchronizacja po każdym
  wywołaniu DSL nie płaci za nowe połączenie TCP.
- Bazowy URL to origin frontendu grupy DEV, który przekazuje `/v2/*` i
  WebSocket do API. Kolejność: argument `url`, `FULLMAG_URL`,
  `http://127.0.0.1:3197`. Token z argumentu lub `FULLMAG_TOKEN`, wysyłany
  wyłącznie jako `Authorization: Bearer`.
- Nagłówek `x-fullmag-session-scope` jest wysyłany tylko do operacji, które go
  deklarują, i tylko gdy klient zna zakres sesji.
- Ponawiane są wyłącznie żądania, które na pewno nie zostały zastosowane:
  nieudane nawiązanie połączenia, zamknięte bezczynne połączenie keep-alive,
  502 z proxy frontendu oraz 409 `development_restart_in_progress`, z
  backoffem do budżetu `retry_budget_s` (domyślnie 60 s). GET dodatkowo przy
  503/504. Komendy przy ponowieniu zachowują ten sam `client_intent_id`.

### 4.2 Modele

- `scripts/generate_python_api_models.py` generuje z `openapi-v2.json`
  domknięcie schematów operacji używanych przez klienta (lista
  `OPERATION_IDS`): `TypedDict`-y, tabele `REQUIRED_FIELDS` i
  `DISCRIMINATED_UNIONS` do walidacji w czasie działania oraz tabelę operacji.
  Dokumenty sceny (`SceneResource` i pokrewne) są nieprzezroczyste
  (`Dict[str, Any]`), bo tworzą je kanoniczne konwertery DSL.
- Wynik leży w `packages/fullmag-py/src/fullmag/client/_generated/` i jest
  commitowany. Generator uruchamiają `pnpm run generate:api` oraz
  `just docker-dev-codegen`; bramka `generated-api-determinism` i test
  `test_generated_models_are_current` wykrywają nieaktualne modele.
- Klient wywołuje operacje wyłącznie przez tabelę: nieznana operacja,
  parametr zapytania lub brak parametru ścieżki to błąd przed wysłaniem;
  ciało żądania przechodzi kontrolę pól wymaganych i dyskryminatora `kind`.

### 4.3 Błędy

| Odpowiedź serwera | Wyjątek |
|---|---|
| 409 `revision_conflict` | `StaleRevisionError` |
| 409 `accepted_execution_input_locked` lub edycja podczas biegu bez pauzy | `InputLockedError` |
| 409 sesja istnieje bez `replace_current` | `SessionExistsError` |
| 409 `development_restart_in_progress` po wyczerpaniu budżetu | `DevelopmentRestartError` |
| 400 / 404 / 422 | `ValidationError` / `NotFoundError` / `UnsupportedCapabilityError` |
| komenda `rejected` / `failed` / zakończona jako `cancelled` | `CommandFailedError` |
| przekroczony czas oczekiwania na komendę | `CommandTimeoutError` |
| niepoprawny payload lokalnie | `RequestValidationError` |
| brak połączenia | `FullmagConnectionError` z adresem i wskazówką o grupie DEV |

Wszystkie dziedziczą po `FullmagClientError`. Klient nie ponawia transakcji po `StaleRevisionError` automatycznie. Sesja
jest współdzielona z Control Room (ADR 0068, pytanie 4), więc konflikt
oznacza zmianę wprowadzoną przez inną stronę i trafia do użytkownika.

### 4.4 Komendy

```python
cmd = client.commands.submit(kind="run", until_seconds=1e-9,
                             target=Target.study(), precondition=...)
cmd.wait(timeout=None)   # zdarzenia WebSocket, a bez nich odpytywanie GET commands/:id
```

`client_intent_id` jest generowany przez klienta i pozwala bezpiecznie
ponowić wysłanie po zerwanym połączeniu.

## 5. Tryb `live` w DSL

### 5.1 Przykład

```python
import fullmag as fm

fm.connect()                       # albo FULLMAG_URL=… python skrypt.py
fm.engine("fdm")
fm.device("cuda:0", precision="double")
fm.cell(5e-9, 5e-9, 10e-9)

layer = fm.geometry(fm.Box(1000e-9, 1000e-9, 10e-9)
                    - fm.Cylinder(radius=75e-9, height=10e-9), name="layer")
layer.Ms = 800e3                   # natychmiast: patch_material
layer.alpha = 0.5
layer.m = fm.texture.uniform(1, 0, 0)

fm.relax()                         # komenda relax, czeka na zakończenie
m = fm.m.to_numpy()

with fm.transaction():             # kilka zmian jako jedna rewizja
    fm.b_ext(0.05, 0, 0)
    layer.alpha = 0.01
fm.run(2e-9)
print(fm.export_script())          # kanoniczny Python
```

Ten sam skrypt bez `fm.connect()` działa jak dziś (`eager`), a uruchomiony
przez `fullmag skrypt.py` jak dziś (`capture`).

### 5.2 Synchronizacja i tożsamość

- Każde wywołanie definiujące scenę wysyła natychmiast jedną transakcję z
  `base_revision` (ADR 0068, D1). Wyjątek: blok `with fm.transaction():`
  zbiera wywołania w jedną transakcję wysyłaną na wyjściu z bloku.
- Wywołanie, którego argumenty nie wystarczają do zbudowania poprawnego
  zasobu, jest odrzucane lokalnie przed wysłaniem; do sesji nie trafia
  częściowo zbudowany obiekt.
- Obiekty mają niezmienny `object_id`. DSL identyfikuje obiekt w sesji po
  `name` (domyślnie `"body"`): ponowne wykonanie `fm.geometry(..., name=X)`
  dla istniejącego `X` aktualizuje geometrię tego obiektu
  (`patch_object_geometry`) zamiast tworzyć duplikat. Zmiana nazwy to
  `rename_object`.
- Typ obiektu nie włącza fizyki; moduły fizyczne włącza się jawnie, tak jak w
  DSL.
- Uchwyty DSL (`MagnetHandle` i pozostałe) w trybie `live` nie trzymają stanu
  dłużej niż jedna rewizja; odczyt po zmianie rewizji pobiera zasób ponownie.
- Funkcja DSL bez zdefiniowanego zachowania w trybie `live` zgłasza
  `NotImplementedError` z nazwą funkcji; nie wykonuje się po cichu lokalnie.

### 5.3 Akcje, stany i pauza

- `fm.relax()`, `fm.run()`, `fm.minimize()`, … wysyłają komendę i czekają na
  stan końcowy. Argument `wait=False` zwraca `RunHandle` z `.wait()`,
  `.progress()` i `.cancel()`.
- `fm.pause()`, `fm.resume()`, `fm.stop()`, `fm.skip()` mapują się na
  komendy o tej samej nazwie.
- `with fm.paused():` wysyła `pause`, czeka na potwierdzony stan wstrzymany,
  wykonuje blok i wysyła `resume` także po wyjątku. Edycje wejścia przyjęte w
  pauzie obowiązują od następnej granicy etapu (ADR 0068, D3).
- Edycja wejścia podczas biegu bez pauzy zgłasza `InputLockedError`; klient
  nie wysyła niejawnie `stop`.

### 5.4 Pętle sterujące

- `fm.on("scalar.sample", fn)` i `fm.on("resource.changed", fn)`: callbacki
  w wątku subskrybenta (sync) lub w pętli asyncio (async).
- `fm.run_until(predicate, chunk_steps=N, max_time=…)`: pętla
  `run(max_steps=N)` → odczyt skalarów → `predicate(sample)`. Koszt: jedno
  wstrzymanie i odczyt na blok; dokumentacja podaje pomiar narzutu.
- Warunki stopu, które backend obsługuje natywnie (tolerancje relax,
  `until_seconds`), mają pierwszeństwo przed `run_until`.

## 6. Dane

- Dekoder FMVP v2–v6 w Pythonie z numpy (`fullmag.client.fmvp`) zachowuje
  wszystkie kontrole dekodera Control Room (`fieldVectorCodec.ts`,
  `artifactFieldVectorCodec.ts`); FMTB (`rows.bin`) dekoduje
  `fullmag.client.fmtb`.
- `FieldVector.to_numpy()` zwraca tablicę `(point_count, n_comp)` w
  jednostkach SI; `as_grid()` dla pola FDM pełnej domeny zwraca
  `(nz, ny, nx, n_comp)` (x zmienia się najszybciej, jak w silniku FDM);
  `as_complex()` łączy pary (re, im).
- `client.data.read_field(q)` korzysta z ETag/`If-None-Match`: brak zmiany
  (304) zwraca poprzednio zdekodowany obiekt bez transferu; 202 jest
  odpytywane do limitu czasu, 204 zwraca `None`.
- `client.data.read_table(id, columns=...)` zwraca `TableRows` z numpy;
  `to_pandas()` tylko gdy pandas jest dostępny.
- Zgodność: próbki w `packages/fullmag-py/tests/fixtures/fmvp/` powstają z
  enkoderów odwzorowujących `field_store.rs` bajt w bajt; dekoduje je test
  Pythona i `fieldVectorCodec.fixtures.test.ts`, porównując z jednym
  `expected.json`.

## 7. Zdarzenia

- Subskrybent WebSocket `fullmag.live.v1` z `after_seq`; po zerwaniu
  połączenia wznawia od ostatniego `seq`, a po `resync` odczytuje zasoby od
  nowa.
- Zdarzenia są wyłącznie powiadomieniami; dane pobiera się osobnym GET po
  zmianie rewizji.
- Dodatek `fullmag[jupyter]`: pasek postępu runu i wykres skalarów na żywo
  (ipywidgets); bez dodatku tryb `live` działa w terminalu i REPL.

## 8. Przemiatanie parametrów (wiele grup DEV)

```python
def point(fm, H):
    fm.b_ext(H, 0, 0)
    fm.relax()
    return fm.m.mean()

results = fm.sweep(point, H=[0.01, 0.02, 0.03, 0.04],
                   groups=["http://127.0.0.1:3197", "http://127.0.0.1:3198"])
```

- Każda grupa DEV (ADR 0067) ma własną sesję `current`; `fm.sweep` tworzy po
  jednym kontekście `live` na grupę i rozdziela punkty między nie.
- Przed każdym punktem kontekst przywraca scenę bazową (`replace_scene`),
  odpowiednik `ns.default()`.
- Równoległość jest ograniczona liczbą uruchomionych grup i ich budżetami
  `FULLMAG_DEV_*`; `fm.sweep` nie uruchamia grup samodzielnie.
- Wynik: lista wyników w kolejności punktów oraz identyfikatory runów w
  każdej grupie (provenance).

## 9. Wymagane zmiany backendu

| Zmiana | Uzasadnienie | Warunek |
|---|---|---|
| Edycje wejścia w pauzie, obowiązujące od granicy etapu | dziś `validate_active_scene_mutation` blokuje każdą zmianę wejścia przy aktywnym runie, także wstrzymanym | deklaracja per ścieżka wykonania; zmiany w trakcie całkowania dopiero po notatce w `docs/physics/` |
| Utrzymanie stanu runtime scratch przy edycji | supervisor kończy proces potomny przy każdej zmianie rewizji sceny, co gubi `m`; przy synchronizacji po każdym wywołaniu byłoby to po każdej linii skryptu | kontrakt przeniesienia stanu z wpisem w provenance |
| Obecność klienta skryptu w sesji | Control Room ma pokazywać, że sesję zmienia skrypt (ADR 0068, pytanie 4) | zasób obecności klientów z rewizją, bez nowego kanału danych |

Wsparcie każdej zmiany jest deklarowane per ścieżka (FDM CPU, FDM GPU,
FEM CPU, FEM GPU) w `docs/specs/capability-matrix-v0.md`; wymuszony GPU nie
przechodzi niejawnie na CPU.

## 10. Fazy i kryteria ukończenia

| Faza | Zakres | Kryterium |
|---|---|---|
| F0 | ADR 0068 i ta spec | zrobione: decyzje przyjęte 22.10.2026 |
| F1 | `fullmag.client`: transport, modele generowane, błędy, komendy, ponawianie przy handoffie | zrobione: `test_live_client_core.py` na prawdziwym serwerze HTTP w procesie, kontrola aktualności modeli, job CI `python-live-client-contracts` |
| F2 | dekoder FMVP, `to_numpy()`, tabele, cache ETag | zrobione: `test_live_client_data.py` i `fieldVectorCodec.fixtures.test.ts` dają identyczne wyniki na wspólnych próbkach |
| F3 | tryb `live` w `world.py`: `fm.connect`/`FULLMAG_URL`, natychmiastowa synchronizacja, reguła tożsamości, `transaction()`, akcje, `paused()`, `export_script()` | skrypt z §5.1 uruchomiony przez `python` buduje scenę w grupie DEV, relax + run działają, `m` wraca jako numpy; eksport odtwarza scenę (round-trip); ten sam skrypt w trybach `eager` i `capture` działa jak przed zmianą |
| F4 | subskrybent WebSocket, `fm.on()`, `fm.run_until()`, dodatek Jupyter | wznowienie po zerwaniu połączenia, pomiar narzutu `run_until` |
| F5 | zmiany backendu z §9 | testy kontraktowe API i dowód runtime w grupie DEV dla każdej deklarowanej ścieżki |
| F6 | `fm.sweep()` na wielu grupach DEV | przemiatanie N punktów na ≥ 2 grupach z wynikami jako numpy i identyfikatorami runów |
| F7 | opcjonalnie tryb in-process (PyO3 + `InteractiveRuntime`) z tym samym protokołem | callback po każdym kroku bez serwera |
| F8 | przykładowy skrypt i notatnik w `examples/`, strona w `public_docs`, ściągawka Boris → Fullmag | dokumentacja publikowana razem z F3 |

## 11. Bezpieczeństwo

- Brak zdalnego wykonania kodu; klient wysyła wyłącznie typowane transakcje i
  komendy.
- Domyślnie tylko loopback; połączenie z innym hostem jest jawne i wymaga
  tokenu tam, gdzie API go wymaga.
- Token nie trafia do URL ani do logów klienta.
