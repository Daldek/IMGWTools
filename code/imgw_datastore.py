import wget
import os
from pathlib import Path
import shutil


class DataDownloader:
    """
    Klasa służąca do pobierania i zarządzania danymi z publicznych zasobów IMGW.

    Obsługuje dane hydrologiczne i meteorologiczne, umożliwiając pobieranie danych w różnych interwałach, takich jak
    dobowe, miesięczne oraz półroczne/roczne (razem). Klasa zarządza również lokalnym zapisem pobranych plików, sprawdza,
    czy pliki są już obecne, przenosi oraz rozpakowuje dane.
    """

    def __init__(self, data_type, meteo_data_subtype=None, meteo_data_interval=None):
        """
        Inicjalizuje instancję klasy DataDownloader dla określonego typu danych (hydrologiczne lub meteorologiczne),
        z opcjonalnymi parametrami podtypu i interwału dla danych meteorologicznych.

        :param data_type: Typ danych do pobrania (dane_hydrologiczne lub dane_meteorologiczne).
        :param meteo_data_subtype: Podtyp danych meteorologicznych (np. klimat, opad, synop).
        :param meteo_data_interval: Interwał danych meteorologicznych (dobowe, miesięczne, terminowe).
        """
        self.public_data_url = (
            r"https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"
        )
        self.data_type = data_type
        self.meteo_data_subtype = meteo_data_subtype
        self.meteo_data_interval = meteo_data_interval
        self.downloaded_files = []

    def file_path(self, file_name):
        """
        Zwraca odpowiednią ścieżkę zdalną dla podanego pliku w zależności od typu danych (hydrologiczne lub meteorologiczne)
        oraz na podstawie nazw plików.

        :param file_name: Nazwa pliku, dla którego ma być wygenerowana ścieżka.
        :return: Ścieżka do pliku na serwerze zdalnym.
        """
        if self.data_type == "dane_hydrologiczne":
            if file_name[:4] == "codz" or file_name[:4] == "zjaw":
                year = file_name[5:9]
                interval = "dobowe"
            elif file_name[:4] == "mies":
                year = file_name[5:9]
                interval = "miesieczne"
            else:
                year = file_name[7:11]
                interval = "polroczne_i_roczne"
            path = f"/{self.data_type}/{interval}/{year}/{file_name}"
        elif self.data_type == "dane_meteorologiczne":
            year = file_name[:4]
            if file_name[-5] == "k":
                self.meteo_data_subtype = "klimat"
            elif file_name[-5] == "o":
                self.meteo_data_subtype = "opad"
            else:
                self.meteo_data_subtype = "synop"
            path = f"/{self.data_type}/{self.meteo_data_interval}/{self.meteo_data_subtype}/{year}/{file_name}"
        else:
            path = None
        return path

    def local_file_path(self, file_name):
        """
        Generuje lokalną ścieżkę pliku na podstawie bieżącego katalogu roboczego, typu danych oraz wygenerowanej zdalnej ścieżki pliku.

        :param file_name: Nazwa pliku, dla którego ma być wygenerowana lokalna ścieżka.
        :return: Lokalna ścieżka do pliku.
        """
        current_path = Path.cwd().parent
        local_path = f"{current_path}\\data\\downloaded"
        local_file_path = local_path + self.file_path(file_name).replace("/", "\\")
        return local_file_path

    def check_zip_file_presence(self, file_name):
        """
        Sprawdza, czy dany plik ZIP już istnieje w lokalnym systemie plików, aby uniknąć ponownego pobierania.

        :param file_name: Nazwa pliku ZIP do sprawdzenia.
        :return: True, jeśli plik istnieje, False w przeciwnym wypadku.
        """
        status = any(
            [os.path.isfile(self.local_file_path(file_name)), os.path.isfile(file_name)]
        )

        if status:
            print("This file has already been downloaded")
        return status

    def compose_url_filename(self, interval, year, var=None):
        """
        Komponuje adres URL i nazwę pliku dla danych hydrologicznych lub meteorologicznych na podstawie wybranego interwału,
        roku i zmiennej.

        :param interval: Interwał danych (dobowe, miesięczne, polroczne_i_roczne, terminowe).
        :param year: Rok, dla którego mają być pobrane dane.
        :param var: Zmienna określająca szczegóły pobieranych danych (np. miesiąc, rodzaj danych).
        :return: Adres URL do pliku oraz nazwa pliku.
        """

        def format_var(var):
            return f"0{var}" if var < 10 else str(var)

        def print_info(url, f_name):
            print("URL address: ", url)
            print("File name: ", f_name, "\n")
            return url, f_name

        if self.data_type == "dane_hydrologiczne":
            if interval == "dobowe":
                if var is not None:
                    var = format_var(var)
                if var == "13":
                    url = f"{self.public_data_url}/{self.data_type}/{interval}/{year}/zjaw_{year}.zip"
                    f_name = f"zjaw_{year}.zip"
                else:
                    if year == 2023:
                        url = f"{self.public_data_url}/{self.data_type}/{interval}/{year}/codz_{year}.zip"
                        f_name = f"codz_{year}.zip"
                    else:
                        url = f"{self.public_data_url}/{self.data_type}/{interval}/{year}/codz_{year}_{var}.zip"
                        f_name = f"codz_{year}_{var}.zip"
            elif interval == "miesieczne":
                url = f"{self.public_data_url}/{self.data_type}/{interval}/{year}/mies_{year}.zip"
                f_name = f"mies_{year}.zip"
            elif interval == "polroczne_i_roczne":
                var = var.upper()
                url = f"{self.public_data_url}/{self.data_type}/{interval}/{year}/polr_{var}_{year}.zip"
                f_name = f"polr_{var}_{year}.zip"
            else:
                raise ValueError(
                    "Invalid interval. Choose from 'dobowe', 'miesieczne', or 'polroczne_i_roczne'."
                )
            print_info(url, f_name)

        elif self.data_type == "dane_meteorologiczne":
            if interval == "dobowe":
                var = format_var(var)
                f_name = f"{year}_{var}_{self.meteo_data_subtype[0]}.zip"
                url = f"{self.public_data_url}/{self.data_type}/{self.meteo_data_interval}/{self.meteo_data_subtype}/{year}/{f_name}"
            elif interval == "miesieczne":
                f_name = f"{year}_m_{self.meteo_data_subtype[0]}.zip"
                url = f"{self.public_data_url}/{self.data_type}/{self.meteo_data_interval}/{self.meteo_data_subtype}/{year}/{f_name}"
            elif interval == "terminowe":
                var = format_var(var)
                f_name = f"{year}_{var}_{self.meteo_data_subtype[0]}.zip"
                url = f"{self.public_data_url}/{self.data_type}/{self.meteo_data_interval}/{self.meteo_data_subtype}/{year}/{f_name}"
            else:
                raise ValueError(
                    "Invalid interval. Choose from 'dobowe', 'miesieczne', or 'terminowe'."
                )
            print_info(url, f_name)
        return url, f_name

    def move_zips(self):
        """
        Przenosi wszystkie pliki ZIP z katalogu roboczego do odpowiedniego katalogu lokalnego na podstawie zdefiniowanej ścieżki lokalnej.

        :return: 1, gdy operacja przeniesienia zakończy się powodzeniem.
        """
        zip_files = [f for f in os.listdir() if ".zip" in f.lower()]

        for zip_file in zip_files:
            new_path = self.local_file_path(zip_file)
            try:
                os.makedirs(os.path.dirname(new_path))
            except FileExistsError:
                pass
            shutil.move(zip_file, new_path)
        return 1

    def unzip_file(self, file_name):
        """
        Rozpakowuje dany plik ZIP do odpowiedniego katalogu lokalnego.

        :param file_name: Nazwa pliku ZIP do rozpakowania.
        :return: 1, gdy operacja rozpakowywania zakończy się powodzeniem.
        """
        zip_file_path = self.local_file_path(file_name)
        dir_path = os.path.dirname(zip_file_path)
        shutil.unpack_archive(self.local_file_path(file_name), dir_path)
        return 1

    def get_period(self, start_year, end_year, var):
        """
        Pobiera dane dla podanego okresu, od start_year do end_year, dla określonej zmiennej.

        :param start_year: Początkowy rok danych do pobrania.
        :param end_year: Końcowy rok danych do pobrania.
        :param var: Zmienna określająca rodzaj danych (np. temperatura, przepływ, głębokość).
        :return: 1, gdy operacja zakończy się powodzeniem.
        """
        end_year += 1
        interval = "polroczne_i_roczne"
        for year in range(start_year, end_year):
            url, f = self.compose_url_filename(interval, year, var)
            if not self.check_zip_file_presence(f):
                wget.download(url, f)
                self.downloaded_files.append(f)
        return 1

    def download_data(self):
        """
        Główna metoda uruchamiana przez użytkownika, służąca do pobierania danych hydrologicznych lub meteorologicznych.

        Zawiera interfejs wiersza poleceń, który pozwala użytkownikowi wybrać interwał danych, rok oraz inne szczegóły.
        Obsługuje również pobieranie danych za ostatnie 30 lat lub całego zakresu danych od 1951 roku.
        """
        if self.data_type == "dane_hydrologiczne":
            while True:
                interval = input(
                    'Choose: "dobowe", "miesieczne" or "polroczne_i_roczne" or\n'
                    'type "all" to get "polroczne_i_roczne" from 1951 to 2023 or\n'
                    'press "Enter" to get "polroczne_i_roczne" from last 30 yrs: '
                ).lower()
                if interval == "":
                    print(
                        "Semi-annual and annual data for the last 30 years will be pulled"
                    )
                    break
                elif interval == "all":
                    print("The entire range of data will be pulled")
                    break
                elif interval not in ["dobowe", "miesieczne", "polroczne_i_roczne"]:
                    print("Wrong input")
                    break

                year = input("Desired (hydrological) year from 1951 to 2023: ")
                try:
                    year = int(year)
                except ValueError:
                    print("The value given is not an integer")
                    break
                if year < 1951 or year > 2023:
                    print("Year given out of data range")
                    break

                if interval == "dobowe":
                    var = input(
                        "Numerical values from 1 (November) to 12 (October), 13 - phenomena: "
                    )
                    try:
                        var = int(var)
                    except ValueError:
                        print("The value given is not an integer")
                        break
                    if var < 1 or var > 13:
                        print("Wrong input")
                        break
                elif interval == "polroczne_i_roczne":
                    var = input(
                        'Choose: "T" - temperature, "Q" - flow, "H" - depth: '
                    ).lower()
                    if var not in ["t", "q", "h"]:
                        print("Wrong input")
                else:
                    var = ""

                url, f = self.compose_url_filename(interval, year, var)
                if not self.check_zip_file_presence(f):
                    wget.download(url, f)
                    self.downloaded_files.append(f)

                continuation = input(
                    '\nEnter "q" to quit or press "Enter" to continue: '
                ).lower()
                if continuation == "q":
                    break

            if interval == "":
                start = 2023 - 30
                end = 2023
                self.get_period(start, end, "Q")
                self.get_period(start, end, "H")
                self.get_period(start, end, "T")
            elif interval == "all":
                self.get_period(1951, 2023, "Q")
                self.get_period(1951, 2023, "H")
                self.get_period(1951, 2023, "T")

            if self.downloaded_files:
                self.move_zips()
                unzip_files = input(
                    '\nEnter "y" to extract all newly downloaded files or\n'
                    'press "Enter" to quit '
                ).lower()
                if unzip_files == "y":
                    [
                        self.unzip_file(downloaded_file)
                        for downloaded_file in self.downloaded_files
                    ]

        elif self.data_type == "dane_meteorologiczne":
            while True:
                self.meteo_data_interval = input(
                    'Choose: "dobowe", "miesieczne" or "terminowe".'
                ).lower()

                year = input("Desired (hydrological) year from 2001 to 2023: ")
                try:
                    year = int(year)
                except ValueError:
                    print("The value given is not an integer")
                    break
                if year < 2001 or year > 2023:
                    print("Year given out of data range")
                    break

                month = input("Numerical values from 1 to 12:")
                try:
                    month = int(month)
                except ValueError:
                    print("The value given is not an integer")
                    break
                if month < 1 or month > 13:
                    print("Wrong input")
                    break

                url, f = self.compose_url_filename(
                    self.meteo_data_interval, year, month
                )
                if not self.check_zip_file_presence(f):
                    wget.download(url, f)
                    self.downloaded_files.append(f)

                continuation = input(
                    '\nEnter "q" to quit or press "Enter" to continue: '
                ).lower()
                if continuation == "q":
                    break

            if self.downloaded_files:
                self.move_zips()
                unzip_files = input(
                    '\nEnter "y" to extract all newly downloaded files or\n'
                    'press "Enter" to quit '
                ).lower()
                if unzip_files == "y":
                    [
                        self.unzip_file(downloaded_file)
                        for downloaded_file in self.downloaded_files
                    ]
            # downloading data not yet supported
        else:
            print("Wrong data type!")
