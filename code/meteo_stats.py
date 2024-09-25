from pathlib import Path
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# from windrose import WindroseAxes


class MeteoStationData:
    def __init__(self, station_id):
        self.station_id = station_id
        self.data = []
        self.data_type = None

    def recognize_data_type(self, csv_path):
        f_name = Path(csv_path).name
        f_type = f_name[:3]
        if f_name[3:5] == "_t":
            f_type += f_name[3:5]
        self.data_type = f_type
        return self.data_type

    def station_data_to_df(self, csv_path):
        if self.data_type is None:
            self.recognize_data_type(csv_path=csv_path)
        if self.data_type == "k_d":
            column_names = [
                "Kod stacji",
                "Nazwa stacji",
                "Rok",
                "Miesiąc",
                "Dzień",
                "Maksymalna temperatura dobowa",
                "Status pomiaru TMAX",
                "Minimalna temperatura dobowa",
                "Status pomiaru TMIN",
                "Średnia temperatura dobowa",
                "Status pomiaru STD",
                "Temperatura minimalna przy gruncie",
                "Status pomiaru TMNG",
                "Suma dobowa opadów",
                "Status pomiaru SMDB",
                "Rodzaj opadu",
                "Wysokość pokrywy śnieżnej",
                "Status pomiaru PKSN",
            ]

            raw_df = pd.read_csv(csv_path, names=column_names, encoding="ANSI")
            filtered_df = raw_df[raw_df["Kod stacji"] == self.station_id]
            return filtered_df
        elif self.data_type == "k_d_t":
            column_names = [
                "Kod stacji",
                "Nazwa stacji",
                "Rok",
                "Miesiąc",
                "Dzień",
                "Średnia dobowa temperatura",
                "Status pomiaru TEMP",
                "Średnia dobowa wilgotność względna",
                "Status pomiaru WLGS",
                "Średnia dobowa prędkość wiatru",
                "Status pomiaru FWS",
                "Średnie dobowe zachmurzenie ogólne",
                "Status pomiaru NOS",
            ]
            raw_df = pd.read_csv(csv_path, names=column_names, encoding="ANSI")
            filtered_df = raw_df[raw_df["Kod stacji"] == self.station_id]
            return filtered_df
        else:
            return "Data type not yet supported"

    def basic_stats(self, df):
        list_len = df.shape[0]
        if self.data_type == "k_d":
            t_max = df["Maksymalna temperatura dobowa"].max()
            t_mean = df["Średnia temperatura dobowa"].mean()
            t_min = df["Minimalna temperatura dobowa"].min()
            print(
                f"\nNumber of observations: {list_len}\n"
                f"Tmax: {t_max}\t Tmean: {t_mean:.2f}\t Tmin: {t_min}\n"
            )
        elif self.data_type == "k_d_t":
            t_mean = df["Średnia dobowa temperatura"].mean()
            print(f"\nNumber of observations: {list_len}\n" f"Tmean: {t_mean:.2f}")
        else:
            print("Data type not yet supported")
        return 1
