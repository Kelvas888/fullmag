# ADR 0058 â€” generacja treĹ›ci artefaktĂłw frequency domain

Status: accepted jako kontrakt korekty C03; implementacja w toku, runtime NOT VERIFIED. Data: 2026-10-13.

## Problem i decyzja

`artifact_set_id` wyprowadzony ze Ĺ›cieĹĽki identyfikuje miejsce, nie wspĂłlnÄ… publikacjÄ™ widma i CSV. Dodajemy `frequency_domain/generation.v1.json`, schema `frequency_domain_artifact_generation.v1`. Koperta zawiera jawnego producer albo null oraz uporzÄ…dkowanÄ… mapÄ™ canonical relative paths â†’ byte_length/SHA256. `generation_id` to SHA256 serde_json zwartej serializacji body, z kolejnoĹ›ciÄ… BTreeMap. Commit nie jest swoim czĹ‚onkiem. ĹšcieĹĽki absolutne, traversal, symlinki i Windows reparse points sÄ… odrzucane.

Producent bierze listÄ™ z bieĹĽÄ…cego wywoĹ‚ania write_artifacts, nie ze skanu katalogu. UwzglÄ™dnia metadata.json i faktycznie zapisane periodic_pairs/node_geometry. Writer uzyskuje wyĹ‚Ä…czny lease przed koĹ„cowymi zapisami; istniejÄ…cy lease daje bĹ‚Ä…d, bez automatycznej kradzieĹĽy ani recovery. Marker zapisuje atomowo jako ostatni. Unikalny plik tymczasowy zapobiega kolizji zapisĂłw tego samego procesu. FEM eigen otrzymuje execution run/stage identity przed wykonaniem; jawna peĹ‚na toĹĽsamoĹ›Ä‡ jest zachowana. Nie wyprowadzamy ownera z folderu, aktywnego widza ani nazwy sesji.

## Odczyt, kompatybilnoĹ›Ä‡ i granice

Czytelnik pobiera marker, weryfikuje canonical serialization i ID, sprawdza dokĹ‚adne bajty zuĹĽytego czĹ‚onka oraz ponawia fence markera. Kontrolowane JSON/CSV majÄ… limit bajtĂłw sprawdzany przed alokacjÄ…. Osobny digest pojedynczego pliku i location artifact_set_id pozostajÄ… osobnymi pojÄ™ciami. Weryfikacja jednego pliku nie kwalifikuje wszystkich czĹ‚onkĂłw publikacji.

Bez markera historyczny solo read pozostaje dostÄ™pny jako legacy_unverified. Producer null to unbound, nigdy bieĹĽÄ…cy request owner. Joins potrzebujÄ… zgodnej generacji i prawdziwego owner/member binding. SHA256 nie uwierzytelnia producenta i nie stanowi dowodu fizyki.

Zachowujemy pliki w ich dotychczasowych lokalizacjach, bez podwajania wielkich pĂłl. Po przerwaniu zapisu stary marker moĹĽe istnieÄ‡, ale zmienione pod nim dane muszÄ… daÄ‡ stale/conflict; nie obiecujemy zachowania czytelnoĹ›ci poprzedniego snapshotu. To celowy odpowiednik fail-closed, a nie immutable history. Recovery lease po awarii wymaga odrÄ™bnego sprawdzenia aktywnego wĹ‚aĹ›ciciela; ten patch nie usuwa danych ani lease automatycznie.

## Bramki i rollback

GHA: zmiana CSV tej samej dĹ‚ugoĹ›ci, podmiana markera, byte budget, traversal/symlink, obcy run/stage, concurrent lease i legacy/unbound. API/OpenAPI/UI wymagajÄ… kolejnego spĂłjnego etapu. Managed publication, browser i science pozostajÄ… NOT VERIFIED aĹĽ do osobnego dowodu. Rollback usuwa producenta addytywnej koperty i Ĺ›wiadomie przywraca legacy_unverified, nie uznaje location hash za verified join.


## Rozszerzenie G3 â€” niezmienne generacje v2

Decyzja: accepted jako cel korekty G3, implementacja etapowa; poniĹĽszy kontrakt
nie oznacza jeszcze przeĹ‚Ä…czenia produkcyjnego writera ani kwalifikacji runtime.

Nowy marker `frequency_domain/generation.v2.json` o schema
`frequency_domain_artifact_generation.v2` wskazuje dokĹ‚adne member bytes w
`frequency_domain/generations/<generation_id bez prefiksu sha256:>/`.
Logiczne Ĺ›cieĹĽki oraz body-content SHA pozostajÄ… jawne; marker nie jest memberem.
Writer zapisuje exact invocation membership do prywatnego stagingu obok
katalogu docelowego, synchronizuje pliki, publikuje katalog create-only przez
wspĂłlny `fullmag_session::publish_directory`, a na koĹ„cu atomowo zastÄ™puje
current marker. Nie ma wyboru generacji przez listing lub mtime, automatycznego
GC, ani nadpisywania poprzednich folderĂłw. ToĹĽsamoĹ›Ä‡ producer pochodzi z tej
samej granicy wykonania co v1; SHA nie uwierzytelnia ownera.

Obecny v2 ma pierwszeĹ„stwo nad v1. Uszkodzony v2, brak czĹ‚onka, traversal,
symlink/reparse point lub rĂłĹĽnica hash/length koĹ„czÄ… odczyt bĹ‚Ä™dem; nie ma
fallbacku do v1 lub root legacy. Capture rozwiÄ…zuje wyĹ‚Ä…cznie zadeklarowane
logical members pod wĹ‚asnym immutable prefixem i ponawia current fence.
Poprzedni folder pozostaje przechowany, lecz capture API dla current moĹĽe po
nowej publikacji zwrĂłciÄ‡ stale; dostÄ™p do historii wymaga osobnej jawnej trasy.

KompatybilnoĹ›Ä‡: v1 zachowuje istniejÄ…ce member-byte verification i statusy
czytnika, ale jawne `is_immutable()` jest false. Nie awansujemy v1 do immutable
history i nie migrujemy istniejÄ…cych danych. Brak jakiegokolwiek markera to nadal
legacy_unverified. Pierwszy etap dodaje v2 publisher/capture; wspĂłlny finalny
writer pozostaje v1 do ukoĹ„czenia odczytĂłw API i regression checks. BezpoĹ›rednie
standalone writers bez commitu pozostajÄ… legacy-only. CAS accepted-study outputs
majÄ… odrÄ™bnego ownera i nie dostajÄ… drugiego konkurencyjnego publishera.

Wynik rename po bĹ‚Ä™dzie bariery moĹĽe byÄ‡ niepewny; zachowujemy typowanÄ… przyczynÄ™,
folder oraz dotychczasowy selector i wymagamy jawnego reconciliation. Awaria po
rename przed markerem pozostawia orphan, ktĂłrego reader nie wybiera. Windows
nie ma tu dowodu directory sync; power-loss durability pozostaje NOT VERIFIED.

ObowiÄ…zki integracyjne: `artifact_generation.rs`, wspĂłlny `artifacts.rs`,
reader owner/root resolver `analysis/results.rs`, `analysis/frequency_domain.rs`
i `data/fields.rs`, a takĹĽe testy Linux/Windows dla no-replace, crash points,
v1/v2 priority, malformed-v2/no-fallback oraz A/B joins. Obecne DTO nie zmieniajÄ…
siÄ™ w etapie addytywnym; przed przeĹ‚Ä…czeniem routingu konieczny jest dowĂłd, ĹĽe
logical path nie otwiera root legacy membera zamiast captured immutable membera.
Runtime, browser i scientific qualification pozostajÄ… osobnymi bramkami.
