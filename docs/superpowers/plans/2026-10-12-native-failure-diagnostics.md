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
