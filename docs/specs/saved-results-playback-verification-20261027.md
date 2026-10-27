# Odtwarzanie zapisanych wyników — weryfikacja 2026-10-27

Status: odtwarzanie rzeczywistego YIG potwierdzone w UI; końcowe sprawdzenie po połączeniu z masterem i integracja CI w toku.

## Zachowanie i zakres

W Home dodaj folder dostępny backendowi, wybierz wynik i Open results viewer
(albo podwójne kliknięcie / Enter). Inspector wybiera etap, klatkę/czas,
składową m i skalę koloru. Istniejący viewport 3D pokazuje zapisane komórki
regularnej siatki. Otwieranie nie tworzy sesji i nie uruchamia solvera.
Niezapisane formularze/edycja obiektu blokują przejście.

Obsługiwane są playback.json i nieskompresowany Zarr v2 float64 LE,
chunks [1,3*N], AoS xyz. Deskryptor zawiera geometrię i jawną oś czasu.
Automatyczne generowanie deskryptora przez każdy writer oraz FEM pozostają
poza tym zakresem. Starszy folder bez deskryptora otrzymuje błąd formatu.

## Potwierdzone sprawdzenia

- Zarządzany build aplikacji backendowej: OK. Runtime zbudowano ze snapshotu
  7443406cd401ef98603b9a1d3bfb5737b41528bbdd409b9017ad7ba6a6a70816
  na bazie ad16c36079a48d4d0fbaca7a2a1bc9f3eff6d43c z opisanymi zmianami.
- Reader Rust: 56/56 testów, w backendzie własnej grupy.
- Test HTTP saved_playback_routes_return_metadata_and_revision_checked_binary_frames:
  1/1, w backendzie własnej grupy.
- Python: 64/64 regresje poświadczenia WSL, czytników dowodów, codegen i browser QA.
- Typecheck i pełny lint: OK przed połączeniem najnowszego mastera; końcowe powtórzenie po integracji w toku.
- Pełny frontend: pierwszy przebieg 8867 OK, 3 błędy, 1 skip. Poprawiono
  użycie surowego invalidate, SSR-asercję suwaka oraz przypięcie testu Next
  do źródeł. Testy cross-app wymagają FULLMAG_TEST_SOURCE_ROOT=/opt/fullmag/source.
  Końcowy pełny przebieg po synchronizacji shadow pozostaje otwarty.
- Git diff --check i składnia YAML workflow: OK.

## Rzeczywisty podgląd YIG

Zarządzana kwalifikacja browser-qa/attempts/4631bda06895459d81cf97c52a2b2f74
zakończyła się succeeded. Źródło scenariusza:
88313211c68f37f482c4e89b348051f2296fb257daf132815593329ecac364bb.
Playwright 1.62.1, SwiftShader WebGL (dowód UI, bez deklaracji sprzętowego GPU).

Workspace item 1: 801 klatek, −4…+4 ns, 1000×20×1 komórek. Manifest:
8a711e55f6501ea8f3786afdf8285fbfaecedfff716bae5c6525f943b4be0c31.
Klatki 0/400/800 miały po 480000 bajtów, zgodne z odzyskanym oryginałem:

- 0: f1567257f629136d0dd8f8b48bde6bb39130965a54233aa22a3718a5f08af595
- 400: 27085242e0e9c9a027d1cc1e0c0c9eca4e8dede4ade844acd29e60590f0a3571
- 800: 92c875c19de85daa2439d27a9ce99ccc2208f1bd8ea61734570c6162446002d4

Potwierdzono: zmieniony obraz canvasu, niezmieniona geometria i kamera,
stabilny Inspector, widoczny canvas, context_lost=false, drawing buffer
649×683, brak błędów hooków, brak mutacji sesji i brak nowej sesji.
Zrzut oraz JSON dowodowy wyeksportowano jako YIG-playback-20261027.png/json
do dokumentów użytkownika. Obraz sprawdzono wizualnie: m_z przedstawia
propagujące paczki na końcowej klatce +4 ns.

Negatywne HTTP: klatka 801 i obcy etap → 404, nieaktualna rewizja → 409.

## Naprawa wznowienia po restarcie WSL

Zaimplementowano reattest-host-device-volume: jawne piny starego certyfikatu,
aktualnego urządzenia, próby development, konfiguracji i źródeł; kontrola
sentinela, inode, silnika, obrazu i zatrzymanych konsumentów. Stare/nowe bajty
są journalowane, częściowy zapis można ponowić wyłącznie dla tych wersji.
Inode bind-mountowanego certyfikatu i token właściciela pozostają zachowane.

Dla tej grupy urządzenie zmieniło się 2128→2096. Operacja
bf65c1df934941e8afddfe45dcf21f6c zakończyła się succeeded. Kontrolowany helper
zamknął osieroconą iterację dc4e49ccc55a40ce96e94a580f5969f1 pod flock
i dokładnym CAS, bez zmiany oryginalnego receipt.json; potwierdzono brak
helpera i brak zachowanych runów. Zwykłe resume
82b6809c6aa1486fa10a52c3e0dfb765 przywróciło API i frontend.

## Pozostałe bramki

Użytkownik jawnie zezwolił na testy tej funkcji i wymagane CI.
Wcześniejsza odmowa kompilacji testów nie blokuje już tego zadania.

Po integracji z aktualnym masterem: końcowy restart/synchronizacja, pełne
testy frontendu, statyczne kontrole oraz ponowny browser QA; następnie PR,
wymagane CI, merge i kwalifikowany cleanup. React Doctor w starym hooku miał
błąd parsera oxlint (Unexpected discriminant 160); nie jest zaliczoną bramką.

Oryginalny zapis YIG zachowuje status nieudanej publikacji ENOSPC.
Odtwarzanie nie przepisuje go na sukces. Rewizja API obejmuje deskryptor
i metadane, bez checksum wszystkich chunków; integralność odzyskanego
oryginału ma odrębny dowód SHA256.
