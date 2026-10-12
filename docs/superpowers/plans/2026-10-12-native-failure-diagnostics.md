# Diagnostyka pozostalych native CTest failures

Stan dowodow: GHA38233264045, source ad12a2a200e4bab7d41053955e8ad9283bc6a3f2, PETSc3.24.6. Wynik9/12PASS, trzyFAIL. Nie jest to kwalifikacja naukowa.

## Pattern fixture69

Pierwszy guard presence borrowed_pmat_copy nie przechodzi; pozniejsze predykaty counts/cleanup nie zostaly ocenione. Nowy failure-only log poprzedza guard: status, error512, diagnostic length/truncation flag i JSON131072. Guard i max_linear_iterations=1 bez zmian. Potrzebny nowy hosted run; brak pomiaru nie uzasadnia PASS ani zmiany budzetu.

## Mixed dense73

Poprzedni failure JSON byl uciety do2048 znakow. Nowy failure-only komunikat zachowuje do131072 znakow diagnostyki, jawne length/truncation i error512. Certification guard bez zmian. Nie przenosic pomiarow45 na73; pelny last_true_probe pozostaje NOT VERIFIED.

## Full modal45

Pelny last_true_probe wykazuje recursive residual0, default reason3, true residual3.303550706404569e-10 wobec threshold2.4125808521746334e-14. Actual ratio13693.015524958842; true-residual gate poprawnie odrzuca konwergencje. LivePC residual7.542700548525e-8, exact Pmat entries matched i Frobenius defect0. FreshLU NONZERO i NONE oba okolo5.150782251730459e-16. To lokalizuje roznice zachowania live/fresh solve, lecz nie dowodzi jej przyczyny ani perturbacji faktorow.

Nie zmieniono production operators, fizyki, tolerancji, preconditionera ani kryteriow. KSPGMRESSetBreakdownTolerance nie jest HapTol. Nowy CPP compile/runtime i kwalifikacja naukowa pozostaja NOT VERIFIED. Dalsza naprawa musi wynikac z nowych logow i niezaleznej kontroli live factorization lifecycle.
