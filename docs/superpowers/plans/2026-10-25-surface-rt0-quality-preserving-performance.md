# Wydajność surface RT0 bez zmiany jakości — 25.10.2026

## Cel i stan początkowy

Poprzedni celowy turn przyniósł postęp: commit aplikacji 498a36ae, udany managed
build 3abcda48 oraz rzeczywiste regresje projektu i odczytu V/J/H. Pełna próba
Universe pozostaje Failed po limicie 1800 s, nie jest aktywnym oczekiwaniem.

Następny etap ma doprowadzić do pełnej mapy, bez zmniejszania liczby 1154
targetów, dokładności, budżetów ani kontroli whole-face/fan i 80/120.
Najpierw osobny mały benchmark istniejącej metody. Nie kwalifikuje on bazy
ani pełnego Universe.

## Prerejestracja porównania

Scenariusz: `examples/antenna_universe/fem_antenna_closed_loop_surface_benchmark.py`.
Geometria przewodnika, sigma, źródło i siatka przewodnika odpowiadają pełnemu
przykładowi; osobny niemagnetyczny sampling ma rozmiar 0.08 mikrometra i środek
(1, 0, 0.3) mikrometra. Publiczna metoda analytic_rt0_surface i wszystkie pola
polityki pozostają identyczne z przykładem Universe. To diagnostyka, nie
redukcja docelowego zadania. Nie ma Relax, Run, LLG ani FFT.

1. Przed edycją kernela wykonać mały przypadek w obecnej grupie managed.
   Zachować pełne V/J/H, wszystkie precision records, work report, package
   provenance, uporządkowane punkty i źródło.
2. Dla pierwszej poprawki przenieść wyłącznie powtarzane wyznaczanie czterech pi
   z każdej ściany do zakresu targetu/precyzji; ta sama formuła i typ.
   Nie zmieniać kolejności sumowania, predykatów, tolerancji i publicznego ABI.
3. Porównać ten sam nośnik i zaakceptowane źródło. Jeżeli generowanie siatki
   zmieni wejścia, porównanie nie jest zaliczone i wymaga przypięcia wejść.
   Wymagać identycznego H binary64 i wszystkich zapisanych wartości precyzji
   oraz niezmienionych refusal/qualification. Raportować rzeczywisty czas
   i peak RSS; liczniki atan2 mają uczciwie maleć. Bez pomiaru nie deklarować
   przyspieszenia.
4. Po potwierdzeniu efektu kontynuować kolejne ograniczone optymalizacje
   lub pełną próbę z niezmienionymi targetami i polityką, zależnie od pomiaru.

Wariant współdzielenia ścian odłożono: wymaga oddzielnego dowodu mapowania
winding i ownerów. Równoleglenie zmieniałoby kontrolę pracy i porządek sum,
więc nie jest pierwszą poprawką. Podniesienie limitu czasu albo obniżenie
jakości nie stanowi rozwiązania.

## Granice weryfikacji

Build tylko w tej samej grupie przez just Docker DEV. Zakaz kompilowania
natywnych testów jednostkowych pozostaje. UI/WebGL nadal NOT VERIFIED.
Canonical physics owner: docs/physics/0950-quasistatic-microwave-antenna-field-basis-and-k-selective-excitation.md, rozdział surface RT0.
Mapa implementacji: surface_rt0.cpp + face_pass, Arithmetic::angle i
evaluate_surface_rt0; accepted_surface_rt0.cpp + evaluate_accepted_surface_rt0.
Nie zmieniamy równań ani statusu inspection_only.
