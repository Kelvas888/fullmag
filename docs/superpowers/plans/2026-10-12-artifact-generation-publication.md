# Plan naprawy wiązania generacji artefaktów

Uwagi4225198873/4246863076. Source checkpoint02f6f86caaebe4946ef19b8595eddac4adc579d4. Stan: analiza źródłowa zakończona; wdrożenie i runtime NOT VERIFIED. Plan nie zastępuje wykonania pozostałych uwag PR97.

## Potwierdzony problem

API frequency_domain.rs2148 wylicza artifact_set_id ze ścieżki katalogu. Fence2181–2203 wykrywa zmianę root/run/stage, lecz nie zastąpienie plików w tym katalogu. results.rs3714–3740 poprawnie hashuje pojedyncze bajty JSON; nie dowodzi to wspólnej publikacji z CSV.

Single-k eigen_output.rs2772–2777/3273–3297 wiąże hashe spectrum/branches, lecz nie wszystkich CSV/diagnostics. Path manifest ma rewizję opartą na licznikach oraz placeholder owners. artifacts.rs2210–2215 pisze pliki sekwencyjnie; eigen_path.rs4309–4316 umieszcza manifest przed mode_artifacts. Sam hash manifestu w API nie naprawia tego kontraktu.

## Wynik docelowy

Nowy addytywny commit envelope frequency_domain_artifact_generation.v1 wiąże uporządkowane member paths, lengths i SHA256 finalnych bajtów. Nie hashuje sam siebie. Zatwierdzenie następuje atomowo po publikacji wszystkich członków; capture API i joins sprawdzają rzeczywistą generację oraz owners. Numerics, częstotliwości, SI i certyfikaty solvera pozostają oddzielne.

Historyczne pliki zachowują odczyt i własne byte revisions. Status legacy_unverified nie daje uprawnienia do multi-artifact join jako verified generation. Nie usuwać danych, nie wymuszać migracji i nie podmieniać niepewnego ownera przez current lub nazwę folderu.

## Etapy i bramki

1. **Kontrakt i owner publikacji.** Uzupełnić istniejący spec frequency-domain-artifacts-v2 i ADR dla nowego provenance/capability. Rozróżnić request/view session od trwałego publisher/run owner; ustalić prawdziwy PublicationContext u callerów write_artifacts, zamiast inferencji z folderu. Uzgodnić wersję schema, legacy capability i rollback. Odbiór: exact call-site trace i schema/reader tests, brak zmiany solver intent.
2. **Producer commit.** Shared boundary artifacts.rs obejmuje single-k i path, z kompletnością CSV/diagnostics/mode members. Członkowie mają canonical relative paths i final-byte digests; immutable generation lub odpowiednik zachowuje poprzednią publikację przy interruption. Commit marker jest ostatnim atomic replace. Odbiór: interrupted-before-commit nie ujawnia nowej generacji; identyczne bytes+owner zachowują tożsamość, changedsame-length bytes zmieniają ID. Nie wolno dodawać nieautoryzowanego GC ani podwajać bez ograniczeń dużych pól.
3. **API capture i fence.** frequency_domain reader odczytuje commit snapshot, weryfikuje digest/length każdego member i ponownie sprawdza commit przed odpowiedzią oraz istniejący request context. Mismatch daje controlled conflict/degraded, nigdy ready. Odbiór: zmieniony CSV/diagnostics pod starym commit, podmieniony commit między capture/ACK, obcy run/stage/mesh i symlink/path escape odrzucane.
4. **Typowany kontrakt i generated transport.** Capability legacy_unverified/committed_generation_verified oraz member/generation provenance przechodzą OpenAPI i jednego typowanego klienta; nie powstają boczne endpointy. Odbiór: generation/version parsing i roundtrip; historyczny solo odczyt działa, historyczny directory ID nie jest dowodem join.
5. **UI/cache/joins.** studyRuntimeResources oraz frequencyDomainChartModels wymagają tej samej verified generation i rzeczywistych owner/member bindings przy łączeniu branches/CSV. Cache jest unieważniany przez generation revision. Panel gałęzi nie przywraca działania za pomocą niezweryfikowanego aliasu. Odbiór: mixed generations przy tych samych licznikach, długościach i folderze odrzucane; source change usuwa stary join; retained snapshot działa wyłącznie dla tej samej tożsamości.
6. **Kwalifikacja.** Rust producer/API, Python consumers i frontend typy/testy/Doctor tylko w GHA. Osobny browser proof dla handoff i canvas, osobny managed runtime dla publish/capture. Scientific convergence i COMSOL/analytical qualification nie wynikają z green source gates.

Właściciel integracji: bieżący wątek. Etapy2–5 zależą od1; nie wdrażać API-only hash, blanketNone ani trusted stage join jako substytutu kompletnego kontraktu. Zmiana naruszająca historyczny read pozostaje niezatwierdzona, dopóki brak dowodu kompatybilności.

## Źródła i SHA256 lokalnego checkpointu

- `crates/fullmag-runner/src/artifacts.rs`: `d830445eb3bbb93704a792031aadebaa56ede469c05ef4ee26b6425d3b07b2c5`
- `crates/fullmag-runner/src/fem/eigen_output.rs`: `31702762ecc21bce2121b091560ca47f446012cd02bd25292743241e4e56887d`
- `crates/fullmag-runner/src/fem/eigen_path_manifest.rs`: `971c6883420fca36a6bb1ee3e14793eca3d0eced961e7cf6e81596f32bcea84c`
- `crates/fullmag-runner/src/fem/eigen_path.rs`: `fc37b109f78c5c05d22c30db35e84a7589c62283758f30ae13bcce8c70943d09`
- `crates/fullmag-api/src/router_v2/handlers/analysis/frequency_domain.rs`: `908e8d07d12695ad674de1bda7426bf356cbe670a722f3cb65bb467783396eee`
- `crates/fullmag-api/src/router_v2/handlers/analysis/results.rs`: `20f0847215045eca20a537e2bb30f246043447002dfac508674f321b8cd3d7b9`
- `apps/control-room/src/shared/domain/analysis/frequencyDomainChartModels.ts`: `d54e4ac7dc4676085d4e5cc79399dc82aa9eb6e6050326512529e6e66b308b46`


## Checkpoint wdrożenia — 13.10.2026

Pierwotny plan powyżej opisuje stan i propozycję z 12.10. Aktualny kontrakt
określa ADR 0058: final-byte receipt i fail-closed fencing istniejących ścieżek,
bez przechowywania immutable history wszystkich payloadów. Przy przerwanym
nadpisaniu poprzedni marker pozostaje, ale jego zmienione member bytes są
odrzucane; nie obiecujemy odczytu dawnego pełnego snapshotu. Jest to jawne
ograniczenie wobec pierwotnego wariantu immutable storage.

Producer `34abffa93d52c8e7af0736552019d87161ecb920` publikuje marker jako ostatni,
wylicza membership z rzeczywistych auxiliary outputs i blokuje równoczesnych
publisherów lease. GHA38355093226 PASS dla kontraktów producenta. JSON/CSV capture,
status legacy/unbound/owner-bound, owner check i końcowe fences wdrożono w
`5e615ff2088fe1c52a31fa0420ed5e77c2af0894`; uzupełnienie pól i binary data plane
w `af32b8c674b6980c81dc8dd7beee1c97ce601523` oraz poprawka readera
`de5f7354b72c6cf299ce2f8a4f52ba2f8696103d`.

GHA38359249932 SUCCESS: pięć testów generation module, sześć testów snapshot
readerów (JSON/CSV/field/legacy/owner), precondition i header tests, starsze
kontrakty session/dataset/HTTP. Filtr enum test w tym runie uruchomił zero testów;
został skorygowany na właściwy `spectrum_residual_tests` i wymaga named PASS.
Nie zaliczamy wcześniejszego zero-testów jako dowodu enum roundtrip.
OpenAPI i typy pochodzą z hosted generatora dokładnego SHA `de5f7354...`;
source identity jest zachowana w artefakcie GHA.

Cache oraz branch/CSV join wymagają tej samej owner-bound generation:
GHA38357648561 SUCCESS, typy/architecture/Doctor również PASS. Propagacja
artifact-generation query/header do overlay i composition jest kolejnym
fragmentem. Managed publish/capture, real browser/WebGL i scientific
qualification pozostają NOT VERIFIED; source/CI fixture nie zastępują tych bramek.


## Checkpoint weryfikacji 13.10.2026 — generacja binarna i zasoby Slurm

Zdalny checkpoint kodu: `27e1efa74cab04dae9227451a756c646166051ac`.
Nie wykonano lokalnych buildów/testów ani mutacji chronionego HEAD/index/stash.

- `0d022d02994e9ee6ea434458201cc8b0f8458cd0` i `d3ed52c92e4cef8ba5ffec4c61b5d4f90551fd27`: Slurm job-wide memory accounting (również bez SLURM_MEM_*), per-task CPU, affinity/quota, serial allocation i child budget. [GHA38365181150](https://github.com/MateuszZelent/fullmag/actions/runs/38365181150) SUCCESS: 20 allocation tests, 4 worker tests, 28 pool tests oraz istniejące output/prefix/control/writer gates PASS. To kontrakty na hosted Linux, nie receipt rzeczywistego Slurm joba.
- `04de2f5f87a1041571668acb6fb8ff1efce0e42b`: typowany artifact generation query/header, metadata preflight, collection generation consistency, exact retained identity i derived renderer keys. `27e1efa74cab04dae9227451a756c646166051ac` poprawia import helpera w fixture oraz rozłączny typ Analysis Result/Frequency Domain overlay. [GHA38366123014](https://github.com/MateuszZelent/fullmag/actions/runs/38366123014) SUCCESS: 791 testów / 41 plików, pełny typecheck, architecture i React Doctor85. Nie jest to browser/WebGL receipt.
- [GHA38364933538](https://github.com/MateuszZelent/fullmag/actions/runs/38364933538) SUCCESS: canonical generated OpenAPI oraz API contracts, w tym named enum test (poprzedni błędny selector uruchamiał zero testów), capture/fence/field binary, 31 dataset tests, 242 FMS i 83 session tests.
- `9f7baefcbcb809fcee3e4a587f0d8c4a001bef3f`: getter-only bounded C04 v2 IDs/configuration, parser i regresje. Parser w [GHA38364429802](https://github.com/MateuszZelent/fullmag/actions/runs/38364429802) PASS; native MFEM/SLEPc build jeszcze w toku w chwili wpisu. Nie uznano C04 full/mixed za naprawione.

Publikacja C03 zachowuje fail-closed stale/conflict przy zmianie członka, bez immutable history. Ta granica ADR0058 pozostaje jawna. G0/G6/G7/G8, realny managed sweep, nauka, browser oraz integracja PR97 pozostają otwarte. A1=0.005 per pair i native tolerances nie zostały zmienione.
