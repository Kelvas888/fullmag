# P8-53BI — Save Project przed restartem

Data: 13.10.2026. Status: **OPEN**. Próba nie potwierdziła pobrania
archiwum ani odtworzenia po Save. Nie zmienia to zamknięcia P8-53BH.

## Kontrakt i wymagane dowody

`workspace.save-project` wywołuje `ProjectDocumentController.save()`.
Kontroler synchronizuje zatwierdzoną scenę przez authoring binding;
nie wykonuje niejawnego Apply lokalnych szkiców Inspectora.
W przeglądarce uruchamia pobranie archiwum i zachowuje dirty document.
Host Tauri zapisuje archiwum i dopiero po potwierdzeniu aktualizuje
persisted_revision oraz dirty=false. Te ścieżki wymagają osobnych dowodów.

Odbiór wymaga rzeczywistego pliku z normalnego Save, kontroli ZIP/CRC,
manifestu, dokumentu sceny i skryptu, zgodności z zatwierdzoną sceną,
a następnie kontrolowanego restartu i dokładnego odtworzenia dokumentu.
Szkic Inspectora nie może zostać zastosowany ani skasowany przez Save.
Pobranie przez przeglądarkę nie dowodzi trwałego zapisu Windows desktop.

## Próba 231cfac682144a9b8c95fa177d08c024

Managed recipe `verify-windows-development-workspace-browser`, owner bundle
`12984ba740244e5e86d8878814069155`, checkout
`1ce6fee668f8bbe56da0c193361bf25a258e2b16`, prywatny port 3258.
Workspace użytkownika na 3197 nie był restartowany.

API `1f1cb566-ea0c-41cf-b5a0-b2f6983f5d4c`, session
`session-18de210b64cbbf2400023578`. Przez UI utworzono projekt
`project-25346248be434ae482f8a3d4081ee786`, nazwa
`P8-53BI Save archive proof`. Scenę z obiektem, regionem, materiałem
i finite Run wprowadzono normalną transakcją `replace_scene`.
Nie jest to dowód pełnego authoringu przez UI.

Setup draft uzyskał pozytywny before-capture. Zapisany checkpoint ma
revision=2, dirty=true i hash archiwum
`fc9555b17f662e60967324e3d7b44da0de71605e9a93f4bc6fe2d370a81761fc`.
Canvas był widoczny, context_lost=false, drawing buffer 679×281.
Kontrole źródeł fixture: typecheck i lint exit=0.

Obsługa zdarzenia download w narzędziu przeglądarkowym nie zwróciła
pliku ani obserwacji po kliknięciu. Narzędzie pozostało w oczekiwaniu
dłużej niż zadany limit. Następnie prywatny serwer zakończył próbę bez
otrzymania restartu/Finish; karta pokazała odmowę połączenia. Nie obchodzono
polityki nawigacji przeglądarki. Nie można z tych danych rozstrzygnąć,
czy Save został wykonany, ani przypisać awarii produktowi.

Terminalny receipt: state=failed, exit_code=1, checks=0,
finished_at=2026-10-13T18:07:35.352221+02:00. Wszystkie 19 procesów
mają waited=true. Brak nowego API i brak dowodu restartu. Próba nie jest PASS.

## Następny krok

Ponowić tę samą zarządzaną trasę dopiero po potwierdzeniu terminalnego
stanu poprzedniej próby (potwierdzono). Rozdzielić kliknięcie Save od
odczytu zdarzenia pobrania, obsłużyć odrzucenie obietnicy i sprawdzić
wynik UI przed dalszym oczekiwaniem. Jeśli używana przeglądarka nadal
nie udostępnia pliku, użyć wspieranej przeglądarki z obsługą pobrań;
nie zastępować rzeczywistego Save eksportem wykonanym przez API.
Nie zmieniać zachowania produktu na podstawie samego timeoutu narzędzia.
