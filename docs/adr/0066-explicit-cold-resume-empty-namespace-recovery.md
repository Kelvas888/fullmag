# 0066. Jawne odzyskanie pustego runtime po zimnym wznowieniu

Status: przyjęty. Rozszerza hostową autoryzację ADR 0063; kontrakt native pozostaje bez zmian.

## Kontekst

Po restarcie VM zachowany owner `Ready` może opisywać zakończoną przestrzeń PID.
Nowa binarka odrzuca inny build przed przyłączeniem native. Taka odmowa nie jest
historycznym drainem ani nieznanym wynikiem starego zatrzymania.

## Decyzja

Jawny helper `prepare_cold_resume_recovery` publikuje osobny journal
`fullmag.docker-cold-resume-recovery-proof.v1`, stan
`stopped-after-restart-build-mismatch`. Wymaga zatrzymania obu dokładnych kontenerów,
prywatnych przestrzeni PID oraz dowodu managed stop, że API zakończyło się przed
native po dokładnym błędzie `native service target/build mismatch; attach refused`.
Nie obsługuje innych błędów po restarcie ani automatycznego recovery przy zwykłym resume.
Po zatrzymaniu dopuszcza też dokładny terminalny `shutdown_unknown` z błędem
`no pinned runtime service owner was available for authenticated drain`.
Pozostałe pola muszą być identyczne z obserwacją sprzed zatrzymania.

Journal przypina surowe hashe ownera, launch, konfiguracji, process receipt,
autentycznego `docker-client-<owner_token>.json` oraz historycznego zweryfikowanego
receiptu wiążącego oba ID, build i snapshot. Przypina też bieżące zakończenie
kontenerów, pusty accepted store i całkowicie zwolniony ledger. Host ponawia te
kontrole pod blokadą lifecycle przed usunięciem dokładnych kontenerów.
SHA surowych bajtów sprzed zatrzymania pochodzi z autentycznej obserwacji w journalu
managed stop. Journal zachowuje sparsowany dokument, nie archiwum tych bajtów.
SHA bieżącego terminalnego dokumentu jest przypięte niezależnie; reserializacja
nie zastępuje oryginalnego hasha.

Po restarcie loop może się zmienić. Readonly `verify` z zachowanej recepty
maintenance dostarcza świeżą tożsamość urządzenia dla ograniczonego probe.
UUID, backing image, stabilna nazwa i opcje wolumenu pozostają przypięte;
zamrożony dokument Compose nie jest przepisywany.

## Konsekwencje i weryfikacja

Istniejący native `recover-container-empty` nadal wykonuje walidację pod blokadami,
archiwizację i zmianę ownera. Python nie zapisuje ownera i nie publikuje drainu.
Źródła, cache, dane użytkownika i żądany dostęp GPU pozostają zachowane.
Dotychczasowe recovery zachowuje swoje wymagania. Odmowa nowej ścieżki zachowuje
stan; wycofanie polega na niewywoływaniu helpera, bez resetu lub migracji danych.

Implementacja: `scripts/docker_volume_container_recovery.py`. Regresje interpretowane:
`test_docker_cold_resume_recovery.py`, `test_docker_volume_container_recovery.py`.
Testy sprawdzają rzeczywiste tworzenie dokumentów, CAS, odmowy i zgodność requestu
z parserem guest. Rzeczywisty native outcome `empty_namespace_recovered` i admission
potwierdził start `3c17a8ffb1ec43f48b555de02af45d72` w `fullmag-master`.
Zwykły restart bez autoryzacji recovery potwierdziła próba
`554e031322854324a62dae066a1cfe9e`. Dowody i granice:
[checkpoint WSL](../plans/active/docker-dev-wsl-20261019.md#wznowienie-po-restarcie-komputera--20102026).
