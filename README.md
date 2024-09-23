# Dane publiczne IMGW

Kod napisany w celu ułatwienia pobierania danych publicznych z bazy Instytutu Meteorologii i Gospodarki Wodnej (IMGW-PIB) z wykorzystaniem Pythona. Dane pochodzą z serwisu https://danepubliczne.imgw.pl/

Aktulanie możliwe jest:
1. Pobieranie aktualnych danych pomiarowo-obserwacyjnych oraz ostrzeżeń przez [API](https://danepubliczne.imgw.pl/pl/apiinfo).
2. Pobieranie historycznych danych hydrologicznych dla wybranego okresu, dotyczy to zarówno zbiorów danych dobowych, miesięcznych oraz półrocznych i rocznych (razem).
3. Obliczanie podstawowych statystyk hydrologicznych dla wybranych posterunków wodowskazowych (m. in. przepływy charakterystyczne II°)
4. Wyznaczanie krzywej prawdopodobieństwa przewyższenia przepływu dla rozkładów [logartymiczno-normalnego](https://pl.wikipedia.org/wiki/Rozk%C5%82ad_logarytmicznie_normalny) oraz [GEV](https://en.wikipedia.org/wiki/Generalized_extreme_value_distribution).
5. Wizualizacja rocznych przepływów maksymalnych, średnich i minimalnych dla wybranych posterunków wodowskazowych.
6. Wizualizacja sieci pomiarowo-obserwacyjnej IMGW.