# Diagnostyka pozostalych native CTest failures

Stan dowodow: GHA38233264045, source ad12a2a200e4bab7d41053955e8ad9283bc6a3f2, PETSc3.24.6. Wynik9/12PASS, trzyFAIL. Nie jest to kwalifikacja naukowa.

## Pattern fixture69

Pierwszy guard presence borrowed_pmat_copy nie przechodzi; pozniejsze predykaty counts/cleanup nie zostaly ocenione. Nowy failure-only log poprzedza guard: status, error512, diagnostic length/truncation flag i JSON131072. Guard i max_linear_iterations=1 bez zmian. Potrzebny nowy hosted run; brak pomiaru nie uzasadnia PASS ani zmiany budzetu.

## Mixed dense73

Poprzedni failure JSON byl uciety do2048 znakow. Nowy failure-only komunikat zachowuje do131072 znakow diagnostyki, jawne length/truncation i error512. Certification guard bez zmian. Nie przenosic pomiarow45 na73; pelny last_true_probe pozostaje NOT VERIFIED.

## Full modal45

Pelny last_true_probe wykazuje recursive residual0, default reason3, true residual3.303550706404569e-10 wobec threshold2.4125808521746334e-14. Actual ratio13693.015524958842; true-residual gate poprawnie odrzuca konwergencje. LivePC residual7.542700548525e-8, exact Pmat entries matched i Frobenius defect0. FreshLU NONZERO i NONE oba okolo5.150782251730459e-16. To lokalizuje roznice zachowania live/fresh solve, lecz nie dowodzi jej przyczyny ani perturbacji faktorow.

Nie zmieniono production operators, fizyki, tolerancji, preconditionera ani kryteriow. KSPGMRESSetBreakdownTolerance nie jest HapTol. Nowy CPP compile/runtime i kwalifikacja naukowa pozostaja NOT VERIFIED. Dalsza naprawa musi wynikac z nowych logow i niezaleznej kontroli live factorization lifecycle.


## Nowy dowod pattern i mixed - GHA38237149103

Source01f2112b nadal9/12PASS. Pattern completeJSON8581:statusOK accepted1,4truecriterion pomiary0violations,maxratio0.0019653927028332276. Serializer observer publikuje tylko dla floquet_slepc_solve_failed, mimo cached capture dla innych wynikow. Brak borrowed_pmat_copy przy sukcesie nie dowodzi braku hooka.

Fixture pattern teraz nie stosuje specjalnego FIELD-only override z fault-quarantine cases; zachowuje bazowy historycznyCSR carrier oraz maxlinear1/rtol/target/privatehook i wszystkie mismatch/cleanupguards. To warunek istniejącego hard-nearest testu, a nie pełny model fizyczny. Nowy runtime NOT VERIFIED. Nie zmieniono production solvera ani tolerancji.

Mixed73 kompletneJSON:subwindow1 shift0.6537857698010644Hz, true residual1.8635310157807875e-10/threshold2.4343592418709787e-14, ratio7655.1191941109355, recursive0/defaultreason3/gate0. LivePC relative residual7.838566796905665e-8, fresh NONZERO/NONE1.201422675269101e-16, exactPmat defect0 i cleanup/phi invariants true. Jest to rzeczywisty fail true-residual gate. Sama zgodność wpisów Pmat nie dowodzi zgodności faktorów; numerical rootcause nadal otwarty.


## Korekta wniosków po GHA 38241463969

Próba pozostawienia pattern na historycznym CSR carrier była błędna: bieżący R4 odrzucił descriptor przed EPS. Przywrócono prawidłowy FIELD-only carrier, a przyczynę braku danych usunięto w serializerze. Po udanym opt-in solve neutralne `candidate_operator_observation` publikuje wyłącznie cached pomiar. Failure-only eksport pozostaje bez zmian. Nie wprowadzono dodatkowych PETSc queries ani zmiany fizyki, tolerancji czy acceptance.

Cztery rzeczywiste wywołania C ABI w prywatnym teście obejmują opt-out success bez diagnostyki, opt-in success z pomiarem, successful pattern probe z rozróżnieniem prywatnej struktury 3/4 względem zgodnej rzeczywistej Pmat i successful solve z niedostępnym fresh-LU probe. Kontrole porównują lambda oraz residual przy istniejącej tolerancji, zachowanie phi RHS/solution, cleanup, niezerowy kod błędu unavailable setup i null residuals. Nowy hosted native compile/runtime: pending.

Pełne modal45 i mixed73 pozostają prawdziwymi porażkami true-residual gate. Ta korekta nie rozwiązuje ich przyczyny i nie zamyka kwalifikacji numerycznej lub naukowej.


## Regresja budżetów K0 GPU — GHA 38248502096

Native compilation przeszła; 2/4 CTest fail w nowej fixture admission. Produkcyjny helper sentinel policy działa, lecz test dla strict GPU używał legacy return-by-value C ABI, który prawidłowo zatrzymuje GPU na wymaganiu caller-sized result v20 attestation. Fixture teraz korzysta z istniejącego v20 envelope dla wszystkich trzech targetów i zachowuje dokładny powód odrzucenia negative budgets. Nie osłabiono wymogu attestation, availability ani GPU fallback; dodano failure-only bounded log. Kolejne hosted CTest pending; urządzeniowy GPU solve nadal NOT VERIFIED.


## Potwierdzenie eksportu sukcesu — GHA 38246943509

Artefakty dowodzą kompilacji i 10/12 CTest PASS na6265812be7b146f0f70102f1db79414765329490. Pattern sukcesu, opt-out, unavailable fresh-LU i guardy prywatnego mismatch przeszły. Pozostają wyłącznie fem_modal_eigen_contract oraz fem_modal_eigen_mixed_dense_contract (true-residual failures). Poprzedni wynik9/12 zastąpiono nowym dowodem; nie nazwać całego native suite zielonym. Receipt SHA256e6ca02ed415d1da23c71a51777e71d412e348dca8e21ed5c5da3098079b88a22; logSHA256b9af77228f89f7d33af8ab56b15003334a96885f9b4cc0c58eed399307d0549a.

GHA38288433960 na554d3a49bfbd03b143d373644d92675a18a2661e:4/4dependency-free C ABI CTest PASS, w tym policy admission z v20 dlaGPU. Receipt SHA2565f575404974019060c3dac4da5faa611d4a60d62fddc17a1ea6d279723c63236. To nie jest GPU urządzeniowy solve.


## Następny falsyfikowalny pomiar faktorów — 12.10.2026

Dwa aktualne JSON-y na6265812 potwierdzają Pmat4x4/16entries: exact structure/value match i Frobenius defect0. LivePC relative residual: full45=7.5427005485e-8, mixed73=7.8385667969e-8; freshLU odpowiednio3.2583845792e-16 i2.3115593840e-16. Zadawany `MAT_SHIFT_NONZERO` około1.4901161194e-8 nie dowodzi rzeczywiście zastosowanego przesunięcia.

Hipoteza, nie potwierdzona przyczyna: liveLU uruchamia conditional shift po małym pivocie symbolic/numeric ordering, freshLU na późniejszym duplikacie nie. W pinned PETSc3.24.6 `MatPivotCheck_nz` (`include/petsc/private/matimpl.h`) uruchamia actual shift zależnie od pivotu i row sum. Numeric LU (`src/mat/impls/aij/seq/aijfact.c`, inode.c) ma istniejące PetscInfo z liczbą shift_nz tries i actual shift_amount. Getter konfiguracji nie mierzy tej decyzji.

Następny bounded hosted experiment: potwierdzić logging Mat, znaczniki fazy liveEPSSetUp/freshKSPSetUp, odczyt metadata/ordering i actual shift log. Nie resetować livePC, nie zmieniać faktorów, tolerance ani acceptance. MatDuplicate kopiuje również inode/diagonal/compressed-row metadata; nie zakładać, że fresh wyłącza inode. Brak logu nie oznacza zerowego shift, dopóki logging nie zostanie zweryfikowany. Różnica actual shift/ordering wspiera hipotezę; równość ją falsyfikuje. Wówczas kolejny pomiar to prywatne cztery jednostkowe RHS i rekonstrukcja efektywnego inverse action. Pomiary niezaimplementowane; rootcause/science nadal NOT VERIFIED.


### Wdrożony pierwszy krok pomiaru — runtime pending

Hosted floquet-modal-slepc profil żąda `PETSC_OPTIONS=-info :mat:self` i prywatnych znaczników live_setup/fresh_setup. Istniejące EPSSetUp/KSPSetUp pozostają wywołane dokładnie raz z tymi samymi argumentami/guardami. Znaczniki używają wyłącznie fprintf/fflush, nie PETSc query; end oznacza powrót call, nie poprawność solve. Konfigurację loggingu zapisuje receipt jako requested, nie observed. Następny actual CTest/log potwierdzi dostępność Mat logging oraz shift_nz tries/amount. Brak logu nie może być uznany za zero shift.

Składnię i filtr potwierdzono w pinned [PETSc3.24.6 verboseinfo.c](https://raw.githubusercontent.com/petsc/petsc/v3.24.6/src/sys/info/verboseinfo.c). Mechanizm nie zmienia fizyki ani tolerancji i nie stanowi kwalifikacji. Odczyt dodatkowych matrix metadata/PCView pozostaje dalszym krokiem zależnym od wyniku tego logu.
