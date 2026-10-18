# Rejestr decyzji — IMGWTools

Każdy wpis zachowuje stan decyzji z dnia przyjęcia; późniejsze zmiany opisuje się jako datowane erraty, bez przepisywania historii. Format: numer, data, status, kontekst, warianty, decyzja, konsekwencje.

## Indeks

| ADR | Tytuł | Data | Status |
|---|---|---|---|
| [ADR-001](#adr-001-magazyn-wersjonowany-imgw) | Magazyn wersjonowany IMGW | 2026-10-17 | Przyjęta |

---

## ADR-001: Magazyn wersjonowany IMGW

**Data:** 2026-10-17  
**Status:** Przyjęta  
**Spec:** `docs/superpowers/specs/2026-10-17-versioned-store-design.md`  
**Plan:** `docs/superpowers/plans/2026-10-17-versioned-store.md`  
**Źródło kontraktu:** `Archiwista/docs/SPEC.md` 4.8, 12.7–12.9; `Archiwista/docs/wymagania-imgwtools.md` IMGW-1..14 i R1..12. Współpraca nie oznacza zależności pakietowej od Archiwisty ani Kartografa.

### Kontekst i warianty

Wydanie 2.1.1 pobiera archiwa do płaskich plików bez wersji, trwałych nagłówków HTTP i pochodzenia; przerwany zapis może zostać uznany za pełny, a różne ścieżki serwera o tej samej nazwie pliku mogą się zderzyć. Opcjonalny cache SQLite obejmuje tylko hydro i nie zachowuje źródłowych bajtów. Konsumenci potrzebują niezmiennych wejść i gotowych szeregów stacji, możliwych do czytania offline i z udziału sieciowego. Rozważono rozwój cache SQLite, współdzielenie formatu/implementacji Kartografa oraz osobny magazyn IMGW. Wybrano osobny magazyn: format stacji i szeregów jest inny niż geodanych, a SQLite/WAL ani mutowalne dowiązania nie mogą być źródłem prawdy na udziale SMB.

### Decyzje D1–D11

| ID | Decyzja | Odrzucone |
|---|---|---|
| D1 | Przyjmujemy kontrakty `imgw-store/1`, `imgw-meta/1`, `imgw-series/1`, `imgw-plan/1`, `imgw-project/1`. Magazyn tylko przyrostowy: żadnych hardlinków, standardowej ścieżki `latest`, nadpisywania lub mutowania plików wersji. Bieżącą wersję oblicza API: archiwa według najnowszej publikacji/etykiety, szeregi według chwili budowy, katalog według chwili pobrania; relabeling tworzy katalog z **kopią** danych. | Wspólna implementacja i dowiązania ADR-036 Kartografa; SQLite w magazynie. |
| D2 | Trzy warstwy: źródłowe archiwa 1:1 według ścieżki na serwerze; pochodne Parquet stacji, GeoJSON katalogu i PMAXTP per komórka; lokalny odbudowywalny indeks pozostaje poza tym wydaniem. Żaden plik `.db` nie jest częścią magazynu. | Baza jako źródło prawdy, serwer przepisujący archiwa. |
| D3 | Układ: `imgw-store.json`; `archives/versions/<ścieżka serwera bez nazwy pliku>/<stem>/<label>_<sha8>/<plik>` + `<plik>.meta.json`; `stations/versions/<label>_<sha8>/stations.geojson` + sidecar; `series/versions/<dataset>/<label>_<sha8>/series.json` + sidecar + `stations/<kod>.parquet`; `pmaxtp/versions/<method>/<indX>_<indY>/<label>_<sha8>/cell.json` + sidecar; `.incoming/<host>_<pid>_<token>/` z usuwaniem pozostałości starszych niż 24 h. Listy stacji IMGW są również archiwami. | Płaski katalog z kolizjami nazw. |
| D4 | Jeden rejestr `DatasetDescriptor`: klucz `pl.imgw.*`, katalog serwera, generator plików offline, parser, zmienne/jednostki, jednostka czasu, rodzaj roku, sygnał aktualizacji i licencja. Korzystają URL-e, CLI, REST, synchronizacja, szeregi, katalog poleceń i walidacja dla Retmana. Pięć zbiorów Archiwisty: `hydro_daily`, `hydro_monthly`, `hydro_semiannual`, `meteo_climate_daily`, `meteo_precip_daily`; dwa pomocnicze deskryptory list stacji `hydro_stations`, `meteo_stations`; dodatkowo PMAXTP (`POT`, `AMP`). | Drugie listy zbiorów w każdej warstwie. |
| D5 | Usuwamy cache SQLite bez shimów: moduły DB, `imgw db …`, `/api/v1/hydro/data`, `IMGW_DB_*`, dodatkową zależność `db`. Przenosimy wciąż potrzebne parsery hydro, pomocnicze daty i kody braków poza `db/`; publiczny `imgwtools.parsers` pozostaje, rozszerzony o meteo. | Dwa równoległe mechanizmy przechowywania. |
| D6 | Wydanie obejmuje pięć archiwalnych zbiorów Archiwisty oraz magazyn PMAXTP komórka po komórce. Dane bieżące, synop i ostrzeżenia pozostają bez magazynu, jako zapytania live. | Rozszerzenie całej macierzy meteo/synop w tej wersji. |
| D7 | `download_hydro_data` i `download_meteo_data` (oraz warianty async) zwracają `DownloadResult(data, url, etag, last_modified, content_length)` zamiast `bytes`; jest to świadoma zmiana niezgodna w 3.0.0. `fetch_pmaxtp` zachowuje sygnaturę i wynik, aby dotychczasowy klient Hydrograf mógł aktualizować niezależnie. | Ciche obejście przez nową funkcję równoległą. |
| D8 | Parquet to opcjonalny `imgwtools[store]` z `pyarrow>=15`; rdzeń nadal wymaga tylko `httpx` i `pydantic`, GeoJSON zapisuje się bez GDAL. Brak dodatku przy operacji Parquet to czytelny wyjątek `IMGWError`. | Obowiązkowy pyarrow w każdym imporcie. |
| D9 | Obowiązują reguły R1..R12: nowy interfejs tylko z argumentami nazwanymi poza wskazanym obiektem, bliźniaki `check_*`, postęp i polskie komunikaty strukturalne, anulowanie między plikami, jawne błędy, eksport publicznych symboli, CLI = API, testy offline i brak cichych pominięć. | Niezależne ścieżki logiki CLI, REST i biblioteki. |
| D10 | Pytania Q1..Q15 rozstrzygnięto poniżej. W szczególności wykrywanie katalogu Kartografa jest po nazwach znaczników i napisach schematów JSON, bez importu; identyczny GeoJSON kolejnego dnia nie tworzy wersji; fixtury i budowniczy są publiczne pod `imgwtools.testing`. | Nieokreślone reguły integracyjne. |
| D11 | Wydanie **3.0.0**, CHANGELOG z sekcją BREAKING; aktualizacja `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/PROGRESS.md` po wdrożeniu. | Ukrycie zmian API i usunięcia DB w minor release. |

### Odpowiedzi na pytania Archiwisty

| Pytanie | Rozstrzygnięcie |
|---|---|
| Q1 | Nazwy, klucze i dokładne sygnatury są normatywne w specyfikacji ADR-001 §API: `archive_files`, `check_store`/`sync_store`, `build_series`, `build_catalog`, `read_*`, `export_series`, `sync_pmaxtp`/`read_pmaxtp`, `imgw store …`, `imgw series …`, `imgw project …`. Klucze pełne `pl.imgw.<slug>`; katalog serii używa samego `<slug>`. |
| Q2 | Pola z IMGW-14 wystarczają po dodaniu jawnego `geometry_sha256` i walidacji bezpieczeństwa ścieżek. Dodajemy `set_project_store` (`imgw project set-store`) z walidacją istniejącego znacznika magazynu, bez zmiany przypięć; ścieżki względne rozwiązujemy względem katalogu projektu. |
| Q3 | Przed zapisem sprawdzamy realne ścieżki przodków i istniejących potomków na `imgw-store.json` oraz na `versions/` z sidecarem `kartograf-meta/1`; `kartograf-project.json` służy tylko do wykrycia `output_dir` wskazującego właśnie kolidujący katalog, nie dyskwalifikuje całego katalogu projektu. Nazwy i napis schematu JSON wystarczą — bez importu Kartografa. Podejrzana/nieczytelna struktura → odmowa zapisu; nie deklarujemy rozpoznawania nieoznaczonego magazynu. |
| Q4 | Kod hydrograficzny zachowujemy jako tekst; wyszukiwanie prefiksowe jest techniczną regułą interfejsu, nie potwierdzoną naukowo hierarchią. Potwierdzenie u IMGW-PIB/MPHP wymaga osobnego badania; nie dopowiadamy danych. |
| Q5 | Kolejność (czwarta kolumna listy) przechowujemy jako pole źródłowe, nie twierdzimy, że rośnie w dół rzeki; nie dekodujemy współrzędnych z cyfr kodu stacji. Obie interpretacje pozostają hipotezami do potwierdzenia u IMGW. |
| Q6 | Zespół IMGWTools występuje o oficjalny wykaz według §8 przed użyciem jako źródła; brak odpowiedzi nie blokuje wydania. `build_catalog(..., user_locations=Path|None)` czyta CSV UTF-8 `station_code,lon,lat,source`; plik użytkownika uzupełnia wyłącznie brak współrzędnych, nie nadpisuje valid API/statycznych. Nie wymyślamy terminów odpowiedzi IMGW. |
| Q7 | Extra `store = ["pyarrow>=15"]`; odczyt samych JSON/GeoJSON bez dodatku, `read_series`, `build_series` i `export_series` wymagają dodatku. |
| Q8 | Nowy `DownloadResult`, nie `bytes`; zmiana w 3.0.0, bez aliasu; Hydrograf używa jedynie niezmienionego `fetch_pmaxtp`. |
| Q9 | Identyczny kanoniczny GeoJSON (ten sam SHA-256) w nowym dniu daje `unchanged`, bez nowego katalogu i mutacji sidecara; źródła z zapytania są raportowane, nie dopisywane wstecz. |
| Q10 | CSV zachowuje jeden standardowy wiersz nagłówka: dwie dodatkowe kolumny `attribution_source` i `attribution_processed`, obie dosłowne formuły §5 w pierwszym wierszu danych (puste w dalszych). Bez wiersza `#` łamiącego `csv.DictReader`/Excel/QGIS; eksport pustego szeregu odrzuca się. |
| Q11 | `year_type=None` w eksporcie oznacza konwencję publikacji: hydro `hydrological`, meteo `calendar`. |
| Q12 | `year_type` w `series.json` oznacza konwencję numeracji archiwów, nie wybór roku w widoku; oba rodzaje lat dla danych dobowych obu rodzin, charakterystyki półroczne/roczne tylko hydrologiczne. |
| Q13 | Tak: `imgwtools.testing.build_fixture_store(root, *, ...)` i małe, rozpowszechniane z pakietem próbki archiwów + nagrane odpowiedzi bez danych osobowych; dokument i testy kontraktu nie wymagają internetu. |
| Q14 | Nie zakładamy, czy ponowna publikacja zmienia bajty. Testy obejmują oba warianty: różny SHA → nowa treść, ten sam SHA pod nowym sygnałem → `relabeled` (kopia). Pomiar live jest badaniem, nie warunkiem poprawności. |
| Q15 | Nie deklarujemy, które archiwa są „danymi o wysokiej wartości”, dopóki IMGW-PIB tego nie potwierdzi. Komunikat `on_notice` cytuje warunki celu użycia (§2–5) i wyjątek dla danych o wysokiej wartości bez kwalifikowania konkretnych zbiorów; nigdy nie blokuje pobrania. |

### Polityka wersji (IMGW-13) i konsekwencje

Obok pięciu schematów D1 rozszerzenie komórkowe `imgw-pmaxtp/1` stosuje te same reguły `/N`, ale nie jest wymagane przez Archiwistę.

`imgw-project/1` jest edytowalną instrukcją: odrzuca obce klucze strukturalne (IMGW-14), a przyszłe opcjonalne dodatki wolno umieszczać tylko w przewidzianej mapie `extensions` z ignorowaniem nieznanych wpisów. Nowy klucz na najwyższym poziomie wymaga `/2`; ta zasada godzi ścisłą walidację projektu z dodatkami w `/1`.

Pięć identyfikatorów schematów (wraz z `imgw-plan/1`) ma własny licznik `/N`, niezależny od wersji pakietu. W ramach `/1` dodajemy tylko pola opcjonalne, nie zmieniamy znaczenia/typów istniejących; czytniki tolerują dodatkowe pola w plikach magazynu i wynikach, ale manifest projektu jako edytowalna instrukcja jest celowo walidowany ściśle. Zmiana niezgodna wymaga `/2`, jawnego odczytu `/1` i `/2` w okresie przejścia, osobnych przykładów i testów kontraktu; zapis starym kodem do nieznanego znacznika jest zabroniony. `store_info` zgłasza nieobsługiwaną wersję, skan raportuje problem i nie parsuje plików nieznanego schematu; API odczytu w 3.x nie usuwa podpisanych publicznych funkcji ani nie zmienia semantyki `/1` bez nowego major. Każda zmiana schematu i publicznego API trafia do CHANGELOG.

Konsekwencje: archiwa źródłowe zachowują bajty i pochodzenie; stacje bez położenia oraz serie z lukami pozostają widoczne; udział SMB nie wymaga bazy, lecz powielone bajty przy relabelingu i koszt budowania Parquet są świadomym kompromisem. Stary magazyn SQLite nie jest migrowany automatycznie; jego lokalne pliki nie są kasowane przez instalację, a dane pobiera się ponownie do nowego magazynu. Niespójny lub nieznany format zatrzymuje zapis bez cichej konwersji. PMAXTP jest rozszerzeniem IMGWTools ponad zakres Archiwisty v1.0, nie zmienia jego kontraktów stacji/szeregów.

### Erraty

**2026-10-18 — relacja do `docs/OBSERWATOR_SPEC.md`.** Decyzją właściciela z 2026-10-17 magazyn według ADR-001 wchodzi teraz, w wydaniu 3.0.0. Szkic Obserwatora (2026-08-11) zakładał w §7 cache SQLite „schemat v2” i numer 3.0.0 dla rebrandingu; oba założenia są nieaktualne: cache SQLite v2 zastępuje magazyn wersjonowany (D1–D5), a Obserwator pozostaje wyłącznie przyszłą zmianą nazwy i rozszerzeniem o providery w kolejnym wydaniu major. Treść decyzji D1–D11 bez zmian; zmiany wydania opisuje `docs/CHANGELOG.md`.
