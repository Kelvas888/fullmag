# Audyt ukończenia R0/R1 — 13.10.2026

## Tożsamość i granica dowodu

Checkout: `C:/git/fullmag/worktrees/inspector-actions-template-20261013`.
Branch: `codex/inspector-actions-template-20261013`.
Snapshot kodu: `7fdb4590908277e11f6d79c943ee806e99f52f60`.
PR148 i PR149 potwierdzone jako MERGED przez GitHub CLI. PR150 pozostaje OPEN.
Główny checkout jest współdzielony i dirty; audyt nie uznaje jego lokalnych
plików za dowód wdrożenia. Nie uruchamiano lokalnej kompilacji testów.

**Wniosek: pierwotny cel R0/R1 nie jest ukończony.** Scalenie PR148/149
potwierdza integrację ich zakresu, ale nie realizację wszystkich kryteriów D07.
PR150 poprawia Inspector i nie zastępuje brakujących etapów backendu/recovery.
R2-T, R2-I oraz R2-Q pozostają poza tym celem.

## Macierz wymagań D07

| Etap | Stan źródeł i wykonane kontrole | Dowody | Braki / następny krok |
|---|---|---|---|
| Korekty dokumentacji | Wymagane rozdzielenie R0/R1, przypisania PR, fixture T56, A→B→A/delete pending i ownership resolvera są obecne | D07 PR03/PR07; D06 resolver/resources; D13 TRS→IR; fixtures/authoring_sequences.json; tests.json | Walidator Windows po ochronie bajtów: PASS 76 wpisów; orakle 10/10. To wyłącznie dokumentacja |
| PR01 baseline | Brak dowodu kompletnego odbioru T01/T02/T18/T33/T49/T55 na rzeczywistym runtime | tests.json pozostawia planned_not_run/specification-only; CI ma węższe testy | Utworzyć macierz test→rzeczywisty receipt, zachować NOT VERIFIED bez pomiaru |
| PR02/PR07 draft | Kernel-owned ObjectEditSessionController oraz identity z epoch są zaimplementowane | kernel/authoring/object-edit; GeometryObjectPanel; ObjectGeneralPanel | GeneralPanel omija beginApply/acknowledge i czyści controller po ACK; sprawdzić późniejsze edycje i zmianę ownera. Geometry invaliduje przed rozstrzygnięciem epoch fence. Delete wymaga pending/draft guard |
| PR03/PR07 Move | Implementacja staged draft jest w źródłach i poprzednich scalonych zmianach | Viewport3DObjectMoveInteraction; ObjectEditSessionController | Historyczny immediate R0 nie jest osobnym publicznym trybem. Pełny R1 pointerup→draft→Apply→Undo/Redo oraz A→B→A wymagają aktualnego runtime/browser receipt |
| PR04 parser | Istnieją walidacje pustych wymiarów i primitive builder | geometryObjectPanelModel | Parser nadal używa Number(trim), bez pełnej gramatyki jednostek; preview nieznanego rodzaju wymaga fail-closed. T56 oracle nie dowodzi produkcyjnego parsera |
| PR05 CAS/receipts | PatchObjectGeometry ma base_revision, geometrię i transform; ACK zawiera wynikową scenę | schemas/authoring.rs, typed API, shared commit path | Brak ordinary-transaction client_intent_id/receipt lookup/journal. Potwierdzić finalny CAS w rzeczywistym backendzie; dopiero potem durable receipt z jednym punktem commit/recovery |
| PR06 journal/history | Lokalna historia i jawne history-degraded istnieją | authoringHistoryMutation.ts | Brak authoringIntentJournal i reload→lookup ordinary mutation; brak dedup historii po owner+intent+commit revision. Timeout nie może być retry z nowym ID |
| PR08 assessment | Czysty wspólny resolver rozróżnia not-built/loading/error/future revision | shared/domain/mesh/artifactAssessment.ts | current/runAllowed=true jest możliwe przy samym source_scene_revision bez identity. Resource owner i Run readiness wymagają zgodnych kryteriów |
| PR09 generation publication | Manifest ma opcjonalne generation_id i topology fingerprint | schemas/mesh.rs, meshing/mesh.rs | Brak kompletnego active-generation/activation marker/digest kontraktu oraz crash/retention dowodu. Trace publishera przed zmianą |
| PR10 consumers | Selection zawiera generation i czyści mismatch w Mesh Details | useMeshDetailsModel.ts, viewport3DTargets.ts | Brak identity nie może dopuszczać current/Run. Backend readiness nadal ma odrębne kryterium revision. Sprawdzić wszystkie consumer paths |
| PR11 recovery/scope | Mesh command intent, observation i brak duplicate POST po unknown są obecne | geometryLifecycleCommandContributions.ts | reconcileMeshSubmission nadal ma MAX_RECONCILE_MESH_COMMANDS=8 i slice. Usunąć limit lub wdrożyć autorytatywny lookup/paging; pokazać rzeczywisty shared-domain scope |
| PR12 release | Wprowadzono historię buildów, widoki i wspólne akcje; PR150 w weryfikacji | InspectorFooter; routing; object mesh history; CI PR150 | Brak kompletnego release evidence manifestu, real generation failure/reload oraz wszystkich deklarowanych lane receipts. Release pozostaje NOT VERIFIED |

## Konkretny dowód dwóch luk mesh

`reconcileMeshSubmission` filtruje kolejkę komend, sortuje po seq, a następnie
wykonuje `.slice(0, MAX_RECONCILE_MESH_COMMANDS)` przy stałej 8. Nie jest to
pełne wyszukanie intencji starszej niż osiem kandydatów. Nie należy mylić tego
z usuniętym limitem w innym wyszukiwaniu historii buildów.

`resolveArtifactAssessment` przy `manifestSourceRev === sceneRev` zwraca
`state: current` i `runAllowed: true`. Nie sprawdza w tej gałęzi generation ID,
digestu ani spójnej publikacji wymaganych zasobów. Test wyłącznie rewizji nie
spełnia wymogu identity z T42/T60.

## Kolejność dalszej realizacji

1. Domknąć CI i dowody przeglądarkowe PR150. Nie utożsamiać syntetycznych
   callbacków fixture z rzeczywistym API end-to-end.
2. Oddzielny etap bezpieczeństwa authoringu: wszystkie Apply przez ten sam
   controller beginApply/acknowledge; epoch przed publikacją; delete pending
   guard; wykonywalne regresje ACK/newer edit/A→B→A/deletion.
3. Oddzielny etap parsera R1 oraz recovery komend mesh >8 kandydatów.
4. PR05/PR06: finalny CAS i trwały ordinary-transaction receipt/journal przez
   istniejące storage, typowane API/generatory i capability. Bez naiwnych
   niezależnych zapisów scena→receipt.
5. PR09/PR10: publisher trace, atomowa aktywacja pełnej generacji, digest,
   fail-closed identity i wspólne kryteria consumerów.
6. Pełne API/browser/managed receipts wymaganych Txx i manifest wydania;
   integracja oraz bezpieczny cleanup zgodnie z governance.

## Bieżąca weryfikacja PR150

CI na a6fe6a195: typecheck przeszło; lint oraz oba browser smoke FAIL.
Przyczyny: order/cycle hookowych ACK, render-time ref reads, niezgodna ścieżka
Chromium i stare oczekiwania smoke dla semantycznego routingu. Poprawki są
w commitach 9c99346a7 i 7fdb45909; ponowny wynik jeszcze NOT VERIFIED.
Rust/Python/generated API/API hygiene/FDM qualification w poprzednim przebiegu
były zielone, ale nie dowodzą brakujących receipts/generation kontraktów.
