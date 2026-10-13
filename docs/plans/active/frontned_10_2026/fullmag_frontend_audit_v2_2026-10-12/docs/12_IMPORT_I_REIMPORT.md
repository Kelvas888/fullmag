# Import i reimport — kontrakt projektu R2-I

ADR-07 do akceptacji. Dowody dotychczasowe S12/S13: wejście Start klasyfikuje STL jako niedostępny; backend assets odczytano jako parser summary. Nie wykazano kompletnego staged-asset lifecycle. Poniższe zasoby są propozycją rozszerzenia v2, nie listą istniejących endpoints.

## 1. Zasoby i transport

| Proponowana operacja pod `/v2/sessions/current/` | Wejście | Wynik / własność |
|---|---|---|
| POST `model/import-stages` | Filename, declared bytes, source format, optional expected hash | stageId, upload lease, backend-published limits; jeszcze zero scene objects |
| PUT `model/import-stages/{id}/content` | Binary bytes, nie base64 JSON | Immutable uploaded content hash; kontrola długości i quota |
| PATCH `model/import-stages/{id}/settings` | Stage version, source units, import mode, tolerance choices | Nowa settings revision; poprzednie checks stają się stale |
| POST `model/import-stages/{id}/checks` | Stage/settings revision, requested mode, intentId | Asynchroniczny check job; status/receipt, nie udawane immediate PASS |
| GET `model/import-stages/{id}` / `checks` | Id + scope | State/limits/settings/check results/leases; cienki control plane |
| GET `data/import-stages/{id}/preview` | Stage version, quality/budget profile | Binary positions/indices/normals + frame/units/version metadata |
| POST `model/transactions` z nowym typed attach/reimport variant | base_revision, stage/version/hash, object_id, full transform, intentId | Atomowy attach sprawdzonej wersji do sceny; stage staje się referenced |
| DELETE `model/import-stages/{id}` | Id i lease ownership | Cancel/release stage; nie usuwa już przyłączonej wersji assetu |

Endpoint strings powstają w centralnym API layer. Komponenty nie wysyłają surowego fetch. Capability procesu mówi, czy importer jest zainstalowany, sesji — czy dana geometria może wejść do wybranej realizacji; checks report dotyczy konkretnej wersji źródła i ustawień. Brak któregokolwiek nie jest zastępowany zielonym checkboxem UI.

Przykładowe stany stage: allocated → uploading → uploaded → checking → checked / invalid / cancelled / expired. `checked` nie znaczy volume-ready; ma wyniki per requested mode. Zmiana units/weld settings unieważnia sprawdzenia i derived preview z poprzedniej wersji. Worker publikuje wynik wyłącznie dla pasującej stage/settings revision.

## 2. Source asset a geometria obiektu

Referencja proponowana w scenie/eksporcie:

```json
{
  "asset_id":"asset-uuid",
  "version_id":"version-uuid",
  "content_sha256":"hex-of-original-bytes",
  "source_format":"stl-binary",
  "source_length_unit":"nm",
  "import_settings_version":"stl-import-v1",
  "canonical_surface_ref":"project-asset://version-uuid/surface-v1",
  "checks_ref":"project-asset://version-uuid/checks-v1"
}
```

To logical resource reference, nie arbitralna ścieżka dysku ani URL do pobrania przez solver. Publiczny Python DSL musi umieć otworzyć ten sam asset z zapisanego projektu i wyeksportować edytowalną deklarację; dokładna nowa funkcja DSL wymaga repo-owego API review, nie dopisujemy nieistniejącego `fullmag.import_stl()` jako działającego polecenia. ProblemIR ma przechowywać rozwiązaną, wersjonowaną referencję/geometry descriptor bez utraty hash/units, a engine/mesher korzystać z kanonicznych SI danych.

Bajty źródła są immutable. Source-unit conversion wykonywana raz: source → canonical SI surface. `Transform3D.scale` jest osobną fizyczną transformacją. Zmiana nm→mm w settings to nowa import version/checks, a nie druga ukryta skala dołożona przez renderer. Preview pokazuje source bounds i wynik w SI/display units.

## 3. Checks i poziomy dopuszczenia

| Check | Construction-only | FEM volume | FDM occupancy |
|---|---|---|---|
| Integralność pliku, liczba rekordów, finite coordinates, limity | Wymagane | Wymagane | Wymagane |
| Niezerowe użyteczne trójkąty / degenerate report | Raport; odrzucenie całkowicie pustej geometrii | Wymagane usunięcie/naprawa w jawnej operacji | Wymagane dla stabilnego testu inside |
| Jednostki i bounds | Wymagany jawny wybór | Wymagany | Wymagany |
| Zamkniętość, manifold, spójna orientacja | Może być warning; brak solver participation | Wymagane przed attach jako magnetic volume | Wymagane dla wybranego solid occupancy rule |
| Self-intersections | Unknown dozwolone tylko z construction warning | Musi być checked-pass albo jawny supported repair | Musi być checked-pass dla solid mode |
| Components/nested shells | Wybór widoku, bez domysłu bryły | Jawna interpretacja cavities/components | Jawna parity/winding/material ownership policy |
| Region/boundary binding | Brak fizyki domyślnej | Wymagane do planu solvera | Wymagane do membership |

Construction-only oznacza wyłączony obiekt pomocniczy z jawnie zapisanym przeznaczeniem, nie „magnes bez dobrego meshu”. Z nazwy `.stl` ani typu presentation nie wynika obecność materiału czy interakcji. Otwartej powierzchni nie wolno domknąć niewidoczną płaszczyzną jako heurystyki occupancy.

Normalne zapisane w STL nie są samodzielnym certyfikatem poprawnej orientacji. Welding/repair to wersjonowana operacja z raportem before/after i tolerancją w SI; default brak automatycznej naprawy. Check unknown nie jest PASS. Nie pobierać arbitralnych lokalnych ścieżek/URL z pliku; importer ma operować wyłącznie na zweryfikowanych upload assets w swoim scope.

## 4. Limity, anulowanie i retencja

**Proponowana początkowa polityka dopuszczenia, do akceptacji ADR-07 i pomiaru B0:** max 64 MiB bajtów źródła oraz 1,000,000 trójkątów, oba ograniczenia jednocześnie. Nie są to zmierzone bezpieczne maksimum sprzętu ani gwarancja czasu importu. Dla binary STL minimalny rozmiar to 84+50N bajtów; 1 mln rekordów to około 50 MB źródła, a runtime potrzebuje dodatkowych buffers/BVH i kopii. Dlatego capabilities muszą publikować rzeczywisty limit backendu, a frontend nie może go sam zwiększać.

Na serwerze: limit transportu przed pełnym read, bezpieczne sprawdzanie overflow liczników, bounded parser, budget time/cancel i quota stagingu per project. Preview korzysta z worker/data plane i nie umieszcza całej tablicy w React state. ASCII ma limit bajtów niezależny od triangle count. Odrzucenie nie zostawia częściowego scene-object. Obniżona jakość preview jest jawnym trybem, nie ukrytym warunkiem „przejścia” benchmarku.

Proponowany lease dla nieprzyłączonego uploadu: 24 h od ostatniej potwierdzonej aktywności; konkretne `expires_at` zwraca backend. To polityka produktu, nie stan istniejący. Podczas aktywnego check jobu lease jest przypięty; staging nie znika pod workerem. Cancel przerywa własny job i zwalnia własne references; nie kasuje współdzielonych referenced assets. Po reload: GET stage/check receipt; po expired poprosić o ponowny upload, nie deklarować zachowanych bajtów.

Przyłączona wersja jest przechowywana do czasu utraty wszystkich referencji projektu/historii i jawnej procedury GC. Wymagany reachability graph obejmuje także unresolved edits i receipt snapshots, jeśli są potrzebne do recovery. Żaden komponent unmount nie usuwa serwerowego assetu jako efekt cleanup.

## 5. Samowystarczalny projekt

Zapis `.fms` ma zawierać oryginalne bajty assetu, ustawienia importu, wersję check engine i wynik checks, immutable normalized surface albo jednoznaczną możliwość jej odtworzenia oraz scene refs. Szczegóły fizycznego kontenera dopasować do istniejącej implementacji persistence; nie zakładać na podstawie rozszerzenia, że już jest zwykłym ZIP-em. Format projektu musi dostać wersjonowaną zmianę/feature requirement.

Projekt z samą ścieżką `C:\\...\\sample.stl` nie spełnia portable mode. External-linked mode jest odłożony; ewentualna przyszła implementacja ma wymagać hash weryfikacji i jawnego unresolved state. Test: zapis na hoście A → odczyt na B bez oryginalnego katalogu, identyczne asset hash/units/world geometry/region mapping.

## 6. Reimport i konflikty

Reimport zachowuje object_id i domyślnie name, tworzy nowy versionId i porównanie. Transakcja zawiera captured base scene revision + expected previous asset version. Zdalna edycja wymiaru/transformu albo reimport wymaga three-way conflict review. Nie używać „ostatni upload wygrywa”.

Material assignment może pozostać object-scoped. Selekcje oparte na source faces/triangles muszą mieć assetVersion provenance; po zmianie triangulacji przechodzą w unresolved. Nie mapować po liczbie, kolejności ani „podobnym ordinalu”. Bbox anchors można przeliczyć, ale importer pokazuje przemieszczenie ich world position. Naprawa orphan bindings: lista regionów/anchors, highlight starej wersji jako snapshot, wybór nowej semantycznej referencji, podgląd i osobny Apply. Stary asset pozostaje dostępny do history/receipt zgodnie z retencją.

## 7. Bramka R2-I

Wymagane: transport i checksum, ASCII/binary parity, units once, closed/open/nonmanifold/selfintersect fixtures, cancellation/reload, portability, reimport conflict i orphan binding. Construction-only oraz każda realizacja FEM/FDM mają osobną qualification. Dostępność importera na CPU nie kwalifikuje GPU occupancy. Dla forced GPU bez wsparcia odmowa, nie cichy fallback.
