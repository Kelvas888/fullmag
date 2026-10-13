# Checkpoint

- Baza: e1865ce66c0291be2bfc03a77253b77972b62d4f.
- Poprzedni PR154 scalony, g≈Ç√≥wny master fast-forward, stary czysty worktree i branch usuniƒôte; dowody zachowane w storage.
- Nowy etap: simulation-mode-consistency-20261013, w≈Ça≈õciciel codex-thread-01a12cc7.
- Potwierdzono przekazanie backend=fem; wykryto sprzeczny status/domain API przed mesh i downstream utratƒô active_lane.
- Backend worker: status.rs/domain.rs i regresje tests.rs.
- Frontend worker: resolver i konsumenty z audit.md, poza status-bar i runOutcome.
- Root: status-bar (jawna metoda i engine not started), provenance runOutcome, audyt/review/integracja.
- Zakaz lokalnej kompilacji/test√≥w pozostaje w mocy; CI uruchomi regresje.
- Pozosta≈Ço: review ca≈Ço≈õci, przeglƒÖd analysis/field-storage, source hygiene, commit etap√≥w, PR/CI/browser, integracja i cleanup.
- Ca≈Çy wcze≈õniejszy goal R0/R1 D07 pozostaje aktywny: receipts/generation/runtime qualification nie sƒÖ zamkniƒôte przez ten etap.


## Etap backendu

Commit: `86ab736c1e26788d0ea0bab1145f727a76092048`.
Zakres: domain.rs, sessions/create.rs, sessions/status.rs, router_v2/tests.rs.
≈πr√≥d≈Çowy review i diff-check PASS; regresje zapisane, nieuruchomione lokalnie. ObejmujƒÖ rzeczywiste POST create‚ÜíGET status/domain dla empty FEM/FDM, built/empty FEM payload i explicit FDM z retained FEM mesh.
FEM bez siatki: `fem:unmaterialized`, domain generation revision/topology 0, counts null, brak structured grid, finite zero bounds. Scratch nie przypisuje fikcyjnej runtime family ani engine id.

Known limits zachowane z wcze≈õniejszego kodu: classifier DomainMeta daje pierwsze≈Ñstwo explicit execution plan/artifact layout; to klasyfikacja reprezentacji danych, nie resolved runtime lane. Built FEM mesh z generation_id=None nadal ma historyczny FDM fingerprint/revision fallback. Ten problem pe≈Çnej publication/generation qualification nale≈ºy do aktywnego D07 i nie zosta≈Ç ukryty przez nowy sentinel.

## Frontend / review

Root: kontrolka metody, osobny stan engine-before-run i run outcome provenance z regresjami. Independent review zg≈Çosi≈Ç P2 utraty ostatniej znanej metody przez chwilowe active_lane=null; poprawione i ponownie zamkniƒôte ≈∫r√≥d≈Çowo. Testy wykonania pozostajƒÖ do CI.
Source architecture hygiene i API hygiene PASS dla pierwszego sp√≥jnego zakresu; ko≈Ñcowe sprawdzenie po zmianach konsument√≥w jeszcze wymagane. Node syntax-check smoke-inspector PASS. PrzeglƒÖd adapter√≥w i paneli trwa.

## Etap komend i analizy

Commit: `c4a4b0344470cfef8df407eebd4d406941d4a77b`.
Review ürÛd≥owy niezaleønego agenta i scoped diff-check PASS. Regresje czekajπ na CI. Guard FDM commands opiera siÍ na active execution, nie retained artifacts. Topological charge zachowuje FDM field topology mimo retained FEM mesh; istniejπca nota 0940 pozostaje kontraktem.

Root rozszerzy≥ zakres o StudyInspectorPanelModel provenance i testy dla CPU preview vs GPU run. Nie zmienia requested device ani legacy/per-step stage legality.

## KoÒcowy review UI

Poprawiono: brak capabilities w adapterach, jawne unresolved Airbox, equality zachowujπce lane i presence, stale explicit_topology flags, zaleønoúci callbacku wizualizacji obiektu, stale lane-specific errors viewportu. Independent review P2 wspÛlnego targetQuantity field poprawiony przez gating aktualnego demandu FDM/FEM; P2 metadata run poprawiony przez unavailable/not loaded zamiast domniemania not started w Inspectorze. Status bar nadal rozrÛønia running + brak metadata od potwierdzonego stanu przed run.

Architecture hygiene, API hygiene, diff-check i smoke script syntax-check PASS; lokalne testy/typecheck/build/browser niewykonane. KoÒcowy CI bÍdzie ürÛd≥em dowodu wykonania.

## CI pierwszego head

Head a20c9cf08d1f4d3b3fdba4f6aed72ee3669e64a7, PR #155. Control Room typecheck wykry≥ brak deklaracji readback metody w Viewport3DFrameProps oraz nullable status po gatingu lane. Naprawa zachowuje neutralny status idle i przekazuje metodÍ jako jawny prop frame, nie rozszerza kontraktu sceny Three.js. Pozosta≥e CI trwa; wynik koÒcowy jeszcze niepotwierdzony. React Doctor CI PASS; local commit hook zg≥osi≥ 13 warnings na niezmienionych liniach, nie traktowaÊ hook score jako wyniku CI dla diff.
