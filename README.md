# IMGWTools - Narzędzie do pobierania danych IMGW i ČHMÚ

Biblioteka Python i narzędzia do pobierania danych publicznych z Instytutu Meteorologii i Gospodarki Wodnej (IMGW-PIB), a od 3.0.0 także z Czeskiego Instytutu Hydrometeorologicznego (Český hydrometeorologický ústav, ČHMÚ). Dane pochodzą z serwisów [IMGW Dane Publiczne](https://danepubliczne.imgw.pl/) i [ČHMÚ Open Data](https://opendata.chmi.cz/).

Obsługuje również dane z modeli probabilistycznych opadów maksymalnych (PMAXTP) z serwisu [IMGW Klimat](https://klimat.imgw.pl/opady-maksymalne/).

---

## Funkcjonalności

- **Biblioteka Python** - `pip install imgwtools` do integracji z innymi projektami
- **CLI** - `imgw`, komendy generowane z katalogu komend
- **REST API** - FastAPI z dokumentacją OpenAPI/Swagger, trasy generowane z tego samego katalogu
- **Serwer MCP** - `imgw mcp` (dodatek `imgwtools[mcp]`) i punkt `/mcp` serwera REST: komendy katalogu jako narzędzia dla agentów AI, domyślnie bez zapisu
- **Web GUI** - formularze pobierania, wyszukiwarka stacji i mapa interaktywna (dane IMGW-PIB)

Od 3.0.0 wszystkie interfejsy korzystają z jednego katalogu 30 komend (`imgw commands list`, `imgw commands schema`): ta sama nazwa opcji w Pythonie, CLI (`--nazwa-opcji`), REST (parametr albo pole JSON) i MCP (argument narzędzia), ta sama walidacja, jedna koperta wyniku `imgw-result/1` i jeden rejestr kodów błędów (`ERROR_CODES`). Wynik maszynowy (koperta, błędy, powiadomienia, opisy katalogu, przewodnik dla agentów AI, serwer MCP) jest po angielsku; polskie teksty dostaje się na prośbę (`--lang pl`, `Accept-Language: pl`), a pomoc i linie CLI dla człowieka są po polsku (`IMGW_LANG=en` przełącza je na angielski). Przewodnik dla agentów AI: [`AGENTS.md`](https://github.com/Daldek/IMGWTools/blob/master/AGENTS.md) i [`llms.txt`](https://github.com/Daldek/IMGWTools/blob/master/llms.txt).

**Obsługiwane dane:**
- Aktualne dane hydrologiczne, meteorologiczne i synoptyczne przez API IMGW
- Historyczne dane archiwalne IMGW-PIB (ZIP/CSV) i ČHMÚ (JSON/CSV per stacja) — rejestr 17 zbiorów dwóch dostawców (`pl.imgw.*`, `cz.chmi.*`)
- Ostrzeżenia hydrologiczne i meteorologiczne
- Dane PMAXTP (opady maksymalne prawdopodobne)
- Listy stacji (wyszukiwanie IMGW-PIB i ČHMÚ) i stany wody stacji hydro IMGW ze współrzędnymi

**Kluczowa zasada:** serwer HTTP niczego nie zapisuje, dopóki administrator nie ustawi `IMGW_ROOT` i nie włączy zapisu; generuje bezpośrednie linki do serwerów IMGW-PIB i ČHMÚ, a dane bieżące przekazuje na żywo. Komenda zapisująca (CLI, Python) ma dwa sposoby zapisu i nigdy nie pisze do katalogu roboczego: `-o`/`--output-dir` zapisuje same pliki, bez metadanych; `--root` albo `IMGW_ROOT` zapisuje do magazynu wersjonowanego. Bez żadnego z nich zapis idzie do magazynu w katalogu danych użytkownika (`<data_dir>/imgw`, `imgw config show --json` pokazuje korzeń i jego źródło). Pojedynczy plik eksportu: `--output PLIK`.

**Wersjonowany magazyn danych** (opcjonalny, od 3.0.0):
- niezmienne wersje archiwów IMGW-PIB i ČHMÚ 1:1 z sumami SHA-256, nagłówkami HTTP i licencją w sidecarze `*.meta.json`,
- sprawdzanie aktualności bez pobierania (IMGW-PIB: listing + `HEAD`, ČHMÚ: jeden listing katalogu serwera) i plan `imgw-plan/1`,
- szeregi stacji w Parquet, katalogi stacji `stations.geojson` obu dostawców, komórki PMAXTP, eksport CSV/JSONL,
- komenda, która pobiera zapisaną wersję jeszcze raz, odtwarzana z jej sidecara (`command_for_version`, dla pinów projektów Archiwisty),
- czytelny offline z dysku lokalnego lub udziału sieciowego, bez bazy danych.

---

## Instalacja

```bash
# Tylko biblioteka (minimalne zależności: httpx, pydantic, pydantic-settings, platformdirs)
pip install imgwtools

# Z CLI
pip install imgwtools[cli]

# Z REST API
pip install imgwtools[api]

# Z magazynem wersjonowanym i szeregami Parquet (pyarrow)
pip install imgwtools[store]

# Z eksportem do DataFrame (PMaXTPData.to_dataframe)
pip install imgwtools[pandas]

# Z serwerem MCP dla agentów AI (imgw mcp; zawiera CLI)
pip install imgwtools[mcp]

# Pełna instalacja (CLI + API + MCP + magazyn + pandas)
pip install imgwtools[full]

# Dla deweloperów (z repozytorium; uv, środowisko z uv.lock)
git clone https://github.com/Daldek/IMGWTools.git
cd IMGWTools
uv sync --locked
```

Zapis do magazynu wersjonowanego wymaga systemu plików z dowiązaniami twardymi — tak jak magazyn Kartografa (jego ADR-036). Linux, macOS i Windows (ext4, APFS, NTFS) oraz udział SMB obsługujący dowiązania twarde działają; na FAT/exFAT, części NAS i FUSE oraz na udziale SMB zamontowanym w macOS `store init` i każdy zapis kończą się błędem `conflict` (`details.reason="not_atomic"`). Odczyt magazynu dowiązań nie wymaga. Zapis zwykłych plików (`--output-dir`, `--output`) dowiązań nie używa i działa także na FAT/exFAT i SMB.

---

## Szybki start

Pełne przewodniki po każdym interfejsie: [docs/USAGE.md](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md).

### Python

```python
from imgwtools import fetch_pmaxtp

# Pobierz dane dla Warszawy (method: "POT" — domyślnie — albo "AMP")
result = fetch_pmaxtp(52.23, 21.01, method="POT")
precip = result.data.get_precipitation(15, 50)
print(f"Opad 15-min, p=50%: {precip} mm")  # opad [mm] dla t=15 min, p=50%
```

### CLI

```bash
imgw datasets list -k hydro
imgw datasets files -d hydro/dobowe -y 2023 -m 1
imgw stations find -k hydro -q wisla --limit 5
imgw current hydro -s 150160180
imgw pmaxtp fetch --lat 52.23 --lon 21.01 --method AMP
imgw datasets download -d hydro/miesieczne -y 2023 -o dane          # zwykłe pliki w katalogu dane/
imgw store sync -d pl.imgw.hydro_monthly -y 2023                    # magazyn wersjonowany w <data_dir>/imgw
```

stdout to jedna linia JSON — koperta `imgw-result/1`; `imgw commands list` wypisuje wszystkie komendy katalogu.

### REST API

```bash
imgw server --reload   # Swagger UI: http://localhost:8000/docs
curl "http://localhost:8000/api/v1/current/hydro?station=150160180"
curl "http://localhost:8000/api/v1/datasets/files?dataset=hydro/dobowe&years=2023&months=1"
```

### Serwer MCP

`imgw mcp` (dodatek `imgwtools[mcp]`) to serwer MCP na stdio; konfiguracja klienta (np. `mcpServers` w pliku ustawień):

```json
{
  "mcpServers": {
    "imgwtools": {
      "command": "imgw",
      "args": ["mcp"],
      "env": {"IMGW_ROOT": "/dane/imgw"}
    }
  }
}
```

Domyślnie bez zapisu (komendy zapisujące zwracają plan); zapis włącza `--allow-writes` i tylko w katalogach z `--allow-dir` (np. `"args": ["mcp", "--allow-writes", "--allow-dir", "/dane/imgw"]`); korzeń poza nimi kończy się błędem `forbidden`.

---

## Agenci AI: AGENTS.md, llms.txt i serwer MCP

Agent (asystent w edytorze, aplikacja czatu, skrypt z modelem językowym) poznaje IMGWTools z jednego źródła zgodnego z kodem:

- [`AGENTS.md`](https://github.com/Daldek/IMGWTools/blob/master/AGENTS.md) — przewodnik: zasada „sprawdź → uruchom → przeczytaj”, odwzorowanie Python/CLI/REST/MCP, koperta i statusy, kody błędów, zbiory obu dostawców z regułami opcji, tabele komend ze skutkami, typowe przepływy (m.in. „opady dobowe ze stacji Poznań”, stacja ČHMÚ) i lista „czego nie robić”;
- [`llms.txt`](https://github.com/Daldek/IMGWTools/blob/master/llms.txt) — skrót według llms.txt v2 z odnośnikami do dokumentacji; ten sam plik serwuje `GET /llms.txt`;
- `imgw commands guide [--format agents|llms] [--lang en|pl] [--output PLIK] [--force]` albo `agent_guide()` w Pythonie — oba pliki wygenerowane na bieżąco (domyślnie po angielsku, `--lang pl` daje polski); `GET /api/v1/commands/guide`.

`AGENTS.md` i `llms.txt` to pliki pochodne katalogu komend, rejestrów i szablonów `src/imgwtools/_data/agents/` — nie edytuje się ich ręcznie (zasady pracy nad kodem: `CLAUDE.md`).

Język, skutki komend i konfiguracja serwera MCP (stdio i `/mcp`): [przewodnik użycia](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#agenci-ai-język-skutki-komend-i-serwer-mcp).

---

## Konfiguracja

Ustawienie pochodzi z pierwszego z: opcji wiersza poleceń, zmiennej `IMGW_<KLUCZ>`, pliku `.env`, zmiennej `NOGAT_<KLUCZ>` (klucze wspólne `data_dir`, `cache_dir`, `lang`), sekcji `[imgw]` i `[nogat]` pliku `nogat.toml`, wartości domyślnej. Najważniejsze zmienne: `IMGW_ROOT` (korzeń magazynu), `IMGW_LANG` (`pl` albo `en`), `IMGW_DATA_DIR`, `IMGW_CACHE_DIR`, `IMGW_REFERENCE_DIR`, `IMGW_MCP_ENABLED`. `imgw config show --json` wypisuje każdy klucz z wartością i źródłem.

Pełna tabela zmiennych, przykład `nogat.toml` i kopia zapasowa magazynu: [Konfiguracja](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#konfiguracja).

---

## Źródła danych

IMGWTools nie dystrybuuje danych IMGW-PIB ani ČHMÚ, a serwer domyślnie ich nie przechowuje — każde pobranie i zapis jest świadomą decyzją użytkownika lub administratora (`--output-dir`, `--output`, `--root`, `IMGW_ROOT`; bez nich CLI i Python zapisują do magazynu w katalogu danych użytkownika). Poniżej zestawienie wykorzystywanych źródeł.

| Źródło | Operator | Warunki korzystania |
|--------|----------|---------------------|
| Archiwum pomiarowo-obserwacyjne — `danepubliczne.imgw.pl/data` (hydro/meteo, ZIP/CSV) | IMGW-PIB | Nieodpłatnie do celów prywatnych i naukowych; dane o wysokiej wartości — w każdym celu; część zastosowań komercyjnych wymaga umowy; obowiązkowa atrybucja. [Regulamin](https://danepubliczne.imgw.pl/regulations)
| API czasu rzeczywistego — `danepubliczne.imgw.pl/api/data` (hydro, synop, meteo, ostrzeżenia) | IMGW-PIB | Jak wyżej ([regulamin](https://danepubliczne.imgw.pl/regulations))
| PMAXTP — `klimat.imgw.pl/opady-maksymalne` | IMGW-PIB | Wskazanie źródła IMGW-PIB (dane ze strony `klimat.imgw.pl/opady-maksymalne`) oraz cytowanie monografii Projektu PMAXTP (red. B. Ozga-Zieliński, IMGW-PIB, Warszawa 2022; monografia: Open Access, CC-BY 4.0); przy danych przetworzonych — adnotacja o przetworzeniu; korzystanie na własne ryzyko. [Regulamin](https://klimat.imgw.pl/opady-maksymalne/) |
| Mapa stacji ze współrzędnymi — `hydro-back.imgw.pl/map/stations/hydrologic` (backend serwisu `hydro.imgw.pl`) | IMGW-PIB | Regulamin serwisu hydro.imgw.pl (akceptacja przez rozpoczęcie korzystania); obowiązuje ogólna zasada wskazania źródła IMGW-PIB. [Regulamin](https://hydro.imgw.pl/#/regulamin) |
| Archiwa i metadane stacji — `opendata.chmi.cz` (`hydrology/historical`, `hydrology/now/metadata`, `meteorology/climate/historical_csv`, `meteorology/climate/historical/metadata`, `meteorology/climate/now/metadata`) | ČHMÚ (Český hydrometeorologický ústav) | Licencja [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): kopiowanie, zmiany i użycie komercyjne pod warunkiem uznania autorstwa ČHMÚ, podania licencji i oznaczenia zmian ([warunki ČHMÚ](https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti)). ČHMÚ nie narzuca formuły; IMGWTools zapisuje „Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, licencja CC BY 4.0”, a przy postaciach przetworzonych dodaje „Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)” |

Obowiązek podania atrybucji przy publikacji wyników spoczywa na użytkowniku pobierającym dane.

### Dane referencyjne (listy stacji, współrzędne, opisy formatów)

Repozytorium **nie zawiera** danych IMGW. Pliki referencyjne używane przez narzędzia (listy stacji, współrzędne, opisy formatów) pobierz jednorazowo — po instalacji pakietu (`pip install -e .`), bez żadnych argumentów:

```bash
python -m imgwtools.reference_data
```

Pobrane pliki trafiają do katalogu danych referencyjnych (`IMGW_REFERENCE_DIR`, domyślnie `<cache_dir>/imgw/reference`, np. `~/.cache/nogat/imgw/reference`; patrz „Konfiguracja”) i pochodzą z IMGW-PIB — podlegają warunkom IMGW-PIB (nie licencji MIT projektu).

Jedyne dołączone do pakietu zbiory geograficzne to obrysy granic Polski `src/imgwtools/_data/poland_border_wgs84.geojson` i Czech `src/imgwtools/_data/czechia_border_wgs84.geojson` (kontrola położeń w katalogach stacji) z Natural Earth 1:10m Admin 0 – Countries v5.1.2 — domena publiczna ([warunki](https://www.naturalearthdata.com/about/terms-of-use/)), nie dane IMGW-PIB ani ČHMÚ.

---

## Dokumentacja

Przewodnik użycia ([docs/USAGE.md](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md)), sekcje:

- [Użycie jako biblioteka Python](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#użycie-jako-biblioteka-python)
- [Szybki start (CLI)](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#szybki-start-cli)
- [REST API](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#rest-api)
- [Web GUI](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#web-gui)
- [Agenci AI: język, skutki komend i serwer MCP](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#agenci-ai-język-skutki-komend-i-serwer-mcp)
- [Struktura danych źródeł](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#struktura-danych-źródeł)
- [Docker](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#docker)
- [Konfiguracja](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#konfiguracja)
- [Magazyn wersjonowany (opcjonalny)](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#magazyn-wersjonowany-opcjonalny)
- [Zmiany w wersji 3.0.0](https://github.com/Daldek/IMGWTools/blob/master/docs/USAGE.md#zmiany-w-wersji-300)

Pozostałe dokumenty:

- [`CLAUDE.md`](https://github.com/Daldek/IMGWTools/blob/master/CLAUDE.md) - Instrukcje dla Claude Code
- [`docs/CODEBASE.md`](https://github.com/Daldek/IMGWTools/blob/master/docs/CODEBASE.md) - Referencja kodu i modułów (publiczne API, katalog komend, formaty danych; [struktura projektu](https://github.com/Daldek/IMGWTools/blob/master/docs/CODEBASE.md#struktura-projektu-z-readme))
- [`docs/TESTING.md`](https://github.com/Daldek/IMGWTools/blob/master/docs/TESTING.md) - Testy: układ, znaczniki, uruchamianie ([instrukcje testów z README](https://github.com/Daldek/IMGWTools/blob/master/docs/TESTING.md#testy-z-readme))
- [`docs/CHANGELOG.md`](https://github.com/Daldek/IMGWTools/blob/master/docs/CHANGELOG.md) - Historia zmian (w tym BREAKING 3.0.0)
- [`docs/DECISIONS.md`](https://github.com/Daldek/IMGWTools/blob/master/docs/DECISIONS.md) - Rejestr decyzji (ADR-001: magazyn wersjonowany, ADR-002: jeden katalog komend, ADR-003: dostawca ČHMÚ, ADR-004: wsparcie agentów AI, ADR-005: środowisko użytkownika, ADR-006: katalog komunikatów, ADR-007: zapis danych, ADR-008: projekty przeniesione do Archiwisty)
- [`docs/ARCHITECTURE.md`](https://github.com/Daldek/IMGWTools/blob/master/docs/ARCHITECTURE.md) - Architektura systemu
- [`docs/PRD.md`](https://github.com/Daldek/IMGWTools/blob/master/docs/PRD.md) - Wymagania produktu
- [`docs/PROGRESS.md`](https://github.com/Daldek/IMGWTools/blob/master/docs/PROGRESS.md) - Stan bieżący, kolejne kroki, pytania otwarte
- [`docs/HISTORY.md`](https://github.com/Daldek/IMGWTools/blob/master/docs/HISTORY.md) - Historia wydań i zamknięte prace
- [`AGENTS.md`](https://github.com/Daldek/IMGWTools/blob/master/AGENTS.md), [`llms.txt`](https://github.com/Daldek/IMGWTools/blob/master/llms.txt) - Przewodnik dla agentów AI (generowany: `imgw commands guide`)

---

## Problemy i wsparcie

Zgłoś problemy w sekcji [Issues](https://github.com/Daldek/IMGWTools/issues).

---

## Licencja

Projekt udostępniony na licencji MIT. Szczegóły w pliku [`LICENSE`](https://github.com/Daldek/IMGWTools/blob/master/LICENSE).

---

## Autor

- [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/)
