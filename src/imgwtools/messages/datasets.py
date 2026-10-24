"""Messages of ``datasets.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "meteo_dobowe_synop_archives_published": Text(
        "The meteo/dobowe/synop archives are published per station and have no "
        "dataset in the registry; use pl.imgw.meteo_synop_monthly",
        "Archiwa meteo/dobowe/synop są publikowane osobno dla każdej stacji i nie "
        "mają zbioru w rejestrze; użyj pl.imgw.meteo_synop_monthly",
    ),
    "meteo_terminowe_synop_archives_published": Text(
        "The meteo/terminowe/synop archives are published per station and have no "
        "dataset in the registry; use pl.imgw.meteo_synop_monthly",
        "Archiwa meteo/terminowe/synop są publikowane osobno dla każdej stacji i nie "
        "mają zbioru w rejestrze; użyj pl.imgw.meteo_synop_monthly",
    ),
    "meteo_terminowe_opad_data_do": Text(
        "The meteo/terminowe/opad data do not exist on the IMGW servers",
        "Dane meteo/terminowe/opad nie istnieją na serwerach IMGW",
    ),
    "unknown_data_provider_allowed": Text(
        "Unknown data provider: {provider!r}; allowed: {allowed}",
        "Nieznany dostawca danych: {provider!r}; dozwolone: {allowed}",
    ),
    "invalid_kind_dataset_allowed_hydro": Text(
        "Invalid kind of dataset: {kind!r}; allowed: hydro, meteo",
        "Nieprawidłowy rodzaj zbioru: {kind!r}; dozwolone: hydro, meteo",
    ),
    "unknown_imgw_dataset_allowed_keys": Text(
        "Unknown IMGW dataset: {dataset!r}; allowed keys: {allowed}",
        "Nieznany zbiór IMGW: {dataset!r}; dozwolone klucze: {allowed}",
    ),
    "option_must_number_text_list": Text(
        "The option {option} must be a number, a text or a list: {value!r}",
        "Opcja {option} musi być liczbą, tekstem lub listą: {value!r}",
    ),
    "invalid_value_option": Text(
        "Invalid value of the option {option}: {item!r}",
        "Nieprawidłowa wartość opcji {option}: {item!r}",
    ),
    "option_needs_non_empty_list": Text(
        "The option {option} needs a non-empty list of values",
        "Opcja {option} wymaga niepustej listy wartości",
    ),
    "invalid_year_range_years_option": Text(
        "Invalid year or range of years in the option {option}: {item!r}",
        "Nieprawidłowy rok lub zakres lat w opcji {option}: {item!r}",
    ),
    "invalid_range_years_option": Text(
        "Invalid range of years in the option {option}: {item!r}",
        "Nieprawidłowy zakres lat w opcji {option}: {item!r}",
    ),
    "option_must_contain_integers": Text(
        "The option {option} must contain integers: {item!r}",
        "Opcja {option} musi zawierać liczby całkowite: {item!r}",
    ),
    "months_must_range_1_12": Text(
        "Months must be in the range 1–12",
        "Miesiące muszą należeć do zakresu 1–12",
    ),
    "option_params_applies_only_dataset": Text(
        "The option params applies only to the dataset pl.imgw.hydro_semiannual, not "
        "{key}",
        "Opcja params dotyczy wyłącznie zbioru pl.imgw.hydro_semiannual, nie {key}",
    ),
    "invalid_semi_annual_parameters_allowed": Text(
        "Invalid semi-annual parameters: {items!r}; allowed: H, Q, T",
        "Nieprawidłowe parametry półroczne: {items!r}; dozwolone: H, Q, T",
    ),
    "dataset_has_no_annual_archives": Text(
        "The dataset {key} has no annual archives",
        "Zbiór {key} nie udostępnia archiwów rocznych",
    ),
    "invalid_years_dataset_first_year": Text(
        "Invalid years of the dataset {key}; the first year is {first_year}",
        "Nieprawidłowe roczniki zbioru {key}; minimalny rok: {first_year}",
    ),
    "archives_dataset_cover_whole_country": Text(
        "The archives of the dataset {key} cover the whole country; the option "
        "stations applies only to datasets with station files (cz.chmi.*)",
        "Archiwa zbioru {key} obejmują cały kraj; opcja stations dotyczy wyłącznie "
        "zbiorów z plikami stacji (cz.chmi.*)",
    ),
    "dataset_needs_option_years_years": Text(
        "The dataset {key} needs the option years (the years of the archives)",
        "Zbiór {key} wymaga opcji years (roczniki archiwów)",
    ),
    "option_stations_must_list_station": Text(
        "The option stations must be a list of station codes, not a single text",
        "Opcja stations musi być listą kodów stacji, nie pojedynczym tekstem",
    ),
    "invalid_station_codes_expected_least": Text(
        "Invalid {short_name} station codes: {codes}; expected at least one code "
        "matching {station_code_pattern}, e.g. 0-203-1-001000",
        "Nieprawidłowe kody stacji {short_name}: {codes}; oczekiwano co najmniej "
        "jednego kodu zgodnego z {station_code_pattern}, np. 0-203-1-001000",
    ),
    "option_months_does_not_apply": Text(
        "The option months does not apply to the dataset {key}: the {short_name} "
        "files are not monthly",
        "Opcja months nie dotyczy zbioru {key}: pliki {short_name} nie są miesięczne",
    ),
    "dataset_needs_option_stations_station": Text(
        "The dataset {key} needs the option stations: {short_name} station codes "
        "(the archives cover single stations)",
        "Zbiór {key} wymaga opcji stations: kodów stacji {short_name} (archiwa "
        "obejmują pojedyncze stacje)",
    ),
    "files_dataset_cover_whole_history": Text(
        "The {short_name} files of the dataset {key} cover the whole history of a "
        "station; the option years does not apply to this dataset",
        "Pliki {short_name} zbioru {key} obejmują całą historię stacji; opcja years "
        "nie dotyczy tego zbioru",
    ),
    "dataset_needs_option_years_without": Text(
        "The dataset {key} needs the option years: without a server listing the "
        "published years are not known",
        "Zbiór {key} wymaga opcji years: bez listingu serwera lata opublikowane nie "
        "są znane",
    ),
    "provider_notice_imgw": Text(
        "For private and research use; other uses require checking the IMGW-PIB "
        "terms, including the exceptions for high-value data.",
        "Do użytku prywatnego i badawczego; inne zastosowania wymagają sprawdzenia "
        "warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości.",
    ),
    "provider_notice_chmi": Text(
        "The CC BY 4.0 licence permits copying, changes and commercial use provided "
        "that the author ČHMÚ is credited, the licence is given and the changes are "
        "marked.",
        "Licencja CC BY 4.0 dopuszcza kopiowanie, zmiany i użycie komercyjne pod "
        "warunkiem uznania autorstwa ČHMÚ, podania licencji i oznaczenia zmian.",
    ),
    "license_notice": Text(
        "{attribution}. {notice}",
        "{attribution}. {notice}",
    ),
    "title_hydro_daily": Text(
        "Daily hydrological data",
        "Dane hydrologiczne dobowe",
    ),
    "title_hydro_monthly": Text(
        "Monthly hydrological data",
        "Dane hydrologiczne miesięczne",
    ),
    "title_hydro_semiannual": Text(
        "Semi-annual and annual hydrological data",
        "Dane hydrologiczne półroczne i roczne",
    ),
    "title_meteo_climate_daily": Text(
        "Daily meteorological data from climate stations",
        "Dane meteorologiczne dobowe ze stacji klimatycznych",
    ),
    "title_meteo_precip_daily": Text(
        "Daily meteorological data from precipitation stations",
        "Dane meteorologiczne dobowe ze stacji opadowych",
    ),
    "title_hydro_stations": Text(
        "List of hydrological stations",
        "Lista stacji hydrologicznych",
    ),
    "title_meteo_stations": Text(
        "List of meteorological stations",
        "Lista stacji meteorologicznych",
    ),
    "title_pmaxtp": Text(
        "Probable maximum precipitation PMAXTP",
        "Opady maksymalne prawdopodobne PMAXTP",
    ),
    "title_hydro_phenomena": Text(
        "Daily hydrological phenomena",
        "Zjawiska hydrologiczne dobowe",
    ),
    "title_meteo_climate_monthly": Text(
        "Monthly meteorological data from climate stations",
        "Dane meteorologiczne miesięczne ze stacji klimatycznych",
    ),
    "title_meteo_precip_monthly": Text(
        "Monthly meteorological data from precipitation stations",
        "Dane meteorologiczne miesięczne ze stacji opadowych",
    ),
    "title_meteo_synop_monthly": Text(
        "Monthly meteorological data from synoptic stations",
        "Dane meteorologiczne miesięczne ze stacji synoptycznych",
    ),
    "title_meteo_climate_terms": Text(
        "Meteorological data at observation times from climate stations",
        "Dane meteorologiczne terminowe ze stacji klimatycznych",
    ),
    "title_chmi_hydro_daily": Text(
        "ČHMÚ — daily hydrological data (H, Q, T)",
        "ČHMÚ — dane hydrologiczne dobowe (H, Q, T)",
    ),
    "note_chmi_hydro_daily_h": Text(
        "Daily mean water level (HD); date = the day of DT (…T00:00:00Z)",
        "Średni dobowy stan wody (HD); data = dzień z DT (…T00:00:00Z)",
    ),
    "note_chmi_hydro_daily_q": Text(
        "Daily mean discharge (QD), equal to the mean of the 24 hourly discharges "
        "labelled 00–23Z of that date (day by the Z labels; UTC or fixed CET — not "
        "confirmed by ČHMÚ)",
        "Średni dobowy przepływ (QD), równy średniej 24 przepływów godzinowych o "
        "etykietach 00–23Z tej daty (doba według etykiet Z; UTC albo stały SEČ — "
        "niepotwierdzone przez ČHMÚ)",
    ),
    "note_chmi_hydro_daily_t": Text(
        "Daily mean water temperature (TD)",
        "Średnia dobowa temperatura wody (TD)",
    ),
    "title_chmi_meteo_daily": Text(
        "ČHMÚ — daily meteorological data (precipitation, air temperature)",
        "ČHMÚ — dane meteorologiczne dobowe (opad, temperatura powietrza)",
    ),
    "note_chmi_meteo_daily_p": Text(
        "Precipitation sum (SRA) from the morning term (06:00Z) of day D to the "
        "morning term of day D+1, assigned to D",
        "Suma opadu (SRA) od terminu porannego (06:00Z) dnia D do terminu porannego "
        "dnia D+1, przypisana do D",
    ),
    "note_chmi_meteo_daily_tmean": Text(
        "Daily mean air temperature (T, AVG) = (T06 + T13 + 2·T20)/4 of the UTC "
        "terms of day D",
        "Średnia dobowa temperatura powietrza (T, AVG) = (T06 + T13 + 2·T20)/4 z "
        "terminów UTC dnia D",
    ),
    "note_chmi_meteo_daily_tmax": Text(
        "Maximum air temperature (TMA) of the period (D−1 20:00, D 20:00] UTC, "
        "assigned to D",
        "Maksymalna temperatura powietrza (TMA) okresu (D−1 20:00, D 20:00] UTC, "
        "przypisana do D",
    ),
    "note_chmi_meteo_daily_tmin": Text(
        "Minimum air temperature (TMI) of the period (D−1 20:00, D 20:00] UTC, "
        "assigned to D",
        "Minimalna temperatura powietrza (TMI) okresu (D−1 20:00, D 20:00] UTC, "
        "przypisana do D",
    ),
    "title_chmi_hydro_stations": Text(
        "ČHMÚ — list of hydrological stations",
        "ČHMÚ — wykaz stacji hydrologicznych",
    ),
    "title_chmi_meteo_stations": Text(
        "ČHMÚ — list of meteorological stations",
        "ČHMÚ — wykaz stacji meteorologicznych",
    ),
}
