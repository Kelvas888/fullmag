# P8-53BM — kamera po development restart

## Status

Potwierdzony błąd P1: restart zachowuje scenę, lecz traci projekcję kamery.
Poprawka ownera jest w realizacji; runtime po poprawce pozostaje **NOT VERIFIED**.
Nie zamyka to P8-53 ani całego planu.

## Dowód przed poprawką

Prywatna próba przeglądarkowa na 3258, z rzeczywistymi procesami Windows:
receipt `4db8d035170f4d5799d7d89443e7eed1` w profilu
`development-backend-api-checks`, worktree-id `fullmag-0950f4dca4ffe38f`.
Katalog receipt zawiera `camera-before-restart.json`,
`camera-after-restart.json` i `camera-after-mounted-kernel.json`.

Normalny przycisk View → Ortho ustawił projekcję `orthographic`.
Po normalnym Restart backend oraz zamontowaniu nowego kernela API zwróciło
`perspective`. Pozostałe pola zachowały wartości: position
`[2e-6, 1.4e-6, 2e-6]`, target `[0,0,0]`, up `[0,0,1]`,
fov_degrees `45`, orthographic_scale `null`.

Stary API instance: `602ba5cb-44f9-4cc1-8a37-8580031cbdb3`;
nowy: `38fab2c2-7269-44b6-a368-29157c037a57`. Nowy kernel osiągnął
generation 1, paused=false, publication_error=null. Model próby był
odtworzonym przez API wejściem testowym; nie jest to dowód ręcznego
autoringu całej sceny w UI. Projekcję zmieniono rzeczywistym przyciskiem UI.

Próbę świadomie zakończono po wykryciu błędu, przed pełnym Grid/Compute/Finish.
Receipt jest terminalny `failed`, exit 1; wszystkie 24 zapisane procesy
mają waited=true. Nie kwalifikować tej próby jako PASS restartu.
Sesji użytkownika na 3197 nie zatrzymano.

![Workspace po restarcie przed poprawką](53bm-camera-reset-before-fix.jpg)

## Wzmocnienie weryfikatora

`scripts/windows/verify_workspace_browser.py` zapisuje kamerę przed restartem
i porównuje po nim wszystkie sześć pól: projection, position, target, up,
fov_degrees oraz orthographic_scale. Brak pola, obce pole, niepoprawna
projekcja, niefinitywna liczba lub niepoprawny parametr blokują pozytywny
wynik; weryfikator nie zastępuje danych wartościami domyślnymi.

Nowy interpretowany regression check sprawdza każdy utracony parametr,
niepoprawne dane, izolację kopii i zachowanie null scale.
`just verify-windows-development-handoff`: **165 testów, 0 skipów, exit 0**.
Receipt `57d5fc8a660e4eaf8c2c1b71ecd30201`; tożsamość źródeł przed/po:
`cc5c085cdc0d1ebbb370170d7b2067a6034891c661705133700a3d41b5314e31`.
Nie kompilowano testów jednostkowych. Te testy dowodzą kontroli dowodu,
a nie naprawienia produkcyjnego odtworzenia kamery.

Ponowna seria po dopasowaniu FOV do backendowego zakresu `[1,179]`:
165 testów, 0 skipów, exit 0, receipt `ba44d7f6f0b74f0daf205dfefa272c3e`.
Źródła przed/po: `03458c10c461ad9f80e2b4e785a0f4c28620b140cac0d595644b2a29b21e70f2`.
Regresja odrzuca także 0,5 oraz 179,5 stopnia.

## Odbiór poprawki

Owner musi przenosić ścisły snapshot kamery, wykrywać jego zmianę podczas
handoffu i odtworzyć go przez istniejący typowany visualization API nowego
procesu. ACK oraz odczyt z nowego pinned API muszą zgadzać się przed
publikacją kernela. Wymagane są także jawny odczyt starszego payloadu,
obsługa pustego workspace i odmowa publikacji przy błędzie.

Pozostają: konkretne regresje ownera, kontrole produkcyjnego frontendu,
nowy zamrożony pakiet oraz rzeczywista próba restartu z porównaniem kamery.

## Checkpoint implementacji ownera

Owner zapisuje teraz workspace v2 z kamerą; starszy v1 ma jawny reader.
Przygotowanie replacement odrzuca brak session_id i niepoprawny session_epoch.
Kamera sesji jest odtwarzana przez typowane PATCH/GET visualization; brak
zgodnego ACK lub odczytu blokuje publikację. Sessionless workspace ma
camera=null i nie wywołuje niedostępnego endpointu sesji.

Scoped lint przeszedł: receipt `3062fa8c0afe40fb8d889dd7da5f440e`.
Pierwsza kontrola produkcyjnych typów (`2e488dd351ef44f894f6ef1da915d1b4`)
wykryła niewężony opcjonalny session_id ownera, poprawiony następnie jawną
walidacją. Wykryła także niezależny błąd nullable snapshot w równolegle
zmienianym computeNodeInventory.ts; nie należy do tej poprawki.

Pierwsza próba konkretnych ownerów w Chrome na 3251 zakończyła się failed:
receipt `6547c409dfec427eb67bedb64aa8a01d`. Istniejący mock NewProblem
nie udostępniał resources.getRevision wymaganego przez useResource;
wykonanie przerwano przed nowymi regresjami kamery. Naprawa adaptera próby
jest w toku. To nie jest PASS ani dowód poprawności produkcyjnego restartu.

## Wyniki review

- P1 owner: świeży rejestr kamery ma lastRemoteRevision=null i kamerę
  domyślną. Dla aktywnej sesji capture musi odmówić przed przyjęciem takiego
  stanu. Wymagane są potwierdzona remoteCamera oraz lastRemoteRevision,
  oprócz braku dirty/sync/error. Dla sessionless workspace pozostaje jawne
  camera=null. Regresja tej odmowy jest w realizacji.
- P1 backend: camera-only PATCH nie zwiększa selection.revision będącej
  rewizją visualization resource. Świeży scope i GET ograniczają ryzyko
  podczas tego restartu, ale nie dowodzą invalidacji innych klientów.
  Osobna poprawka rewizji pozostaje otwarta.
- P2 backend: orthographic_scale=null w PATCH jest interpretowane jak brak
  pola przez Option<f64>. Świeży backend ma domyślnie null, ale ACK/readback
  musi odmówić publikacji, jeśli docelowy stan nie zgadza się z capture.
  Pełne czyszczenie skali pozostaje osobnym otwartym kontraktem.

Review nie znalazło automatycznego PATCH nowego rejestru przy montażu:
hydracja wykonuje zapis/odczyt przed publikacją, a świeży namespace zasobów
po montażu pobiera backend. To dowód źródłowy; runtime po poprawce pozostaje
NOT VERIFIED. Nie zamykać punktu na podstawie samego review.

Weryfikator odrzuca także position==target i zerowy up, zgodnie z backendem.
Seria `5a42876f577b4d3fbfded703698d7637` wykryła brak importu sys w tej
nowej kontroli. Po dodaniu importu receipt `d812db40be7c49efaf800c74c26e8da3`
potwierdził ponownie 165 testów, 0 skipów i exit 0. Nie jest to dowód
runtime ownera kamery.

## Końcowe dowody konkretnych ownerów

Managed Chrome na 3251: receipt `98aedd887c6d41a3a2370c19dde2fdc2`,
**34/34 PASS**, exit 0, brak page_errors i console_errors, własny serwer
terminalny. Fingerprint przed/po:
`53809fd60c1431074c2dcdb44475cc6d86f84921e2635da4726dafad1c83b7dd`.
Rzeczywiste kontrolery projektu, registry i typowana fasada API wykonały
przenoszenie sześciu pól, odmowę przy niezgodnym ACK/readback, mutation guard,
odmowę niezaobserwowanej kamery ze zwolnieniem guardów, odmowę współdzielenia
starego rejestru, v1 compatibility i sessionless null. Odpowiedzi API są
fixtures: nie jest to restart procesu Windows ani kwalifikacja solvera.

Finalny scoped lint ownera: receipt `42269c36ee83410fabfa7125319f353f`, PASS.
Kontrola produkcyjnych typów `1d0f5dcc0766432b9bfe1f19a0c86fb2` nie zgłaszała
już błędów ownera ani fixture; pozostał obcy błąd computeNodeInventory.ts:260
(`snapshot` possibly null). Cała kontrola ma zatem FAILED, nie PASS.

Próby pośrednie zachowano: `17fb3745c0e8451585f52d4f4e9f9b9c` miała
32/33 PASS, bo asercja canSave wymagała otwartego projektu zamiast pustego
dokumentu; `b7c55c20283949fe8844cba3ef9840cb` miała 33/33 kontrole ownerów,
ale stary selektor dialogu New Problem zatrzymał dodatkową kontrolę UI.
Aktualizacja smoke do etykiet New simulation/Create simulation i nazwanej
zgody zastąpienia zachowuje asercje Cancel/pending/failure. Receipt
`609f4f48ce6d4b809e145c8e76e39455` potwierdził 34/34 przed dodaniem ostatniej
regresji odmowy współdzielenia rejestru. Końcowy receipt jest podany powyżej.

Natywny restart po poprawce oraz dwa restarty A→B→C w jednej sesji
przeglądarki pozostają NOT VERIFIED. Status P8-53 pozostaje otwarty.

API hygiene: receipt `cea917eb274649e1b65aa5c876c9c68a`, PASS.
Końcowa kontrola produkcyjnych typów po guardzie świeżości rejestru:
`e5ec865c017d4184a73eabeb2ee3a7f1`, FAILED wyłącznie na
computeNodeInventory.ts:260. Własne pliki poprawki nie zgłosiły diagnoz.
Nie promować tego checkpointu do pełnej kwalifikacji frontendu ani wydania.
