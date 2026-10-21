# ADR 0067 — niezależne grupy Docker DEV

Status: decyzja użytkownika przyjęta 21.10.2026; implementacja etapami.
Data: 2026-10-21.

Stan implementacji:

| Punkt | Stan |
|---|---|
| 1. Ledger per grupa | **niezaimplementowany**; grupy DEV nadal współdzielą globalny `host-ledger-v1` (etap R2.9 audytu) |
| 2. Statyczne budżety `FULLMAG_DEV_*` | zaimplementowane w launcherze |
| 3. Automatyczny port | zaimplementowany w launcherze |
| 4. Zasada zmian stanu DEV | obowiązuje dla nowych zmian; jedyny wyjątek to istniejący globalny ledger do czasu punktu 1 |

Dopóki punkt 1 nie zostanie wdrożony, migracja polityki globalnego ledgera
nadal wymaga skoordynowanego zatrzymania konsumentów `/host-ledger`
(`--migrate-host-capacity`, ADR 0061).

## Kontekst

Kilku agentów pracuje równolegle w osobnych worktree, każdy w swojej grupie
`fullmag-worktree-<id>` (ADR 0061, 0064). Audyt
`docs/audits/2026-10-21-docker-dev-workflow-audit.md` (§5.8, §9) wykazał, że
jedynym twardym sprzężeniem między grupami jest globalny host ledger: obraz
`fullmag-host-ledger-v1.ext4` w hostowym `storage`, montowany przez
uprzywilejowany `nsenter` i współdzielony przez wszystkie grupy jednego
checkoutu. Każdy `just docker-dev` rejestruje grupę jako jego konsumenta, a
migracja polityki pojemności (`bbf3b2f44`, `ac8f72ffd`) wymaga zatrzymania
wszystkich grup. Pozostałe wspólne zasoby to fizyczne CPU/RAM/GPU maszyny
wirtualnej Docker oraz porty loopback frontendu.

## Decyzja

1. **Ledger per grupa w DEV.** Profil volume DEV (`docker_volume_dev`, cargo
   `backend-dev`) używa ledgera w wolumenie kontrolnym własnej grupy: zwykłe
   pliki i blokada `flock` (`writer.rs`), bez obrazu ext4, urządzenia loop,
   uprzywilejowanego helpera i deskryptora pojemności hosta. Polityka ledgera
   grupy jest jej własnym budżetem. W DEV nie ma admisji rezerwacji między
   grupami. Globalny `host-ledger-v1` pozostaje jedynym źródłem prawdy dla
   release, kwalifikacji i managed runtime (`fullmag_docker_runtime`).
2. **Ochrona między grupami przez statyczne budżety.** Każda grupa dostaje
   limity Compose dla `backend` i `frontend` z `FULLMAG_DEV_BACKEND_CPUS`,
   `FULLMAG_DEV_BACKEND_MEMORY_GIB`, `FULLMAG_DEV_FRONTEND_CPUS` i
   `FULLMAG_DEV_FRONTEND_MEMORY_GIB` (zmienna procesu, potem `.env` głównego
   checkoutu). Wartości domyślne wynikają z pojemności VM, tak aby zmieściły
   się trzy grupy: backend min(8, CPU/4) CPU i min(32, RAM/6) GiB, frontend
   min(4, CPU/10) CPU i 8–16 GiB (dotychczasowe 16 GiB frontendu na dużym hoście). Limity są górnymi granicami, nie
   rezerwacjami: przeciążenie spowalnia grupę, nie zatrzymuje innych. Ta sama
   wartość backendu wyznacza kwotę kontenera, profil natywny
   (`FULLMAG_DOCKER_CPU_MILLIS`, `FULLMAG_DOCKER_MEMORY_BYTES`) oraz
   `CARGO_BUILD_JOBS`. Każda grupa ma jeden równoległy worker GPU
   (`compute_max_concurrency: 1`); `FULLMAG_GPU_ACCESS` wyłącza GPU w grupie.
   Pamięć VRAM nie jest rezerwowana między grupami. Run, dla którego brakuje
   VRAM lub RAM, ma czekać w kolejce z widocznym powodem „oczekiwanie na
   zwolnienie zasobów” na podstawie zmierzonej wolnej pamięci urządzenia
   (osobne zadanie; do czasu wdrożenia brak VRAM kończy run błędem CUDA, bez
   cichego przejścia na CPU).
3. **Port frontendu.** Bez jawnego portu skonfigurowany port jest preferencją
   nowej grupy; zajęty port zastępuje pierwszy wolny w stałej dla projektu
   rotacji kolejnych portów. Porty przypięte przez zatrzymane grupy są
   traktowane jako zajęte. Istniejąca grupa zachowuje swój port.
4. **Zasada zmian stanu DEV.** Zmiana schematu lub polityki stanu DEV
   (ledger, wolumen kontrolny, receipty, dokumenty grupy) jest albo lokalna
   dla jednej grupy i wykonywana przy jej własnym starcie, albo wstecznie
   zgodna, tak że starsze grupy działają bez zmian. Żadna migracja DEV nie
   wymaga zatrzymania cudzych grup ani nie sprawdza ich stanu. Migracje
   globalnego ledgera dotyczą wyłącznie jego konsumentów (kontenerów z
   mountem `/host-ledger`).

## Konsekwencje

- Trzy grupy mogą jednocześnie budować i uruchamiać runy w swoich budżetach;
  restart lub recreate jednej nie zatrzymuje pozostałych.
- Po wdrożeniu punktu 1 także migracja jednej grupy nie zatrzymuje
  pozostałych, a grupy DEV przestają korzystać z kontroli cgroup2
  i deskryptora pojemności hosta.
- Suma budżetów może przekroczyć VM przy niestandardowych wartościach `.env`;
  skutkiem jest spowolnienie lub OOM wewnątrz grupy, która przekroczyła swój
  limit, nie zatrzymanie innych.
- Rezerwacje istniejące w globalnym ledgerze nie są przenoszone do ledgera
  grupy. Grupa przechodzi na ledger per grupa przy własnym starcie z nowym
  kodem.

## Weryfikacja

Wymagany dowód runtime: trzy grupy z trzech worktree startują i kompilują
równolegle, a restart jednej nie zmienia stanu pozostałych (`docker ps`, logi
backendów). Do czasu tego dowodu implementacja ma status NOT VERIFIED.
Punkt 1 wymaga osobnego dowodu: migracja polityki ledgera jednej grupy przy
działających pozostałych grupach.
