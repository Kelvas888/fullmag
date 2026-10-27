# Recovery mastera po ponownym uruchomieniu WSL

Cel: zachować bieżącą sesję i wyniki, uruchomić `fullmag-master` na 3198 i sprawdzić w przeglądarce picker Quantity Source Airboxa bez Solve/Compute Fields.

## Uzgodniony podział

Ten branch odpowiada za jawne ponowne przyjęcie obecnego magazynu Linux po zmianie `st_dev`; zwykłe strażniki pozostają ścisłe. Branch `codex/docker-session-recovery-20261027` odpowiada za natywne odzyskanie zatrzymanego runtime i terminalnych runów. Nie edytujemy jego modułów runtime ani offline reconciliation. Grupa master pozostaje wyłącznie w zakresie tego zadania.

## Kontrakt

Legacy certyfikat nie ma UUID filesystemu. Readmisja nie udaje historycznego dowodu UUID: jawnie przyjmuje wskazany istniejący store. Zachowuje ścieżkę, inode, engine, owner token, image i provenance; dopuszcza wyłącznie przypiętą zmianę numeru urządzenia. Bieżący UUID zapisuje jako nową obserwację.

Przed publikacją wymagane są: zarejestrowane źródła/grupa, dokładne piny attempt/config, stopped backend/frontend i ich obrazy, brak innych aktywnych konsumentów magazynu, SHA surowych cert/marker/probe/sentinel/restart oraz natywnego ownera/process receipt. Operacja grupy i blokada OWNER muszą objąć ponowną walidację i oba zapisy. Readmisja nie zmienia natywnego OWNER, runów, leases ani journalu i nie ogłasza drain.

Najpierw zachować niezmienione bajty dowodów w control volume i manifest prepared. Potem opublikować identyczny certyfikat i marker zmienione tylko o host_device, wykonać readback i receipt committed. Przerwanie między zapisami pozostaje fail-closed; osobna przypięta kontynuacja nie może nadpisać archiwum. Zwykły start nadal odmawia rozbieżnych dokumentów. Po readmisji wymagany świeży zarządzany storage probe przed API, ponieważ stary probe przypina surowy certyfikat i namespace.

## Kolejność i dowody

1. Czysta walidacja readmisji i regresje Python: obcy token/inode/engine, dodatkowe różnice, symlink, zmiana bajtów po planie, brak/zmiana sentinel, błędne piny muszą blokować operację.
2. Przypięty kontroler readmisji z trwałym archiwum i wznowieniem; review przed mutacją. Bez kompilowania testów jednostkowych.
3. Zintegrowana natywna ścieżka odzyskania bez sztucznego stop journalu i bez Solve. Jeżeli brakuje obsługiwanej ścieżki, pozostawić blokadę i wskazać dokładną brakującą bramkę.
4. Build i start przez launcher Compose wybranego mastera; dowód źródeł, grupy, receiptu i świeżego probe. Zachować sesję i wyniki.
5. Przeglądarka: realny Airbox Quantity Source zawiera H_demag/H_eff/H_ext i wyklucza m. Zapisać disabled/reason niezależnie od obliczenia pól, screenshot i WebGL canvas/context/buffer.

Aktualny stan: diagnoza potwierdzona, brak mutacji runtime i certyfikatów; implementacja rozpoczęta. Dane buildu i receipty pozostają w Dockerze. Hostowy dokument zawiera wyłącznie plan operacyjny.

## Checkpoint walidatora

Commit `350cce8fd330c52461a87a7caeaca66b8f3bc4a8`: czysty planner i CAS readmisji. 18 regresji Python PASS; planner na rzeczywistych niezmienionych dowodach mastera PASS (wyłącznie odczyt). Żaden certyfikat, OWNER ani store nie został zmieniony. Kontroler publikacji i abrupt-stop nadal w implementacji.

## Checkpoint kontrolerów

- `6c388f394d7ce649c74f8b7a04e9bb008c05fb5d`: operator v2, autentyczny abrupt-stop proof, request v3, przygotowanie bez startu i kwalifikacja aliasów zarejestrowanych grup. Regresje hostowego recovery, wrappera i mapowania zielone; dwa P1 review poprawione i ponownie przejrzane.
- `feb092575b44ac075bd77457a45a1facf0dd8d78`: bridge v3, faktyczny binary capability gate i atomowy immutable proof. 19 testów runtime service i 5 istniejących bridge PASS. P2 publikacji po częściowym zapisie poprawiony. Native v3 dostarcza skoordynowany branch; jego integracja jest osobną wymaganą bramką.
- Kontroler readmisji: 15 regresji Python PASS; review wyścigu RELEASED i klasyfikacji unknown poprawione. Jeszcze bez wykonania na runtime.

Odczyt magazynu wykazał 17 runów: 2 cancelled, 3 failed, 10 succeeded i 2 accepted. Decyzja operatora o dwóch przyjętych runach jest oczekiwana; nie zmieniamy ich statusu i nie rozszerzamy v3 do accepted. Zachowano inwentarz 1240 plików (około 1,55 GB), SHA 44 katalogów runów/artefaktów oraz metadane plików. Wstępny odczyt nie wykazał innego compute attempt niż bieżący catalog.

Kwalifikacja obcych konsumentów pozostaje ścisła: odrębne aliasy są dopuszczane dopiero po potwierdzeniu źródeł. Sześć aliasowych konsumentów spoza Fullmaga wymaga osobnego dowodu odrębności. Nie są zatrzymywane. Walidator kernelowego dowodu tylko do odczytu jest w implementacji.

Master API, świeży probe i UI Airbox: nadal NOT VERIFIED; nie uruchomiono Solve ani Compute Fields i nie zmieniono certyfikatów, natywnego OWNER ani danych magazynu.
