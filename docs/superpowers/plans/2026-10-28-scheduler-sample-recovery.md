# Scheduler sample recovery — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans for the bounded tasks below.

**Cel:** przejściowo nieaktualna próbka compute-node nie zabija schedulera;
rozliczyć bez replay przyjęty, claimed run bez workera, potwierdzić widoczne
strzałki FDM H_demag w powietrzu i bezpiecznie zamknąć własną grupę.

**Architektura:** zachować istniejący `ComputeNodeSampleNotCurrent` wraz z
przyczyną oraz `WorkerLaunchDeferred` przed wykorzystaniem launch permit.
Wygasła próbka nigdy nie pozwala na spawn. Odtwarzanie obecnego runu używa
istniejącego natywnego `--cancel-failed-no-spawn` i `WorkerNoSpawn`, z jawnymi
pinami owner/config/claim/lease/reservation oraz managed operation receipt.
Kolejne zatrzymanie i start muszą zachować natywne dowody oraz wszystkie dane.

**Technologie:** istniejący Rust runtime-control/API, Python launcher,
grupa Compose `fullmag-worktree-fullmag-8a0aa9b8c1577182`, Control Room/Playwright.

**Specyfikacja:** bezpośrednie polecenie użytkownika; ADR 0061 — terminalna awaria
przed startem workera; `docs/specs/native-runtime-service-v1.md`;
`docs/specs/compute-resource-execution-v1.md`; zachowane raw receipty
`own-scheduler-block/summary.json` w operacyjnych artefaktach tego zadania.

## Ograniczenia

- Istniejący worktree i branch; nie zmieniać MAIN ani grup innych wątków.
- Zachować sesje, wyniki, intent/CAS, historyczne dzienniki i dowody awarii.
- Nie ponawiać niejednoznacznych POST ani Solve po awarii. Nowe próby mają
  oddzielne jawne request/run IDs i wejście z limitem pracy.
- Żadnych lokalnych kompilacji unit tests Rust/C++; regression cases uruchamia
  autoryzowane GitHub CI. Lekkie Python checks dozwolone.
- Build i runtime wyłącznie w przypisanej grupie przez launcher/just.
- `Consumed`, `Unknown`, zmiana ownera/pinów lub inne aktywne rezerwacje blokują
  no-spawn cancellation; brak dowodów nigdy nie jest dowodem braku workera.
- Nie wyłączać walidacji czasu, boot ID, ownera, generacji ani limitów zasobów.

## Ryzyka do review

- Dwa odczyty próbki przed spawnem: drugi nie może nadal kończyć schedulera
  ogólnym błędem ani pozostawiać aktywnego supervision slotu.
- Wyczerpany retry oddaje sterowanie pętli schedulera, aby drain/anulowanie
  pozostawały obsługiwane. Ten sam claim/Start/lease pozostaje przypięty.
- Błędy właściciela, konfiguracji, CAS i uszkodzonego rekordu nadal są fatalne.
- Operator używa natywnego monotonicznego protokołu, a nie edycji JSON.
- Stop po błędzie i start nowej binarki muszą mieć kompletne receipty Linux,
  również przy zachowanym niepustym store i terminalnym runie.

## Kroki

- [x] Zidentyfikować wyzerowanie przyczyny w `host_runtime` i brak deferral
  w `accepted_study_supervisor`; zachować wcześniejsze receipty błędu.
- [x] Dodać regresje Rust dla chwilowego braku próbki, odroczenia po retry,
  ponownego odczytu i niezmienionej fatalności konfliktów tożsamości.
- [x] Poprawić `crates/fullmag-runtime-control/src/host_runtime.rs` i
  `crates/fullmag-api/src/accepted_study_supervisor.rs`; przypiąć testy w CI.
- [x] Dodać managed wrapper natywnego no-spawn cancellation, jego Python
  regresje, receptę just i dokumentację istniejącego operatora. Przed apply
  ponownie sprawdzić rzeczywiste piny i wszystkie chronione dane runów.
- [ ] Wykonać jedną kontrolowaną cancellation; potwierdzić `Cancelled`,
  `Closed`, oba release i niezmienność pozostałych runów. Zachować receipt.
- [ ] Zakwalifikować i wykonać bezpieczny stop/restart wyłącznie własnej grupy;
  poprawić właściwy managed guard, jeżeli brakuje zgodnej ścieżki Linux.
- [ ] Build aplikacji w tej grupie; sprawdzić scheduler po odświeżeniu próbki
  i terminalny wynik kontrolnego FDM z jawnym output storage i limitem czasu.
- [ ] UI: Airbox ma H_demag/H_eff/H_ext i nie ma m; dane H_demag mapują się
  dokładnie na pusty support, widoczne strzałki w screenshot, niezagubiony
  WebGL, dodatni drawing buffer. Nie mylić SwiftShader z kwalifikacją GPU.
- [ ] Niezależny review, wymagane CI, commit/push/PR/merge i koordynowane FF.
- [ ] Zachować sesje/wyniki i artefakty operatora; drain/usunąć tylko własne
  kontenery, wykonać kwalifikowaną retencję i dokończyć cykl worktree.
  Jeżeli aplikacja blokuje usunięcie primary checkoutu, użyć wspieranego
  surviving checkoutu albo zapisać precyzyjną blokadę bez force.

## Checkpoint źródeł i kontroli

- `18ac614fc1d9ff37541837567768664e1b68ed94`: typed sample error oraz deferral,
  cztery regresje przypięte w CI; lokalnie nie kompilowano testów Rust.
- Wrapper operatora, osobny dowód Linux i finalizer historycznego loader error:
  175 lekkich regresji Python PASS (9 + 10 + 35 + 45 + 64 + 12).
- Pierwsze wywołanie operatora zatrzymał loader przed wykonaniem native;
  unknown receipt i request zachowane. Kontrolowane 86 plików / 324022 B
  pozostaje byte-identical; dokładny probe owner/config/claim/lease/gate także.
- Kanoniczne środowisko CPU ABI + `ldd` przechodzi w działającym backendzie.
  Odczytowy helper z przypiętego obrazu potwierdził właściwe binarium.
- Managed preview reconciliacji: PASS, 12 plików target runu, inventory
  `acb6ddc2a1841193a511ff4c1a4e2807ad5e3fc33f401ba6cba94cd107df5e09`.
  Na tym checkpointcie apply, przebudowa i końcowy render pozostają niewykonane.
