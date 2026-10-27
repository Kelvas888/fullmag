# Odtwarzanie zapisanych wyników — stan weryfikacji 2026-10-27

Status: implementacja lokalna; integracja i kwalifikacja przeglądarki niezakończone.

## Zachowanie

Home otwiera zarejestrowany folder wyników przez Open results viewer, podwójne kliknięcie lub Enter. Inspector wybiera etap, klatkę/czas, składową m i skalę koloru. Istniejący viewport 3D wyświetla zapisane komórki regularnej siatki. Otwieranie nie tworzy sesji i nie uruchamia solvera. Zmiana klatki zachowuje geometrię i kamerę. Niezapisane formularze/edycja obiektu blokują przejście.

Obsługiwane są deskryptor playback.json i nieskompresowany Zarr v2 float64 LE, chunks [1,3*N], AoS xyz. Deskryptor zawiera geometrię i jawną oś czasu. Automatyczne generowanie deskryptora przez każdy writer oraz FEM nie należą do tej realizacji. Starszy folder bez deskryptora otrzymuje błąd obsługiwanego formatu.

## Dowody

- Zarządzany build aplikacji backendowej w grupie tego worktree przeszedł. Nie kompilowano testów Rust.
- Managed OpenAPI codegen wygenerował trzy zmienione artefakty API; client.ts nie zmienił treści.
- Rzeczywisty folder YIG: workspace item 1, 801 klatek, −4…+4 ns, 1000×20×1 komórek. Manifest revision: 8a711e55f6501ea8f3786afdf8285fbfaecedfff716bae5c6525f943b4be0c31.
- HTTP: klatki 0, 400, 800 mają po 480000 bajtów i są identyczne z odzyskanym oryginałem. Indeks 801 i obcy etap zwracają 404; nieaktualna rewizja 409; lista sesji pozostała pusta. Pełny receipt: /home/kkingstoun/git/fullmag/fullmag/.fullmag/scenarios/saved_results_playback_20261027/http-playback.json.
- Frontend: typecheck i pełny lint przeszły przed ostatnim dodaniem ochrony pending forms w KernelProvider.tsx. Ta ostatnia zmiana została porównana z istniejącym kontraktem PendingFormRegistry; jej ponowna kontrola narzędziowa pozostaje otwarta.
- Architecture hygiene oraz statyczny finder API hygiene przeszły. Standardowy skrypt API hygiene w obrazie nie miał rg; nie jest raportowany jako zaliczony.
- Niezależne review wykryło warunkowy hook w shellu; poprawiono, a reviewer potwierdził poprawkę. Ostatnia ochrona pending forms wymaga jeszcze końcowej kontroli.
- Aktualne testy interpretowanych helperów Python: python3 -B -m unittest scripts/test_docker_dev_codegen.py scripts/test_docker_dev_browser_qa.py — 45 testów, OK.
- git diff --check: OK.
- Hook commita uruchomił React Doctor, ale lint nie zakończył analizy: oxlint JS plugin zwrócił Unexpected discriminant 160 for TSNamespaceDeclarationKind. Commit powstał; wynik React Doctor jest NOT VERIFIED, a komunikat No issues found nie oznacza zaliczonej bramki.

## Otwarte bramki

1. Przeglądarka/WebGL: NOT VERIFIED. Pierwsza próba managed QA nie dotarła do UI z powodu niedostępnego frontend/API. Scenariusz do ponowienia: just docker-dev-browser-qa <worktree> 3298 '' 180 1800 1. Sprawdza klatki 0/400/800, tożsamość geometrii i kamery, zmieniony obraz, widoczny canvas, brak utraty kontekstu i brak mutacji sesji.
2. Grupa fullmag-worktree-saved-results-playback-20261027-cbb94d0116c96f9a ma obecnie obie usługi zatrzymane (ExitCode 255). Obsługiwane resume-volume odmówiło: Retained Linux host directory/engine identity differs. Host device w certyfikacie to 2128, obecnie 2096; inode 4597014 i Docker engine 81a2002d-4c88-48aa-b4da-fed771788cfa nadal zgodne. Brak obsługiwanej migracji tego przypadku. Nie zmieniono certyfikatów, ownerów, lease ani receiptów. Również fresh-state przechodzi tę samą kontrolę certyfikatu, więc nie jest obejściem.
3. Vitest oraz testy Rust/CI: NOT VERIFIED. Automatyczna kontrola uprawnień odrzuciła Vitest z powodu obowiązującego zakazu kompilacji testów w AGENTS.md. Wcześniejsza zgoda użytkownika dotyczyła innych poprawek; osobne pytanie o testy tej funkcji nadal nie ma odpowiedzi.
4. Push/PR/merge/cleanup nie wykonano; push może uruchomić niedozwoloną obecnie kompilację testów w CI. Worktree, wyniki i grupa pozostają zachowane.

## Dane i ograniczenia

Oryginalny zapis YIG zachowuje status nieudanej publikacji ENOSPC; odtwarzanie nie przepisuje go na sukces. Kopia do odtwarzania znajduje się w przestrzeni danych użytkownika grupy, /user-data/imported/yig-waveguide-20261027-8ns. Surowe chunki są niezmiennymi hardlinkami; pozostałe metadane skopiowano.

Rewizja API obejmuje deskryptor i metadane, bez checksum wszystkich chunków. Czytnik wykrywa nieprawidłowy rozmiar, NaN, brak pliku i zmianę pliku w trakcie odczytu. Skończona podmiana chunku przed żądaniem nie zmienia rewizji; pełna integralność odzyskanego YIG ma odrębne dowody SHA256.
