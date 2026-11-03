"""
Names and formulas that keep their wording in every language.

The attribution formulas are persisted in sidecars, series, catalogs and CSV exports
and one of them is the wording the IMGW-PIB terms of use prescribe, so a file must not
depend on the language of the person or program that wrote it; an institution has one
official name. The Polish text is the English one by design (the guard test allows it
for this area only).
"""

from imgwtools.messages import Text

_IMGW_NAME = "Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy"
_IMGW_PROCESSED = (
    "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu "
    "Badawczego zostały przetworzone"
)
_CHMI_ATTRIBUTION = (
    "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, "
    "licencja CC BY 4.0"
)
_CHMI_PROCESSED = "Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)"

MESSAGES = {
    "imgw_name": Text(_IMGW_NAME, _IMGW_NAME),
    "imgw_attribution": Text(
        f"Źródłem pochodzenia danych jest {_IMGW_NAME}",
        f"Źródłem pochodzenia danych jest {_IMGW_NAME}",
    ),
    "imgw_processed_attribution": Text(_IMGW_PROCESSED, _IMGW_PROCESSED),
    "chmi_attribution": Text(_CHMI_ATTRIBUTION, _CHMI_ATTRIBUTION),
    "chmi_processed_attribution": Text(_CHMI_PROCESSED, _CHMI_PROCESSED),
}
