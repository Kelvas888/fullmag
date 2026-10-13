# Źródła i metodyka V2

## Tożsamość i zakres

Dokumentacja V2: **12 października 2026**. Audyt V1 i przegląd użytkownika: 11 października 2026. Kod pozostaje przypięty do **2a3c6becb9c7e111ae1497ec0cd9ac9576acba95**. Nie pobierano nowszego HEAD w celu podmiany snapshotu. To aktualizacja dokumentacji na podstawie Q01–Q24, nie ponowna kwalifikacja bieżącego mastera na dzień V2.

Oryginalny `manifest.json` ma SHA256 `d635a2619655b71f66685ad86f8069988d12020410f3269764af9688cbe9b3d0`; wartość przeliczono na pliku z ZIP i zgadza się z uwagami użytkownika. Pliki historyczne znajdują się w `historical/`. Nie zmieniono repozytorium, worktree użytkownika ani archiwum V1.

Zakres obejmuje geometry/mesh authoring w istniejącym Control Room. Poza zakresem pozostają: legacy_web, pełna refaktoryzacja wyników/wykresów/Automation, implementacja solverów, kwalifikacja aparatury i rzeczywiste benchmarki. Zmiany backend/Python opisane są jako wymagane punkty integracji, nie jako wykonane wdrożenie.

## Co zweryfikowano w tej rewizji

Ponownie odczytano przez konektor GitHub kontrakt transakcji geometrii, handler i dispatcher, Transform3D, ograniczenia adaptera Rust i Python, bounds oraz instrukcje frontendu i widoczną część AGENTS. Odczyty są zakresowe. Przykładowo lokalne linie handlera przytoczone przez recenzenta nie były liniami HEAD: użyto stabilnego symbolu `apply_object_geometry_patch` i ponownie znaleziono go w zakresie 4100–4330. Nie korygowano lokalnego checkoutu użytkownika.

Potwierdzono: geometry+transform w jednej scenie; zastępowanie pełnego Transform3D; obecność pól q/scale/pivot; odmowę rotation/scale w odczytanych adapterach; pominięcie pivotu w odczytanej funkcji bounds. Nie dowiedziono całego łańcucha blokad/CAS/trwałego zapisu w `main.rs`, nie zweryfikowano wszystkich evaluatorów CPU/GPU. Dlatego T51/T52 i macierz kwalifikacji są warunkami odbioru, nie dowodami PASS.

Próba pobrania pełnego pliku bezpośrednio do kontenera nie powiodła się z powodu braku rozwiązywania DNS. Duże odpowiedzi konektora były obcinane; opierano się na osobno odczytanych zakresach, nie rekonstruowano brakujących fragmentów. Rejestr S25–S32 podaje nowe dowody; S01–S24 są odziedziczone z V1 i nie udają pełnego ponownego odczytu.

Wykonano tylko lokalną kontrolę pakietu, modeli algebraicznych/fixture i spójności dokumentacji. Nie uruchomiono Fullmaga, Vitest, meshera, runtime, WebGL ani benchmarku. Oryginalnych R01–R07 nie uruchamiano ponownie i nie nadpisano ich wyników. Nowe obliczenia geometryczne to niezależne oracle dokumentacji, nie testy poprawionej produkcji.

## Klasy ustaleń i statusów

| Klasa | Znaczenie |
|---|---|
| C | Statycznie potwierdzona struktura/zachowanie w odczytanym kodzie. |
| L | Kod i historyczny izolowany model mechanizmu; nie E2E. |
| R | Ryzyko integracyjne wymagające reprodukcji w produkcyjnej ścieżce. |
| G | Luka względem żądanego zakresu produktu. |

Klasy i priorytety wszystkich 28 pozycji zachowano. Korekty F03/F10 zmieniają interpretację i plan naprawy, nie stan implementacji. Pole `status=not_retested_in_production` zapobiega odczytaniu aktualizacji Markdown jako zamknięcia defektów. `planned/unsupported/qualified` w macierzy realizacji nie jest zamiennikiem C/L/R/G.

## Źródła nowe — zakresy i symbole

### S25 — `crates/fullmag-api/src/schemas/authoring.rs`

Odczyt: 1440–1645. Symbole: `AuthoringTransactionRequest::PatchObjectGeometry`, `AuthoringTransactionResponse`.

[Źródło na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-api/src/schemas/authoring.rs) · Git blob SHA `d04dcbd98bc87fc48af85348e060ea243322f9cc`. Nie jest to lokalnie obliczony SHA256.

### S26 — `crates/fullmag-api/src/router_v2/handlers/model/authoring.rs`

Odczyt: 3260–3505; 4100–4330; 2800–2880. Symbole: `commit_authoring_transaction`, `apply_object_geometry_patch`, `patch_authoring_object_geometry`, `apply_create_object_transaction`.

[Źródło na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-api/src/router_v2/handlers/model/authoring.rs) · Git blob SHA `5f9e4ddd81338caa1ff20c13a83a07bf8e04982f`. Nie jest to lokalnie obliczony SHA256.

### S27 — `crates/fullmag-authoring/src/scene.rs`

Odczyt: 130–215. Symbole: `Transform3D`, `impl Default for Transform3D`.

[Źródło na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-authoring/src/scene.rs) · Git blob SHA `d57b91ad0d5db7ed8989e4a31a9bc9b5588e5fa2`. Nie jest to lokalnie obliczony SHA256.

### S28 — `crates/fullmag-authoring/src/adapters.rs`

Odczyt: 80–245. Symbole: `scene_document_to_script_builder`, `owner_transform_rotation_scale_unsupported`.

[Źródło na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-authoring/src/adapters.rs) · Git blob SHA `515ab5d8b1a8a252e706a50ad9103e91ac449c6f`. Nie jest to lokalnie obliczony SHA256.

### S29 — `packages/fullmag-py/src/fullmag/runtime/scene_document.py`

Odczyt: 1920–2025. Symbole: `_owner_frame_translation`, `builder_overrides_from_scene_document`.

[Źródło na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/packages/fullmag-py/src/fullmag/runtime/scene_document.py) · Git blob SHA `9ac49c5f39686132076d797b677d271000d32181`. Nie jest to lokalnie obliczony SHA256.

### S30 — `crates/fullmag-authoring/src/geometry.rs`

Odczyt: 320–520; 900–1020. Symbole: `realize_geometry_scene`, `geometry_capabilities`, `derive_object_bounds`, `derive_geometry_bounds`.

[Źródło na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/crates/fullmag-authoring/src/geometry.rs) · Git blob SHA `728fbe032ff0009a9333c07a3b3062c8c32802a9`. Nie jest to lokalnie obliczony SHA256.

### S31 — `.agents/instructions/frontend.md`

Odczyt: 1–260. Symbole: `9.1 Control-room API invariant`, `9.2 Frontend architecture invariant`, `9.4 Zero-tolerance quality gate`, `Reguły z korekt projektu`.

[Źródło na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/.agents/instructions/frontend.md) · Git blob SHA `392039b2692c0cb5dec95085fdd3af1d5eddd27d`. Nie jest to lokalnie obliczony SHA256.

### S32 — `AGENTS.md`

Odczyt: 1–100. Symbole: `Obowiązkowy cykl pracy w worktree`, `Kontrakt Fullmag`, `Build i dowody`.

[Źródło na SHA](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/AGENTS.md) · Git blob SHA `945a1e883ff54ae3b8830d662c1a57ef4f6d161b`. Nie jest to lokalnie obliczony SHA256.

## Źródła odziedziczone i kontrola referencji

Pełne wpisy S01–S32: [sources.json](../sources.json). Oryginalne zakresy V1: [historical/v1_sources.json](../historical/v1_sources.json). D02 linkuje każdy dowód do tego SHA; nowe fragmenty mają symbol i zakres. Hash podany przez recenzenta nie jest przedstawiany jako samodzielnie obliczony hash pliku repo.

Do samodzielnego czytania raportu linki do GitHuba wymagają dostępu do repozytorium; dokumenty, diagramy, makiety, fixtures i wyniki kontroli pakietu są lokalne. Bibliografia komercyjna z V1 pozostaje referencją projektową; nie wykonano ponownej kontroli dostępności jej zewnętrznych stron.

## Kontrola galerii i oracle dokumentacji

Przykład TRS/pivot, AABB, przekrój tetra i parser/no-op sprawdzono niezależnym skryptem dokumentacji. Obejrzano M02 i arkusz siedmiu makiet; etykiety v2 nie zastępują kwalifikacji kontrolki. Czytnik HTML sprawdzono w Chromium przez dostarczenie własnej treści (`set_content`); środowisko blokowało nawigację `file://`. Sprawdzono 17 widoków, załadowanie 11 obrazów i nawigację do decyzji, planu, testów oraz galerii bez page errors. To nie uruchomienie Control Room ani test WebGL Fullmaga. [Wynik kontroli galerii](../verification/gallery_browser_check.json).
