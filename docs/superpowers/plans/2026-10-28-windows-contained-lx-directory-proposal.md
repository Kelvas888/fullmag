# Propozycja kwalifikacji zawartych dowiązań katalogowych LX

Status: propozycja do decyzji operatora; rozszerzenie nie jest zastosowane.
Dotyczy wyłącznie recovery grupy anteny na porcie 3203 i odczytowego dowodu
izolacji obcych bindów Windows. Nie jest nową polityką solvera.

## Stan i rzeczywista odmowa

Bazowy commit recepty: `a41d4c9cdc46a64ed2d4a1f4ad5f4042636d06f5`.
Bieżący adapter obsługuje zwykłe katalogi i zawarte względne linki do plików,
lecz odrzuca linki katalogowe. Ma przypięte źródła:

| Plik | SHA256 |
|---|---|
| `scripts/docker_windows_bind_isolation.py` | `4411410a48c18b49dbdfb982683853e3937aabb375d4f36680cfea9a74b372dd` |
| `scripts/test_docker_windows_bind_isolation.py` | `910add55d62a518c16c6652143ba19f7d6f19b7cde322da25e45e519c94fe4e7` |

77 testów adaptera i jego integracji z kanonicznym recovery przeszło.
Rzeczywisty preflight nadal odmawia. Dowody w control volume grupy:
`verification/recovery-mount-order-20261028/windows-contained-tests.json`,
`actual-contained-error.log` oraz `contained-provider-1.stderr`.

Konkretna ścieżka odmowy:
`D:/git/fullmag/storage/runs/microwave-antenna-latest-2026090-78aaec16ccf52671/ff4035657e4a40ad84e15ca2a07764a0/execution/node_modules/react-doctor`.
Kernel WSL odczytał następujący względny cel:
`.pnpm/react-doctor@0.9.12_@opentelemetry+core@2.10.0_@opentelemetry+api@1.9.1__eslint@9.39.4_jiti@2.7.0_/node_modules/react-doctor`.
Obserwacja lstat: mode 41471, device 118, inode 281474981481733.
Windows podał atrybuty 1040, bez obsługi Target w Get-Item. Ten odczyt nie
zastępuje kwalifikacji natywnego tagu i całego łańcucha.

Automatyczna kontrola odrzuciła zapis rozszerzenia, uzasadniając:
„zatwierdzony zakres obejmował wyłącznie zawarte względne linki do plików”
i kwalifikując dopuszczenie katalogów jako nieautoryzowane osłabienie ochrony.
Nie ponawiano odrzuconego zapisu inną drogą.

## Dokładny zakres proponowanej zmiany

1. `WINDOWS_PROVIDER` / `Descendants`: pełna enumeracja zwykłych katalogów
   pozostaje. Nie schodzić w żaden reparse. Zbierać plikowe i katalogowe
   dowiązania wyłącznie z dokładnym tagiem LX_SYMLINK `0xa000001d`.
   Junction, UNC oraz pozostałe tagi nadal odrzucać.
2. `_validate_descendants` i `_file_link_paths`: nieopublikowane `file_links`
   zastąpić przez `links: [{path, tag, kind}]`, z kind `file` albo `directory`.
   Zastosować nazwę `_link_paths`. Zachować zamknięte pola, unikalność,
   sortowanie, liczniki i limity: 100 000 wpisów, 256 linków, 15 sekund.
3. `_relative_link_target` i mały `_resolve_link_target`: dopuścić wyłącznie
   wiodące `..`, cofające po znanych zwykłych rodzicach, bez przekroczenia
   korzenia kandydata. Odrzucać `x/../y`, cele absolutne, drive/UNC,
   backslash, colon, znaki kontrolne i niejednoznaczne segmenty.
4. `_qualify_file_links` i `_validate_file_link_evidence`: uogólnić na
   `_qualify_links` / `_validate_link_evidence`. Każdy hop musi występować
   w dokładnym inventory LX, mieć zgodny kind i stabilne lstat/readlink/lstat.
   Rodzice pozostają zwykłymi katalogami na tym samym DrvFs. Końcowy obiekt
   musi być zwykłym plikiem lub katalogiem zgodnym z kind, nadal pod tym
   samym korzeniem i na tym samym urządzeniu. Maksymalnie 16 hopów;
   cykle, nieznane hopy i dowiązania w katalogach pośrednich odrzucać.
5. `_observation` / `validate_windows_bind_disjoint_proof`: użyć nazwy
   `contained_links`; oba pełne odczyty muszą zgadzać się co do natywnego
   inventory, celów, tożsamości hopów i końcowego obiektu. Nie zmieniać
   sprawdzania root FileID, serial, ancestry, backing VHD, nlink ani engine ID.

Dopuszczenie linku nie jest pominięciem walidacji. Zwykłe katalogi docelowe
wewnątrz root są niezależnie objęte pełną enumeracją. Link wychodzący poza
root, zmieniający urządzenie lub prowadzący przez inny reparse nadal blokuje
operację. To dowód obserwacyjny przed/po, bez gwarancji atomowości wobec
złośliwego administratora hosta.

## Ryzyko i obowiązkowe dowody

Błąd kwalifikacji mógłby dopuścić obcy kontener z dostępem do chronionych danych.
Dlatego przed zmianą runtime wymagane są regresje: PNPM z katalogiem docelowym,
wiodące ../../ pozostające pod root, root escape, x/../y, kind mismatch,
niezinwentaryzowany hop, cykl, symlink rodzica, junction/unknown tag oraz drift
celu i końcowej tożsamości. Następnie rzeczywisty preflight pełnych 43 runów
musi przejść bez modyfikowania historii. Fixture nie zamyka tej bramki.

Decyzja dotyczy implementacji i weryfikacji tego ograniczonego rozszerzenia.
Nie obejmuje zmiany obcej grupy, usuwania danych ani promowania zapisanego
wyniku Failed/unassessed do zakwalifikowanej bazy. Build własnego backendu,
probe i recovery pozostają oddzielnymi, przypiętymi krokami już zleconej pracy.
Nie istnieje jeszcze zastosowany patch tego rozszerzenia; niniejszy dokument
jest konkretnym zakresem zmiany po odmowie zapisu, a nie dowodem jej wykonania.
