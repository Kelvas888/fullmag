# Docker DEV i wielomateriałowy mixed-P1 FEM — plan wykonania

Data: 2026-10-19. Branch: `codex/docker-volume-only-implementation-20261018`.
Baza: `fc50a43efa6a19ed10e03e1f9a0060809014605f`. PR: #197.

## Cel i zakres

Dokończyć architekturę `docs/guides/docker-development-architecture.md`:
dwa stałe serwisy Compose wybranego checkoutu, build i runtime w tym samym
backendzie, readonly źródła, frontend HMR, przyrostowy cache i wszystkie dane
budowania w Docker volumes/BuildKit. Sesje, wyniki, projekty i ustawienia
pozostają w skonfigurowanym fizycznym storage Windows.

Użytkownik 19.10.2026 rozszerzył zakres o wielomateriałowy mixed-P1 FEM dla
`examples/permalloy_layer_cofeb_rings_relax_300nm.py`. Obowiązują rzeczywiste
stałe i instrukcje skryptu; jego stary docstring nie opisuje obecnej geometrii.
Nie zmieniamy GPU na CPU, pryzmatów na free-tet ani dwóch materiałów na jeden.
Odrębny smoke nie dowodzi wykonania tego modelu.

## Kolejne wyniki i odpowiedzialność

1. **Bootstrap Docker — root.** Naprawa pełnych wejść interpolacji Compose
   przy odczycie/zapisie receiptów oraz rozwiązywania logicznego klucza mountu
   do dokładnej external volume. Commit `48c52e530ab6e73505f4c78f63208a328aabd121`.
   Regresja najpierw odtworzyła brak dwóch zmiennych; 36 testów bootstrapu
   przechodzi. Rzeczywisty zarządzany bootstrap przeszedł do BuildKit.
2. **Kontrakt naukowy — agent dokumentacji.** Przed kodem zaktualizować
   kanoniczną notę 0106 i source-map, ADR 0021, masterplan oraz zakres capability
   matrix. Opisać mapowanie materiałów i komórek, fizykę rozłącznych ciał,
   współczynniki operatorów i granice interfejsów. Stan planned/implemented
   nie zastępuje kwalifikacji runtime.
3. **Python, mesher i planner — agent planner.** Rozszerzyć realną generację
   conforming shared-domain prism/pyramid/tet, certyfikat dokładnej warstwy,
   mapowanie body/region/material oraz lowering Ms/A/alpha i anisotropii.
   Nie zdejmować walidacji bez odpowiadającego jej wykonania. Zachować
   authored/requested/resolved identity i fail-closed dla nieobsłużonych zakresów.
4. **Natywne FEM — agent native.** Sprawdzić i rozszerzyć operatorowe użycie
   współczynników w exchange, demag source/recovery/energy, Zeemanie,
   anisotropii i metryce PG-BB dla CPU/GPU. Uzgodnić ABI i certyfikat z plannerem.
   Zachować GPU residency i brak niejawnego fallbacku.
5. **Weryfikacja źródeł — właściciele części.** Dodać regresje dodatnie i ujemne
   dla wielu materiałów, markerów, dokładnych warstw, geometrii, współczynników
   i granic nieobsługiwanych przypadków. Lekkie testy Python uruchamiać zgodnie
   z zakresem. Lokalne kompilowanie testów jednostkowych pozostaje zabronione;
   pełny build aplikacji wykonuje tylko stały backend. CI ma wcześniej
   autoryzowany wyjątek dla wymaganych kontroli tego zadania.
6. **Build i wykonanie — root.** Z natywnego Pythona Windows uruchomić
   `bootstrap_docker_toolchain.py --direct-development`, następnie
   `docker_dev.py up --source-root <ten checkout> --port 32871`.
   Obowiązuje grupa `fullmag-worktree-docker-volume-only-implementatio-670653a9f4702651`.
   Chronić działający backend innego worktree. Sprawdzić rzeczywiste mounty,
   gotowość API, Home oraz konkretny requested/resolved/executed GPU i artefakty.
   Exact rings, skrypt auto-Solve i wait-for-solve są osobnymi dowodami.
7. **Cykl DEV i dysk — root.** Potwierdzić restart bez zmian z tym samym ID
   i cache-hit, przyrostową zmianę backendu, HMR po zapisie Windows,
   trwałość danych użytkownika i brak nowych duplikatów technicznych.
   Mierzyć fizyczne miejsce Windows oraz Docker VM. Nie usuwać cudzych danych,
   wolumenów, aktywnego cache ani globalnie prune. Retencję pakietów
   sprawdzić osobno; brak ogólnego GC/quota raportować jawnie.
8. **Integracja — root i niezależny reviewer.** Zapisane logiczne części
   zweryfikować, commit/push, aktualny PR opis, wymagane CI i review,
   merge, fast-forward głównego mastera z zachowaniem cudzych zmian.
   Cleanup tylko po wykazaniu braku użycia i cudzych/unikalnych zmian;
   aktywne mounty albo istniejące zmiany `.claude/skills` blokują automatyczne
   usunięcie worktree i muszą trafić do rejestru.

## Warunek ukończenia

Sukces wymaga dowodów dla wszystkich powyższych punktów. Zielony source test,
build, otwarty port, wykryte GPU ani sam status Running nie zastępują
odpowiednio UI, poprawnego solvera, konkretnego urządzenia i zakończonego runu.
Nie uznawać samego istnienia named volumes za dowód ograniczonego wzrostu dysku.
