# Viewport 3D — checkpoint implementacji

## Tożsamość

- Zadanie: `viewport-visual-quality-20261020`.
- Owner: `codex:01a15981-ab31-7ca0-960f-3d1145a8311d`.
- Worktree: `C:\git\fullmag\worktrees\viewport-visual-quality-20261020`.
- Branch: `codex/viewport-visual-quality-20261020`.
- Baza: `88a9b68d29ec173a0b1f1b8750c126da022b0244`.
- Rejestr: `storage/index/viewport-visual-quality-20261020-781a03fef79664b6.json`.
- Cel: pełny plan R0–R8, nie tylko gradient.

## R0 — stan początkowy

20.10.2026: master ma cudze dirty zmiany; implementacja odizolowana. Kopie audytu i planu zachowane w worktree. Docker po uzyskaniu dostępu pokazuje zdrowe backend/frontend `fullmag-master` na porcie 3198. Zarządzane `docker_dev_browser_qa.py --source-root .../fullmag --port 3198` zakończyło się kodem 1: `Browser QA requires a succeeded live volume DEV receipt`. Zdrowy kontener nie jest dowodem admission. Nie zmieniano receiptów ani nie restartowano tej grupy. Próba otwarcia IAB przekroczyła limit narzędzia; nie uzyskano obrazu bazowego runtime. Referencją wizualną pozostają dwa obrazy użytkownika; tożsamość oryginalnej sceny i materiałów pozostaje NOT VERIFIED.

## Zakresy równoległe

- Worker appearance_preferences: R1, prywatne preferencje/store/manifest; bez kamery i danych fizycznych.
- Worker dimension_hud: R2/R3, model ramki i etykiety; bez sceny i store.
- Prowadzący: tło, światło/materiały, integracja UI, kamera, efekty, eksport i weryfikacja.

## Bramy

- Obowiązuje zakaz budowania testów jednostkowych; nie uruchamiano ich.
- Wszystkie buildy i ciężkie kontrole wymagają właściwej grupy Compose oraz danych technicznych w named volumes.
- R0 runtime, R1–R8: w toku / NOT VERIFIED. Brak podstaw do deklaracji ukończenia.

## Próby środowiska

- Toolchain: `61e713183ebf41ee8b9c098c343f9114`, succeeded, image `sha256:fd6aaecf9d9534741ece960786e0adbbdfadca84c29662a74cf90aa0fc898eb7`.
- Grupa: `fullmag-worktree-viewport-visual-quality-20261020-781a03fef79664b6`, port 3218.
- Próba DEV `47764242ed494f8ebbc8c8d3acd69603`: terminalny `failed-confirmed`, kod 1. Backend zakończył się przed kompilacją aplikacji: live source changed while creating its closed manifest. Dwie kontrolne kopie źródeł różniły się podczas równoległych edycji. Zachowano control volume, logi, obrazy i cache; niczego nie usuwano. Nie ponawiać startu do czasu zakończenia aktywnych zapisów.
- Control volume: `fullmag-build-control-fullmag-worktree-viewport-visual-quality-20261020-781a03fef79664b6-e17595d5cb3174c4`.
- R2: dodano renderer tła solid/gradient, tokeny Mocha/Latte i integrację Scene. Panel ustawień w trakcie integracji z R1. Weryfikacja browser/typy pozostaje NOT VERIFIED.
