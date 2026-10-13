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
