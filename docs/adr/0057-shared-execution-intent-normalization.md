# ADR 0057 — wspólna normalizacja intencji wykonania

Status: accepted w zakresie naprawy P1 4247310808; runtime i nowe testy pending. Data: 2026-10-12.

## Kontekst

Authoring adaptive porównywał legacy requested_backend/device sceny, choć profil i warstwy zastępują te pola przed planowaniem. Istniejący materializer jest czysty i używa tylko typów fullmag-ir oraz std, lecz pełna application zależy od authoring. Bezpośredni import tworzyłby cykl; drugi resolver w authoring rozjechałby precedence, Auto i provenance.

## Decyzja

Czystą normalizację execution_profile.v1/execution_request.v1 współdzielimy w `fullmag-ir::execution_profile_materialization`. Przeniesiony algorytm pozostaje taki sam: defaults, ordered patches, origin, hash, zakaz weaken i submit precedence. Application zachowuje dotychczasowe publiczne funkcje jako re-export tego samego symbolu. Referenced lookup nadal jest przekazanym callbackiem; core nie wykonuje I/O, nie odczytuje hosta i nie planuje zasobów.

Authoring z zadeklarowanym profilem używa tego core do admission adaptive; bez profilu zachowuje legacy explicit FEM/CPU gate. Scene intent nie jest mutowany. Invalid profiles/layers i GPU/Auto/FDM lanes nadal fail closed. Capability resolution, ProblemIR binding, submit, host allocation, runtime legality i executed receipts pozostają w application/planner/runner.

## Skutki i granice

Scoped supersession dotyczy wcześniejszego ownership pure materialization opisanego w spec compute-resource-execution-v1 E1 oraz komentarzu IR execution_profile. Nie zmienia ADR0052 polityki, wire, Python DSL, OpenAPI, native ABI, capability vocabulary ani wsparcia GPU. Nie powstaje fallback CPU i nie znikają requested Auto ani origins. Publiczne application paths nie są usuwane.

## Obowiązki i dowody

Przenieść core bez zmian semantyki, zachować app reference/property/materialization tests, dodać authoring cases dla profilu FEM/CPU przy stale legacy fields, odrzucenia GPU/FDM/Auto, explicit narrowing layer oraz invalid weakening. GHA: pełne IR/application i nowe authoring regressions. Source equivalence i parser nie dowodzą wykonania. Runtime/HPC/GPU nadal osobne NOT VERIFIED.

## Rollback

Przywrócić pure core do application i re-exporty w ramach spójnego rollbacku. Nie zostawiać dwóch implementacji ani pomijać admission profilu; feature nie może zostać uznany za kwalifikowany bez przejścia bramek.
