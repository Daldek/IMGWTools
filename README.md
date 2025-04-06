# Dane publiczne IMGW

Kod napisany w celu ułatwienia pobierania danych publicznych z bazy Instytutu Meteorologii i Gospodarki Wodnej (IMGW-PIB) z wykorzystaniem Pythona. Dane pochodzą z serwisu https://danepubliczne.imgw.pl/

Możliwe jest również pobieranie danych z modeli probabilistycznych opadów maksymalnych o określonym czasie trwania i prawdopodobieństwie - projekt PMAXTP, które są udostpęniane w serwiesie https://klimat.imgw.pl/opady-maksymalne/

Aktulanie możliwe jest:
1. Pobieranie aktualnych danych pomiarowo-obserwacyjnych oraz ostrzeżeń przez [API](https://danepubliczne.imgw.pl/pl/apiinfo).
2. Pobieranie historycznych danych hydrologicznych dla wybranego okresu, dotyczy to zarówno zbiorów danych dobowych, miesięcznych oraz półrocznych i rocznych (razem).
4. Pobieranie opadów maksymalnych prawdopodobnych dla określonych czasów trwania i prawdopodobieństw.
5. Obliczanie podstawowych statystyk hydrologicznych dla wybranych posterunków wodowskazowych (m. in. przepływy charakterystyczne II°)
6. Wyznaczanie krzywej prawdopodobieństwa przewyższenia przepływu dla rozkładów [logartymiczno-normalnego](https://pl.wikipedia.org/wiki/Rozk%C5%82ad_logarytmicznie_normalny), [GEV](https://pl.wikipedia.org/wiki/Rozk%C5%82ad_Fishera-Tippetta), [Pearsona typu III](https://en.wikipedia.org/wiki/Pearson_distribution#The_Pearson_type_III_distribution).
7. Wyznaczenie krzywej prawdopodobieńsywa nieosiągnięcia przepływu dla rozkładu Fishera-Tippeta (GEV).
8. Wizualizacja rocznych przepływów maksymalnych, średnich i minimalnych dla wybranych posterunków wodowskazowych.
9. Wizualizacja sieci pomiarowo-obserwacyjnej IMGW.