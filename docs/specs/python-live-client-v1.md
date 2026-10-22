# Klient Pythona dla żywej sesji — specyfikacja v1

- Status: **szkic**; runtime NOT IMPLEMENTED.
- Data: 2026-10-22.
- Decyzja: [ADR 0068](../adr/0068-python-live-session-client.md) (propozycja).
- Kontrakty nadrzędne: [`session-run-api-v1.md`](session-run-api-v1.md),
  [`resource-first-control-room-api-v2.md`](resource-first-control-room-api-v2.md),
  [`scene-document-authoring-v1.md`](scene-document-authoring-v1.md),
  ADR 0053 (FMVP).

## 1. Cel i zakres

Notatnik Jupytera (lub dowolny proces Pythona poza skryptem przechwytywanym
przez `fullmag script.py`) łączy się z działającym `fullmag-api` i w trybie
interaktywnym:

- buduje i zmienia scenę: obiekty, materiały, regiony, couplingi, napędy,
  etapy;
- wysyła komendy runtime i czeka na ich wynik;
- odczytuje pola, skalary i tabele jako tablice numpy;
- subskrybuje zdarzenia żywej sesji;
- eksportuje stan sesji do kanonicznego skryptu Pythona.

Poza zakresem v1: wykonanie zdalnego kodu, synchroniczny callback po każdym
kroku solvera (faza F7), wiele sesji w jednym procesie API.

## 2. Odwzorowanie Boris → Fullmag

| Boris (`NetSocks.py`) | Fullmag v1 |
|---|---|
| `NSClient(scriptserverport=1542)` | `fm.connect(url="http://127.0.0.1:<port>")` → `LiveSession` |
| `ns.addmesh(...)`, `ns.Ferromagnet(rect, cellsize)` | `session.objects.create(...)` → transakcja `create_object` |
| `mesh.param.damping.setparam(0.01)` | `session.materials["py"].alpha = 0.01` → `patch_material` |
| `ns.setstages([...])`, `ns.addstage(...)` | `session.stages.add_relax(...)`, `add_run(...)` → `merge_patch` na `study.stages` |
| `ns.Run()` (blokujące) | `session.run(1e-9)` → `RunHandle`; `.wait()` blokuje jawnie |
| `ns.stop()`, `ns.runstage(i)` | `session.stop()`, `session.run_stage(i)` → komendy z `target` |
| `bufferCommand=True` + `runcommbuffer` | `with session.transaction(): …` → jedna transakcja |
| `mesh.quant.M.getvalue(...)`, OVF2 | `session.field("m").to_numpy()` (FMVP) |
| `Get_Data_Columns(file)` | `session.table(id).to_numpy()` / `.to_pandas()` |
| `Run(callback)` (embedded) | `session.on(...)`, `run_until(predicate, chunk_steps=N)` |
| `NSMultiClient` | `fm.sweep(...)` przez batche projektów |
| komenda `default` | `session.reset()` → `replace_scene` pustą sceną |

## 3. Warstwa niska `fullmag.client`

### 3.1 Transport

- HTTP JSON przez httpx; API synchroniczne (`Client`) i asynchroniczne
  (`AsyncClient`) o tym samym kształcie.
- Bazowy URL domyślnie loopback; inny host wymaga jawnego argumentu.
- Nagłówki: `x-fullmag-session-scope` po pierwszym odczycie sesji;
  `Authorization: Bearer` tylko gdy podano token.
- Zależności jako dodatek `fullmag[client]`; import `fullmag` bez dodatku
  nie wymaga httpx.

### 3.2 Modele

- Generowane z `openapi-v2.json` dla tagów: sessions, model (authoring),
  simulation (commands, runs, stages), data, events, persistence (projects,
  batches, checkpoints).
- Generator i podzbiór tagów są zapisane w recepcie uruchamianej przez
  `just docker-dev-codegen`; wynik leży w
  `packages/fullmag-py/src/fullmag/client/_generated/` i jest commitowany.
- Test kontraktowy porównuje listę wygenerowanych schematów ze specyfikacją.

### 3.3 Błędy

| Odpowiedź serwera | Wyjątek |
|---|---|
| 409 `scene_stale_revision` | `StaleRevisionError(expected, actual)` |
| 409 `accepted_execution_input_locked` | `InputLockedError` |
| 409 sesja istnieje bez `replace_current` | `SessionExistsError` |
| 4xx walidacji | `ValidationError` z polami z odpowiedzi |
| komenda `Rejected` / `Failed` | `CommandFailedError(command_id, reason)` |
| brak połączenia | `ConnectionError` z adresem i wskazówką o grupie DEV |

Klient nie ponawia transakcji po `StaleRevisionError` automatycznie, z
wyjątkiem operacji oznaczonych w spec jako idempotentne i rebase-safe
(odczyt rewizji, ponowna próba tej samej transakcji z nowym
`base_revision` tylko gdy zmieniony zasób nie był dotknięty przez innego
klienta).

### 3.4 Komendy

```python
cmd = client.commands.submit(kind="run", until_seconds=1e-9,
                             target=Target.study(), precondition=...)
cmd.wait(timeout=None)   # WebSocket, a bez niego odpytywanie GET commands/:id
```

`client_intent_id` jest generowany przez klienta i pozwala bezpiecznie
ponowić wysłanie po zerwanym połączeniu.

## 4. Dane

- Dekoder FMVP w czystym Pythonie z numpy (`fullmag.client.fmvp`),
  przeniesiony z dekodera Control Room (`kernel/api/binaryDecode*`).
- `session.field(q).to_numpy()` zwraca tablicę `(…, 3)` w jednostkach SI z
  metadanymi siatki (FDM: kształt komórek i rozmiar; FEM: węzły/elementy).
- Cache po ETag/`If-None-Match`; brak zmiany rewizji oznacza brak transferu.
- Tabele: `rows.bin` → numpy; `to_pandas()` tylko gdy pandas jest dostępny.
- Zgodność: wspólne próbki binarne w `packages/fullmag-py/tests/fixtures/fmvp/`
  dekodowane identycznie przez dekoder TS i Python.

## 5. Warstwa wysoka `LiveSession`

```python
import fullmag as fm

s = fm.connect()                       # istniejąca sesja current
s = fm.connect(create=dict(backend="fdm", device="cuda"))
s.load(study)                          # StudyBuilder → replace_scene
disk = s.objects["disk"]
disk.material.Ms = 800e3               # patch_material
with s.transaction():                  # jedna transakcja
    disk.m = fm.texture.uniform(1, 0, 0)
    s.stages.add_relax()
h = s.run(2e-9)                        # RunHandle
h.wait()
m = s.field("m").to_numpy()
print(s.export_script())               # kanoniczny Python
```

Zasady:

- Proxy nie trzyma kopii stanu dłużej niż jedna rewizja; odczyt po zmianie
  rewizji pobiera zasób ponownie.
- Identyfikacja obiektów po niezmiennym `object_id`; `name` służy tylko do
  wyszukania. Zmiana nazwy to `rename_object`.
- Typ obiektu nie włącza fizyki; moduły fizyczne włącza się jawnie, tak jak w
  DSL.
- `session.load(study)` używa `build_scene_document_from_builder`; nie
  powstaje druga ścieżka konwersji.
- `fm.connect()` wywołane w trakcie przechwytywania skryptu zgłasza
  `RuntimeError` z wyjaśnieniem, że skrypt autorski nie steruje sesją.

### 5.1 Stany i pauza

`with s.paused():` wysyła `pause`, czeka na potwierdzony stan wstrzymany,
wykonuje blok i wysyła `resume` także po wyjątku. Edycje odrzucone przez
backend zgłaszają `InputLockedError`; klient nie wysyła niejawnie `stop`.

### 5.2 Pętle sterujące

- `s.on("scalar.sample", fn)` i `s.on("resource.changed", fn)`: callbacki w
  wątku subskrybenta (sync) lub w pętli asyncio (async).
- `s.run_until(predicate, chunk_steps=N, max_time=…)`: pętla
  `run(max_steps=N)` → odczyt skalarów → `predicate(sample)`. Koszt: jedno
  wstrzymanie i odczyt na blok; dokumentacja podaje pomiar narzutu.
- Warunki stopu, które backend obsługuje natywnie (tolerancje relax,
  `until_seconds`), mają pierwszeństwo przed `run_until`.

## 6. Zdarzenia

- Subskrybent WebSocket `fullmag.live.v1` z `after_seq`; po zerwaniu
  połączenia wznawia od ostatniego `seq`, a po `resync` odczytuje zasoby od
  nowa.
- Zdarzenia są wyłącznie powiadomieniami; dane pobiera się osobnym GET po
  zmianie rewizji.
- Dodatek `fullmag[jupyter]`: pasek postępu runu i wykres skalarów na żywo
  (ipywidgets); bez dodatku klient działa w zwykłym REPL.

## 7. Wymagane zmiany backendu

| Zmiana | Uzasadnienie | Warunek |
|---|---|---|
| Tabela edycji dozwolonych w pauzie per ścieżka wykonania | dziś `validate_active_scene_mutation` blokuje każdą zmianę wejścia przy aktywnym runie, także wstrzymanym | notatka w `docs/physics/` dla zmian parametrów fizycznych w trakcie całkowania |
| Utrzymanie stanu runtime w trybie scratch przy edycji | supervisor kończy proces potomny przy każdej zmianie rewizji sceny, co gubi `m` | kontrakt przeniesienia stanu z wpisem w provenance |
| Opcjonalnie `step{n}` i long-poll zakończenia komendy | wygoda notatnika | tylko jeśli `run(max_steps)` i WebSocket okażą się niewystarczające |
| Dostęp do API grupy DEV z hosta | notatnik działa poza kontenerem | zgodnie z ADR 0067 i `development_admission` |

Wsparcie każdej zmiany jest deklarowane per ścieżka (FDM CPU, FDM GPU,
FEM CPU, FEM GPU) w `docs/specs/capability-matrix-v0.md`; wymuszony GPU nie
przechodzi niejawnie na CPU.

## 8. Fazy i kryteria ukończenia

| Faza | Zakres | Kryterium |
|---|---|---|
| F0 | ADR 0068, ta spec, decyzje D1–D5, notatka fizyczna dla D3 | decyzje zaakceptowane, tabela edycji w pauzie |
| F1 | `fullmag.client`: transport, modele, błędy, komendy | testy pytest na nagranych odpowiedziach + test zgodności ze spec, bez kompilacji Rusta |
| F2 | dekoder FMVP, `to_numpy()`, tabele, cache ETag | identyczne tablice z dekoderem TS na wspólnych próbkach |
| F3 | `LiveSession`, proxy, `transaction()`, `paused()`, `export_script()` | notatnik buduje scenę, uruchamia relax + run, czyta `m`; eksport odtwarza scenę (round-trip) |
| F4 | subskrybent WebSocket, `on()`, `run_until()`, dodatek Jupyter | wznowienie po zerwaniu połączenia, pomiar narzutu `run_until` |
| F5 | zmiany backendu z §7 | testy kontraktowe API i dowód runtime w grupie DEV dla każdej deklarowanej ścieżki |
| F6 | `fm.sweep()` przez batche projektów | przemiatanie N punktów z wynikami jako numpy |
| F7 | opcjonalnie tryb in-process (PyO3 + `InteractiveRuntime`) z tym samym protokołem `Session` | callback po każdym kroku bez serwera |
| F8 | przykładowy notatnik w `examples/notebooks/`, strona w `public_docs`, ściągawka Boris → Fullmag | dokumentacja publikowana razem z F3 |

## 9. Bezpieczeństwo

- Brak zdalnego wykonania kodu; klient wysyła wyłącznie typowane transakcje i
  komendy.
- Domyślnie tylko loopback; połączenie z innym hostem jest jawne i wymaga
  tokenu tam, gdzie API go wymaga.
- Token nie trafia do URL ani do logów klienta.
