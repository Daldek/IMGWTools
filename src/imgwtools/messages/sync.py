"""Messages of ``store/sync.py``."""

from imgwtools.messages import Text

MESSAGES = {
    "parameter_datasets_must_list_dataset": Text(
        "The parameter datasets must be a list of dataset keys",
        "Parametr datasets musi być listą kluczy zbiorów",
    ),
    "choose_least_one_dataset": Text(
        "Choose at least one dataset",
        "Wybierz co najmniej jeden zbiór",
    ),
    "imgw_pib_archives_cover_whole": Text(
        "The IMGW-PIB archives cover the whole country; the option stations applies "
        "only to ČHMÚ station datasets",
        "Archiwa IMGW-PIB obejmują cały kraj; opcja stations dotyczy wyłącznie "
        "zbiorów stacji ČHMÚ",
    ),
    "imgw_pib_datasets_need_option": Text(
        "The IMGW-PIB datasets need the option years",
        "Zbiory IMGW-PIB wymagają opcji years",
    ),
    "datasets_need_option_stations_station": Text(
        "The datasets {keys} need the option stations: station codes (the source "
        "files cover single stations)",
        "Zbiory {keys} wymagają opcji stations: kodów stacji (pliki źródła obejmują "
        "pojedyncze stacje)",
    ),
    "option_months_does_not_apply": Text(
        "The option months does not apply to the datasets {keys}: the station files "
        "are not monthly",
        "Opcja months nie dotyczy zbiorów {keys}: pliki stacji nie są miesięczne",
    ),
    "one_call_covers_datasets_one": Text(
        "One call covers datasets of one kind: national IMGW-PIB archives (without "
        "the option stations) or ČHMÚ station files (with the option stations); "
        "given {names}",
        "Jedno wywołanie obejmuje zbiory jednego rodzaju: archiwa krajowe IMGW-PIB "
        "(bez opcji stations) albo pliki stacji ČHMÚ (z opcją stations); podano "
        "{names}",
    ),
    "plan_must_written_outside_store": Text(
        "The plan must be written outside the store: {target}",
        "Plan musi być zapisany poza magazynem: {target}",
    ),
    "directory_plan_file_does_not": Text(
        "The directory of the plan file does not exist: {parent}",
        "Katalog pliku planu nie istnieje: {parent}",
    ),
    "give_plan_selectors_datasets_years": Text(
        "Give a plan or the selectors datasets/years/months/stations, not both",
        "Podaj plan albo selektory datasets/years/months/stations, nie oba naraz",
    ),
    "without_plan_parameter_datasets_required": Text(
        "Without a plan the parameter datasets is required",
        "Bez planu wymagany jest parametr datasets",
    ),
    "plan_concerns_another_store": Text(
        "The plan concerns another store: {root}",
        "Plan dotyczy innego magazynu: {root}",
    ),
}
