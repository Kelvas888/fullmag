# Kontrola dokumentacji, nie kwalifikacja Fullmaga

Uruchom z rozpakowanego pakietu:

```sh
python verification/check_spec_oracles.py
python verification/check_package.py
```

Skrypty drukują JSON do stdout. Nie zmieniają reprodukcji v1 ani plików aplikacji. Pierwszy sprawdza liczby fixture dokumentacji; drugi SHA256 manifestu, referencje i spójność identyfikatorów. Zapisane `*_results.json` i `package_checks.json` dotyczą wyłącznie niniejszego pakietu. Browser check galerii HTML, jeśli dołączony, nie uruchamia Fullmaga ani WebGL produktu.

Fixtures zawierają znaki spoza ASCII (`µm`, `μm`) i są czytane jawnie jako UTF-8. Korekta 12.10.2026: `check_spec_oracles.py` czytał je kodowaniem locale, przez co na Windows (cp1250) kontrola „Numeric grammar fixture” zwracała FAIL niezależnie od treści specyfikacji.

