# Wzorce z COMSOL, 3ds Max i bibliotek viewportu

## 1. Zakres porównania

Porównanie dotyczy konkretnych publicznie udokumentowanych wzorców pracy, nie pełnego testu zainstalowanych aplikacji. Źródła COMSOL mają wersję 6.4. Dokumenty Autodesk 2012 są **historycznymi źródłami trwałych zasad interakcji**, nie opisem najnowszej wersji 3ds Max. Nie przenoszę licencjonowanych screenshotów ani całego interfejsu do makiet.

| Wzorzec | Co zastosować w Fullmagu | Czego nie kopiować bez analizy |
|---|---|---|
| COMSOL: rozdzielenie obiektu geometrii i meshu | Model geometryczny, operacje/recepta i wynik z własnym lifecycle. | Założenia o identycznych rodzinach elementów i fizyce. |
| COMSOL: import i przekształcenia w procesie budowy | Jawny source, units, placement, build/rebuild i diagnostyka. | Utożsamienia triangulacji wejściowej z zakwalifikowanym solver mesh. |
| 3ds Max: Transform Type-In | Wartości numeryczne obok manipulacji myszy; absolute/delta. | Konkretnej mapy skrótów bez kontroli kolizji w Fullmagu. |
| 3ds Max: ramy odniesienia | World/Local/View i czytelna informacja, względem czego wykonywana jest operacja. | Ukrytej zmiany obiektu, tekstury lub kamery przy wspólnym gizmo. |
| Three.js: TransformControls | Adapter narzędzia, zdarzenia gestu, osie, tryby, snap. | Traktowania Object3D jako kanonicznego modelu fizycznego. |
| React Three Fiber: event/ray semantics | Prawidłowe zarządzanie capture i raycast, testy rzeczywistego drag. | Założenia, że każde event.point jest nowym punktem na stabilnej płaszczyźnie. |

## 2. COMSOL: rozdzielenie etapów

Dokumentacja mesh-based geometry opisuje budowanie geometrii na podstawie siatki, z kontrolowanymi operacjami i osobną siatką obliczeniową. Dokumentacja importu opisuje import node i transformacje oraz ponowne wykonanie importu w sekwencji budowania. W Fullmagu odpowiada temu trwałe źródło assetu, jawna konwersja jednostek, niezależny transform obiektu i określony target meshowania. [B01], [B02].

Projekt Fullmaga nie powinien jednak udawać pełnego drzewa operacji COMSOL, dopóki nie ma wersjonowania operacji i zależności. W pierwszym etapie drzewo może przedstawiać obiekty, przypisania, polityki oraz artefakty; CSG i pełna historia cech wymagają osobnego kontraktu.

## 3. 3ds Max: precyzja równolegle z manipulacją

Type-In daje precyzyjne numeryczne sterowanie translacją, rotacją i skalą; ramy odniesienia określają osie operacji. To właściwy wzorzec dla Fullmaga: wspólny draft, czytelny pivot, tryb absolute/delta i równoprawna obsługa numeryczna. Archiwalna dokumentacja wystarcza do uzasadnienia tych zasad, ale nie do deklarowania obecnego wyglądu produktu. [B03], [B04].

Fullmag potrzebuje dodatkowo jednoznaczności jednostek SI i semantyki fizycznej. Obrót obiektu może oznaczać zmianę lokalnych osi materiału, ale nie automatyczny obrót laboratoryjnego pola zewnętrznego. Tej decyzji nie rozstrzyga zachowanie programu graficznego.

## 4. Biblioteki nie zastąpią lifecycle

TransformControls dokumentuje tryby translate/rotate/scale, space i snap oraz zdarzenia interakcji. Może posłużyć za adapter, ale musi zostać spięty z historią, session fence i transakcją. Dokumentacja R3F odróżnia capture od typowego DOM i opisuje dane przecięcia/ray; uzasadnia to test F15, nie dowodzi sama w sobie błędu konkretnego gestu. [B05], [B06].

Repo deklaruje zależności jako zakresy wersji w package.json. Publiczna dokumentacja bibliotek nie musi odpowiadać dokładnej wersji lockfile. Przed wdrożeniem sprawdzić API wersji faktycznie zainstalowanej. [S24: `package.json`](https://github.com/MateuszZelent/fullmag/blob/2a3c6becb9c7e111ae1497ec0cd9ac9576acba95/apps/control-room/package.json).

## Źródła pierwotne — odczyt 2026-10-11

- **B01 — COMSOL 6.4, Mesh-Based Geometry:** https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_ref_geometry.23.034.html
- **B02 — COMSOL 6.4, Importing Meshes:** https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_ref_mesh.24.32.html
- **B03 — Autodesk 3ds Max 2012, Transform Type-In:** https://download.autodesk.com/us/3dsmax/2012help/files/GUID-B9779BBF-5B04-44EF-95EC-465DD726770-276.htm
- **B04 — Autodesk 3ds Max 2012, Reference Coordinate System:** https://download.autodesk.com/us/3dsmax/2012help/files/GUID-0F3E2822-9296-42E5-A572-B600884B07E-298.htm
- **B05 — Three.js, TransformControls:** https://threejs.org/docs/pages/TransformControls.html
- **B06 — React Three Fiber, Events:** https://r3f.docs.pmnd.rs/api/events
