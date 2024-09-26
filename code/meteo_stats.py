from pathlib import Path
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from meteo_columns_config import column_names_dict

# from windrose import WindroseAxes


class MeteoStationData:
    def __init__(self, station_id):
        self.station_id = station_id
        self.data = []
        self.data_type = None

    def _validate_csv_file(self, csv_path):
        """Walidacja pliku CSV: sprawdza czy plik istnieje oraz czy ma poprawne rozszerzenie"""
        file_path = Path(csv_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Plik {csv_path} nie istnieje.")
        if file_path.suffix != ".csv":
            raise ValueError(f"Plik {csv_path} nie jest plikiem CSV.")

    def _recognize_data_type(self, csv_path):
        """Rozpoznanie typu danych na podstawie nazwy pliku CSV"""
        f_name = Path(csv_path).name
        f_type = f_name[:3]
        if f_name[3:5] == "_t" or f_name[3:5] == "_d":
            f_type += f_name[3:5]
        self.data_type = f_type
        return self.data_type

    def station_data_to_df(self, csv_path):
        """Wczytanie danych do DataFrame w zależności od typu danych"""
        # Walidacja pliku CSV
        self._validate_csv_file(csv_path)

        # Rozpoznanie typu danych, jeśli jeszcze nie zostało zrobione
        if self.data_type is None:
            self._recognize_data_type(csv_path=csv_path)

        # Wybór odpowiednich kolumn na podstawie rozpoznanego typu danych
        column_names = column_names_dict.get(self.data_type)
        if column_names is None:
            raise ValueError(f"Typ danych {self.data_type} nie jest obsługiwany.")

        # Wczytanie pliku CSV i filtrowanie danych według ID stacji
        raw_df = pd.read_csv(csv_path, names=column_names, encoding="ANSI")
        filtered_df = raw_df[raw_df["Kod stacji"] == self.station_id]
        return filtered_df

    def basic_stats(self, df):
        """Obliczanie podstawowych statystyk na podstawie wczytanych danych"""
        list_len = df.shape[0]
        if self.data_type == "k_d":
            t_max = df["Maksymalna temperatura dobowa"].max()
            t_mean = df["Średnia temperatura dobowa"].mean()
            t_min = df["Minimalna temperatura dobowa"].min()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Temperatura maksumalna: {t_max}\n Temperatura średnia: {t_mean:.2f}\n Temperatura minimalna: {t_min}"
            )

        elif self.data_type == "k_d_t":
            t_mean = df["Średnia dobowa temperatura"].mean()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Temperatura średnia: {t_mean:.2f}"
            )

        elif self.data_type == "k_m_d":
            t_abs_max = df["Absolutna temperatura maksymalna"].max()
            t_mean_max = df["Średnia temperatura maksymalna"].mean()
            t_mean = df["Średnia temperatura miesięczna"].mean()
            t_abs_min = df["Absolutna temperatura minimalna"].min()
            t_mean_min = df["Średnia temperatura minimalna"].min()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Absolutna temperatura maksymalna: {t_abs_max}\t Średnia temperatura maksymalna: {t_mean_max:.2f}\n"
                f"Średnia temperatura miesięczna:   {t_mean:.2f}\n"
                f"Absolutna temperatura minimalna:  {t_abs_min}\t Średnia temperatura minimalna:  {t_mean_min:.2f}"
            )

        elif self.data_type == "k_m_t":
            t_mean = df["Średnia miesięczna temperatura"].mean()
            ws_mean = df["Średnia miesięczna prędkość wiatru"].mean()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Średnia miesięczna temperatura:     {t_mean:.2f}\n"
                f"Średnia miesięczna prędkość wiatru: {ws_mean:.2f}"
            )

        elif self.data_type == "k_t":
            t_mean = df["Temperatura powietrza"].mean()
            ws_mean = df["Prędkość wiatru"].mean()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Średnia temperatura powietrza:  {t_mean:.2f}\n"
                f"Średnia prędkość wiatru:        {ws_mean:.2f}"
            )

        elif self.data_type == "o_d":
            p_sum = df["Suma dobowa opadów"].sum()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Suma dobowa opadów:  {p_sum:.2f}\n"
            )

        elif self.data_type == "o_m":
            p_sum = df["Miesięczna suma opadów"].sum()
            p_max = df["Opad maksymalny"].max()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Miesięczna suma opadów:  {p_sum}\n"
                f"Opad maksymalny: {p_max}"
            )

        elif self.data_type == "s_d":
            t_max = df["Maksymalna temperatura dobowa"].max()
            t_mean = df["Średnia temperatura dobowa"].mean()
            t_min = df["Minimalna temperatura dobowa"].min()
            p_sum = df["Suma dobowa opadu"].sum()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Temperatura maksumalna: {t_max}\n Temperatura średnia: {t_mean:.2f}\n Temperatura minimalna: {t_min}"
                f"Suma dobowa opadów:  {p_sum}\n"
            )

        elif self.data_type == "s_d_t":
            t_mean = df["Średnia dobowa temperatura"].mean()
            ws_mean = df["Średnia dobowa prędkość wiatru"].mean()
            p_day_sum = df["Suma opadu dzień"].sum()
            p_night_sum = df["Suma opadu dzień"].sum()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Średnia dobowa temperatura:     {t_mean:.2f}\n"
                f"Średnia dobowa prędkość wiatru: {ws_mean:.2f}"
                f"Suma opadu dzień:               {p_day_sum}\n"
                f"Suma opadu noc:                 {p_night_sum}\n"
            )

        elif self.data_type == "s_m_d":
            t_abs_max = df["Absolutna temperatura maksymalna"].max()
            t_mean_max = df["Średnia temperatura maksymalna"].mean()
            t_mean = df["Średnia temperatura miesięczna"].mean()
            t_abs_min = df["Absolutna temperatura minimalna"].min()
            t_mean_min = df["Średnia temperatura minimalna"].min()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Absolutna temperatura maksymalna: {t_abs_max}\t Średnia temperatura maksymalna: {t_mean_max:.2f}\n"
                f"Średnia temperatura miesięczna:   {t_mean:.2f}\n"
                f"Absolutna temperatura minimalna:  {t_abs_min}\t Średnia temperatura minimalna:  {t_mean_min:.2f}"
            )

        elif self.data_type == "s_m_t":
            t_mean = df["Średnia miesięczna temperatura"].mean()
            ws_mean = df["Średnia miesięczna prędkość wiatru"].mean()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Średnia temperatura powietrza:       {t_mean:.2f}\n"
                f"Średnia miesięczna prędkość wiatru:  {ws_mean:.2f}\n"
            )

        elif self.data_type == "s_t":
            t_mean = df["Temperatura powietrza"].mean()
            print(
                f"\nLiczba obserwacji: {list_len}\n"
                f"Średnia temperatura powietrza:  {t_mean:.2f}\n"
            )

        else:
            print("Data type not yet supported")
        return 1
