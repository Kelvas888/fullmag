# P0 — aktualny inwentarz operacji API

Stan źródła: 42d92610312871d591db16a5b60a8f7a6d6339b5 (master). Wygenerowane OpenAPI ma SHA-256 2c9fa47e8d0e087e2ec2293ac5ff9a9f1cdee6a6c7fbd1d8bce835a8b568c7ad.

- OpenAPI: **307 ścieżek**, **371 operacji**.
- Zakres /v2/sessions/current: **308 operacji**.
- Dopasowanie do routera: **371/371** z rozpoznanym handlerem; **0** nierozstrzygniętych i **0** bez rejestracji routera.
- Router-only: **2** rejestracje poza OpenAPI.

Porównanie z poprzednim [inventory.json](inventory.json) (HEAD 93f11dbc564c00b725d174ccb2fd0ff9a96493c9, OpenAPI SHA-256 29869197ba8976190a6c53f45e9d39610705407348f6a82b6f0fc20b9347da54): **304 → 371 operacji**, czyli **67 dodanych i 0 usuniętych** według pary metoda + znormalizowana ścieżka.

## Pochodzenie i metoda

Inwentarz używa źródła checkoutu na HEAD 42d92610312871d591db16a5b60a8f7a6d6339b5. Przed wygenerowaniem sprawdzono brak zmian i plików nieśledzonych w OpenAPI oraz routerze tymi poleceniami:

- `git status --short --untracked-files=all -- apps/control-room/src/kernel/api/generated/openapi-v2.json crates/fullmag-api/src/router_v2`
- `git diff --quiet HEAD -- apps/control-room/src/kernel/api/generated/openapi-v2.json crates/fullmag-api/src/router_v2`

SHA-256 schematu i drzewa źródeł routera zapisano w [JSON](07-current-api-inventory.json).

Mapowanie wykonano helperem scripts/audit_refactor_p0.py, przez operation_mapping(root, {}): metoda/ścieżka OpenAPI → literalna rejestracja Axum → definicja symbolu handlera. Dowód konsumentów celowo wyłączono, bo współdzielony checkout ma zmienione niezwiązane pliki źródłowe. FOUND znaczy tylko, że symbol handlera odnaleziono w źródle; nie potwierdza poprawności semantyki ani wykonania.

Dwie rejestracje router-only:

| Metoda | Ścieżka | Handler | Rejestracja |
|---|---|---|---|
| GET | /v2 | get_v2_index | crates/fullmag-api/src/router_v2/mod.rs:69 |
| PUT | /v2/sessions/current/model/script | handlers::model::sync_authoring_script | crates/fullmag-api/src/router_v2/mod.rs:310 |

Macierz 371 operacji ze statusem review znajduje się w [P3a current endpoint review](../p3a/10-current-endpoint-review.md). Poprzednia macierz P3a nie jest automatycznie dziedziczona. To źródłowy inwentarz, nie bramka runtime; runtime pozostaje **NOT VERIFIED**.
