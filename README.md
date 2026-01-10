# IMGWTools - Narzędzie do pobierania danych IMGW

Narzędzie do pobierania danych publicznych z Instytutu Meteorologii i Gospodarki Wodnej (IMGW-PIB). Dane pochodzą z serwisu [IMGW Dane Publiczne](https://danepubliczne.imgw.pl/).

Obsługuje również dane z modeli probabilistycznych opadów maksymalnych (PMAXTP) z serwisu [IMGW Klimat](https://klimat.imgw.pl/opady-maksymalne/).

---

## Funkcjonalności

1. **Trzy interfejsy dostępu**:
   - **CLI** - narzędzie linii poleceń do pobierania danych
   - **REST API** - FastAPI z dokumentacją OpenAPI/Swagger
   - **Web GUI** - interfejs webowy z mapą interaktywną

2. **Pobieranie danych**:
   - Aktualne dane meteorologiczne i hydrologiczne przez API IMGW
   - Historyczne dane archiwalne (ZIP/CSV)
   - Ostrzeżenia hydrologiczne i meteorologiczne
   - Dane PMAXTP (opady maksymalne prawdopodobne)

3. **Kluczowa zasada**:
   - Dane NIE są przechowywane na serwerze
   - Generowane są bezpośrednie linki do serwerów IMGW

---

## Instalacja

```bash
# Klonowanie repozytorium
git clone https://github.com/Daldek/IMGWTools.git
cd IMGWTools

# Utworzenie środowiska wirtualnego
python3 -m venv .venv
source .venv/bin/activate

# Instalacja pakietu
pip install -e ".[dev]"
```

---

## Szybki start

### CLI

```bash
# Uruchom serwer API
imgw server --reload

# Pobierz dane hydrologiczne
imgw fetch hydro -i dobowe -y 2023

# Pobierz dane meteorologiczne
imgw fetch meteo -i miesieczne -s synop -y 2020-2023

# Pobierz aktualne dane z API
imgw fetch current hydro

# Pobierz dane PMAXTP
imgw fetch pmaxtp --lat 52.23 --lon 21.01

# Lista stacji
imgw list stations --type hydro
```

### REST API

Po uruchomieniu serwera (`imgw server`):
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Przykłady:
```bash
# Aktualne dane hydrologiczne
curl http://localhost:8000/api/v1/hydro/current

# Generuj URL do pobrania danych
curl "http://localhost:8000/api/v1/download/url?data_type=hydro&interval=dobowe&year=2023"
```

### Web GUI

Po uruchomieniu serwera dostępne pod http://localhost:8000:
- `/` - Dashboard
- `/download` - Formularze pobierania danych
- `/stations` - Lista stacji
- `/map` - Mapa interaktywna

---

## Struktura danych IMGW

### Dane hydrologiczne (1951-obecnie)
- `dobowe`: pliki miesięczne (przed 2023) lub roczne (od 2023)
- `miesieczne`: pliki roczne
- `polroczne_i_roczne`: pliki roczne z parametrami T, Q, H

### Dane meteorologiczne (1951-obecnie)
- **1951-2000**: foldery 5-letnie, pliki roczne
- **2001+**: foldery roczne, pliki miesięczne
- Podtypy: klimat, opad, synop

---

## Struktura projektu

```
src/imgwtools/
├── api/          # REST API (FastAPI)
├── cli/          # Narzędzie CLI (Typer)
├── core/         # Logika biznesowa
│   └── url_builder.py  # Generowanie URL-i
├── web/          # Web GUI (HTMX + Jinja2)
└── config.py     # Konfiguracja

data/             # Metadane (listy stacji, opisy formatów)
docker/           # Konfiguracja Docker
tests/            # Testy
```

---

## Docker

```bash
cd docker
docker-compose up -d
```

---

## Dokumentacja

- `CLAUDE.md` - Instrukcje dla Claude Code
- `ARCHITECTURE.md` - Architektura systemu
- `PRD.md` - Wymagania produktu

---

## Problemy i wsparcie

Zgłoś problemy w sekcji [Issues](https://github.com/Daldek/IMGWTools/issues).

---

## Licencja

Projekt udostępniony na licencji MIT. Szczegóły w pliku `LICENSE`.

---

## Autor

- [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/)
