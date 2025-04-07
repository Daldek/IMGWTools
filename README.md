# IMGWTools - Narzędzie do pobierania i analizy danych IMGW

Kod napisany w celu ułatwienia pobierania danych publicznych z bazy Instytutu Meteorologii i Gospodarki Wodnej (IMGW-PIB) z wykorzystaniem Pythona. Dane pochodzą z serwisu [IMGW Dane Publiczne](https://danepubliczne.imgw.pl/).

Możliwe jest również pobieranie danych z modeli probabilistycznych opadów maksymalnych o określonym czasie trwania i prawdopodobieństwie - projekt PMAXTP, które są udostępniane w serwisie [IMGW Klimat](https://klimat.imgw.pl/opady-maksymalne/).

---

## Funkcjonalności

1. **Pobieranie danych pomiarowo-obserwacyjnych oraz ostrzeżeń**:
   - Aktualne dane meteorologiczne, hydrologiczne oraz ostrzeżenia przez [API](https://danepubliczne.imgw.pl/pl/apiinfo).
   - Historyczne dane meteorologiczne oraz hydrologiczne dla wybranego okresu i interwału (dobowe, miesięczne, półroczne i roczne).

2. **Modele probabilistyczne opadów maksymalnych (PMAXTP)**:
   - Pobieranie opadów maksymalnych prawdopodobnych dla określonych czasów trwania i prawdopodobieństw.

3. **Analiza hydrologiczna**:
   - Obliczanie podstawowych statystyk hydrologicznych dla wybranych posterunków wodowskazowych (np. przepływy charakterystyczne II°).
   - Wyznaczanie krzywej prawdopodobieństwa przewyższenia przepływu dla rozkładów:
     - Logarytmiczno-normalnego.
     - GEV (Generalized Extreme Value).
     - Pearson typu III.
   - Wyznaczanie krzywej prawdopodobieństwa nieosiągnięcia przepływu dla rozkładu Fishera-Tippeta (GEV).

4. **Wizualizacja danych**:
   - Roczne przepływy maksymalne, średnie i minimalne dla wybranych posterunków wodowskazowych.
   - Sieć pomiarowo-obserwacyjna IMGW.

5. **Interfejs graficzny (GUI)**:
   - Prosty interfejs graficzny do pobierania danych PMAXTP w formacie JSON.

---

## Wymagania

- Python 3.12 lub nowszy.
- Zainstalowane biblioteki:
  - `requests`
  - `seaborn`
  - `pandas`
  - `numpy`
  - `scipy`
  - `pyshp`
  - `pyproj`

Aby zainstalować wymagane biblioteki, użyj:
```bash
pip install -r requirements.txt
```

---

## Instalacja
1. Sklonuj repozytorium:
```bash
git clone https://github.com/TwojeRepozytorium/IMGWTools.git
cd IMGWTools
```
2. Zainstaluj wymagane biblioteki:
```bash
pip install -r requirements.txt
```

---

## Szybki start
Pobieranie danych PMAXTP przez GUI:
1. Uruchom interfejs graficzny:
```bash
python code/pmaxtp_gui.py
```
2. Wprowadź parametry:
    - Metoda. Annual Max Precipitation (AMP) lub Peak Over Threshold (POT).
    - Długość geograficzna.
    - Szerokość geograficzna.
    - Ścieżka folderu do zapisu pliku.
3. Kliknij przycisk **Pobierz dane**. Dane zostaną zapisane do pliku JSON.

Pobieranie najnowszych danych pomiarowo-obserwacyjnychych przez API.
Przykład pobierania danych hydrologicznych:
```python
from code.imgw_api import HYDRO
hydro = HYDRO(station_id="150160180")
data = hydro.get_hydro_data()
print(data)
```

Pobieranie historycznych danych plikowych.
Przykład pobierania danych hydrologicznych:
```python
from code.imgw_datastore import *
data_type = "dane_hydrologiczne"
downloader = DataDownloader(data_type)
downloader.download_data()
```
Odpowiadając na kolejne pytania, możliwe jest pobranie danych z ostatnich 30 lat lub wybranego okresu oraz dla wybranego interwału czasowego.

---

## Struktura katalogów
- `code/` - Główne moduły aplikacji:
  - `hydro_stats.py` - Klasy do obliczania podstawowych statystyk hydrologicznych i wizaulizacji danych.
  - `imgw_api.py` - Klasy do obsługi API IMGW.
  - `imgw_datastore.py` - Klasa służąca do pobierania i zarządzania danymi z publicznych zasobów IMGW.
  - `imgw_spatial.py` - Klasy do wizualizacji lokalizacji wybranej lokalizacji na mapie Polski.
  - `meteo_stats.py` -Klasy do obliczania podstawowych statystyk meteorologiczne i wizaulizacji danych.
  - `pmaxtp_gui.py` - Interfejs graficzny do pobierania danych PMAXTP.
- `data/` - Wszystko to co niezbędne do zrozumienia danych i pracy na nich.
  - `desc/` - Opis strutury danych.
  - `downloaded/` - Zapisane pliki.
- `Notebooks/` - Notebooki Jupyter z przykładami użycia.
- `LICENSE` - Licencja.
- `README.md` - Dokumentacja projektu.

---
## Problemy i wsparcie
Jeśli napotkasz problemy, zgłoś je w sekcji [Issues](https://github.com/Daldek/IMGWTools/issues).

---
## Licencja
Projekt jest udostępniony na liencji MIT. Szczegóły znajdziesz w pliku ``License``.

---
## Autorzy
- [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/) [@LinkedIn](https://www.linkedin.com/in/piotr-de-bever/)