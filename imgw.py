import wget
import os
import shutil


class DataDownloader:
    def __init__(self, public_data_url, data_type):
        self.public_data_url = public_data_url
        self.data_type = data_type
        self.downloaded_files = []

    def file_path(self, file_name):
        if file_name[:4] == "codz" or file_name[:4] == "zjaw":
            year = file_name[5:9]
            interval = "dobowe"
        elif file_name[:4] == "mies":
            year = file_name[5:9]
            interval = "miesieczne"
        else:
            year = file_name[7:11]
            interval = "polroczne_i_roczne"

        current_path = os.getcwd()
        path = f"{current_path}\\data\\downloaded\\{interval}\\{year}\\{file_name}"
        return path

    def check_zip_file_presence(self, file_name):
        status = any(
            [os.path.isfile(self.file_path(file_name)), os.path.isfile(file_name)]
        )

        if status:
            print("This file has already been downloaded")
        return status

    def compose_url_filename(self, interval, year, var):
        if interval == "dobowe":
            if var < 10:
                var = f"0{var}"
            if var == 13:
                url = f"{self.public_data_url}/{self.data_type}/{interval}/{year}/zjaw_{year}.zip"
                f = f"zjaw_{year}.zip"
            else:
                url = f"{self.public_data_url}/{self.data_type}/{interval}/{year}/codz_{year}_{var}.zip"
                f = f"codz_{year}_{var}.zip"
        elif interval == "miesieczne":
            url = f"{self.public_data_url}/{self.data_type}/{interval}/{year}/mies_{year}.zip"
            f = f"mies_{year}.zip"
        elif interval == "polroczne_i_roczne":
            var = var.upper()
            url = f"{self.public_data_url}/{self.data_type}/{interval}/{year}/polr_{var}_{year}.zip"
            f = f"polr_{var}_{year}.zip"
        else:
            raise ValueError(
                "Invalid interval. Choose from 'dobowe', 'miesieczne', or 'polroczne_i_roczne'."
            )

        print("URL address: ", url)
        print("File name: ", f, "\n")
        return url, f

    def move_zips(self):
        zip_files = [f for f in os.listdir() if ".zip" in f.lower()]

        for zip_file in zip_files:
            new_path = self.file_path(zip_file)
            try:
                os.makedirs(os.path.dirname(new_path))
            except FileExistsError:
                pass
            shutil.move(zip_file, new_path)
        return 1

    def unzip_file(self, file_name):
        zip_file_path = self.file_path(file_name)
        dir_path = os.path.dirname(zip_file_path)
        shutil.unpack_archive(self.file_path(file_name), dir_path)
        return 1

    def get_period(self, start_year, end_year, var):
        end_year += 1
        interval = "polroczne_i_roczne"
        for year in range(start_year, end_year):
            url, f = self.compose_url_filename(interval, year, var)
            if not self.check_zip_file_presence(f):
                wget.download(url, f)
                self.downloaded_files.append(f)
        return 1

    def download_data(self):
        while True:
            interval = input(
                f'Choose: "dobowe", "miesieczne" or "polroczne_i_roczne" or\n'
                f'type "all" to get "polroczne_i_roczne" from 1951 to 2023 or\n'
                f'press "Enter" to get "polroczne_i_roczne" from last 30 yrs: '
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
        elif interval == "all":
            self.get_period(1951, 2023, "Q")

        if self.downloaded_files:
            self.move_zips()
            unzip_files = input(
                f'\nEnter "y" to extract all newly downloaded files or\n'
                f'press "Enter" to quit '
            ).lower()
            if unzip_files == "y":
                [
                    self.unzip_file(downloaded_file)
                    for downloaded_file in self.downloaded_files
                ]
