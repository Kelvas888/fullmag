# ADR 0069 — zakładki sesji w Control Room jako instancje

Status: decyzja użytkownika przyjęta 23.10.2026 („Tab = instancja”).
Data: 2026-10-23.
Powiązane: ADR 0067 (niezależne grupy DEV, automatyczny port),
ADR 0068 (tryb live DSL, sesja wspólna ze skryptem Python).

## Kontekst

Użytkownik chce w Control Room układu jak w przeglądarce: stała zakładka Home
i osobna zakładka dla każdej sesji. Backend utrzymuje jedną sesję live na
proces API (`AppState.current_live_state`); wszystkie trasy sesji mają postać
`/v2/sessions/current/...`. Każda grupa DEV (i każda instancja runtime)
publikuje frontend Next.js na własnym porcie loopback, a frontend przekazuje
`/v2/*` do swojego API. Jeden port to więc jedna instancja: UI, API i sesja
w zgodnych wersjach. Skrypt Python łączy się z tym samym adresem
(`fm.connect("http://127.0.0.1:<port>")`).

Rozważone warianty:

1. zakładka = instancja (wybrany),
2. wiele sesji w jednym API (`/v2/sessions/{id}/...`; przebudowa stanu API
   i setek tras),
3. jedna sesja live i zakładki historii tylko do odczytu.

## Decyzja

1. **Tożsamość zakładki.** Zakładka to para (port instancji, `session_id`).
   Port wyznacza origin `http(s)://<host strony>:<port>`; nazwa hosta jest
   brana z bieżącej strony, więc `localhost` i `127.0.0.1` nie mieszają się.
   Klucz pozostaje ważny, gdy w przyszłości jedna instancja będzie miała wiele
   sesji (wariant 2).

2. **Wykrywanie instancji w backendzie.** `GET /v2/platform/instances`
   sprawdza ograniczone okno portów loopback i zwraca instancje Fullmag,
   które odpowiedziały poprawną listą sesji:
   - okno domyślne `3197-3260` (port preferowany i 64 porty rotacji launchera
     z ADR 0067); zmienna `FULLMAG_INSTANCE_DISCOVERY_PORTS=<od>-<do>`,
     najwyżej 256 portów;
   - host: `FULLMAG_INSTANCE_DISCOVERY_HOST`, a bez niej `host.docker.internal`,
     gdy ta nazwa się rozwiązuje (kontener Docker Desktop), w przeciwnym razie
     `127.0.0.1`;
   - każda sonda to jedno żądanie `GET /v2/sessions HTTP/1.0` bez poświadczeń,
     z limitem połączenia 300 ms, limitem całości 1,5 s i limitem odpowiedzi
     256 KiB; brak przekierowań;
   - instancją Fullmag jest tylko odpowiedź 200 z nagłówkiem
     `x-fullmag-api-instance` i treścią `SessionListResource`; port z inną
     odpowiedzią (np. frontend z zatrzymanym backendem albo obca usługa) nie
     jest instancją;
   - własna instancja jest rozpoznawana po identyfikatorze procesu API
     (`x-fullmag-api-instance`) i oznaczona `self: true`.

   Wykrywanie robi backend, a nie przeglądarka, bo sondy z przeglądarki do
   zamkniętych portów zapisują błędy `ERR_CONNECTION_REFUSED` w konsoli, którą
   sprawdzają testy przeglądarkowe.

3. **Treść zakładki.** Sesja własnej instancji to istniejący workspace (bez
   ramki). Zakładka innej instancji osadza jej własne UI w `iframe` z jej
   originu, więc UI zawsze pasuje do wersji API tej instancji. Osadzone UI
   rozpoznaje, że jest w ramce (`window.top !== window.self`) i nie rysuje
   własnego paska zakładek.

4. **Nagłówki ramek.** CSP `frame-ancestors` dopuszcza `'self'` oraz originy
   loopback (`http://127.0.0.1:*`, `http://localhost:*` i odpowiedniki
   `https`); nagłówek `X-Frame-Options` jest usunięty, bo nie wyraża listy
   originów, a przy `frame-ancestors` przeglądarki go pomijają. Strony spoza
   loopback nadal nie mogą osadzać Control Room.

5. **Cykl życia zakładek.** Zamknięcie zakładki usuwa ramkę i nigdy nie
   zatrzymuje sesji ani instancji. Nieaktywne ramki pozostają zamontowane
   (ukryte przez `visibility`), aby zachować stan widoku i kontekst WebGL.
   Lista otwartych zakładek i aktywna zakładka są wygodą przeglądającego:
   trzymane w `localStorage` originu strony, odczyt i zapis w `try/catch`,
   bez wpływu na poprawność przy braku magazynu. Zakładka instancji, której
   wykrywanie nie zwraca, pokazuje stan „niedostępna” i nie znika sama.

6. **Home.** Home pokazuje sesje własnej instancji (ADR 0068) oraz sekcję
   innych instancji na tym komputerze z nazwą sesji, statusem i przyciskiem
   otwarcia w zakładce. Pasek zakładek odświeża wykrywanie co 5 s, gdy strona
   jest widoczna.

## Konsekwencje

- Backend bez zmian w modelu sesji; jedna nowa trasa tylko do odczytu.
- Awaria jednej instancji nie zamyka zakładek innych.
- Każda osadzona instancja ładuje własny bundle UI i własny kontekst WebGL;
  przy wielu zakładkach rośnie zużycie pamięci przeglądarki.
- Ograniczenie: na silniku Docker bez Docker Desktop porty opublikowane na
  `127.0.0.1` hosta nie są osiągalne z kontenera przez bramę hosta; wtedy
  wykrywanie zwraca tylko własną instancję, chyba że
  `FULLMAG_INSTANCE_DISCOVERY_HOST` wskaże osiągalny adres.
- Osadzanie dopuszczone dla originów loopback zwiększa powierzchnię
  clickjackingu tylko o lokalne strony; strony zdalne pozostają zablokowane.

## Weryfikacja

- Testy jednostkowe Rust: parsowanie okna portów, parsowanie odpowiedzi
  sondy (status, nagłówek instancji, limit rozmiaru, odrzucenie
  `transfer-encoding`), oznaczanie własnej instancji.
- Testy vitest: magazyn zakładek (otwieranie, zamykanie, aktywacja,
  odporność na brak `localStorage`), pasek zakładek, sekcja Home.
- Dowód runtime: dwie grupy DEV na jednym hoście; z jednej strony widoczna
  druga instancja w Home i w pasku, osadzony workspace drugiej instancji
  w zakładce, przełączanie Home ↔ sesja ↔ druga instancja bez utraty stanu.

### Dowód runtime (24.10.2026, grupa DEV 3199)

- `GET /v2/platform/instances` z grupy 3199 zwrócił siebie (`is_self: true`)
  i grupę 3206 z jej sesją `fullmag-python-live` (`awaiting_command`).
- Strona `http://localhost:3199` osadziła `http://127.0.0.1:3199/workspace`
  (inny origin) bez błędów CSP; nagłówki zawierają `frame-src` i
  `frame-ancestors` dla originów loopback.
- Zakładka instancji: ramka widoczna, osadzone UI rysuje workspace bez
  własnego paska zakładek, workspace hosta jest `inert`. Powrót do Home
  ukrywa ramkę (`visibility: hidden`) bez odmontowania; ponowne otwarcie
  pokazuje tę samą ramkę. Zamknięcie usuwa ramkę i wpis w `localStorage`.
- Instancja sprzed tej zmiany (3206) odmawia osadzenia (`frame-ancestors
  'self'`); pasek oferuje wtedy „Open in window”.
- Nie sprawdzono: dwóch odrębnych procesów API z nowym kodem naraz (druga
  grupa nie przeszła progu 32 GiB wolnego miejsca na dysku hosta).
