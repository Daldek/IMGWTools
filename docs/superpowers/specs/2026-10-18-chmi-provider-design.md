# Spec: dostawca ČHMÚ w magazynie IMGW

**Data:** 2026-10-18  
**Status:** propozycja do ADR-003 (wymaga zatwierdzenia właściciela); kontrakt implementacji dostawcy ČHMÚ w 3.1.0 (C02–C10) oraz poprawki kontraktów `/1` przed tagiem v3.0.0 (C01)  
**Decyzje:** `docs/DECISIONS.md` ADR-003  
**Baza:** `2026-10-17-versioned-store-design.md` §1–§13 (ADR-001, ADR-002). Ten dokument opisuje wyłącznie zmiany i dodatki; czego nie zmienia, obowiązuje bez zmian.  
**Wymagania:** `Archiwista/docs/wymagania-imgwtools.md` IMGW-15..IMGW-19 (sekcje 4.15–4.19), stan z commita Archiwisty `4435cf7` (2026-10-18; IMGW-15 i IMGW-16 po uwagach IMGWTools, wcześniej `a59c6bc`)  
**Plan:** §16 (C01–C10)

## 0. Źródła faktów i oznaczenia

Fakty o źródle pochodzą z rozpoznania opendata.chmi.cz na żywo 2026-10-18 między 17:08 a 17:28 UTC, wykonanego przez trzech agentów: **CzHydro** (hydrologia), **CzMeteo** (klimatologia) i **CzLegal** (licencja, nagłówki HTTP, listingi). Wszystkie żądania były sekwencyjne (kilkaset, bez odpowiedzi 429 ani 503). Raporty są artefaktami sesji, a surowe próbki i listingi leżały w nietrwałym `/tmp/cz-explore/`, dlatego przy każdym fakcie podajemy adres i zaobserwowaną wartość.

Pomiar rozmiarów drzew meteo dobowych (§1.1, ADR-003 D6) wykonał 2026-10-18 ok. 18:45 UTC agent **CzSha** wyłącznie z listingów katalogów: 13 sekwencyjnych GET (11 katalogów elementów `historical_csv`, katalog `historical/data/daily/` i katalog główny `historical_csv/data/daily/`), bez pobierania plików danych.

- **[V]** — zweryfikowane na żywo 2026-10-18; w nawiasie raport i jego sekcja, np. [V CzHydro §7].
- **[I]** — wniosek z faktów zweryfikowanych.
- **[U]** — niezweryfikowane; rozstrzyga pytanie otwarte z §15 albo test `live`.

Skróty adresów: `O` = `https://opendata.chmi.cz/`, `H` = `O` + `hydrology/`, `C` = `O` + `meteorology/climate/`.

## 1. Zakres i granice

**W zakresie** (ADR-003 D4): zbiory `cz.chmi.hydro_daily` i `cz.chmi.meteo_daily` z szeregami, listy stacji `cz.chmi.hydro_stations` i `cz.chmi.meteo_stations` oraz katalog stacji `cz.chmi.stations`, w kontraktach i katalogu komend 3.x.

**Poza zakresem:**

| Co | Powód |
|---|---|
| `H now/`, `H recent/`, `C now/`, `C recent/` | Dane operacyjne i niewalidowane: „aktuálně naměřených a nevalidovaných dat” [V CzHydro §6, `H hydrologicka_data_now_a_recent_popis.pdf`]. `H recent` trzyma tylko bieżący rok kalendarzowy [V CzHydro §5.5]. `C recent` trzyma bieżący miesiąc i 12 katalogów miesięcznych, przenosi pliki między ścieżkami, a ostatnie dni mają `QUALITY 5` i są regenerowane [V CzMeteo §5–6]. Przestoje całodniowe nie są uzupełniane (2026-08-23, 2026-08-27..29) [V CzHydro §10]. ADR-001 D6: dane bieżące tylko na żywo; tu nie dodajemy też komend live ČHMÚ. |
| Hydro godzinowe, 10-minutowe, miesięczne, `NATQ`, `OF`, `OH7`, `OT7`; klimat 10-minutowy, godzinowy, miesięczny, roczny, pentadowy, zjawiska; elementy dobowe inne niż SRA, T, TMA, TMI (np. SCE, SNO, SVH, API30, TMInoc, TPM) | Zakres Archiwisty v0.6: hydro dobowe H, Q, T i meteo dobowe opad i temperatura powietrza (wymagania Archiwisty §1.2). Każdy z tych zbiorów można dodać później addytywnie jako nowy deskryptor. |
| `H characteristic/`, `H product/` (roczniki, warstwy GIS), ostrzeżenia CAP | Poza zakresem v0.6. |
| PMAXTP | Brak odpowiednika u ČHMÚ [V CzMeteo §12]; ADR-003 D15. |
| Zmiana nazwy pakietu (Obserwator) | Osobna, przyszła decyzja (ADR-003 D16). |

**Bez zmian:** znacznik `imgw-store/1`, układ i bajty wszystkich plików IMGW (sidecary, szeregi, katalog), koperta, kody błędów i gramatyka slotów ADR-002. Reguły wersji ADR-001 obowiązują; dla zbiorów z formą kanoniczną dochodzi jeden wiersz: inne bajty o tej samej treści kanonicznej → `unchanged` bez zapisu (§3.1, ADR-003 D6 i D17).

### 1.1 Fakty przesądzające

| Fakt | Wartość | Status |
|---|---|---|
| Plik hydro dobowy | `H historical/data/daily/H_<WIGOS>_DQ_<RRRR>.json`, gdzie RRRR to rok kalendarzowy („RRRR v názvu datové sady označuje kalendářní rok”) | [V CzHydro §1, `H read_me/Popis_datovych_sad_historical.pdf`] |
| Inwentarz hydro dobowych | 39 291 plików, 803 stacje, lata 1887–2025, 604,6 MB; 102 stacje mają brakujące lata w swoim okresie; brak pliku = 404 `text/html`, 153 B | [V CzHydro §5.1–5.2; CzLegal §3] |
| Plik meteo dobowy (wybrany) | `C historical_csv/data/daily/<grupa>/dly-<WIGOS>-<ELEMENT>.csv`: cała historia stacji, jeden element, bez koperty | [V CzMeteo §1, §2.2] |
| Plik meteo JSON (odrzucony) | `C historical/data/daily/dly-<WIGOS>.json`: 1 537 plików, 25,36 GB, największy 148 974 521 B (Praha-Klementinum `0-203-0-11514`), z kopertą | [V CzMeteo §7; listing `C historical/data/daily/`] |
| Koperta | `zaznamID`, `datovyZdrojID`, `datovyTokID`, `datumVytvoreni`, `verzeDat`, `data`; przy każdej generacji nowe `zaznamID` i `datumVytvoreni`, a te same `data` dają inną sumę SHA-256 | [V CzHydro §7: `H recent/metadata/meta1-20261016.json` vs `-20261017.json`; CzMeteo §13 p. 2] |
| `ETag` | nginx `"<hex mtime>-<hex size>"`, np. `"6a0eea27-548f"` = 2026-05-21T11:19:03Z i 21 647 B; `If-None-Match` i `If-Modified-Since` → 304; brak kompresji odpowiedzi | [V CzHydro §7; CzLegal §3] |
| Ponowne publikacje | Hydro dobowe: 38 733 pliki z mtime 2025-07-01 12:07; rocznik 2025: 552 pliki z 2026-05-21; poprawka 6 plików stacji `0-203-1-456505` z 2026-02-06. Meteo: wszystkie pliki dobowe JSON i CSV z 2026-09-04. | [V CzHydro §7; CzMeteo §6; listingi] |
| Listing | nginx autoindex (HTML): `<a href>`, `DD-Mon-YYYY HH:MM` (UTC), rozmiar w bajtach; bez `ETag`, `Last-Modified` i `Content-Length`; `H historical/data/daily/` = 5,27 MB | [V CzLegal §3–4] |
| Retencja | serwer przechowuje wyłącznie bieżącą wersję pliku | [V CzMeteo §14; CzHydro §7] |
| Licencja | CC BY 4.0, warunek „uvedení původu (zdroje ČHMÚ)”, bez stałej formuły atrybucji | [V CzLegal §1] |
| Rozmiar drzew meteo dobowych | `C historical_csv/data/daily/`: 11 katalogów elementów, 14 833 pliki, 19 826 176 829 B (19,83 GB; 14 790 plików z mtime 2026-09-04); wybrane SRA, T, TMA, TMI: 3 351 plików, 4 362 990 268 B (SRA 1 531 / 1,72 GB, T 709 / 1,88 GB, TMA 556 / 0,38 GB, TMI 555 / 0,38 GB). `C historical/data/daily/` (JSON): 1 537 plików, 25 359 042 104 B. Na stację (1 535 wspólnych): mediana JSON 10,03 MB, mediana czterech CSV 1,59 MB (mediana stosunku 0,18); Praha-Klementinum 148,97 MB wobec 32,25 MB. Listingi CSV razem 1,99 MB (11 GET), listing JSON 203 KB | [V pomiar CzSha 2026-10-18, wyłącznie listingi katalogów, bez pobierania plików] |

## 2. Rejestr dostawców i zbiorów

### 2.1 Typy (addytywnie wobec §2 i §13.9 spec 2026-10-17)

```python
@dataclass(frozen=True)
class License:
    id: str                          # C01: było Literal["IMGW-PIB"]; "IMGW-PIB" | "CC-BY-4.0"
    attribution: str                 # formuła źródła (archiwa, listy stacji)
    url: str
    terms_url: str | None = None     # w sidecarze zapisywane tylko, gdy nie None

@dataclass(frozen=True)
class ProviderDescriptor:
    id: str                          # wartość pola provider: "IMGW-PIB" | "CHMI"
    short_name: str                  # w tekstach: "IMGW-PIB" | "ČHMÚ"
    name: str                        # pełna nazwa instytucji
    country: str                     # ISO 3166-1 alfa-2: "PL" | "CZ"
    key_prefix: str                  # "pl.imgw" | "cz.chmi"
    base_url: str                    # baza server_path
    license: License
    processed_attribution: str       # formuła postaci przetworzonych (bez kropki końcowej)
    notice: str                      # dalszy tekst komunikatu license_terms
    station_code_pattern: str        # gramatyka kodu stacji
    datasets: tuple[str, ...]        # klucze zbiorów w kolejności rejestru

# DatasetDescriptor — pola addytywne:
#   provider: str = "IMGW-PIB"
#   archive_scope: Literal["country", "station_year", "station_element"] = "country"
#   update_signal: Literal["http", "listing", "none"]            # nowa wartość "listing"
#   variable_notes: Mapping[str, str] = {}                       # konwencja zmiennej, po polsku
#   measurement_fields: tuple[Literal["quality", "source_flag"], ...] = ()
#   content_form: str | None = None                              # klucz CONTENT_FORMS (§3.1); None = tożsamość wyłącznie bajtów
#   volatile_fields: tuple[str, ...] = ()                        # = CONTENT_FORMS[content_form].volatile_fields; () bez formy
# ArchiveFile — pole addytywne:
#   station_code: str | None = None

STATION_CODE_PATTERN = r"^([0-9]{9}|0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16})$"   # C01; suma gramatyk

def providers() -> tuple[ProviderDescriptor, ...]: ...
def get_provider(provider: str, /) -> ProviderDescriptor: ...      # id albo key_prefix
def datasets(*, kind: Literal["hydro", "meteo"] | None = None,
             provider: str | None = None) -> tuple[DatasetDescriptor, ...]: ...
def station_source_files(*, provider: str = "IMGW-PIB") -> tuple[ArchiveFile, ArchiveFile]: ...
```

Nieznany dostawca w `get_provider` i w opcji `provider` → `validation_error` z `details.allowed`.

| Pole | `IMGW-PIB` | `CHMI` |
|---|---|---|
| `short_name` | `IMGW-PIB` | `ČHMÚ` |
| `name` | Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy | Český hydrometeorologický ústav |
| `country` | `PL` | `CZ` |
| `key_prefix` | `pl.imgw` | `cz.chmi` |
| `base_url` | `https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/` | `https://opendata.chmi.cz/` |
| `license` | bez zmian (§4 spec 2026-10-17) | §8 |
| `processed_attribution` | „Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone” (dziś stała w `store/series.py`) | „Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)” |
| `notice` | „Do użytku prywatnego i badawczego; inne zastosowania wymagają sprawdzenia warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości.” (dzisiejszy tekst) | §8 |
| `station_code_pattern` | `^[0-9]{9}$` | `^0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16}$` |

Niezmienniki rejestru (test C02): klucze, slugi i aliasy są unikalne globalnie; `key` zaczyna się od `key_prefix` swojego dostawcy; pierwsze segmenty `server_dir` różnych dostawców są rozłączne (IMGW `dane_hydrologiczne`, `dane_meteorologiczne`; ČHMÚ `hydrology`, `meteorology`); gramatyki kodów różnych dostawców są rozłączne; `providers()` ma stałą kolejność `IMGW-PIB`, `CHMI`.

Kod ČHMÚ to identyfikator WIGOS dokładnie jak w źródle (ADR-003 D3). Obserwowane postaci: hydro `0-203-1-NNNNNN` (DBC, 6 cyfr) i `0-203-1-CBNNNNNN` (19 stacji Povodí Vltavy, bez archiwum `historical`) [V CzHydro §2]; meteo `0-20000-0-NNNNN` (43), `0-203-0-NNNNN` (269), `0-203-0-` + 11 cyfr (1 298), `0-203-0-` + 9 cyfr (1) w historical meta1 oraz 10 cyfr w now meta1 [V CzMeteo §3]. Gramatyka ČHMÚ obejmuje wszystkie kody z metadanych pobranych 2026-10-18 (hydro: 546 kodów now meta1, 563 meta3, 831 historical meta1; meteo: 1 611 historical meta1, 757 now meta1), a kody hydro i meteo są rozłączne [V próbki CzHydro i CzMeteo].

### 2.2 Deskryptory ČHMÚ

| Pole | `cz.chmi.hydro_daily` | `cz.chmi.meteo_daily` | `cz.chmi.hydro_stations` | `cz.chmi.meteo_stations` |
|---|---|---|---|---|
| `slug` | `chmi_hydro_daily` | `chmi_meteo_daily` | `chmi_hydro_stations` | `chmi_meteo_stations` |
| `kind` | `hydro` | `meteo` | `hydro` | `meteo` |
| `title` | ČHMÚ — dane hydrologiczne dobowe (H, Q, T) | ČHMÚ — dane meteorologiczne dobowe (opad, temperatura powietrza) | ČHMÚ — wykaz stacji hydrologicznych | ČHMÚ — wykaz stacji meteorologicznych |
| `server_dir` | `hydrology/historical/data/daily` | `meteorology/climate/historical_csv/data/daily` | `hydrology/historical/metadata` | `meteorology/climate/historical/metadata` |
| `parser` | `parse_chmi_hydro_daily` | `parse_chmi_meteo_daily` | `parse_chmi_stations` | `parse_chmi_stations` |
| `variables` | `H: cm`, `Q: m3/s`, `T: degC` | `P: mm`, `Tmean: degC`, `Tmax: degC`, `Tmin: degC` | — | — |
| `time_unit` / `year_type` | `day` / `calendar` | `day` / `calendar` | `station_list` / `none` | `station_list` / `none` |
| `first_year` | 1887 | `None` (pliki bez roku) | — | — |
| `archive_scope` | `station_year` | `station_element` | `country` | `country` |
| `update_signal` | `listing` | `listing` | `http` | `http` |
| `measurement_fields` | — | `quality`, `source_flag` | — | — |
| `content_form` / `volatile_fields` | `chmi-json/1` / `zaznamID`, `datumVytvoreni` | — / — | `chmi-json/1` / `zaznamID`, `datumVytvoreni` | `chmi-json/1` / `zaznamID`, `datumVytvoreni` |
| `in_store` / `legacy_alias` | tak / — | tak / — | tak / — | tak / — |

`first_year` 1887 to najwcześniejszy rok w pełnym listingu `H historical/data/daily/` z 2026-10-18 [V CzHydro §5.1]. Generator offline odrzuca wcześniejsze lata (`details.minimum`), a górnej granicy nie ma (jak §2.1 spec 2026-10-17). Rejestr liczy 17 deskryptorów (13 z §13.4 + 4).

`variable_notes` (tekst w `datasets list`, w metadanych Parquet i w dokumentacji):

| Zmienna | Źródło ČHMÚ | Konwencja | Status |
|---|---|---|---|
| H | `HD`, `unit` `CM` | Średni dobowy stan wody; data = dzień z `DT` (`…T00:00:00Z`) | [V CzHydro §2, §3.1] |
| Q | `QD`, `M3_S` | Średni dobowy przepływ, równy średniej 24 przepływów godzinowych `QH` o etykietach 00–23Z tej daty (doba według etykiet `Z`; UTC czy stały SEČ — §15) | [V CzHydro §6: 72 dni stacji `0-203-1-000400`, średnia różnica 0,00025 m³/s; strefa — U] |
| T | `TD`, `0C` | Średnia dobowa temperatura wody | [V CzHydro §2] |
| P | `SRA`, `TIMEFUNC` `06:00`, `DT` `D T06:00Z` | Suma od terminu porannego dnia D do terminu porannego dnia D+1, przypisana do D | [V CzMeteo §4: 29/29 dni stacji `0-203-0-42106052001`] |
| Tmean | `T`, `TIMEFUNC` `AVG`, `DT` `D T00:00Z` | (T06 + T13 + 2·T20)/4 z terminów UTC dnia D | [V CzMeteo §4: 17/17 dni Cheb] |
| Tmax, Tmin | `TMA`, `TMI`, `TIMEFUNC` `20:00`, `DT` `D T20:00Z` | Ekstremum okresu (D−1 20:00, D 20:00] UTC, przypisane do D | [V CzMeteo §4 dla TMI w Chebie 2026-10-17; TMA analogicznie — I] |

Jednostki źródła są jawne w każdym szeregu hydro (`CM`, `M3_S`, `0C`) [V CzHydro §2], a dla meteo podaje je historical `meta2.json` (SRA mm, T/TMA/TMI °C) [V CzMeteo §2.3].

### 2.3 Pliki i `archive_files`

Gramatyka nazw (ścisłe dopasowanie; inne nazwy w listingu są ignorowane, np. zbiorcze `H_<kod>_OH_1980_1981_…_2000.json` w `measured_water_level/` [V CzHydro §15 p. 4]):

| Zbiór | Ścieżka względem `O` | Wyrażenie nazwy pliku |
|---|---|---|
| hydro | `hydrology/historical/data/daily/H_<kod>_DQ_<RRRR>.json` | `^H_(0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16})_DQ_([0-9]{4})\.json$` |
| meteo | `meteorology/climate/historical_csv/data/daily/precipitation/dly-<kod>-SRA.csv` i `…/temperature/dly-<kod>-{T,TMA,TMI}.csv` | `^dly-(0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16})-(SRA\|T\|TMA\|TMI)\.csv$` |
| listy stacji | `hydrology/historical/metadata/meta1.json`, `meteorology/climate/historical/metadata/meta1.json` | nazwa stała `meta1.json` |

Listing `precipitation/` zawiera też `dly-<kod>-API30.csv`, a `temperature/` — `TMInoc` i `TPM`; łącznie 3 044 i 2 514 plików, wszystkie z mtime 2026-09-04 [V listingi CzMeteo]. Wyrażenie je pomija.

```python
def archive_files(dataset: str, /, *, years: YearsArg | None = None,
                  months: MonthsArg | None = None,
                  params: Iterable[Literal["H", "Q", "T"]] | None = None,
                  stations: Iterable[str] | None = None) -> tuple[ArchiveFile, ...]: ...
```

Reguły (walidacja przed czymkolwiek; błąd `validation_error` z `details.option`):

- `pl.imgw.*`: bez zmian; `years` wymagane jak dotąd; `stations` → błąd, bo archiwa IMGW obejmują cały kraj.
- `cz.chmi.hydro_daily`: `stations` wymagane (niepusta lista bez powtórzeń, każdy kod zgodny z gramatyką ČHMÚ, `details.value` przy błędzie); `years` wymagane (offline nie znamy inwentarza); rok < 1887 → `details.minimum`. Wynik to kandydaci stacja × rok posortowani po (kod, rok); `year` = rok, `year_type="calendar"`, `period_start`/`period_end` = 1 I / 31 XII, `station_code` ustawione.
- `cz.chmi.meteo_daily`: `stations` wymagane; `years` → błąd („pliki ČHMÚ obejmują całą historię stacji”). Wynik: cztery pliki na stację w kolejności SRA, T, TMA, TMI; `year=None`, `year_type="none"`, `period_start`/`period_end` = `None`, `param` = element, `station_code` ustawione.
- `months` i `params` dla `cz.chmi.*` → błąd.
- Listy stacji ČHMÚ zwraca `station_source_files(provider="CHMI")`; `archive_files` odrzuca je jak listy IMGW.
- `url` = `base_url` dostawcy + `server_path`.
- Wynik offline to **kandydaci**. O istnieniu pliku rozstrzyga listing (`check_store`, §4.2) albo odpowiedź 404 (`download_archives`, §4.4). To świadomy wyjątek od IMGW-4 kryt. 2 („nie zwraca kombinacji, których IMGW nie publikuje”): zbiór stacja × rok nie wynika z reguł [V CzHydro §5.2].
- Odwrotne mapowanie `server_path` → `ArchiveFile` (wewnętrzne; test zgodności z `archive_files` dla każdej ścieżki) obsługuje `read_archive`, `StorePlan.from_json` i parsowanie listingu.

## 3. Magazyn: sloty, układ i sidecary

```text
<root>/imgw-store.json                                                           bez zmian
  archives/versions/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2025/2026-05-21_<sha8>/H_0-203-1-001000_DQ_2025.json[.meta.json]
  archives/versions/meteorology/climate/historical_csv/data/daily/precipitation/dly-0-203-0-11573-SRA/2026-09-04_<sha8>/dly-0-203-0-11573-SRA.csv[.meta.json]
  archives/versions/hydrology/historical/metadata/meta1/2026-02-06_<sha8>/meta1.json[.meta.json]
  series/versions/chmi_hydro_daily/<label>_<sha8>/series.json[.meta.json]
                                                  stations/0-203-1-001000.parquet
  stations/versions/<label>_<sha8>/stations.geojson[.meta.json]                    katalog IMGW (bez zmian)
  stations/versions/chmi_stations/<label>_<sha8>/stations.geojson[.meta.json]      katalog ČHMÚ
```

| Rodzaj | Przykład slotu | Katalog slotu |
|---|---|---|
| archiwum hydro | `archive:cz.chmi.hydro_daily:H_0-203-1-001000_DQ_2025.json` | `archives/versions/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2025/` |
| archiwum meteo | `archive:cz.chmi.meteo_daily:precipitation/dly-0-203-0-11573-SRA.csv` | `archives/versions/meteorology/climate/historical_csv/data/daily/precipitation/dly-0-203-0-11573-SRA/` |
| lista stacji | `archive:cz.chmi.hydro_stations:meta1.json` | `archives/versions/hydrology/historical/metadata/meta1/` |
| szereg | `series:cz.chmi.hydro_daily` | `series/versions/chmi_hydro_daily/` |
| plik stacji szeregu (tylko przypięcia) | `series:cz.chmi.meteo_daily:0-203-0-11573` | `series/versions/chmi_meteo_daily/<label>_<sha8>/stations/0-203-0-11573.parquet` |
| katalog stacji | `catalog:cz.chmi.stations` | `stations/versions/chmi_stations/` |

- Gramatyka slotów, etykiety, `relabeled`, `unchanged`, atomowa publikacja, `.incoming/` i reguła bieżącej wersji — bez zmian (§3 i §13.7 spec 2026-10-17), z jednym dodatkowym wierszem `unchanged` dla zbiorów z formą kanoniczną (§3.1). Selektor nie zawiera `:` (kod WIGOS ma tylko cyfry, wielkie litery i `-`).
- Zbiór slotu archiwum = zbiór z najdłuższym pasującym `server_dir` (reguła U05) — rozłączność `server_dir` pilnuje rejestr.
- Pod `stations/versions/` katalog o nazwie `<label>_<sha8>` to wersja katalogu IMGW, a katalog o nazwie slugu zarejestrowanego katalogu dostawcy (`^[a-z][a-z0-9_]*$`; etykiety zaczynają się cyfrą) zawiera wersje tego dostawcy; inne nazwy → `unknown_entry`.
- Czytnik 3.0.0 widzi wpisy ČHMÚ jako `unknown_entry` ze slotem `null`: nie zna `server_dir` ani slugu `chmi_hydro_daily`, a `chmi_stations` nie pasuje do `<label>_<sha8>` [I z reguły U05, §13.7 spec 2026-10-17]. Nie czyta ich błędnie.
- `StoreEntry.provider` = dostawca zbioru slotu; problem bez slotu ma `None`.

**Sidecar archiwum ČHMÚ** (nagłówki HTTP z [V CzHydro §7]; pozostałe wartości umowne):

```json
{"schema":"imgw-meta/1","producer":"imgwtools","producer_version":"3.1.0","dataset":"cz.chmi.hydro_daily","country":"CZ","provider":"CHMI","request":{"server_path":"hydrology/historical/data/daily/H_0-203-1-001000_DQ_2025.json","year":2025,"month":null,"station_code":"0-203-1-001000","param":null},"license":{"id":"CC-BY-4.0","attribution":"Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, licencja CC BY 4.0","url":"https://creativecommons.org/licenses/by/4.0/","terms_url":"https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti"},"downloaded_at":"2026-10-18T18:00:00Z","sha256":"0000000000000000000000000000000000000000000000000000000000000000","size_bytes":21647,"content_sha256":"1111111111111111111111111111111111111111111111111111111111111111","content_form":"chmi-json/1","extra":{"version":{"label":"2026-05-21","label_source":"last_modified"},"period":{"year":2025,"month":null,"param":null,"year_type":"calendar","start":"2025-01-01","end":"2025-12-31","station_code":"0-203-1-001000"},"http":{"url":"https://opendata.chmi.cz/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2025.json","etag":"\"6a0eea27-548f\"","last_modified":"Thu, 21 May 2026 11:19:03 GMT","content_length":21647}}}
```

- `request` = `server_path`, `year`, `month` oraz addytywnie `station_code` i `param`; `extra.period` jak w 3.0.0 plus `station_code`. Dla meteo `year`, `start` i `end` = `null`, `year_type` = `none`, `param` = element.
- `extra.http` pochodzi z odpowiedzi GET (pełny `ETag`, `Last-Modified` z sekundami, `Content-Length`); `extra.version.label` = data `Last-Modified` w UTC (`label_source` `last_modified`), jak dla IMGW.
- `license` = `ProviderDescriptor.license`; `terms_url` jest zapisywane tylko, gdy ustawione, więc sidecary IMGW nie zmieniają bajtów.
- Pola `country` i `provider` pochodzą z rejestru (dziś w `store/writer.py`, `store/series.py` i `store/catalog.py` są stałymi `"PL"` i `"IMGW-PIB"`).
- `content_sha256` i `content_form` (§3.1) — tylko dla zbiorów z `content_form`; sidecar CSV meteo ČHMÚ i sidecary IMGW ich nie mają.

### 3.1 Treść kanoniczna i `content_sha256` (ADR-003 D17)

Bajty archiwum zostają zapisane 1:1, a `sha256` (suma bajtów) pozostaje tożsamością wersji: daje `<sha8>` w `<label>_<sha8>`, klucz par (slot, SHA-256) w manifestach szeregów i wartość pinów. `content_sha256` to suma postaci kanonicznej. Służy wyłącznie do dwóch rozstrzygnięć: czy nowe bajty niosą nową treść (tabela niżej) i czy przypięcie da się odtworzyć treścią (§12). Żaden czytnik, slot ani nazwa katalogu nie używa jej zamiast `sha256`.

**Rejestr form** (`src/imgwtools/store/content.py`, poza `__all__`; zamknięty i tylko dopisywany — inny zestaw pól ulotnych albo inna metoda wymaga nowego identyfikatora, a forma raz wydana się nie zmienia):

```python
@dataclass(frozen=True)
class ContentForm:
    id: str                              # "chmi-json/1"
    method: Literal["json-jcs"]
    volatile_fields: tuple[str, ...]     # klucze najwyższego poziomu usuwane przed sumą

CONTENT_FORMS: Mapping[str, ContentForm] = {
    "chmi-json/1": ContentForm("chmi-json/1", "json-jcs", ("zaznamID", "datumVytvoreni")),
}
def content_sha256(data: bytes, /, *, form: str) -> str: ...   # IMGWDataError, gdy bajty nie spełniają formy
```

Niezmienniki rejestru (test C02): `content_form` deskryptora jest kluczem `CONTENT_FORMS` albo `None`; `volatile_fields` deskryptora = pola jego formy (puste bez formy); żaden zbiór `pl.imgw.*` ani PMAXTP nie ma formy.

**Metoda `json-jcs`** (dokładnie w tej kolejności):

1. Bajty → tekst: UTF-8 ścisłe; jeden BOM U+FEFF na początku jest usuwany. Błąd dekodowania → błąd formy.
2. Parsowanie JSON (RFC 8259): powtórzony klucz w dowolnym obiekcie, `NaN`, `Infinity`, `-Infinity`, liczba poza zakresem IEEE 754 double i dowolny tekst po wartości głównej → błąd formy. Liczby przyjmują wartość double (jak `JSON.parse`), więc różne zapisy tej samej liczby są równe; publikowane współrzędne (do 8 miejsc) i wartości mieszczą się w double bez straty.
3. Wartość główna musi być obiektem. Z obiektu głównego usuwa się klucze `volatile_fields` formy; brak klucza nie jest błędem (pliki hydro `historical` nie mają koperty). Pozostałe pola koperty (`datovyZdrojID`, `datovyTokID`, `verzeDat`) i całe `data` zostają: zmiana `verzeDat` jest zmianą treści. Pola zagnieżdżone nigdy nie są usuwane.
4. Serializacja według RFC 8785 (JCS): bez białych znaków; klucze każdego obiektu posortowane po jednostkach kodowych UTF-16; kolejność elementów tablic bez zmian (kolejność wierszy jest treścią); napisy z minimalnym escapingiem JCS (`\"`, `\\`, `\b`, `\f`, `\n`, `\r`, `\t`, pozostałe U+0000–U+001F jako `\u00xx` małymi literami, reszta dosłownie, bez `\u` dla znaków spoza ASCII); liczby w zapisie ECMAScript `Number.prototype.toString` (`90.0` → `90`, `1E2` → `100`, `-0` → `0`, `1e21` → `1e+21`, `0.419` → `0.419`).
5. `content_sha256` = SHA-256 bajtów UTF-8 wyniku, 64 małe cyfry hex.

Skutek: kolejność kluczy, odstępy, zapis liczb, escaping napisów i nowe `zaznamID`/`datumVytvoreni` nie zmieniają `content_sha256`; każda zmiana wartości, wiersza, kolejności wierszy albo innego pola — zmienia. Implementacja wyłącznie na bibliotece standardowej (`json.loads` z `object_pairs_hook` wykrywającym powtórzenia i `parse_constant` odrzucającym stałe; własny zapis liczb JCS); rdzeń nadal wymaga tylko `httpx` i `pydantic` (ADR-001 D8).

**Zbiory i źródła z formą:**

| Zbiór albo źródło | `content_form` | Pola ulotne | Uzasadnienie |
|---|---|---|---|
| `cz.chmi.hydro_daily` | `chmi-json/1` | `zaznamID`, `datumVytvoreni` (w plikach nieobecne) | brak koperty [V CzHydro §3.1]; forma chroni przed ponowną serializacją bez zmiany danych (kolejność kluczy, odstępy, `12` / `12.0`) |
| `cz.chmi.hydro_stations`, `cz.chmi.meteo_stations` (`historical/metadata/meta1.json`) | `chmi-json/1` | `zaznamID`, `datumVytvoreni` | każda generacja ma nowe `zaznamID` i `datumVytvoreni`; w parze `meta1-20261016`/`-20261017` różniły się wyłącznie te dwa klucze [V CzHydro §7; CzMeteo §13 p. 2] |
| źródła katalogu bez archiwum: `H now/metadata/meta1.json` (co godzinę), `meta3.json` (codziennie), `C now/metadata/meta1-<RRRRMMDD>.json` | `chmi-json/1` (wpisy `extra.catalog[]`, §7.5) | jw. | ta sama koperta [V CzHydro §7]; tożsamością katalogu nadal jest kanoniczny GeoJSON (§7.2) |
| `cz.chmi.meteo_daily` (CSV) | `None` | — | CSV bez koperty [V CzMeteo §2.2]; brak dowodu, że regeneracja zmienia bajty (pytanie do ČHMÚ, §15); inne bajty = nowa wersja jak w ADR-001 |
| wszystkie `pl.imgw.*`, PMAXTP | `None` | — | ZIP i CSV bez koperty; sidecary IMGW zachowują bajty 3.0.0 |

**Pola sidecara** (`imgw-meta/1`, addytywnie; schemat §11): `content_sha256` (`^[0-9a-f]{64}$`) i `content_form` (niepusty tekst) występują razem albo wcale (`dependentRequired`). `write_archive` zapisuje je wyłącznie dla zbioru z formą — liczone z tych samych bajtów co `sha256`, w tym samym przebiegu — i nigdy nie zapisuje `null`, więc sidecary IMGW nie zmieniają bajtów (jak `terms_url`). Kopia przy `relabeled` przenosi oba pola bez zmian. Brak pól czyta się jako `None` (`Meta.content_sha256`, `Meta.content_form`). Czytnik sprawdza wzorzec i parę pól; nieznany identyfikator formy jest tolerowany (IMGW-13), ale taka wersja porównuje się wyłącznie bajtami.

**Decyzja `write_archive`** — porównanie z **bieżącą** wersją slotu (reguła bieżącej wersji ADR-001; starsza wersja o tej samej treści nie jest brana pod uwagę, jak dla bajtów):

| Bieżąca wersja | `sha256` nowych bajtów | `content_sha256` | Sygnał (`Last-Modified`, `ETag`) | Wynik | Zapis |
|---|---|---|---|---|---|
| brak | — | liczony, gdy zbiór ma formę | — | `created` | nowa wersja |
| jest | = bieżącej | = (wynika z bajtów) | = | `unchanged` | brak |
| jest | = bieżącej | = | ≠ | `relabeled` | kopia bajtów pod nową etykietą (ADR-001 D1) |
| jest | ≠ | = `content_sha256` bieżącej, liczone formą zapisaną w bieżącej wersji | dowolny | `unchanged` + komunikat `content_unchanged` (`info`) | brak; `VersionResult.observed_sha256` = suma nowych bajtów |
| jest | ≠ | ≠, albo zbiór bez formy, albo bieżąca wersja bez pól treści lub z nieznaną formą | dowolny | `created` | nowa wersja (z formą bieżącą rejestru) |

- Treść zbioru z formą niezgodna z formą (krok 1–3) → `IMGWDataError` (`data_error`) z nazwą pliku i miejscem, bez zapisu wersji; pozycja synchronizacji `failed`. To jedyne odstępstwo od zapisu archiwów bez parsowania i dotyczy wyłącznie zbiorów z formą.
- Komunikat `content_unchanged` podaje slot, ścieżkę bieżącej wersji, jej `sha256`, `observed_sha256` i wspólne `content_sha256`; `VersionResult` ma `status="unchanged"`, `path` i `sha256` bieżącej wersji.
- `unchanged` przy innych bajtach nie zapisuje nowego sygnału, bo nie powstaje wersja (magazyn tylko przyrostowy). Dopóki treść się nie zmieni, `check_store` widzi w listingu inny mtime niż w `extra.http` bieżącej wersji i daje `newer`, a każda `sync_store` powtarza HEAD+GET i znów kończy się `unchanged` z komunikatem; dla list stacji to samo robi HEAD w `check_catalog`. Koszt: 2–33 KB na plik hydro i jeden plik listy na rodzinę. Trwały zapis zaobserwowanego sygnału bez wersji danych jest pytaniem do właściciela (§15).

## 4. Inwentarz z listingu, aktualność i synchronizacja

### 4.1 Listing

- Źródło: GET `base_url + server_dir + "/"`; dla meteo — każdy z katalogów `precipitation/` i `temperature/`; raz na wywołanie `check_store` i katalog. Odpowiedź to HTML nginx autoindex z `<pre>` i wierszami `<a href="NAZWA">…</a>   DD-Mon-YYYY HH:MM   ROZMIAR` (dla katalogów rozmiar `-`), bez `ETag`, `Last-Modified` i `Content-Length` (chunked) i bez kompresji [V CzLegal §3–4].
- Nazwa = `href` po dekodowaniu URL, nie tekst wyświetlany: `href` są kodowane [V CzLegal §4], a nginx obcina długie nazwy wyświetlane [I]. Czas = UTC z dokładnością do minuty, zgodny z `Last-Modified` pliku (listing `17:00`, nagłówek `17:00:08 GMT`) [V CzLegal §4]. Rozmiar = dokładna liczba bajtów, zgodna z `Content-Length` [V CzMeteo §6].
- Ignorowane: `../`, katalogi i nazwy spoza wyrażenia zbioru (§2.3).
- Błąd sieci albo HTTP ≠ 200 → wszystkie pozycje zbioru z tego katalogu mają `check_failed` (przy synchronizacji z planu kod `source_unavailable`). HTTP 200 bez żadnego wiersza w oczekiwanym formacie albo pasująca nazwa bez czasu lub rozmiaru → `check_failed` z kodem `data_error` („nieczytelny listing”).
- Rozmiary listingów z 2026-10-18 (bez kompresji): `H historical/data/daily/` 5,27 MB (39 291 plików), `C historical_csv/data/daily/precipitation/` 414 KB, `…/temperature/` 334 KB [V CzLegal §4; listingi CzMeteo].
- Para (mtime z dokładnością do minuty, rozmiar) to dokładnie to, co koduje nginx `ETag`, bez sekund [V CzLegal §3].
- Parser listingu jest jeden: `parse_listing(html, /, *, url) -> tuple[ListingEntry, ...]` (nazwa, czas UTC co do minuty, rozmiar) w `src/imgwtools/_parsing/chmi.py`; korzystają z niego synchronizacja, katalog (`C now/metadata/`) i `find_stations`.

### 4.2 `check_store` dla `cz.chmi.*`

```python
def check_store(root: RootArg, /, *, datasets: Iterable[str], years: YearsArg | None = None,
                months: MonthsArg | None = None, stations: Iterable[str] | None = None,
                plan: PathArg | None = None, on_progress=None, on_notice=None,
                cancel=None) -> StorePlan: ...
def sync_store(root: RootArg, /, *, datasets: Iterable[str] | None = None,
               years: YearsArg | None = None, months: MonthsArg | None = None,
               stations: Iterable[str] | None = None,
               plan: StorePlan | PathArg | None = None, series: bool = True,
               on_progress=None, on_notice=None, cancel=None) -> SyncReport: ...
```

**Walidacja.** Wywołanie obejmuje zbiory jednego rodzaju: `stations` jest wymagane, gdy którykolwiek zbiór to `cz.chmi.*`, i zabronione, gdy którykolwiek to `pl.imgw.*` (mieszanie → `validation_error`, `details.option="stations"`). Kod niezgodny z gramatyką ČHMÚ → `validation_error` z `details.value`. `years`: wymagane dla `pl.imgw.*` (jak dotąd), opcjonalne dla `cz.chmi.hydro_daily`, zabronione dla `cz.chmi.meteo_daily`. `months` dla `cz.chmi.*` → błąd.

**Przebieg** (bez zapisu w `root`, bez HEAD i bez GET treści archiwów):

1. Walidacja i — gdy podano `years` — kandydaci offline z `archive_files`.
2. GET listingu każdego potrzebnego katalogu (§4.1).
3. Dla każdej stacji: pliki listingu pasujące do kodu (i do `years`, jeśli podano).
4. Dla każdego pliku: bieżąca wersja slotu (`current_version`) i status:
   - brak wersji lokalnej → `missing`;
   - wersja bez `extra.http.last_modified` → `unverifiable` („brak porównywalnego sygnału”);
   - `Last-Modified` wersji obcięte do minuty = czas z listingu **i** `size_bytes` = rozmiar z listingu → `current`;
   - w przeciwnym razie → `newer`.
5. Para stacja × rok (albo element) z żądania, której brak w listingu, choć stacja ma w nim inne pliki → `unverifiable` z `error="nieopublikowany"`, jak IMGW (T12): nie jest błędem zadania, synchronizacja daje `unchanged` z `version=None` i nie blokuje szeregów.
6. Stacja bez żadnego pliku zbioru w listingu → jedna akcja `PlanAction(command="store sync", status="unverifiable", detail="stacja <kod>: brak plików zbioru <klucz> u źródła")`, bez pozycji dla każdego roku. Tak samo widać stacje spoza rodziny zbioru (np. kod meteo podany dla hydro).
7. `series_state` (kluczowany slugiem, np. `chmi_hydro_daily`) — jak w 3.0.0.
8. Kolejność pozycji: zbiór (kolejność rejestru), `station_code`, `year`, `param`, `server_path`.

**Pola planu (addytywnie w `imgw-plan/1`):** pozycja ma `station_code`, `signal` (`"listing"` dla ČHMÚ, `"head"` dla IMGW) i `remote_listed_at` (czas z listingu w postaci `YYYY-MM-DDTHH:MMZ`); `content_length` = rozmiar z listingu; `remote_etag` i `remote_last_modified` = `null`. Plan ma `requests` = `{"made": <liczba żądań wykonanych przez sprawdzenie>, "planned": <2 × liczba pozycji newer i missing, czyli HEAD+GET>}`; to samo liczy się dla IMGW. `StorePlan.from_json` przyjmuje plany 3.0.0 bez tych pól.

### 4.3 `sync_store`

- Bez planu wywołuje `check_store` z tymi samymi selektorami (także `stations`). Plan wyklucza `datasets`, `years`, `months` i `stations`.
- Dla pozycji `newer` i `missing`: najpierw HEAD. `Last-Modified` obcięte do minuty ≠ `remote_listed_at`, `Content-Length` ≠ `content_length` albo HEAD 404/410 → `stale_plan`, bez GET. Błąd sieci przy HEAD → `failed` (`source_unavailable`).
- GET → `write_archive` (jedno przejście po bajtach, SHA-256 i — dla zbioru z formą — `content_sha256`, `fsync`, atomowa publikacja) → wynik według tabeli §3.1: `created`, `relabeled` (ta sama suma co bieżąca wersja, inne nagłówki) albo `unchanged` (identyczny sygnał i bajty albo inne bajty o tej samej treści kanonicznej, z komunikatem `content_unchanged`).
- **Masowa ponowna publikacja:** listing pokazuje nowy mtime wszystkich plików → `newer` → HEAD+GET → identyczne bajty → `relabeled` (nowa etykieta, kopia treści), a bajty hydro inne przy tej samej treści kanonicznej → `unchanged` bez wersji; w obu przypadkach szeregi `reused`, bo zbiór par (slot, SHA-256) się nie zmienił. Inne bajty CSV meteo → `created` i nowa budowa szeregu; identyczny `series.json` z nowego manifestu wejść dostaje etykietę `<label>+<8 hex>` (T13 spec 2026-10-17).
- **Poprawka ČHMÚ:** inna treść → `created`, poprzednia wersja nietknięta, szereg budowany od nowa.
- `series=True` buduje szeregi tylko z kompletnego, skutecznie zsynchronizowanego zestawu; pozycje `nieopublikowany` go nie blokują. Anulowanie między plikami — jak w 3.0.0.

### 4.4 `download_archives` (pobieranie płaskie)

`download_archives(dataset, /, *, years=None, months=None, params=None, stations=None, output=…, …)` pobiera kandydatów z `archive_files` do `<output>/<server_path>` przez `.part`, bez listingu (dla małych wyborów GET kandydata jest tańszy niż listing 5,3 MB). Dla `cz.chmi.*` odpowiedź 404/410 daje pozycję o nowym statusie `not_published` (`path=None`, `error="nieopublikowany"`, `error_code=None`); w tabeli statusów §13.6 to sukces pozycji. Inne błędy — jak w ADR-002 (`failed` z kodem).

### 4.5 Ruch sieciowy

- Żądania sekwencyjne z nagłówkiem `User-Agent: imgwtools/<wersja>`; ČHMÚ nie wymaga User-Agenta ani klucza [V CzLegal §2]. Brak opublikowanego limitu i brak 429/503 przy ok. 2–3 żądaniach na sekundę [V CzLegal §2; CzHydro §13]; `robots.txt` → 404 [V]. Brak nagłówków CORS, więc wyłącznie pobieranie po stronie serwera [V].
- Szacunki: sprawdzenie hydro = 1 GET listingu (5,3 MB); pobranie pliku = HEAD+GET (2–33 KB na stację-rok, ok. 11 KB dla samego QD, ok. 21,6 KB dla HD+QD) [V CzHydro §8]. Sprawdzenie meteo = 2 listingi (ok. 0,75 MB); pobranie = 4 pliki na stację (mediany: SRA 1,02 MB, T 1,78 MB, TMA i TMI 0,45 MB; maksimum T 18,4 MB) [V CzMeteo §7].

## 5. Parsery i normalizacja

Wspólne zasady: wartości nigdy nie są uzupełniane, interpolowane ani poprawiane według jakości; brak jednej zmiennej nie zmienia innych; błąd treści → `IMGWDataError` z nazwą pliku i miejscem (ścieżka JSON albo numer wiersza CSV), nigdy pusty wynik.

### 5.1 `parse_chmi_hydro_daily(content: bytes | str, /, *, filename: str) -> Iterator[NormalizedRecord]`

Format [V CzHydro §3.1; schemat `H historical/metadata/H_SCHEMA_DQ.json`]: zwarty JSON `{"objID": <kod>, "tsList": [{"tsConID": …, "unit": …, "tsData": {"type": "DataCollection", "data": {"header": "DT,VAL", "values": [[DT, VAL], …]}}}]}`. Schemat (JSON Schema 2020-12) dopuszcza `tsConID` ∈ {`HD`, `QD`, `TD`, `PD`}, nagłówek `DT,VAL`, wiersze o dokładnie dwóch elementach i wartość typu `number` [V]. Kodowanie UTF-8 bez BOM [V CzHydro §9].

1. Dekodowanie UTF-8 (BOM dopuszczalny); niepoprawny JSON → błąd z pozycją.
2. `objID` = kod z nazwy pliku; rok wiersza = rok z nazwy pliku.
3. Każdy `tsList[i]`: `tsConID` spoza {HD, QD, TD, PD} → błąd (`tsList[i].tsConID`). `PD` (zawiesiny, `G_M3`) jest sprawdzany strukturalnie i pomijany — poza zbiorem. `unit` musi być `CM` dla HD, `M3_S` dla QD i `0C` dla TD [V CzHydro §2].
4. `header` = `DT,VAL`; wiersz ma dwa elementy; `DT` w ISO 8601 z `Z`; data = część daty w UTC, a czas jest ignorowany (HD, QD i TD mają `T00:00:00Z`; PD — głównie `T18:00:00Z`) [V CzHydro §3.1].
5. `VAL`: liczba JSON całkowita albo zmiennoprzecinkowa → `float64` (typy mieszane w jednym szeregu [V CzHydro §9]); `null` → `missing` (nieobserwowane i niezgodne ze schematem, ale wymagane przez IMGW-18); inny typ → błąd.
6. Duplikat (data, zmienna): ta sama wartość → jeden pomiar; różne → błąd.
7. Wynik: jeden `NormalizedRecord` na datę z co najmniej jedną z H, Q, T — `station_code`, `dataset`, `date`, `hydro_year` (XI–X), `period=None`, a w `measurements` wyłącznie zmienne obecne tego dnia (`value` albo `missing` dla `null`).
8. Brak wiersza, brak szeregu w pliku i brak pliku nie dają rekordów; kalendarz ciągły tworzy builder (§6).

Postaci spotykane w danych [V CzHydro §3.1, §5.3–5.4]: plik z samym QD (`…075000_DQ_1990`), H i Q od różnych dni (`…000400_DQ_2021`: HD od 10-20, QD od 10-21), plik zaczynający się 1 listopada (`…001000_DQ_1919`), przerwa QD 123 dni (`…171000_DQ_2002`), HD kończące się 2022-03-30 przy pełnym QD (`…199200_DQ_2022`).

### 5.2 `parse_chmi_meteo_daily(content: bytes | str, /, *, filename: str) -> Iterator[NormalizedRecord]`

Format [V CzMeteo §2.2, §8]: CSV UTF-8 bez BOM, końce linii LF, nagłówek `STATION,ELEMENT,TIMEFUNC,DT,VALUE,FLAG,QUALITY,` (przecinek końcowy daje ósmą, pustą kolumnę), np. `0-203-0-11573,SRA,06:00,1994-01-01T06:00Z,0.2,,0.0,`; `DT` bez sekund; typ `application/octet-stream`. Dane są równe JSON `dly-<kod>.json` (SRA Benešova: 5 022 wiersze, 0 różnic) [V].

1. Dekodowanie UTF-8 (BOM dopuszczalny), moduł `csv`. Nagłówek = dokładnie siedem nazw (plus opcjonalna pusta ósma kolumna); wiersz ma 7 albo 8 kolumn (ósma pusta), inaczej błąd z numerem wiersza.
2. `STATION` = kod z nazwy pliku; `ELEMENT` = element z nazwy pliku.
3. `TIMEFUNC` i czas w `DT`: SRA `06:00` / `T06:00Z`; TMA i TMI `20:00` / `T20:00Z`; T `AVG` / `T00:00Z` → Tmean, a wiersze terminów T (`06:00`, `13:00`, `20:00`) są pomijane; inna kombinacja → błąd. `DT` przyjmuje `HH:MMZ` i `HH:MM:SSZ`; data = część daty.
4. `VALUE` puste → wartość `None`, flaga `missing`; inaczej liczba dziesiętna → `float`; tekst nieliczbowy → błąd.
5. `QUALITY`: liczba całkowita zapisana dziesiętnie (`0.0`…`5.0`) → `int` w `Measurement.quality`; puste → `None`; wartość niecałkowita lub nieliczbowa → błąd. Znaczenie według `meta4` [V CzMeteo §9]: 0 dobra, 1 podejrzana, 2 słaba („zatím nepoužívat”), 3 szacowana, 4 brak, 5 nieznana (dane operacyjne). Jakość nie zmienia wartości ani flagi.
6. `FLAG` → `Measurement.source_flag` dosłownie (puste → `None`). Znane kody SRA według `meta3`: `T` — „Neměřitelné množství” (ślad, wartość 0.0), `M` — suma z deszczomierza ręcznego [V CzMeteo §9]. `meta3` nie jest kompletny (np. `R` przy SCE spoza słownika [V]), więc nieznany kod jest zachowywany bez błędu.
7. Flagi P: puste `VALUE` → `missing`; `0.0` bez `FLAG` → `no_phenomenon` z wartością 0.0 („brak opadu”, 2 378 dni w Benešovie) [V CzMeteo §9]; pozostałe, także ślad `T` → `value`. Flagi Tmean, Tmax, Tmin: puste → `missing`, inaczej `value`. `accumulated` nie występuje: `meta3` nie ma flagi sumy zbiorczej [V], a czy sumy wielodniowe występują w danych — [U].
8. Kolejność wierszy nie jest gwarantowana (JSON: element → blok → VTYPE → data [V CzMeteo §9]; w próbkach CSV wiersze były posortowane [V]); duplikaty jak w §5.1.
9. Jawne wiersze braku wewnątrz bloku są rekordami (`VALUE` puste, `QUALITY 4`; np. 8 034 takie wiersze TMA w Chebie); między blokami nie ma wierszy (Cheb TMA 1920–1960) [V CzMeteo §9, plik `dly-0-20000-0-11406-TMA.csv`].
10. Wynik: rekord na datę wiersza (bez terminów T) z pomiarem zmiennej pliku, z `quality` i `source_flag`.

### 5.3 `parse_chmi_stations(content: bytes | str, /, *, kind: Literal["hydro", "meteo"]) -> Iterator[StationListEntry]` i źródła katalogu

Koperta [V CzHydro §3.3; CzMeteo §2.1]: `{"zaznamID", "datovyZdrojID", "datovyTokID": "Open.Data.Metadata", "datumVytvoreni", "verzeDat", "data": {"type": "DataCollection", "data": {"header": "<kolumny po przecinku>", "values": [[…], …]}}}`. Pola koperty nie wpływają na treść; kolumny lokalizuje się po nazwie z `header`, nie po pozycji.

| Plik | Kolumny używane | Uwagi |
|---|---|---|
| `H now/metadata/meta1.json` (546 stacji; przepisywany co godzinę ok. :01) | `objID`, `STATION_NAME`, `STREAM_NAME`, `GEOGR1` (szerokość), `GEOGR2` (długość), `SPA_TYP`, `SPAH_UNIT`, `DRYH`, `SPA1H`…`SPA4H`, `SPAQ_UNIT`, `DRYQ`, `SPA1Q`…`SPA4Q` | [V CzHydro §3.3, §4, §7] |
| `H now/metadata/meta3.json` (563 stacje; codziennie ok. 02:03) | `objID`, `STATION_NAME`, `STREAM_NAME`, `GEOGR1`, `GEOGR2`, `HLGP4` | 47 kolumn spoza dokumentacji `read_me`; używamy tylko kolumn o nazwach opisanych w `Popis_kodu_historical.pdf` [V CzHydro §3.3] |
| `H historical/metadata/meta1.json` (831 stacji, także zamknięte; ostatnio 2026-02-06) | jak now meta1 oraz `HLGP4` | archiwum `cz.chmi.hydro_stations`; współrzędne z 7 miejscami dziesiętnymi [V próbka] |
| `C now/metadata/meta1-<RRRRMMDD>.json` (760 wierszy, 757 kodów; codziennie ok. 00:01) | `WSI`, `FULL_NAME`, `GEOGR1` (**długość**), `GEOGR2` (**szerokość**), `ELEVATION` | najnowsza data z listingu `C now/metadata/` (serwer trzyma 2 dni) [V CzMeteo §1, §2.3]; trzy kody występują dwukrotnie z różnymi `GH_ID` (np. `0-203-0-41003091001` z położeniami różnymi o ok. 130 m) [V próbka `meta1-20261018.json`] |
| `C historical/metadata/meta1.json` (5 539 wierszy okresów, 1 611 WSI; 2026-02-12) | `WSI`, `BEGIN_DATE`, `END_DATE`, `FULL_NAME`, `GEOGR1` (długość), `GEOGR2` (szerokość), `ELEVATION` | archiwum `cz.chmi.meteo_stations`; `""` = brak (1 wiersz bez szerokości, 3 bez wysokości); 1–8 miejsc dziesiętnych [V CzMeteo §2.3, §8; próbka] |

Liczby czyta się z `parse_float=Decimal`, żeby zachować publikowany zapis dziesiętny (§7.2); `""` i `null` → brak. `parse_chmi_stations` zwraca jeden `StationListEntry` na kod (`provider="CHMI"`; dla meteo nazwa z okresu o najpóźniejszym `BEGIN_DATE`; dla hydro `river` = `STREAM_NAME`, `hydrographic_code` = `HLGP4` jako tekst; `river_order` i `short_code` = `None`). Kod powtórzony w jednym pliku (poza okresami historical meta1 meteo, które są osobnymi wierszami z założenia) → pierwszy wiersz w kolejności pliku i wpis w `problems`, jak dla list IMGW.

## 6. Szeregi i pokrycie

### 6.1 Budowa

- `build_series(root, *, dataset="cz.chmi.…")` ma kontrakt 3.0.0: czyta bieżące wersje wszystkich slotów archiwów zbioru (wszystkie stacje obecne w magazynie), składa stacje w plikach tymczasowych, używa ponownie wersji przy tym samym zbiorze par (slot, SHA-256) i tej samej wersji schematu, publikuje atomowo. Wpis `extra.source_files[]` sidecara szeregu dla wejścia z formą kanoniczną ma addytywne `content_sha256` i `content_form` z sidecara wejścia (piny `input`, §12); szeregi IMGW i CSV meteo ich nie mają, więc bajty sidecarów IMGW się nie zmieniają.
- **Okresy znane per stacja** (ADR-003 D10):
  - `station_year` — suma lat kalendarzowych [1 I, 31 XII] posiadanych archiwów stacji (z `extra.period`), sąsiednie scalone;
  - `station_element` — dla każdego posiadanego pliku stacji przedział od pierwszej do ostatniej daty jego wierszy (także jawnych braków), suma po elementach, sąsiednie scalone.
- **Kalendarz stacji:** każdy dzień od pierwszego do ostatniego rekordu stacji (dowolnej zmiennej zbioru, także jawnego braku); dzień bez rekordu → `missing` dla każdej zmiennej, nigdy wartość wstawiona.
- `periods` zbioru = suma okresów stacji; `year_type` = `calendar`; `hydro_year` (XI–X) liczy builder jak dla każdego zbioru.

### 6.2 Parquet `imgw-series/1`

- Hydro ČHMÚ ma te same kolumny co `pl.imgw.hydro_daily`: `date: date32`, `hydro_year: int32`, `H_value: float64`, `H_flag: dictionary<string>`, `Q_value`, `Q_flag`, `T_value`, `T_flag`.
- Meteo ČHMÚ: `date`, `hydro_year` i dla każdej z P, Tmean, Tmax, Tmin: `<V>_value: float64`, `<V>_flag: dictionary<string>`, `<V>_quality: int8` (nullable), `<V>_source_flag: dictionary<string>` (nullable).
- Metadane schematu: `imgw_schema=imgw-series/1`, `dataset`, `units` (jak dotąd) oraz addytywnie `variable_notes` (kanoniczny JSON).
- Żaden wiersz nie jest odrzucany z powodu jakości; `null` wartości występuje wyłącznie z flagą `missing`.

### 6.3 `series.json`

Jak w 3.0.0, plus addytywne `stations[<kod>].periods` (lista par [początek, koniec]) dla zbiorów z `archive_scope` ≠ `country`. Szeregi IMGW tego pola nie mają, więc ich bajty się nie zmieniają. Klucze `stations` i `file` stosują gramatykę kodów z C01. Przykład (wartości umowne; rok 2005 nieopublikowany):

```json
{"schema":"imgw-series/1","dataset":"cz.chmi.hydro_daily","year_type":"calendar","periods":[["2004-01-01","2004-12-31"],["2006-01-01","2006-12-31"]],"stations":{"0-203-1-900002":{"file":"stations/0-203-1-900002.parquet","sha256":"0000000000000000000000000000000000000000000000000000000000000000","rows":1096,"periods":[["2004-01-01","2004-12-31"],["2006-01-01","2006-12-31"]],"variables":{"H":{"unit":"cm","first":"2004-11-01","last":"2006-12-31","with_value":426,"accumulated":0,"gaps":[]},"Q":{"unit":"m3/s","first":"2004-01-01","last":"2006-12-31","with_value":731,"accumulated":0,"gaps":[]},"T":{"unit":"degC","first":null,"last":null,"with_value":0,"accumulated":0,"gaps":[]}}}}}
```

Rok 2005 ma 365 wierszy `missing` w Parquet, ale nie jest luką, bo leży poza `periods` stacji (jednostki nieznane).

### 6.4 Pokrycie

- `summarize_coverage(records, /, *, dataset, station_periods: Mapping[str, Sequence[tuple[date, date]]] | None = None)`. Dla `archive_scope` ≠ `country` jednostki znane to dni w okresach stacji: z argumentu (builder podaje okresy z §6.1) albo — bez argumentu — wyprowadzone z rekordów (hydro: lata kalendarzowe z dowolnym rekordem stacji; meteo: suma przedziałów [min, max] dat rekordów każdej zmiennej). Dla IMGW bez zmian.
- Luki = maksymalne ciągi znanych dni bez wartości między pierwszą i ostatnią wartością zmiennej; `no_phenomenon` liczy się jako wartość; `accumulated` = 0.
- Przypadki graniczne (testy C05): zero braków; jeden dzień bez wiersza (luka 1 dnia); 29 II 2024; granica 31 X / 1 XI (`hydro_year`); stacja otwarta 1 XI; stacja zamknięta w trakcie zakresu; H krótsze niż Q (wzorzec 1995–X 2004 [I CzHydro §5.3]); rok nieopublikowany między opublikowanymi (nieznany, nie luka); P `no_phenomenon`; blok meteo bez wierszy (luka). „Suma zbiorcza” nie ma odpowiednika u ČHMÚ — test sprawdza `accumulated` = 0.

### 6.5 Odczyt i eksport

- `read_series` zwraca `Measurement(value, flag, quality, source_flag)`.
- `export_series` (CSV): dla meteo ČHMÚ każda zmienna ma kolumny `<V> [<jednostka>]`, `<V>_flag`, `<V>_quality`, `<V>_source_flag`; `attribution_source` = formuła źródła ČHMÚ, `attribution_processed` = `processed_attribution` ČHMÚ (pierwszy wiersz danych, jak IMGW). Pozostałe zasady — §9 (T17) spec 2026-10-17.
- `export_archive` (`store export`) dla archiwów ČHMÚ: nagłówek CSV `station_code,dataset,date,hydro_year,period`, dalej `<V> [<jednostka>],<V>_flag` oraz dla meteo `<V>_quality,<V>_source_flag`; JSONL zawiera nowe pola `Measurement`.
- Komunikat `license_terms` — tekst ČHMÚ (§8).

## 7. Katalog stacji ČHMÚ

### 7.1 Funkcje

```python
def check_catalog(root: RootArg, /, *, provider: str = "IMGW-PIB", user_locations: PathArg | None = None,
                  on_progress=None, on_notice=None, cancel=None) -> StorePlan: ...
def build_catalog(root: RootArg, /, *, provider: str = "IMGW-PIB", user_locations: PathArg | None = None,
                  on_progress=None, on_notice=None, cancel=None) -> CatalogReport: ...   # + CatalogReport.provider
def read_catalog(version: PathArg | None = None, /, *, root: RootArg | None = None,
                 provider: str | None = None) -> tuple[StationFeature, ...]: ...
def read_station_list(root: RootArg, /, *, kind: Literal["hydro", "meteo"],
                      provider: str = "IMGW-PIB") -> tuple[StationListEntry, ...]: ...
```

- Jedno wywołanie `check_catalog`/`build_catalog` = katalog jednego dostawcy, więc typ wyniku się nie zmienia (wartość domyślna `IMGW-PIB` zachowuje zachowanie 3.0.0).
- `read_catalog`: dokładnie jedno z `version` i `root`. Z `root` zwraca bieżące katalogi wszystkich dostawców (albo wskazanego) w kolejności rejestru, każdy posortowany po `station_code`; `StationFeature.provider` pochodzi z sidecara. Bez katalogu dostawcy: przy `provider=None` pomija go, przy jawnym `provider` → `not_found`.
- Katalog dostawcy bierze wyłącznie indeksy szeregów zbiorów tego dostawcy; katalog IMGW zbudowany na magazynie z danymi ČHMÚ jest bajtowo równy katalogowi z magazynu bez nich.
- Plik użytkownika (`station_code,latitude,longitude[,source]`) może zawierać kody obu dostawców: katalog bierze kody swojej gramatyki, kody drugiego dostawcy pomija, a kody niepasujące do żadnej gramatyki trafiają do `problems`.

### 7.2 Źródła, pierwszeństwo i położenie

| Kolejność | Hydro (`source`) | Meteo (`source`) | Archiwizowane | Sygnał w `check_catalog` |
|---|---|---|---|---|
| 1 | `H now/metadata/meta1.json` (`chmi_hydro_now`) | najnowsze `C now/metadata/meta1-<RRRRMMDD>.json` (`chmi_meteo_now`) | nie; `sha256` i `content_sha256` (`chmi-json/1`, §3.1) odpowiedzi w `extra.catalog[]` | `unverifiable` (koperta zmienia się co godzinę albo co dzień; bez ukrytego GET) |
| 2 | `H now/metadata/meta3.json` (`chmi_hydro_meta3`) | — | nie | `unverifiable` |
| 3 | archiwum `cz.chmi.hydro_stations` (`chmi_hydro_stations`) | archiwum `cz.chmi.meteo_stations` (`chmi_meteo_stations`) | tak — `write_archive` przed budową, jak listy IMGW | HEAD (`ETag`, `Last-Modified`) → `current`/`newer`/`missing` |
| 4 | plik użytkownika (`user`) | jak hydro | nie (SHA-256 w sidecarze) | SHA-256 pliku |
| 5 | bieżące indeksy szeregów `cz.chmi.*` (`series`) | jak hydro | — | jak w 3.0.0 |

- Zbiór stacji = suma kodów ze źródeł 1–3 i 5 (wszystkie, także zamknięte i zagraniczne); kody tylko z pliku użytkownika → `problems`. Zależności zbiorów (stan 2026-10-18): wszystkie 803 stacje archiwum dobowego są w historical meta1; 28 stacji historical meta1 nie ma plików dobowych; 41 stacji now meta1 nie ma archiwum dobowego (w tym 10 kodów `CB…`); 251 stacji archiwum kończy się przed 2025 [V CzHydro §4]. W meteo 74 WSI z historical meta1 nie ma pliku dobowego, a 43 czynne stacje mają dane dobowe tylko w `recent` [V CzMeteo §5]. Takie stacje są w katalogu bez szeregów.
- Nazwa, rzeka i progi: pierwsze źródło, które je podaje (1 → 2 → 3). Nazwy różnią się między źródłami dla 69 stacji hydro, np. `0-203-1-381000` „Bystřička pod nádrží” i „VD Bystřička” [V CzHydro §4].
- Położenie: pierwszy poprawny kandydat w kolejności 1 → 2 → 3 → 4; z historical meta1 meteo — wiersz okresu o najpóźniejszym `BEGIN_DATE`. Kolejność `GEOGR1`/`GEOGR2` zależy od rodziny: hydro (szerokość, długość), meteo (długość, szerokość) [V CzHydro §3.3; CzMeteo §2.3, Cheb 12,39 / 50,07]. Zły punkt wyższego źródła nie blokuje poprawnego niższego (jak IMGW).
- Walidacja: `0,0` → `zero`; punkt poza obrysem Czech → `outside_country`; brak współrzędnych we wszystkich źródłach → `none` (wpis zostaje). Obrys: Natural Earth 1:10m Cultural Vectors v5.1.2, Admin 0 – Countries, `ADM0_A3=CZE` (domena publiczna), w wheel jako `src/imgwtools/_data/czechia_border_wgs84.geojson`, z tolerancją `BORDER_TOLERANCE_M` = 1500 m jak dla Polski. Znane stacje zagraniczne: Reykjavik `0-20000-0-04030` (dł. −21,9, szer. 64,1) w now meta1 i „Marambio, Base” w historical meta1 [V CzMeteo §3]; 4 stacje hydro obsługiwane przez urząd Dolnej Austrii — położenie [U].
- Niepewność = max(150 m, połowa kroku zaokrąglenia publikowanego zapisu szerokości i długości w metrach na szerokości stacji), jak w 3.0.0. JSON gubi końcowe zera (np. Doksany dł. `14.17`) [V CzMeteo §13 p. 3], więc to oszacowanie z góry. Hydro historical meta1 ma 7 miejsc dziesiętnych → 150 m [V próbka]; meteo historical meta1 ma 1–8 miejsc [V próbka].
- Rozbieżność źródeł: dla 506 wspólnych stacji now i historical meta1 hydro 6 położeń różni się o ≥ 200 m (najwięcej 1 631 m, `0-203-1-121000` Kosky - Hamr) [V CzHydro §4]; w meteo 37 stacji ma inne bieżące położenie niż ostatni okres historyczny [V CzMeteo §5]. Gdy wybrane położenie i inny poprawny kandydat różnią się o więcej niż większa z ich niepewności, komunikat `location_conflict` (poziom `info`) podaje liczbę i kody stacji; wybór zostaje według pierwszeństwa.
- `active` = kod obecny w źródle 1 w dniu budowy (dla meta3-only i stacji tylko historycznych `false`).
- Błąd źródła (HTTP, JSON, ten sam kod w dwóch rodzinach) → wyjątek (`source_unavailable` albo `data_error`), bez częściowego katalogu — jak w 3.0.0.
- Identyczny kanoniczny GeoJSON → `unchanged` bez nowej wersji, niezależnie od kopert źródeł (IMGW-17 kryt. 3).
- Archiwum listy stacji (źródło 3) ma formę `chmi-json/1`: nowa generacja `meta1.json` z tymi samymi danymi daje w `write_archive` `unchanged` z komunikatem `content_unchanged`, bez nowej wersji listy. Nowy sygnał nie jest zapisywany, więc `check_catalog` pokazuje listę jako `newer`, a `build_catalog` pobiera ją ponownie, dopóki dane się nie zmienią (§3.1).

### 7.3 Pola wpisu

| Właściwość | Hydro ČHMÚ | Meteo ČHMÚ |
|---|---|---|
| `id`, `station_code` | `objID` | `WSI` |
| `kind` | `hydro` | `meteo` |
| `meteo_kind` | `null` | `null` — ČHMÚ nie podaje klasy stacji [V CzMeteo §14] |
| `name` | `STATION_NAME` | `FULL_NAME` |
| `river` | `STREAM_NAME` | `null` |
| `hydrographic_code` | `HLGP4` jako tekst (np. `1-05-02-0720`), puste → `null` (3 stacje) [V CzHydro §2] | `null` |
| `river_order` | `null` | `null` |
| `location_source`, `location_uncertainty_m`, `location_missing_reason` | §7.2 | §7.2 |
| `active` | §7.2 | §7.2 |
| `established_year` | `null` (niepublikowany) | rok najwcześniejszego `BEGIN_DATE` WSI w historical meta1 (np. 1775 dla `0-203-0-11514`) [V CzMeteo §2.3] |
| `gauge_zero_m` | `null` (nie znaleziono w źródłach [U]) | `null` |
| `river_km` | `null` (`RICKM` w meta3 bez opisu [U]) | `null` |
| `elevation_m` | `null` (`WGS_ELE` w meta3 bez opisu [U]) | `ELEVATION` źródła położenia |
| `thresholds` (addytywnie) | obiekt §7.4 albo `null` | właściwość nieobecna |

`HLGP4` to „Hydrologické povodí IV. řádu” w postaci `a-bb-cc-dddd`; `a` = główne dorzecze (1 Łaba, 2 Odra, 4 Dunaj); pełny číslo hydrologického pořadí ma postać `a-bb-cc-dddd-e-ff-gg` [V `H read_me/Popis_kodu_historical.pdf`, `watersheds_attributies.pdf`]. Filtr „z dopływami” po prefiksie pełnych segmentów (np. `1-05`) jest techniczną regułą interfejsu, jak P19 dla IMGW; hierarchię segmentów opisuje ČHMÚ, a zgodność granic dorzeczy z prefiksem to [I].

### 7.4 Progi SPA

Przykład dla Špindlerův Mlýn `0-203-1-001000` z now meta1 [V CzHydro §3.3]:

```json
"thresholds": {"source": "chmi_hydro_now", "type": "H", "H": {"unit": "cm", "drought": 90, "spa1": 165, "spa2": 200, "spa3": 220, "q50": 297}, "Q": {"unit": "m3/s", "drought": 0.419, "spa1": 19.3, "spa2": 39.4, "spa3": 54.5, "q50": 137}}
```

- `type` = `SPA_TYP` — wielkość, według której wyznacza się stopnie SPA (H: 522, Q: 24 stacje w now meta1) [V CzHydro §3.3].
- `drought` = `DRYH`/`DRYQ` („limit stavu sucha”); `spa1`…`spa3` = `SPA1H`…`SPA3H` / `SPA1Q`…`SPA3Q` (1.–3. stopień aktywności powodziowej); `q50` = `SPA4H`/`SPA4Q` („Vodní stav / Průtok úrovně 50letého průtoku”) — stan albo przepływ odpowiadający przepływowi 50-letniemu, **nie** czwarty stopień [V `H read_me/Popis_kodu_historical.pdf`].
- Jednostki `CM` → `cm`, `M3_S` → `m3/s`; liczby jak w źródle; brak → `null` (np. `SPA1H` puste dla 127 z 546 stacji) [V CzHydro §3.3].
- `source` = `chmi_hydro_now` albo `chmi_hydro_stations` (progi różnią się między źródłami [V CzHydro §4]).
- Bez mapowania na stany ostrzegawcze i alarmowe IMGW: polskie odpowiedniki nazw stopni (bdělost, pohotovost, ohrožení) i ich relacja do progów IMGW to [U].

### 7.5 Sidecar katalogu ČHMÚ

`dataset="cz.chmi.stations"`, `country="CZ"`, `provider="CHMI"`, `license` ČHMÚ z `attribution` = formuła źródła + „. ” + `processed_attribution` (katalog jest postacią przetworzoną; CC BY wymaga oznaczenia zmian), `extra.derived="catalog"`, `extra.catalog[]` = `{source, url, file, fetched_at, count, sha256}` dla `chmi_hydro_now`, `chmi_hydro_meta3`, `chmi_hydro_stations` (ścieżka wersji archiwum), `chmi_meteo_now`, `chmi_meteo_stations`, `user` (z `available`) i po jednym wpisie `series` na zbiór ČHMÚ z wersją szeregu. Wpisy pięciu źródeł `chmi_*` mają addytywne `content_sha256` i `content_form` (`chmi-json/1`; dla archiwum — z jego sidecara). Kody komunikatów: `license_terms` (§8), `location_rejected`, `location_source`, `location_conflict` (nowy), `series_station`, `station_without_location`, `catalog_problem`, `source_unverifiable`, `leftover_incoming`.

## 8. Licencja, atrybucja i komunikaty

Fakty [V CzLegal §1]: FAQ ČHMÚ — „Otevřená data ČHMÚ můžete využívat bezplatně při respektování licence Creative Commons BY 4.0.”; strona „Vyloučení odpovědnosti a licencování” — „…podléhají licenci Creative Commons 4.0 CC-BY. Dílo smíte sdílet a upravovat za podmínky uvedení původu (zdroje ČHMÚ).”; wszystkie 124 dystrybucje `hydrology/*` i `meteorology/climate/*` w NKOD mają CC BY 4.0, bez ochrony sui generis; ČHMÚ nie publikuje stałej formuły atrybucji (ani czeskiej, ani angielskiej). Zbiory o wysokiej wartości (rozporządzenie UE 2023/138): hydro `historical`, `now`, `recent` i klimat `historical/data/daily`, `now`, `recent`; `historical_csv` nie ma tej flagi, ale ma tę samą licencję [V CzLegal §1.1]. Warstwa GIS stacji z geoportal.gov.cz ma CC BY-NC-ND 4.0 — nie używamy jej [V CzLegal §1].

| Miejsce | Wartość |
|---|---|
| `license.id`, `url`, `terms_url` | `CC-BY-4.0`, `https://creativecommons.org/licenses/by/4.0/`, `https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti` |
| `license.attribution` archiwów i list stacji | „Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, licencja CC BY 4.0” |
| `license.attribution` szeregów i katalogu | formuła źródła + „. ” + „Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)” |
| CSV: `attribution_source`, `attribution_processed` | formuła źródła; formuła przetworzenia (pierwszy wiersz danych, jak IMGW) |
| `on_notice` `license_terms` | „{attribution}. Licencja CC BY 4.0 dopuszcza kopiowanie, zmiany i użycie komercyjne pod warunkiem uznania autorstwa ČHMÚ, podania licencji i oznaczenia zmian.” (`notice` dostawcy) |

Regulamin IMGW-PIB, jego formuły i komunikat o celu użycia nigdy nie dotyczą danych ČHMÚ. Każda operacja dotyczy jednego zbioru albo katalogu jednego dostawcy, więc komunikat wybiera dostawca zbioru.

## 9. API i katalog komend (zmiany wobec §13 spec 2026-10-17)

### 9.1 Podpisy

```python
def providers() -> tuple[ProviderDescriptor, ...]: ...
def get_provider(provider: str, /) -> ProviderDescriptor: ...
def datasets(*, kind=None, provider: str | None = None) -> tuple[DatasetDescriptor, ...]: ...
def archive_files(dataset, /, *, years=None, months=None, params=None, stations=None) -> tuple[ArchiveFile, ...]: ...
def download_archives(dataset, /, *, years=None, months=None, params=None, stations=None, output=..., ...) -> DownloadReport: ...
def find_stations(*, kind=None, query=None, source="live", root=None, provider: str | None = None,
                  timeout=DEFAULT_TIMEOUT) -> tuple[StationListEntry, ...]: ...
def iter_store(root, /, *, kind=None, provider: str | None = None) -> Iterator[StoreEntry]: ...
def check_store(root, /, *, datasets, years=None, months=None, stations=None, plan=None, ...) -> StorePlan: ...
def sync_store(root, /, *, datasets=None, years=None, months=None, stations=None, plan=None, series=True, ...) -> SyncReport: ...
def check_catalog(root, /, *, provider="IMGW-PIB", user_locations=None, ...) -> StorePlan: ...
def build_catalog(root, /, *, provider="IMGW-PIB", user_locations=None, ...) -> CatalogReport: ...
def read_catalog(version=None, /, *, root=None, provider=None) -> tuple[StationFeature, ...]: ...
def read_station_list(root, /, *, kind, provider="IMGW-PIB") -> tuple[StationListEntry, ...]: ...
def summarize_coverage(records, /, *, dataset, station_periods=None) -> list[StationCoverage]: ...
def data_commands(*, provider: str | None = None) -> tuple[DataCommand, ...]: ...
def parse_chmi_hydro_daily(content, /, *, filename) -> Iterator[NormalizedRecord]: ...
def parse_chmi_meteo_daily(content, /, *, filename) -> Iterator[NormalizedRecord]: ...
def parse_chmi_stations(content, /, *, kind) -> Iterator[StationListEntry]: ...
```

Reguła wartości `provider`: funkcje zwracające listy przyjmują `provider=None` = wszyscy dostawcy; funkcje budujące albo czytające jeden obiekt dostawcy (`check_catalog`, `build_catalog`, `read_station_list`) mają domyślnie `IMGW-PIB` (zgodność z 3.0.0). `find_stations` z `source="live"` i dostawcą `CHMI` pobiera `H now/metadata/meta1.json` oraz najnowsze `C now/metadata/meta1-<RRRRMMDD>.json` (listing + GET) i zwraca też współrzędne z tych plików (bez walidacji obrysem); z `source="store"` czyta listy i katalogi z magazynu, a dostawców bez zapisanej listy pomija. Normalizacja `query` (NFKD bez znaków diakrytycznych, casefold) obejmuje czeskie znaki („spindleruv” znajduje „Špindlerův Mlýn”).

Eksport w `imgwtools.__all__` (R7): `ProviderDescriptor`, `providers`, `get_provider`, `STATION_CODE_PATTERN`, `parse_chmi_hydro_daily`, `parse_chmi_meteo_daily`, `parse_chmi_stations`.

### 9.2 Słownik opcji (uzupełnienie §13.2)

| Opcja | Typ | Ograniczenia i normalizacja | CLI | REST | Znaczenie |
|---|---|---|---|---|---|
| `provider` | `choice` | `IMGW-PIB` \| `CHMI`; w komendach listowych brak = wszyscy dostawcy, w `store catalog` domyślnie `IMGW-PIB` (jedna wersja katalogu na wywołanie) | `--provider` | parametr | dostawca |
| `stations` | `list` (`str`) | elementy według gramatyki dostawcy zbioru (w schemacie `STATION_CODE_PATTERN`), bez powtórzeń; w `datasets files\|download` i `store check\|sync` wymagane dla `cz.chmi.*` i zabronione dla `pl.imgw.*` | `--stations`, `-s` | parametr | wiele stacji |
| `station` | `str` | `STATION_CODE_PATTERN`; `current synop` bez zmian (`^[0-9]{5}$`); `current hydro\|meteo` przyjmują wyłącznie kody IMGW | `--station`, `-s` | parametr | jedna stacja |
| `years` | jak w §13.2 | dodatkowo: opcjonalne dla `cz.chmi.hydro_daily` w `store check\|sync` (brak = lata opublikowane), zabronione dla `cz.chmi.meteo_daily` | `--years`, `-y` | parametr | roczniki |

### 9.3 Komendy (uzupełnienie §13.3; razem 36)

| Komenda | Funkcja | REST | Check | Wynik | Zmiana |
|---|---|---|---|---|---|
| `datasets providers` (nowa) | `providers` | `GET /api/v1/datasets/providers` | — | `Page[ProviderDescriptor]` | — |
| `datasets list` | `datasets` | bez zmian | — | `Page[DatasetDescriptor]` | + `provider` |
| `datasets files` | `archive_files` | bez zmian | — | `Page[ArchiveFile]` | + `stations`; `years` wymagane poza `cz.chmi.meteo_daily` |
| `datasets download` | `download_archives` | — | `check_command` | `DownloadReport` (+ status `not_published`) | + `stations` |
| `stations find` | `find_stations` | bez zmian | `check_command` | `Page[StationListEntry]` (+ `provider`) | + `provider` |
| `store info` | `store_info` | bez zmian | — | `StoreInfo` (+ `providers`) | — |
| `store scan` | `iter_store` | bez zmian | — | `Page[StoreEntry]` (+ `provider`) | + `provider` |
| `store check` | `check_store` | bez zmian | sama | `StorePlan` (+ pola §4.2) | + `stations`; `years` warunkowe |
| `store sync` | `sync_store` | bez zmian | `check_store` | `SyncReport` | + `stations`; `plan` wyklucza też `stations` |
| `store catalog` | `build_catalog` | bez zmian | `check_catalog` | `CatalogReport` (+ `provider`) | + `provider=IMGW-PIB` |
| `series *`, `project *` | bez zmian | bez zmian | bez zmian | bez zmian | dopuszczają zbiory `cz.chmi.*` i kody WIGOS |
| `current *`, `pmaxtp *` | bez zmian | bez zmian | bez zmian | bez zmian | wyłącznie IMGW |

Reguły uzupełniające (`validate_command`, publikowane w `command_schema` jako `x-imgw.rules` po polsku):

- `datasets files|download` przyjmują 12 zbiorów archiwalnych (10 IMGW i 2 ČHMÚ; bez list stacji i PMAXTP); `store check|sync` i komendy `series` — 7 zbiorów z `in_store=true` i `time_unit` `day`, `month` albo `half_year`.
- `stations`, `years`, `months` i `params` według §2.3 i §4.2; kod stacji sprawdzany gramatyką dostawcy zbioru.
- `data_commands(provider=…)`: wybory opcji `dataset`/`datasets`/`provider` zawężone do dostawcy; komendy bez żadnego zbioru dostawcy są pominięte (dla `CHMI`: `current …` i `pmaxtp …`). Bez argumentu — pełny katalog.
- CLI i REST powstają z katalogu bez ręcznego kodu (§13.10); `stations` w query REST jako lista po przecinku.
- Web GUI w 3.1 oferuje wyłącznie zbiory IMGW-PIB (`datasets(provider="IMGW-PIB")`); formularz bez pola stacji nie obsłuży zbiorów ČHMÚ. Obsługa ČHMÚ w web to osobna pozycja backlogu.

### 9.4 Typy (uzupełnienie §13.9)

```python
# StoreInfo           + providers: tuple[ProviderDescriptor, ...] = ()
# StoreEntry          + provider: str | None = None
# Meta                + provider: str = "IMGW-PIB"; country: str = "PL"   (z sidecara)
#                     + content_sha256: str | None = None; content_form: str | None = None   (C01; brak w sidecarze = None)
# VersionResult       + observed_sha256: str | None = None   # suma pobranych bajtów, tylko w wierszu `content_unchanged` (§3.1)
# ProjectFile         + content_sha256: str | None = None; content_form: str | None = None   (C01; pin zbioru z formą)
# ProjectReport       tasks: + "content_match"; files[].status: + "restored_by_content" (sukces pozycji w §13.6)
#                     stan pinu w project check|status|verify: + "content_match"
# StationFeature      + provider: str = "IMGW-PIB"
# StationListEntry    + provider: str = "IMGW-PIB"
# Measurement         + quality: int | None = None; source_flag: str | None = None
# PlanItem            + station_code: str | None = None; signal: Literal["head", "listing"] = "head"
#                     + remote_listed_at: str | None = None
# StorePlan           + requests: Mapping[str, int] | None = None        # JSON: {"made": n, "planned": m}
# StationSeriesIndex  + periods: tuple[tuple[date, date], ...] | None = None
# CatalogReport       + provider: str = "IMGW-PIB"
# DownloadItem        status + "not_published"
# ArchiveFile         + station_code: str | None = None
# DatasetDescriptor   + provider, archive_scope, variable_notes, measurement_fields, content_form, volatile_fields; update_signal + "listing"
# License             id: str (C01); + terms_url: str | None = None
```

## 10. Błędy i komunikaty

Rejestr kodów §13.5 pozostaje zamknięty; nie dochodzi żaden kod.

| Sytuacja | Kod (CLI/HTTP) | Gdzie |
|---|---|---|
| Brak lub zbędne `stations`; niedozwolone `years`, `months`, `params`; kod spoza gramatyki dostawcy; nieznany dostawca; mieszanie `pl.imgw.*` i `cz.chmi.*` w jednym wywołaniu z `stations` | `validation_error` (2/400) | `validate_command`, funkcje |
| Błąd sieci, przekroczony czas, HTTP spoza 2xx (poza 404 kandydata w `download_archives`) | `source_unavailable` (5/502); tytuł zmieniony na „Źródło danych niedostępne”, `detail` podaje dostawcę i URL | listing, HEAD, GET, metadane katalogu |
| Nieczytelny listing; JSON lub CSV niezgodny z §5; zła jednostka; `objID`, `STATION` albo `ELEMENT` niezgodne z nazwą pliku; duplikat z inną wartością; data spoza roku pliku; bajty zbioru z formą niezgodne z formą (§3.1: zły UTF-8, powtórzony klucz, `NaN`, wartość główna nie jest obiektem) — wtedy bez zapisu wersji | `data_error` (7/500), z nazwą pliku i miejscem | parsery, listing, `write_archive` |
| Brak katalogu lub listy ČHMÚ przy jawnym `provider` | `not_found` (3/404) | `read_catalog`, `read_station_list` |
| Pozostałe | bez zmian (§13.5) | — |

Statusy pozycji (nie wyjątki): `unverifiable` z `error="nieopublikowany"`; `check_failed` (`source_unavailable` albo `data_error` przy synchronizacji z planu); `stale_plan`; `not_published` (pobieranie płaskie); `restored_by_content` (pozycja `ProjectReport`, sukces) i stan pinu `content_match` (§12). Nowe kody komunikatów: `location_conflict` (`info`), `content_unchanged` (`info`, §3.1), `pin_restored_by_content` (`warning`, §12); `license_terms` niesie tekst dostawcy.

## 11. Zmiany kontraktów `/1` przed 3.0.0 (C01)

| Schemat | Pole | Było (3.0.0 przed tagiem) | Jest |
|---|---|---|---|
| `imgw-meta/1` | `dataset` | `^pl\.imgw\.[a-z_]+$` | `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$` |
| | `country` | `const "PL"` | `^[A-Z]{2}$` |
| | `provider` | `const "IMGW-PIB"` | `string`, `minLength: 1` |
| | `license.id` | `const "IMGW-PIB"` | `string`, `minLength: 1` |
| `imgw-series/1` | `dataset` | `^pl\.imgw\.` | jak w `imgw-meta/1` |
| | klucze `stations` | `^[0-9]{9}$` | `STATION_CODE_PATTERN` |
| | `stations.*.file` | `^stations/[0-9]{9}\.parquet$` | `^stations/([0-9]{9}\|0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16})\.parquet$` |
| `stations.geojson` | `id`, `properties.station_code` | `^[0-9]{9}$` | `STATION_CODE_PATTERN` |
| | `properties.location_source` | `api_hydro`, `api_meteo`, `static`, `user`, `null` | dodatkowo `chmi_hydro_now`, `chmi_hydro_meta3`, `chmi_hydro_stations`, `chmi_meteo_now`, `chmi_meteo_stations` |
| `imgw-project/1` | `files[].station_code` | `^[0-9]{9}$` | `STATION_CODE_PATTERN` |
| | `options.stations` (przez `validate_command`) | `^[0-9]{9}$` | `STATION_CODE_PATTERN` |
| `imgw-commands/1` | `pattern` opcji `station`, `stations` | `^[0-9]{9}$` | `STATION_CODE_PATTERN` |
| `imgw-meta/1` | `content_sha256`, `content_form` (nowe, opcjonalne) | — | `content_sha256`: `^[0-9a-f]{64}$`; `content_form`: `string`, `minLength: 1`; `dependentRequired` w obie strony |
| `imgw-project/1` | `files[].content_sha256`, `files[].content_form` (nowe, opcjonalne) | `additionalProperties: false` bez tych kluczy | jak w `imgw-meta/1`, z `dependentRequired` w obie strony |

- Czytnik po C01: sidecar zbioru znanego rejestrowi musi mieć `country` i `provider` równe wartościom rejestru (inaczej `invalid_meta`); `license.id` jest dowolnym niepustym tekstem; poprawny klucz nieznanego zbioru daje katalog wersji bez slotu → `unknown_entry` (reguła 3.0.0).
- Zapis IMGW bez zmian: te same bajty sidecarów, szeregów, katalogu i manifestów (pola treści są wyłącznie opcjonalne i nigdy nie zapisuje się ich jako `null`). Python: `License.id: str`; jedna stała `STATION_CODE_PATTERN` zastępuje lokalne wyrażenia w `store/reader.py`, `commands.py` i `project.py`; `Meta` i `ProjectFile` mają pola `content_sha256` i `content_form`, a `open_project` zachowuje je przy ponownym zapisie manifestu.
- Czytnik po C01: tylko jedno z pól treści albo `content_sha256` niezgodne ze wzorcem → `invalid_meta` (sidecar) albo `validation_error` (manifest); identyfikator formy nieznany rejestrowi jest tolerowany (§3.1).
- **Wariant awaryjny** (v3.0.0 otagowane przed C01): pliki ČHMÚ zapisuje się jako `imgw-meta/2` i `imgw-series/2`, a manifest z zadaniem ČHMÚ jako `imgw-project/2`, z dokładnie tymi zmianami dziedzin; pliki IMGW zostają przy `/1`; czytniki 3.1 przyjmują `/1` i `/2`, a Archiwista deklaruje obsługę `/2`. C01 staje się wtedy taskiem 3.1 z dodatkowym testem czytnika obu wersji.

## 12. Projekty i odtwarzalność

- Zadanie `imgw-project/1` dotyczy jednego zbioru (`options.dataset`), a więc jednego dostawcy; projekt może łączyć zadania IMGW i ČHMÚ bez nowych kluczy. Kryterium IMGW-19 nr 2 („zadanie ze stacjami IMGW i ČHMÚ”) realizuje projekt z zadaniami obu dostawców.
- `add_project_task` waliduje opcje przez `validate_command` (gramatyka kodów dostawcy zbioru). Wybór obszarem czyta bieżący katalog dostawcy zbioru i przypina jego plik (`catalog`).
- `download_project` synchronizuje potrzebne archiwa: dla ČHMÚ stacje zadania × `years` (brak = lata opublikowane), buduje albo używa ponownie (`reused`) szeregów i przypina pliki.
- Odtworzenie na pustym magazynie działa bez zastrzeżeń, gdy źródło podaje identyczne bajty (`created`; nagrania w testach). Inna treść → pozycja `failed` z tekstem zależnym od dostawcy: „<short_name> udostępnia inną treść <server_path> (SHA-256 …) niż przypięta (…); przypięcia bez zmian, świadome przepięcie: update="upgrade"” (dziś tekst ma stałe „IMGW”).
- **Odtworzenie treścią** (ADR-003 D14, D17) — wyłącznie zbiory z `content_form` (`cz.chmi.hydro_daily`, listy stacji ČHMÚ):
  - Pin archiwum takiego zbioru ma `content_sha256` i `content_form` z sidecara wersji (pin `input` — z `extra.source_files[]` sidecara szeregu, §6.1). Piny IMGW i CSV meteo ich nie mają, więc ich manifesty zachowują bajty.
  - `download_project` (`update="pinned"`), pin archiwum nieobecny w magazynie: GET → `write_archive` (§3.1). Bieżąca wersja slotu pod przypiętą ścieżką z przypiętym `sha256` → `created`. W przeciwnym razie, gdy bieżąca wersja slotu (nowo zapisana albo już istniejąca) ma treść równą pinowi — `content_sha256(bajty, form=pin.content_form)` = `pin.content_sha256` — pozycja ma status `restored_by_content` z `version` = ścieżka wersji równoważnej. Obejmuje to też te same bajty pod inną etykietą (dziś błąd „Identyczne bajty zapisano jako …”, który dla zbiorów bez formy zostaje). Inna treść → `failed` jak wyżej.
  - Szereg odtwarza się, gdy zbiór slotów bieżących wejść = zbiór slotów przypiętych wejść, a każde wejście pasuje bajtami albo treścią. `series.json` nie zawiera sum wejść (T13 spec 2026-10-17), więc te same rekordy dają te same bajty. Po `build_series` plik szeregu i pliki stacji z przypiętym `sha256` pod przypiętą ścieżką → `created`, pod inną ścieżką (inna etykieta z nowych `Last-Modified` wejść) → `restored_by_content`; inny `sha256` → `failed` (`data_error`).
  - Manifest w trybie `pinned` się nie zmienia; `update="upgrade"` przepina na wersje równoważne (`upgraded`). Komunikat `pin_restored_by_content` (poziom `warning`), raz na zadanie, wymienia każdą parę: ścieżkę i `sha256` pinu, ścieżkę i `sha256` wersji równoważnej oraz wspólne `content_sha256`.
  - `check_project`, `project status` i `verify_project`: pin nieobecny pod przypiętą ścieżką, gdy bieżąca wersja jego slotu pasuje treścią (archiwum) albo ma ten sam `sha256` (szereg i plik stacji zbioru z formą) → stan `content_match` zamiast `missing`; `verify_project` liczy przy tym od nowa `sha256` i `content_sha256` wersji równoważnej z jej bajtów. Zadanie, którego piny są `current` albo `content_match` (co najmniej jeden), ma status `content_match`; koperta `ok` z komunikatem `warning`, nigdy cicho jako `current`. Ponowne `download_project` niczego nie pobiera: takie piny są `content_match` offline.
- Fakty: serwer ČHMÚ przechowuje wyłącznie najnowszą wersję pliku; archiwa są przepisywane masowo (2025-07-01) i punktowo (2026-02-06, 6 plików stacji `0-203-1-456505`) [V CzHydro §7; CzMeteo §14]. Czy przepisania zmieniają bajty — [U]. Przypięcie ČHMÚ jest więc odtwarzalne ze źródła tylko do najbliższej zmiany treści (kanonicznej dla zbiorów z formą, bajtów dla CSV meteo); trwałe odtworzenie wymaga kopii magazynu (np. wspólny udział SMB) albo przypiętych katalogów wersji. `check_project` pokazuje zmianę źródła (`newer`) przed pobraniem. Paczka przypięć nie jest częścią tego wydania.

## 13. Fixtury i testy

### 13.1 Zasady

- Dane syntetyczne, małe i bez problemów licencyjnych (ta sama zasada co §12 spec 2026-10-17). Odtwarzają dokładnie formaty źródła — kolejność kluczy, kopertę, nagłówek CSV z przecinkiem końcowym, wiersz listingu nginx, `ETag` `"%x-%x"` zgodny z `Last-Modified` i `Content-Length` — ale nie rzeczywiste dane.
- Kody fikcyjne: w metadanych z 2026-10-18 żaden kod hydro nie zaczyna się od `0-203-1-9`, a żaden kod meteo od `0-203-0-9` ani `0-20000-0-99` [V próbki CzHydro i CzMeteo].
- Pliki źródłowe: `tests/fixtures/store/archives/hydrology/**` i `tests/fixtures/store/archives/meteorology/**` (lustro ścieżek serwera, jak dla IMGW). Nagrania z `base_url` `https://opendata.chmi.cz/`: `tests/fixtures/store/chmi_recordings.json` (aktualność i synchronizacja), `chmi_catalog_recordings.json` (katalog i wyszukiwanie), `chmi_builder_recordings.json` (magazyn testowy). Kopia 1:1 w `src/imgwtools/_data/fixtures/`, pilnowana istniejącym testem.
- Przypadki negatywne parserów (zła jednostka, nieznany `tsConID`, niezgodny `objID`, duplikat z inną wartością, zły `TIMEFUNC`, niecałkowite `QUALITY`, nieczytelny listing) są bajtami w testach, nie plikami fixtur.

### 13.2 Zestaw syntetyczny

| Kod | Rola | Pliki | Co sprawdza |
|---|---|---|---|
| `0-203-1-900001` | hydro pełna | `H_…_DQ_2023.json`, `H_…_DQ_2024.json` | H, Q, T; 29 II 2024; granica 31 X / 1 XI; liczby całkowite i zmiennoprzecinkowe; jeden dzień bez wiersza (luka 1 dnia); PD z `T18:00:00Z` (pomijane); położenie now ≠ historical o > 200 m (`location_conflict`) |
| `0-203-1-900002` | hydro z dziurą | `H_…_DQ_2004.json` (QD cały rok, HD od 1 XI), `H_…_DQ_2006.json`; 2005 nieobecny w listingu | H krótsze niż Q; rok nieopublikowany = nieznany, nie luka (§6.3) |
| `0-203-1-CB900003` | kod alfanumeryczny | tylko now meta1 i meta3 | stacja w katalogu bez szeregu; `HLGP4` z meta3; akcja `unverifiable` w planie |
| `0-203-1-900004` | położenie | now meta1 z `0,0`, historical z poprawnym punktem | pierwszeństwo źródeł i `zero` bez blokowania niższego źródła |
| `0-203-0-90001` | meteo pełna | SRA, T, TMA, TMI | SRA: 0.0 bez flagi, ślad `T`, `M`, QUALITY 3 i 1, puste `VALUE` z QUALITY 4, nieznana flaga `R`; T z `AVG` i terminami 06/13/20; TMA z blokiem bez wierszy (luka); wiersze nieposortowane |
| `0-203-0-90000000002` | meteo tylko opad | SRA | brak T, TMA, TMI → pozycje `nieopublikowany` |
| `0-20000-0-99903` | stacja zagraniczna | tylko metadane meteo (now i historical) | `outside_country`; okresy historyczne z różnymi położeniami; pusty `GEOGR2` w starym okresie |

Metadane: hydro now meta1 (dwie wersje z inną kopertą i tymi samymi danymi → katalog `unchanged`), meta3, historical meta1 (druga generacja z nową kopertą i tymi samymi danymi → archiwum listy `unchanged` z `content_unchanged`); meteo historical meta1 (wiele okresów na WSI) i now meta1 z dwóch dat. Druga serializacja `H_0-203-1-900001_DQ_2023.json` (inna kolejność kluczy, odstępy, `12.0` zamiast `12`, te same wartości) do scenariuszy (8) i (9). Listingi: `daily/` (z `../`, nazwą zbiorczą `H_0-203-1-900001_DQ_2023_2024.json` do zignorowania i plikami fixtur), `precipitation/` i `temperature/` (z plikami API30 i TMInoc do zignorowania), `C now/metadata/` (dwie daty).

Scenariusze nagrań: (1) pierwsza publikacja — `missing` → `created`; (2) masowa ponowna publikacja — te same bajty, nowy mtime → `newer` → `relabeled`, szereg `reused`; (3) poprawka — nowe bajty `900001` 2024 → `created`, nowa wersja szeregu; (4) zmiana po planie — HEAD ≠ listing → `stale_plan`; (5) listing HTTP 500 → `check_failed` (`source_unavailable`), listing bez wierszy → `check_failed` (`data_error`); (6) 404 kandydata w `download_archives` → `not_published`; (7) nowa koperta metadanych bez zmiany danych → katalog `unchanged`; (8) ponowna serializacja bez zmiany danych — druga serializacja `900001` 2023 z nowym mtime → `newer` → HEAD+GET → `unchanged` z `content_unchanged` i `observed_sha256`, bez nowego katalogu, szereg `reused`, a kolejne `check_store` nadal `newer`; (9) odtworzenie treścią — pusty magazyn, nagranie podaje drugą serializację → pin archiwum `restored_by_content`, szereg zbudowany ponownie z tym samym `sha256` pod inną ścieżką → `restored_by_content`, zadanie `content_match`, komunikat `pin_restored_by_content`.

### 13.3 Test na żywo i magazyn testowy

- `tests/live/test_chmi_live.py` (pomijany bez `IMGW_LIVE=1`): listing hydro i meteo, synchronizacja jednego pliku stacji-roku hydro (np. `0-203-1-001000`, 2025) i jednego pliku SRA, katalog ČHMÚ z metadanych na żywo; sprawdza format listingu, nagłówki i zgodność `ETag` z mtime i rozmiarem; raportuje liczbę żądań.
- `imgwtools.testing.build_fixture_store(root, *, variant="complete_pl_cz")` — nowy, addytywny wariant: `complete` (IMGW, bez zmian) + archiwa ČHMÚ w wersjach (pierwsza, `relabeled`, poprawiona), szeregi obu zbiorów ČHMÚ i katalog ČHMÚ, offline z nagrań. Odpowiada na Q13 Archiwisty dla v0.6.

## 14. Kryteria akceptacji ↔ IMGW-15..IMGW-19

| Wymaganie | Kryterium (Archiwista) | Test | Spec |
|---|---|---|---|
| IMGW-15 | zmiany kontraktów tylko addytywne | C01: sidecar, spis, katalog i manifest ČHMÚ spełniają schematy `/1`; zestaw IMGW bez zmian bajtów | §11 |
| IMGW-15 k1 | magazyn z oboma dostawcami przechodzi `iter_store` bez problemów; każdy wpis ma dostawcę; stacje o tym samym kodzie u dwóch dostawców to dwa wpisy | C09: `complete_pl_cz` → `iter_store` bez `problem`, każde `StoreEntry.provider` ∈ {IMGW-PIB, CHMI}; katalogi dostawców to osobne wpisy; para (`provider`, `station_code`) unikalna w `read_catalog(root=…)` | §3, §7 |
| IMGW-15 k2 | magazyn sprzed ČHMÚ czyta się bez zmian | C06: `complete` (3.0.0) → identyczny skan, `provider="IMGW-PIB"` | §3 |
| IMGW-15 k3 | `store_info` wymienia dostawców; filtr `provider` | C06: `store_info().providers`; `iter_store(provider="CHMI")` bez wpisów IMGW | §9 |
| IMGW-16 k1 | `check_store` daje `current`, `newer`, `missing` bez pobierania treści | C04: 1 GET listingu, 0 HEAD i 0 GET archiwów; statusy z listingu; `nieopublikowany` | §4.2 |
| IMGW-16 k2 | nowa wersja tylko przy innej treści; anulowanie bez częściowych wersji | C02 i C04: tabela §3.1 — `relabeled` przy tych samych bajtach i nowym sygnale, `unchanged` z `content_unchanged` przy innych bajtach o tej samej treści kanonicznej, `created` przy innej treści; anulowanie w trakcie → brak wersji w `versions/` | §3.1, §4.3 |
| IMGW-16 k3 | plan podaje stacje, pliki, rozmiary i liczbę zapytań | C04: `station_code`, `server_path`, `content_length`, `requests` | §4.2 |
| IMGW-17 k1 | każda stacja z metadanych ČHMÚ w katalogu, także bez położenia | C06 | §7.2 |
| IMGW-17 k2 | współrzędne i kody bez zaokrągleń i konwersji na liczby | C06: kod WIGOS i `HLGP4` jako tekst; współrzędne równe publikowanemu zapisowi | §7.3 |
| IMGW-17 k3 | ta sama treść metadanych nie tworzy wersji | C06: nowa koperta → katalog `unchanged` i archiwum listy stacji `unchanged` (`content_unchanged`) | §3.1, §7.2 |
| IMGW-18 k1 | szeregi i listy przerw zgodne z ręcznym wyliczeniem dla przypadków granicznych, w obu rodzajach lat | C05: przypadki §6.4; `export_series` z `year_type` `hydrological` i `calendar` | §6 |
| IMGW-18 k2 | wszystkie stacje zbioru w szeregach, także z lukami | C05 | §6.1 |
| IMGW-18 k3 | te same wejścia → `reused` | C05, scenariusz (2) z §13.2 | §6.1 |
| IMGW-19 k1 | polecenie z `format_command` daje w CLI te same wersje i `sha256` co API | C09: parytet Python/CLI/REST dla `store check\|sync`, `series build\|summary\|export`, `store catalog --provider CHMI`, `datasets providers` przy zamrożonym zegarze | §9 |
| IMGW-19 k2 | `download_project` odtwarza projekt z zadaniami IMGW i ČHMÚ na pustym magazynie z identycznymi `sha256` | C08: identyczne bajty → `created` z identycznymi `sha256`; inne bajty o tej samej treści (scenariusz 9) → `restored_by_content` i `content_match` z komunikatem `warning`, przypięcia bez zmian | §12 |
| IMGW-19 k3 | każdy sidecar i eksport ČHMÚ ma CC BY 4.0 i atrybucję ČHMÚ | C04, C05, C06; C09: przegląd wszystkich sidecarów i eksportów ČHMÚ w `complete_pl_cz` | §8 |

## 15. Ryzyka i pytania otwarte

| Ryzyko | Skutek | Ograniczenie |
|---|---|---|
| Regeneracja zmienia bajty bez zmiany danych [U] | JSON z formą: `unchanged` bez wersji, ale stały `newer` w `check_store` i powtarzane HEAD+GET do następnej zmiany treści (§3.1); CSV meteo: każda masowa publikacja = nowe wersje i przebudowa szeregów (identyczny `series.json` dostaje etykietę z sumą manifestu, §7 T13 spec 2026-10-17) | koszt ograniczony do wybranych stacji; pomiar przy najbliższej regeneracji (test `live`); trwały zapis sygnału — pytanie do właściciela |
| Nowe pole ulotne w kopercie ČHMÚ (poza `zaznamID`, `datumVytvoreni`) | każda generacja listy stacji to nowa treść i nowa wersja (stan bezpieczny: nic nie ginie) | nowa forma `chmi-json/2` w rejestrze i w deskryptorach; wersje z `chmi-json/1` porównuje się formą zapisaną w nich (§3.1) |
| `historical_csv` nie jest zbiorem o wysokiej wartości [V CzLegal §1.1] | brak gwarancji prawnej ciągłości publikacji | dane CSV = dane JSON [V]; JSON meteo jako slot jest po D17 możliwy bez łamania zasady 1:1 (forma `chmi-json/1` pomija kopertę), ale cztery potrzebne elementy w CSV to 4,36 GB wobec 25,36 GB JSON, mediana na stację 1,59 MB wobec 10,03 MB (§1.1); zmiana tylko jako nowa decyzja |
| Zmiana układu katalogów (był już `recent/data/10min/`, którego nie ma [V CzHydro §1]; PDF klimatu opisuje inne nazwy niż serwer [V CzMeteo §1]) | listing bez pasujących nazw | `check_failed` z `data_error` zamiast cichego zera |
| Listing nie wykrywa przepisania w tej samej minucie z tym samym rozmiarem | przegapiona zmiana do następnej publikacji | akceptowane; tożsamość i tak potwierdza SHA-256 przy pobraniu |
| Opóźniona publikacja roczna (hydro 2025: 2026-05-21 zamiast „do końca kwietnia” [V CzLegal §5]) | rok nieopublikowany w planie | status `nieopublikowany`, bez błędu |
| Czytnik 3.0.0 na magazynie z ČHMÚ | problemy `unknown_entry` | Archiwista v0.6 wymaga IMGWTools ≥ 3.1 |

Pytania otwarte:

- **Właściciel:** zatwierdzenie C01 (dziedziny i pola treści) przed tagiem v3.0.0 (inaczej wariant awaryjny `/2`, §11); identyfikator `CHMI` i statusy z §4.2 — Archiwista zmieniła już tekst IMGW-15 i IMGW-16 (commit `4435cf7`); akceptacja braku danych `recent` w magazynie; czy po `unchanged` przy innych bajtach zostawić stały `newer` w `check_store` (§3.1), czy dodać trwały zapis zaobserwowanego sygnału bez wersji danych (nowy element układu slotu, wyłącznie dla zbiorów z formą).
- **ČHMÚ** (chmi@chmi.cz):
  - czy znaczniki czasu `historical` są w UTC czy w stałym SEČ i jak zdefiniowana jest doba HD i QD (PDF hydro: „datum a čas [SEČ a SELČ]”; dane `now`/`recent` są w UTC [V CzHydro §9]; dane historyczne nie mają artefaktów zmiany czasu [V], ale UTC vs SEČ — [U]);
  - oficjalny rok hydrologiczny (pierwsze pliki stacji zaczynają się 1 listopada [V], XI–X — [I]);
  - czy regeneracje zachowują bajty i czy istnieje rejestr korekt;
  - ciągłość i deterministyczność `historical_csv`;
  - znaczenie `WGS_ELE`, `RICKM`, `HA`, `QA`, `CEVT`, `PRF_ID` i czy publikowana jest rzędna zera wodowskazu;
  - pełny słownik `FLAG` i przesunięcie 20 minut sum opadu stacji automatycznych (05:40Z);
  - czy w plikach `historical` hydro mogą wystąpić `null` albo kody braku (sprawdzono 64 z ok. 167 tys. plików).
- **Archiwista:** użycie `stations[<kod>].periods` w etykietach pokrycia ČHMÚ (rok nieopublikowany = „nieznane”, nie luka); IMGW-16 („Ta sama treść pod nowym sygnałem = `relabeled`”, kryterium 2) — te same bajty → `relabeled`, ta sama treść kanoniczna przy innych bajtach → `unchanged`; IMGW-19 kryterium 2 — status `restored_by_content` i stan pinu `content_match` obok „identycznych `sha256`”; brak pól `content_sha256`/`content_form` czytany jako `null`.

## 16. Plan wdrożenia (C01–C10)

**Zasady pracy:** jak w planie `../plans/2026-10-17-versioned-store.md` — zadania jednej fali mają rozłączne pliki (także testy), w fali pracują najwyżej dwa taski, każdy task pisze tylko własne testy, pełna bramka (`.venv/bin/python -m pytest`, `.venv/bin/ruff check src/ tests/`, `npx -y pyright src/imgwtools/`) raz na końcu (C09). Nazwy, typy, sloty i podpisy są zamrożone w tym dokumencie; rzeczywista sprzeczność → najpierw errata tutaj i w ADR-003, potem kod. Kontrakt-first w obrębie fali: task może użyć podpisu lub typu, który kończy inny task tej samej fali; testy tej ścieżki wykonuje następna fala. Fixtury dodane w `tests/fixtures/store/` task kopiuje 1:1 do `src/imgwtools/_data/fixtures/`. Taski C02–C10 zaczynają się po U16 i opierają wyłącznie na końcowym stanie ADR-002.

| Fala | Taski (równolegle) | Zakres |
|---|---|---|
| C0 (3.0.0, po U14, przed U16 i tagiem) | C01 | otwarte dziedziny kontraktów `/1` |
| C1 (3.1.0, po tagu v3.0.0) | C02, C03 | rejestr dostawców i typy; parsery i pliki syntetyczne |
| C2 | C04, C06 | listing, aktualność i synchronizacja; katalog stacji i odczyt |
| C3 | C05, C07 | szeregi, pokrycie i eksport; katalog komend, wyszukiwanie i web |
| C4 | C08 | projekty i magazyn testowy PL + CZ |
| C5 | C09, C10 | kontrakt IMGW-15..19 i test na żywo; dokumentacja wydania |

### Fala C0 — przed tagiem v3.0.0

**C01 — Otwarte dziedziny kontraktów `/1`.**  
**Pliki (wyłączna własność):** `src/imgwtools/_data/fixtures/contract_schemas.json` i `tests/fixtures/store/contract_schemas.json` (schematy z §11, w tym pola treści `imgw-meta/1` i `files[]` `imgw-project/1`); `src/imgwtools/store/reader.py` (wyłącznie walidacja: `_DATASET`, `_CODE`, `_PARQUET`, pola `country`/`provider`/`license.id`, zgodność z rejestrem dla znanych zbiorów, para `content_sha256`/`content_form`); `src/imgwtools/store/types.py` (wyłącznie `Meta.content_sha256`, `Meta.content_form`); `src/imgwtools/datasets.py` (wyłącznie `License.id: str` i stała `STATION_CODE_PATTERN`); `src/imgwtools/commands.py` (wyłącznie `_STATION` z tej stałej); `src/imgwtools/project.py` (wyłącznie `_STATION` oraz opcjonalne klucze pinu `content_sha256`/`content_form` w `ProjectFile`, walidacji i zapisie manifestu); testy `tests/unit/test_store_reader.py`, `tests/unit/test_project.py`, `tests/unit/test_command_schema.py` (wyłącznie nowe przypadki); noty `[ADR-003]` w §2, §4, §10.1 i §11 spec 2026-10-17 po zakończeniu bieżących edycji §13.  
**Zależy od:** U14; wykonywany przed U16 i tagiem (jeśli tag był wcześniej — wariant awaryjny z §11 w fali C1).  
**Test akceptacji:** sidecar z `dataset` `cz.chmi.hydro_daily`, `country` `CZ`, `provider` `CHMI` i `license.id` `CC-BY-4.0` spełnia schemat `imgw-meta/1`, a `read_meta` go czyta; ten sam sidecar z `content_sha256` i `content_form` `chmi-json/1` spełnia schemat i daje `Meta.content_sha256`, a z tylko jednym z pól albo z `content_sha256` o złym wzorcu → schemat odrzuca i skan daje `invalid_meta`; `series.json` z kluczem `0-203-1-CB900003` i plikiem `stations/0-203-1-CB900003.parquet` przechodzi `read_series_index` (bez pyarrow); manifest z `files[].station_code` w postaci WIGOS przechodzi `open_project`; pin z `content_sha256` i `content_form` przechodzi `open_project` i wraca bez zmian po ponownym zapisie manifestu, a pin z jednym z tych pól → `validation_error`; kody `0-203-1-cb900003` (małe litery) i `12345678` są odrzucane; sidecar zbioru `pl.imgw.*` z `provider` `CHMI` → `invalid_meta`; poprawny sidecar nieznanego zbioru w nieznanym katalogu → `unknown_entry` ze slotem `null`; dotychczasowy zestaw testów bez zmian wyników, a fixtura `complete` (sidecary i manifesty bez pól treści) daje identyczne bajty.

### Fala C1

**C02 — Rejestr dostawców, deskryptory ČHMÚ i typy.**  
**Pliki:** `src/imgwtools/datasets.py` (także `content_form` i `volatile_fields` deskryptorów), `src/imgwtools/store/types.py` (także `VersionResult.observed_sha256`), `src/imgwtools/store/writer.py` (pola `country`, `provider` i `license` z rejestru, `station_code` i `param` w `request`, `station_code` w `extra.period`, `terms_url` tylko gdy ustawione, pola treści i tabela decyzji §3.1, komunikat `content_unchanged`); utwórz `src/imgwtools/store/content.py` (`ContentForm`, `CONTENT_FORMS`, `content_sha256`), `tests/unit/test_datasets_chmi.py`, `tests/unit/test_store_writer_chmi.py`, `tests/unit/test_store_content.py`; zmodyfikuj `tests/unit/test_store_types.py`.  
**Zależy od:** C01, U16.  
**Test akceptacji:** `providers()` zwraca `IMGW-PIB` i `CHMI` z polami §2.1, a `get_provider("cz.chmi")` = `get_provider("CHMI")`; rejestr ma 17 deskryptorów i spełnia niezmienniki §2.1 i §3.1 (forma tylko dla trzech zbiorów ČHMÚ z §3.1, `volatile_fields` = pola formy); `archive_files("cz.chmi.hydro_daily", stations=[A, B], years="2023-2024")` daje 4 pliki w kolejności (kod, rok) z URL `https://opendata.chmi.cz/hydrology/historical/data/daily/H_<A>_DQ_2023.json`; brak `stations`, `months`, `params` albo rok < 1887 → `validation_error` z `details.option`; meteo: cztery pliki na stację, a `years` → `validation_error`; `stations` dla `pl.imgw.*` → `validation_error`, a wyniki IMGW są równe złotym URL-om U03; odwrotne mapowanie odtwarza każdy `ArchiveFile` z `archive_files`; nowe pola typów mają wartości domyślne, więc obecne konstruktory działają bez zmian; `datasets(provider="CHMI")` zwraca 4 deskryptory; `content_sha256`: inna kolejność kluczy, odstępy, `12`/`12.0`/`1.2E1`, escaping `\u0161`/`š`, BOM i nowe `zaznamID`/`datumVytvoreni` dają tę samą sumę, a inna wartość, inna kolejność wierszy, inne `verzeDat` i zmiana pola zagnieżdżonego o nazwie `zaznamID` — inną; liczby według wektorów RFC 8785 (dodatek B); powtórzony klucz, `NaN`, zły UTF-8 i tablica jako wartość główna → `IMGWDataError`; `write_archive` realizuje każdy z pięciu wierszy tabeli §3.1 (w tym `unchanged` z `observed_sha256` i komunikatem `content_unchanged` bez nowego katalogu, `relabeled` przenoszące pola treści, bieżąca wersja bez pól treści → `created`), a bajty niezgodne z formą → `data_error` bez katalogu w `versions/` i w `.incoming/`; `write_archive` dla pliku ČHMÚ i nagranej odpowiedzi zapisuje sidecar zgodny z przykładem §3, sidecar CSV meteo nie ma pól treści, a sidecary IMGW na fixturze `complete` są bajtowo równe 3.0.0.

**C03 — Parsery ČHMÚ i pliki syntetyczne.**  
**Pliki:** utwórz `src/imgwtools/_parsing/chmi.py` (parsery §5 i `parse_listing` z §4.1); zmodyfikuj `src/imgwtools/parsers.py` (eksport trzech parserów, dyspozycja `normalize_archive`), `src/imgwtools/models.py` (`Measurement.quality`, `Measurement.source_flag`, `StationListEntry.provider`); utwórz `tests/unit/test_parsing_chmi.py`; utwórz pliki §13.2 w `tests/fixtures/store/archives/hydrology/**` i `…/meteorology/**` oraz ich kopie.  
**Zależy od:** C01; z C02 wyłącznie nazwy parserów i zmiennych z §2.2 (kontrakt-first).  
**Test akceptacji:** każdy punkt §5.1–§5.3 ma test na fixturze albo na bajtach w teście: mapowanie HD/QD/TD na H/Q/T z jednostkami, pominięcie PD, `null` → `missing`, data z `DT` bez czasu, rekordy tylko dla obecnych zmiennych; meteo: `no_phenomenon` dla 0.0 bez flagi, `value` i `source_flag="T"` dla śladu, `quality` 3 i 1 zachowane, puste `VALUE` → `missing`, terminy T pominięte, nieznana flaga bez błędu, nieposortowane wiersze; metadane: kolumny po nazwie, `GEOGR1` = szerokość (hydro) i długość (meteo), `Decimal` zachowuje zapis, jeden wpis na WSI z najnowszego okresu; `parse_listing`: nazwa z `href` po dekodowaniu, czas UTC co do minuty, rozmiar w bajtach, katalogi i `../` pominięte, listing bez wierszy → `IMGWDataError`; każdy przypadek negatywny z §13.1 → `IMGWDataError` z nazwą pliku i miejscem; dla IMGW `normalize_archive` bez zmian.

### Fala C2

**C04 — Listing, aktualność i synchronizacja.**  
**Pliki:** `src/imgwtools/store/sync.py`; `src/imgwtools/fetch.py` (wyłącznie `download_archives`); utwórz `tests/unit/test_store_sync_chmi.py`, `tests/unit/test_download_archives_chmi.py`, `tests/fixtures/store/chmi_recordings.json` (+ kopia).  
**Zależy od:** C02, C03.  
**Test akceptacji (nagrania `respx`):** `check_store` dla `cz.chmi.hydro_daily` i dwóch stacji wykonuje jedno GET listingu i zero HEAD i GET archiwów, niczego nie zapisuje; statusy według §4.2 (`current`, `newer`, `missing`, `unverifiable` z `nieopublikowany`, akcja dla stacji bez plików), `years=None` = lata z listingu; HTTP 500 listingu → `check_failed` wszystkich pozycji zbioru, listing bez wierszy → `check_failed` z `data_error`; plan ma `station_code`, `signal`, `remote_listed_at`, `content_length` z listingu i `requests`, a JSON robi round-trip (także plan 3.0.0 bez nowych pól); `sync_store`: HEAD przed GET, różnica wobec planu albo HEAD 404 → `stale_plan` bez GET; scenariusze (1)–(4) i (8) z §13.2 (w (8): pozycja `unchanged`, komunikat `content_unchanged` w kopercie, brak nowego katalogu, szereg `reused`, kolejne `check_store` → `newer`); inne bajty CSV meteo → `created`; sidecar ČHMÚ zgodny z przykładem §3; meteo: cztery pliki na stację, brakujący element → `nieopublikowany`; `download_archives`: 404 → `not_published` i koperta `ok`; zachowanie IMGW i liczba jego żądań bez zmian (istniejące testy).

**C06 — Katalog stacji ČHMÚ, listy stacji i odczyt.**  
**Pliki:** `src/imgwtools/store/catalog.py`; `src/imgwtools/store/reader.py` (`store_info().providers`, `iter_store(provider=)`, `StoreEntry.provider`, katalogi dostawców pod `stations/versions/<slug>/`, `read_catalog(root=, provider=)`, `read_station_list(provider=)`, `read_archive` dla ČHMÚ); utwórz `src/imgwtools/_data/czechia_border_wgs84.geojson`, `tests/unit/test_store_catalog_chmi.py`, `tests/unit/test_store_reader_chmi.py`, `tests/fixtures/store/chmi_catalog_recordings.json` (+ kopia).  
**Zależy od:** C02, C03.  
**Test akceptacji:** każda stacja ze źródeł §7.2 jest w katalogu, także bez położenia; pierwszeństwo położenia, nazwy i progów według §7.2; `0,0` → `zero` bez blokowania niższego źródła, stacja zagraniczna → `outside_country`, brak współrzędnych → `none`; niepewność 7 miejsc → 150 m, 2 miejsca → ok. 556 m; `location_conflict` dla `900001`; `HLGP4` jako tekst, a prefiks `1-05` wybiera wyłącznie kody `1-05-…`; `thresholds` z now z `source`, `q50` z `SPA4*`; `active` według źródła 1; nowa koperta przy tych samych danych → katalog `unchanged`, a archiwum historical meta1 z nową kopertą → `unchanged` z `content_unchanged` (bez nowej wersji listy); sidecar `cz.chmi.stations` z `extra.catalog[]` każdego źródła (wpisy `chmi_*` z `content_sha256` równym dla obu kopert now meta1) i licencją ČHMÚ; katalog IMGW na magazynie z danymi ČHMÚ bajtowo równy katalogowi bez nich; `read_catalog(root=R)` zwraca stacje obu dostawców z `provider`, a `provider="CHMI"` — tylko ČHMÚ; `iter_store(provider="CHMI")` bez wpisów IMGW (problemy bez slotu obecne); magazyn `complete` (3.0.0) skanuje się bez problemów z `provider="IMGW-PIB"`; `read_station_list(kind="hydro", provider="CHMI")` czyta archiwum `meta1.json`.

### Fala C3

**C05 — Szeregi, pokrycie per stacja i eksport.**  
**Pliki:** `src/imgwtools/store/series.py`, `src/imgwtools/coverage.py`, `src/imgwtools/store/export.py`, `src/imgwtools/store/reader.py` (wyłącznie `read_series_index`, `read_series`, `export_archive` w zakresie nowych pól); utwórz `tests/unit/test_store_series_chmi.py`, `tests/unit/test_coverage_chmi.py`, `tests/unit/test_store_export_chmi.py`.  
**Zależy od:** C04, C06.  
**Test akceptacji:** na magazynie z fixtur ČHMÚ `build_series` tworzy wersję w `series/versions/chmi_hydro_daily/` i `chmi_meteo_daily/` z Parquet każdej stacji i `stations[<kod>].periods`; kalendarz ciągły i przypadki graniczne §6.4 zgodne z ręcznym wyliczeniem (przykład §6.3 dosłownie dla `900002`); kolumny `<V>_quality` i `<V>_source_flag` tylko dla meteo; `hydro_year` poprawny na granicy XI; drugie wywołanie → `reused` bez zapisu; `extra.source_files[]` sidecara `chmi_hydro_daily` ma `content_sha256` i `content_form` każdego wejścia, a `chmi_meteo_daily` — nie; `summarize_coverage` z `station_periods` i bez nich daje to samo pokrycie co spis; `export_series` ma kolumny jakości i atrybucję ČHMÚ (źródło i przetworzenie) w pierwszym wierszu, a rok poprawny w `hydrological` i `calendar`; `read_series` zwraca `quality` i `source_flag`; szeregi i eksport IMGW na fixturze `complete` bajtowo równe 3.0.0.

**C07 — Katalog komend, wyszukiwanie stacji i web.**  
**Pliki:** `src/imgwtools/commands.py`, `src/imgwtools/stations.py`, `src/imgwtools/exceptions.py` (tytuł `source_unavailable`), `src/imgwtools/web/app.py` (filtr zbiorów IMGW-PIB), `src/imgwtools/__init__.py` (eksporty §9.1); utwórz `tests/unit/test_commands_chmi.py`, `tests/unit/test_stations_chmi.py`; zmodyfikuj `tests/unit/test_web_app.py` (wyłącznie lista zbiorów w formularzu).  
**Zależy od:** C04, C06; z C05 wyłącznie podpisy.  
**Test akceptacji:** katalog ma 36 komend, a `datasets providers` zwraca dwóch dostawców; `validate_command` stosuje reguły §9.2–§9.3 (`stations` wymagane i zabronione, `years` dla meteo, nieznany dostawca, kod spoza gramatyki dostawcy zbioru → `validation_error` z `details.option`); `format_command` → ponowne sparsowanie → `validate_command` daje identyczne opcje dla przykładów ČHMÚ każdej zmienionej komendy; `command_schema` publikuje `provider`, `stations` z wzorcem i reguły; `data_commands(provider="CHMI")` nie zawiera `current …` ani `pmaxtp …`, a wybory zbiorów to `cz.chmi.*`; `find_stations(provider="CHMI", query="spindleruv")` na nagraniu znajduje „Špindlerův Mlýn” z `provider="CHMI"`, a `source="store"` czyta katalog ČHMÚ; tytuł `source_unavailable` = „Źródło danych niedostępne”; formularz web oferuje wyłącznie zbiory IMGW-PIB.

### Fala C4

**C08 — Projekty i magazyn testowy PL + CZ.**  
**Pliki:** `src/imgwtools/project.py` (teksty z nazwą dostawcy, synchronizacja stacji zadań ČHMÚ, piny z polami treści, odtworzenie treścią §12: `restored_by_content`, `content_match`, `pin_restored_by_content`), `src/imgwtools/testing.py` (wariant `complete_pl_cz`); utwórz `tests/fixtures/store/chmi_builder_recordings.json` (+ kopia), `tests/unit/test_project_chmi.py`, `tests/unit/test_fixture_builder_chmi.py`.  
**Zależy od:** C04–C07.  
**Test akceptacji:** projekt z zadaniem IMGW i zadaniem ČHMÚ przechodzi init → add → check → download → status → verify; piny wejść `cz.chmi.hydro_daily` mają `content_sha256` i `content_form`, a piny IMGW i CSV meteo — nie (manifest zadania IMGW bajtowo jak w 3.0.0); `download_project` na pustym magazynie odtwarza oba zadania z identycznymi `sha256`; scenariusz (9) z §13.2: pin archiwum i piny szeregu `restored_by_content`, zadanie `content_match`, komunikat `pin_restored_by_content` z obiema ścieżkami i sumami, manifest bez zmian, `verify_project` → `content_match` po przeliczeniu sum, drugie `download_project` bez żadnego żądania, `update="upgrade"` → `upgraded` i piny wersji równoważnych; te same bajty pod inną etykietą w zbiorze z formą → `restored_by_content`, w zbiorze IMGW → `failed` jak w 3.0.0; nagranie z inną treścią pliku ČHMÚ → pozycja `failed` z tekstem „ČHMÚ udostępnia inną treść …”, przypięcia bez zmian; `build_fixture_store(variant="complete_pl_cz")` buduje offline magazyn z §13.3, a `variant="complete"` daje bajty identyczne z 3.0.0.

### Fala C5

**C09 — Kontrakt IMGW-15..19 i test na żywo.**  
**Pliki:** utwórz `tests/contract/test_chmi_contract.py` i `tests/live/test_chmi_live.py`; na czas fali wyłączna własność `src/**` i `tests/**` do napraw (C10 zmienia wyłącznie dokumentację).  
**Zależy od:** C01–C08.  
**Test akceptacji:** każdy wiersz §14 jest testem na `complete_pl_cz` i nagraniach; parytet Python/CLI/REST z §14 (koperty równe po kanonicznym zrzucie, te same `sha256` przy zamrożonym zegarze); zero ruchu sieciowego poza nagraniami; pełna bramka raz bez błędów; `IMGW_LIVE=1 .venv/bin/python -m pytest tests/live/test_chmi_live.py` przechodzi na serwerach ČHMÚ i raportuje liczbę żądań; każde znalezisko na żywo naprawione z testem offline.

**C10 — Dokumentacja wydania 3.1.0.**  
**Pliki:** `docs/CHANGELOG.md`, `README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md` (status ADR-003 i datowane erraty ADR-001 i ADR-002 według sekcji „Wpływ”), `docs/superpowers/specs/2026-10-17-versioned-store-design.md` (noty `[ADR-003]` w §13.2–§13.7).  
**Zależy od:** C09.  
**Test akceptacji:** CHANGELOG 3.1.0 w „Dodane” obejmuje każdą zmianę z §9 i §11; tabele komend w README i CLAUDE.md zgadzają się z wynikiem `imgw commands schema` (jednorazowy skrypt, bez trwałego testu); każdy przykład ČHMÚ z README uruchomiony raz offline na `complete_pl_cz` daje opisany wynik; historyczne wpisy ADR bez przeredagowania.
