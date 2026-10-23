# Naprawa głębokości i podglądu primitive 3D

Cel: usunąć artefakty powierzchni przy zbliżeniu do ringu i zapewnić czytelny
wireframe geometrii przed zbudowaniem siatki, bez zmiany fizyki i solver mesh.

- Checkout: `/home/kkingstoun/git/fullmag/worktrees/viewport-depth-20261022`.
- Branch: `codex/viewport-depth-20261022`.
- Baza: `e19ee0664173b5d0dafe281b402c0b088a11b3d5`.
- Owner: `codex:01a16521-315c-78a3-bf99-15e1b8af74c4`.
- Grupa: `fullmag-worktree-viewport-depth-20261022-d13d8cf2842d9225`.

## Zakres i odbiór

1. Polityka near/far: zachować geometrię przy zmianach FOV, wyeliminować
   załamanie near przy wejściu kamery w globalną sferę bounds, dobrać far do
   rzeczywistej skali sceny. Odbiór: odróżnianie cienkich warstw, perspektywa
   i ortho, zoom/orbit i cel poza modelem.
2. Primitive wireframe: krawędzie opisujące bryłę, bez przekątnych triangulacji
   kapsli ringu. Zachować pole powierzchni, pozycję, picking, bounds i cleanup;
   nie zmieniać wyświetlania właściwej siatki FEM/FDM.
3. Weryfikacja: diagnostyka funkcji, typecheck/lint, React Doctor w zakresie
   zmian, zarządzany browser/WebGL z canvas visibility, kontekstem i buforem.
   Zakaz kompilacji testów jednostkowych pozostaje w mocy. Dowód pikseli musi
   obejmować primitive i gotową siatkę; test obliczeń nie zastępuje obrazu.
4. Review, scoped commit/push/PR, wymagane kontrole, merge i integracja do
   lokalnego mastera z zachowaniem równoległych zmian, cleanup wyłącznie
   zasobów tego zadania. Każda blokada otrzymuje konkretny checkpoint.

## Stan

- Utworzono i zarejestrowano izolację; rejestr w rozwiązanym `storage/index`.
- W masterze pozostaje wcześniejszy audyt i cudze zmiany. Nie skopiowano ich
  do implementacji. Grupa zadania używa portu 3212; master 3198 pozostaje aktywny.
- Zaimplementowano skalowany zakres głębokości, wspólny dla Fit, projekcji
  i bieżącej kamery podczas gestów OrbitControls. Review wykrył i skorygowano
  dodatkowy przypadek środka bounds w płaszczyźnie oka.
- Primitive ma osobny generator krawędzi prezentacyjnych. Diagnostyka
  rzeczywistych deklaracji i Three r186 sprawdza 27 wariantów geometrii.
  Pierwszy przebieg wykrył po cztery rozbieżności na zamknięciach CSG;
  ekstrakcja obrzeży z rzeczywistych trójkątów usunęła rozbieżności.
  Końcowy probe: 27/27 przypadków, zero odcinków poza krawędziami powierzchni.
  Siatka obliczeniowa nie korzysta z tego generatora.
- Lint produkcyjnych zmian i parsery MJS: PASS. Typecheck aplikacji: PASS
  (po poprawieniu zmiennej środowiskowej wywołania na istniejący cache root).
  React Doctor: częściowy wynik, brak findingów w zmienianych plikach;
  pełny skan shadow checkoutu i błąd dead-code ograniczają dowód.
- Obliczenie dla zapisanej kamery: modelowy krok 24-bitowego depth buffer
  23,96 nm → 0,0378 nm; film 1,6 nm: 0 → 42 poziomy. To dowód obliczeń,
  nie pikseli WebGL. Dodano źródła regresji; zgodnie z zakazem nie kompilowano
  ani nie uruchamiano testów jednostkowych.
- Toolchain i obrazy grupy zadania gotowe. Frontend healthy; trwa pierwszy
  przyrostowy build aplikacji backendowej w stałym kontenerze backend.
  Przygotowano fixture odtwarzający istniejący przykład z oczekiwaniem na
  Compute oraz kontrolowane ujęcia z bliska; browser/WebGL: NOT VERIFIED.
- PR uruchamia automatycznie `bootstrap.yml`, w tym kompilację testów C++
  i `cargo test`. Przed otwarciem PR trzeba rozstrzygnąć ten konflikt
  z tymczasowym zakazem kompilacji testów; nie wyłączamy kontroli CI.
- Wolne miejsce WSL przed pracą: około 27 GiB; przestrzeń Docker wymaga
  odrębnego preflightu. Nie ma zgody na czyszczenie cudzych cache.

## Checkpoint 23.10.2026

- Commity: kamera `5e12f782c4d5be861078b092917db26b9a922699`, Primitive
  `fded49ec104eeed75a60dd9be77ae5567df8bf09`, integracja mastera
  `5ac7eae523e5fc117eab9195f62ecda404841601`, regresje/QA
  `b098a82ea0887729228b9c1041b9c64957438678`.
- Aktualny master/origin master: `ae8e570f2aa9655cb9fd8321c716b8d49a87e084`.
  Merge bez konfliktów, zachowano poprawki transferu Primitive→mesh.
- Po merge: lint, tsc bez kompilacji unit tests, parsery MJS i geometria27/27
  PASS. Wykonywalna asercja precyzji przechodzi; kontrola starej polityki
  prawidłowo kończy się exit1. Niezależne review źródeł bez findingów.
- 3 kontrolowane kamery × 3 tryby renderowania, z przywróceniem ustawień
  przez widoczne UI. Browser jeszcze nie uruchomiony; backend buduje
  przyrostowo zmiany bieżącego mastera w tej samej grupie3212.
- Bieżący raport: `docs/diagnostics/viewport-depth-fix-2026-10-23.md`.

## Checkpoint odbioru runtime

- Zarządzana archiwizacja starego stanu i start46515f12...: PASS; istniejąca
  grupa3212 jest healthy. Błąd foreign-host writera zachowano w control volume.
- Fixture wymagała przeniesienia do `examples/qa/viewport_depth_preview.py`
  ze względu na canonical output mapping; nowa aktywacja nadal trwa.
- Weryfikacja źródeł obejmuje36 geometrii, kontrolę negatywną głębokości
  i pełnej triangulacji. Unit tests niekompilowane.
- Browser preflight: timeout60s w odczycie control volume, przed browserem.
  Eksporter konfiguracji czeka na I/O; nie przerywano ani nie powtarzano jego
  żądania. Canvas/PNG/mesh acceptance nadal NOT VERIFIED.
- PR/merge/cleanup pozostają do wykonania po bramce WebGL i rozstrzygnięciu
  automatycznej kompilacji unit tests w CI. Zachować worktree i jego zasoby.
