# ADR 0068 — interaktywny klient Pythona dla żywej sesji (notatnik → API)

Status: **szkic, propozycja** — decyzje D1–D5 czekają na akceptację użytkownika.
Data: 2026-10-22.
Specyfikacja: [`docs/specs/python-live-client-v1.md`](../specs/python-live-client-v1.md).

Ten dokument nie opisuje działającego runtime. Żaden punkt nie jest
zaimplementowany; stan kodu odpowiada commitowi `e19ee0664`.

## Kontekst

Użytkownik chce sterować symulacją z notatnika Jupytera w pełnym trybie
interaktywnym: tworzyć i zmieniać obiekty, parametry i etapy, uruchamiać,
wstrzymywać i przerywać runy oraz odczytywać wyniki, tak jak w Boris
Spintronics przez `NetSocks.py`
(`external_solvers/BORIS/NetSocks.py`, submoduł `external_solvers`).

### Jak robi to Boris

- Jeden język komend konsoli (~600 komend) jest wspólnym kanałem GUI, skryptów
  i Pythona. Wszystkie trafiają do `Simulation::HandleCommand(std::string)`
  (`Boris/Commands.cpp`).
- Serwer TCP na porcie 1542: wątek `Listen_Incoming_Message`
  (`Commands.cpp:26`) odbiera komunikat `hasło*komenda arg…` (`*` cicho,
  `>` z echem w konsoli) i odsyła wartości rozdzielone tabulatorem (bufor
  4096 B). Każda komenda to osobne połączenie connect → send → recv → close.
- Komendy wykonują się pod `userInputMutex` i `simulationMutex`, więc nie
  wchodzą w środek iteracji. Komenda wysłana podczas biegu zatrzymuje
  symulację, a klient najpierw odbiera komunikat `stopped`. `run` blokuje
  klienta do końca biegu.
- `NSClient` w `NetSocks.py` ma ~640 metod wygenerowanych ze zrzutu komend
  (każda z wariantem `bufferCommand`, czyli paczką `buffercommand` +
  `runcommbuffer`). Nad nimi leży fasada obiektowa: `Mesh`
  (`ns.Ferromagnet(...)`), `Param` (`mesh.param.damping.setparam(...)`),
  `Quantity` (`mesh.quant.M.getvalue(...)`), algebra `Shape`, helpery etapów
  (`setstages`, `Relax`, `Hxyz`) oraz lokalny odczyt i zapis OVF2.
- Tryb embedded: moduł C `BPython` (`Boris/PythonScripting.h`) wykonuje te
  same stringi w procesie Borisa. `Run(callback)` zastępuje pętlę solvera
  atrapą i woła `Simulate()` po jednej iteracji z pętli Pythona, wykonując
  callback użytkownika po każdym kroku.
- `NSMultiClient` rozdziela przemiatanie parametrów na kilka instancji
  Borisa (osobne porty) w wątkach.

Słabości, których Fullmag nie przejmuje: brak schematu, wersjonowania i
typowanych błędów; brak rewizji i kontroli współbieżności; zatrzymanie biegu
przez dowolną komendę; hasło otwartym tekstem; zdalne wykonanie dowolnego
kodu (`runscript`); dane wyłącznie przez pliki.

### Co Fullmag już ma

| Potrzeba | Istniejący mechanizm |
|---|---|
| Mutacje sceny | `POST /v2/sessions/current/model/transactions` (`AuthoringTransactionRequest`, `crates/fullmag-api/src/schemas/authoring.rs`), każda z `base_revision`; konflikt → `scene_stale_revision` (409) |
| Etapy | `scene.study.stages` przez transakcję `merge_patch` |
| Sterowanie runem | `POST /v2/sessions/current/simulation/commands` (`StructuredCommandRequest`, `schemas/commands.rs`): `run`, `relax`, `pause`, `resume`, `stop`, `skip`, `compute_fields`, … z `RuntimeCommandIntent` (target, precondition, `client_intent_id`) i dziennikiem stanów |
| Powiadomienia | WebSocket `/v2/sessions/current/events/ws` (`fullmag.live.v1`), wyłącznie powiadomienia o zmianie rewizji |
| Dane | binarne FMVP `…/data/fields/:q/samples/vector` (ADR 0053), tabele `rows.bin`, ETag |
| Model w Pythonie | `StudyBuilder`, `MagnetHandle`; konwertery builder ↔ SceneDocument (`fullmag/runtime/scene_document.py`) |
| Kontrakt | OpenAPI v2 (`/v2/platform/openapi.json`), generator klienta TypeScript |

Braki: w `packages/fullmag-py` nie ma klienta HTTP/WebSocket, sesji ani
dekodera FMVP; API ma jedną sesję `current` na proces; w trybie accepted
(Docker) edycje wejścia przy aktywnym, także wstrzymanym, runie są odrzucane
z błędem `accepted_execution_input_locked`
(`crates/fullmag-api/src/live_execution_binding.rs`); supervisor scratch
kończy proces potomny przy każdej zmianie rewizji sceny
(`crates/fullmag-cli/src/scratch_runtime.rs`); przechwytywanie skryptu
blokuje zdarzenia `socket.*` (`fullmag/runtime/accepted_source_capture.py`).

## Decyzje (propozycja)

**D1. Bez tekstowego języka komend.** Zgodnie z inwariantem 13.1
(`.agents/instructions/contracts.md`) jedyną kanoniczną powierzchnią
skryptową jest DSL Pythona. Klient interaktywny tłumaczy operacje na
istniejące typowane transakcje i komendy API. Każdy stan sesji z notatnika
musi dać się wyeksportować do kanonicznego skryptu (`GET …/model/script`).

**D2. Dwie warstwy w `packages/fullmag-py`.**
Warstwa niska `fullmag.client` używa modeli wygenerowanych z OpenAPI v2 dla
wybranego podzbioru tagów (odpowiednik generowanych metod `NSClient`, ale
typowany). Warstwa wysoka `fm.connect()` → `LiveSession` udostępnia
obiekty-proxy zasobów (odpowiednik `Mesh`/`Param`/`Quantity`). Każde
przypisanie w proxy to jedna jawna transakcja z `base_revision`. Konwertery
buildera służą tylko do wgrania całego modelu (`session.load(study)` →
`replace_scene`). Lokalna kopia buildera z diffem zostaje odrzucona: ukrywa
granice transakcji i utrudnia obsługę konfliktów rewizji.

**D3. Edycja podczas biegu tylko przez jawną pauzę.** Klient nie zatrzymuje
runu niejawnie (inaczej niż Boris). `with session.paused(): …` wysyła
`pause`, czeka na stan wstrzymany, wykonuje edycje i wysyła `resume`.
Backend musi zdefiniować per ścieżka wykonania (FDM/FEM × CPU/GPU), które
edycje są dozwolone w pauzie i od kiedy obowiązują (natychmiast albo od
granicy etapu). Zmiana parametrów fizycznych w trakcie całkowania zmienia
semantykę numeryczną, więc wymaga wcześniej notatki w `docs/physics/`.
Do tego czasu klient w pauzie dopuszcza tylko to, co backend już przyjmuje,
a pozostałe edycje zgłasza jako `InputLockedError` z kodem serwera.

**D4. Odpowiednik `Run(callback)`.** Zdalnie: callbacki na zdarzenia
WebSocket (`scalar.sample`, `resource.batch_changed`), warunki stopu po
stronie serwera oraz `run_until(predicate, chunk_steps=N)` jako pętla
`run(max_steps=N)` z oceną predykatu między blokami, z udokumentowanym
kosztem. Synchroniczny callback po każdym kroku wymaga trybu in-process przez
PyO3 i `InteractiveRuntime` (faza F7 spec), poza zakresem pierwszej wersji.

**D5. Przemiatanie parametrów przez batche projektów.** Odpowiednik
`NSMultiClient` używa `/v2/persistence/projects/:pid/batches`, a nie wielu
żywych sesji `current`.

Dodatkowo: klient nie udostępnia zdalnego wykonania kodu; łączy się domyślnie
z loopback; zapisy wymagające autoryzacji przekazują token bearer; komunikacja
respektuje nagłówek `x-fullmag-session-scope`.

## Konsekwencje

- `packages/fullmag-py` dostaje opcjonalną zależność HTTP (httpx) i WebSocket;
  rdzeń DSL i ścieżka `fullmag script.py` pozostają bez nich.
- `just docker-dev-codegen` generuje także modele Pythona; zmiana schematu API
  wymaga regeneracji obu klientów.
- Dekoder FMVP istnieje w dwóch językach; zgodność pilnują wspólne próbki.
- Notatnik i Control Room mogą edytować tę samą sesję; rozstrzyga optymistyczna
  kontrola rewizji, a klient musi zgłaszać konflikty zamiast ich nadpisywać.
- Trzeba zmienić backend (D3, utrzymanie stanu runtime w trybie scratch);
  zakres opisuje faza F5 spec.

## Odrzucone alternatywy

- **Port protokołu Borisa (tekst po TCP).** Duplikowałby semantykę poza DSL i
  ProblemIR, bez rewizji i typów.
- **Generowanie całego klienta z pełnego OpenAPI.** Specyfikacja ma ~1,8 MB;
  pełny klient byłby duży i niestabilny. Generowany jest podzbiór tagów.
- **Wiele sesji `current` jako równoległe workery.** API ma jedną sesję na
  proces; przemiatanie należy do trwałych batchy.

## Otwarte pytania

1. Czy port API grupy Docker DEV jest dostępny z hosta dla notatnika i jak
   klient przechodzi `development_admission`?
2. Które edycje są dozwolone w pauzie dla każdej ścieżki wykonania i czy
   obowiązują natychmiast, czy od granicy etapu (D3)?
3. Czy dodać komendę `step{n}` i long-poll na zakończenie komendy, czy
   wystarczą `run(max_steps)` i zdarzenia WebSocket?
4. Jaka polityka UX przy przejęciu sesji używanej przez Control Room
   (`replace_current`, ostrzeżenia o konfliktach)?
