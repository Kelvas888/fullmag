# ADR 0058 — generacja treści artefaktów frequency domain

Status: accepted jako kontrakt korekty C03; implementacja w toku, runtime NOT VERIFIED. Data: 2026-10-13.

## Problem i decyzja

`artifact_set_id` wyprowadzony ze ścieżki identyfikuje miejsce, nie wspólną publikację widma i CSV. Dodajemy `frequency_domain/generation.v1.json`, schema `frequency_domain_artifact_generation.v1`. Koperta zawiera jawnego producer albo null oraz uporządkowaną mapę canonical relative paths → byte_length/SHA256. `generation_id` to SHA256 serde_json zwartej serializacji body, z kolejnością BTreeMap. Commit nie jest swoim członkiem. Ścieżki absolutne, traversal, symlinki i Windows reparse points są odrzucane.

Producent bierze listę z bieżącego wywołania write_artifacts, nie ze skanu katalogu. Uwzględnia metadata.json i faktycznie zapisane periodic_pairs/node_geometry. Writer uzyskuje wyłączny lease przed końcowymi zapisami; istniejący lease daje błąd, bez automatycznej kradzieży ani recovery. Marker zapisuje atomowo jako ostatni. Unikalny plik tymczasowy zapobiega kolizji zapisów tego samego procesu. FEM eigen otrzymuje execution run/stage identity przed wykonaniem; jawna pełna tożsamość jest zachowana. Nie wyprowadzamy ownera z folderu, aktywnego widza ani nazwy sesji.

## Odczyt, kompatybilność i granice

Czytelnik pobiera marker, weryfikuje canonical serialization i ID, sprawdza dokładne bajty zużytego członka oraz ponawia fence markera. Kontrolowane JSON/CSV mają limit bajtów sprawdzany przed alokacją. Osobny digest pojedynczego pliku i location artifact_set_id pozostają osobnymi pojęciami. Weryfikacja jednego pliku nie kwalifikuje wszystkich członków publikacji.

Bez markera historyczny solo read pozostaje dostępny jako legacy_unverified. Producer null to unbound, nigdy bieżący request owner. Joins potrzebują zgodnej generacji i prawdziwego owner/member binding. SHA256 nie uwierzytelnia producenta i nie stanowi dowodu fizyki.

Zachowujemy pliki w ich dotychczasowych lokalizacjach, bez podwajania wielkich pól. Po przerwaniu zapisu stary marker może istnieć, ale zmienione pod nim dane muszą dać stale/conflict; nie obiecujemy zachowania czytelności poprzedniego snapshotu. To celowy odpowiednik fail-closed, a nie immutable history. Recovery lease po awarii wymaga odrębnego sprawdzenia aktywnego właściciela; ten patch nie usuwa danych ani lease automatycznie.

## Bramki i rollback

GHA: zmiana CSV tej samej długości, podmiana markera, byte budget, traversal/symlink, obcy run/stage, concurrent lease i legacy/unbound. API/OpenAPI/UI wymagają kolejnego spójnego etapu. Managed publication, browser i science pozostają NOT VERIFIED aż do osobnego dowodu. Rollback usuwa producenta addytywnej koperty i świadomie przywraca legacy_unverified, nie uznaje location hash za verified join.


## Rozszerzenie G3 — niezmienne generacje v2

Decyzja: accepted jako cel korekty G3, implementacja etapowa; poniższy kontrakt
nie oznacza jeszcze przełączenia produkcyjnego writera ani kwalifikacji runtime.

Nowy marker `frequency_domain/generation.v2.json` o schema
`frequency_domain_artifact_generation.v2` wskazuje dokładne member bytes w
`frequency_domain/generations/<generation_id bez prefiksu sha256:>/`.
Logiczne ścieżki oraz body-content SHA pozostają jawne; marker nie jest memberem.
Writer zapisuje exact invocation membership do prywatnego stagingu obok
katalogu docelowego, synchronizuje pliki, publikuje katalog create-only przez
wspólny `fullmag_session::publish_directory`, a na końcu atomowo zastępuje
current marker. Nie ma wyboru generacji przez listing lub mtime, automatycznego
GC, ani nadpisywania poprzednich folderów. Tożsamość producer pochodzi z tej
samej granicy wykonania co v1; SHA nie uwierzytelnia ownera.

Obecny v2 ma pierwszeństwo nad v1. Uszkodzony v2, brak członka, traversal,
symlink/reparse point lub różnica hash/length kończą odczyt błędem; nie ma
fallbacku do v1 lub root legacy. Capture rozwiązuje wyłącznie zadeklarowane
logical members pod własnym immutable prefixem i ponawia current fence.
Poprzedni folder pozostaje przechowany, lecz capture API dla current może po
nowej publikacji zwrócić stale; dostęp do historii wymaga osobnej jawnej trasy.

Kompatybilność: v1 zachowuje istniejące member-byte verification i statusy
czytnika, ale jawne `is_immutable()` jest false. Nie awansujemy v1 do immutable
history i nie migrujemy istniejących danych. Brak jakiegokolwiek markera to nadal
legacy_unverified. Pierwszy etap dodaje v2 publisher/capture; wspólny finalny
writer pozostaje v1 do ukończenia odczytów API i regression checks. Bezpośrednie
standalone writers bez commitu pozostają legacy-only. CAS accepted-study outputs
mają odrębnego ownera i nie dostają drugiego konkurencyjnego publishera.

Wynik rename po błędzie bariery może być niepewny; zachowujemy typowaną przyczynę,
folder oraz dotychczasowy selector i wymagamy jawnego reconciliation. Awaria po
rename przed markerem pozostawia orphan, którego reader nie wybiera. Windows
nie ma tu dowodu directory sync; power-loss durability pozostaje NOT VERIFIED.

Obowiązki integracyjne: `artifact_generation.rs`, wspólny `artifacts.rs`,
reader owner/root resolver `analysis/results.rs`, `analysis/frequency_domain.rs`
i `data/fields.rs`, a także testy Linux/Windows dla no-replace, crash points,
v1/v2 priority, malformed-v2/no-fallback oraz A/B joins. Obecne DTO nie zmieniają
się w etapie addytywnym; przed przełączeniem routingu konieczny jest dowód, że
logical path nie otwiera root legacy membera zamiast captured immutable membera.
Runtime, browser i scientific qualification pozostają osobnymi bramkami.
