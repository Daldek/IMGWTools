import os
from pathlib import Path
import csv
from statistics import mean
from scipy.stats import kstest, lognorm, genextreme, pearson3
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt


class StationData:
    def __init__(self, station_id, interval="polroczne_i_roczne", parameter=None):
        self.interval = interval
        self.station_id = station_id
        self.parameter = parameter
        self._data = []

    def _is_leap_year(self, year):
        """Check if a year is a leap year."""
        return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

    def station_data_to_dict(self, csv_path):
        """function that writes data from a csv file for a desired station to a dictionary

        Parameters
        ----------
        csv_path : str
            Path of the analyzed csv file

        Returns
        -------
        Union[dict, List[dict]]
            A dictionary filled with data or a list of dictionaries
        """

        if self.interval == "dobowe":
            station_dict_list = []
            with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as csv_f:
                # read first line to determine the separator
                first_line = csv_f.readline().strip()
                if "," in first_line:
                    separator = ","
                elif ";" in first_line:
                    separator = ";"
                else:
                    raise ValueError("No matching separator found in CSV file.")
                # Move file pointer to the beginning
                csv_f.seek(0)
                reader = csv.reader(csv_f, delimiter=separator)
                for row in reader:
                    station_id = int(row[0].replace(" ", ""))
                    if self.station_id == station_id:
                        if int(row[3]) == 2023:
                            station_dict = {
                                "station_id": int(self.station_id),
                                "year": int(row[3]),
                                "month": int(row[4]),
                                "day": int(row[5]),
                                "H": float(row[7]),
                                "Q": float(row[6]),
                                "T": float(row[8]),
                            }
                            station_dict_list.append(station_dict)
                        else:
                            station_dict = {
                                "station_id": int(self.station_id),
                                "year": int(row[3]),
                                "month": int(row[4]),
                                "day": int(row[5]),
                                "H": float(row[6]),
                                "Q": float(row[7]),
                                "T": float(row[8]),
                            }
                            station_dict_list.append(station_dict)
            return station_dict_list
        elif self.interval == "miesieczne":
            station_dict_list = []
            with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as csv_f:
                # read first line to determine the separator
                first_line = csv_f.readline().strip()
                if "," in first_line:
                    separator = ","
                elif ";" in first_line:
                    separator = ";"
                else:
                    raise ValueError("No matching separator found in CSV file.")
                # Move file pointer to the beginning
                csv_f.seek(0)
                reader = csv.reader(csv_f, delimiter=separator)
                for row in reader:
                    station_id = int(row[0].strip())
                    if self.station_id == station_id:
                        if int(row[3]) == 2023:
                            station_dict = {
                                "station_id": int(self.station_id),
                                "year": int(row[3]),
                                "month": int(row[4]),
                            }
                            if int(row[5]) == 1:
                                station_dict["H_min"] = float(row[7])
                                station_dict["Q_min"] = float(row[6])
                                station_dict["T_min"] = float(row[8])
                            elif int(row[5]) == 2:
                                station_dict["H_mean"] = float(row[7])
                                station_dict["Q_mean"] = float(row[6])
                                station_dict["T_mean"] = float(row[8])
                            elif int(row[5]) == 3:
                                station_dict["H_max"] = float(row[7])
                                station_dict["Q_max"] = float(row[6])
                                station_dict["T_max"] = float(row[8])
                            else:
                                pass
                            station_dict_list.append(station_dict)
                        else:
                            station_dict = {
                                "station_id": int(self.station_id),
                                "year": int(row[3]),
                                "month": int(row[4]),
                            }
                            if int(row[5]) == 1:
                                station_dict["H_min"] = float(row[6])
                                station_dict["Q_min"] = float(row[7])
                                station_dict["T_min"] = float(row[8])
                            elif int(row[5]) == 2:
                                station_dict["H_mean"] = float(row[6])
                                station_dict["Q_mean"] = float(row[7])
                                station_dict["T_mean"] = float(row[8])
                            elif int(row[5]) == 3:
                                station_dict["H_max"] = float(row[6])
                                station_dict["Q_max"] = float(row[7])
                                station_dict["T_max"] = float(row[8])
                            else:
                                pass
                            station_dict_list.append(station_dict)
            return station_dict_list
        elif self.interval == "polroczne_i_roczne":
            station_dict = {
                "station_id": int(self.station_id),
                "year": None,
                "winter_min": None,
                "winter_mean": None,
                "winter_max": None,
                "summer_min": None,
                "summer_mean": None,
                "summer_max": None,
                "year_mean": None,
            }

            with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as csv_f:
                # read first line to determine the separator
                first_line = csv_f.readline().replace(" ", "")
                if "," in first_line:
                    separator = ","
                elif ";" in first_line:
                    separator = ";"
                else:
                    raise ValueError("No matching separator found in CSV file.")

                # Flag to check if year column is present
                row = first_line.split(separator)
                is_year_column_present = row[5].strip().isdigit()

                # Move file pointer to the beginning
                csv_f.seek(0)
                reader = csv.reader(csv_f, delimiter=separator)
                for row in reader:
                    station_id = int(row[0].replace(" ", ""))
                    if self.station_id == station_id:
                        if not is_year_column_present:
                            station_dict["year"] = int(row[3])
                            if int(row[4]) == 13:
                                if int(row[6]) == 1:
                                    station_dict["winter_min"] = float(row[7])
                                elif int(row[6]) == 2:
                                    station_dict["winter_mean"] = float(row[7])
                                elif int(row[6]) == 3:
                                    station_dict["winter_max"] = float(row[7])
                                else:
                                    pass
                            elif int(row[4]) == 14:
                                if int(row[6]) == 1:
                                    station_dict["summer_min"] = float(row[7])
                                elif int(row[6]) == 2:
                                    station_dict["summer_mean"] = float(row[7])
                                elif int(row[6]) == 3:
                                    station_dict["summer_max"] = float(row[7])
                                else:
                                    pass
                            elif int(row[4]) == 15:
                                station_dict["year_mean"] = float(row[7])
                            else:
                                pass
                        else:
                            if int(row[3]) == 13:
                                if int(row[5]) == 1:
                                    station_dict["winter_min"] = float(row[6])
                                elif int(row[5]) == 2:
                                    station_dict["winter_mean"] = float(row[6])
                                elif int(row[5]) == 3:
                                    station_dict["winter_max"] = float(row[6])
                                else:
                                    pass
                            elif int(row[3]) == 14:
                                if int(row[5]) == 1:
                                    station_dict["summer_min"] = float(row[6])
                                elif int(row[5]) == 2:
                                    station_dict["summer_mean"] = float(row[6])
                                elif int(row[5]) == 3:
                                    station_dict["summer_max"] = float(row[6])
                                else:
                                    pass
                            elif int(row[3]) == 15:
                                station_dict["year_mean"] = float(row[6])
                            else:
                                pass
            return station_dict
        else:
            return None

    def station_data_to_df(self, start_year=1951, end_year=2023):
        """Use previously downloaded data to analyse chosen period
        for a gauge station

        This function analyses previously downloaded files which have been saved
        to the default location and extracted from zip to csv. The functions goes
        through each file, row by row, looking for the desired gauge station id,
        analysing the first column and when it finds it, it takes the value in
        the 5th column. If it's equal to 15 (yeah, fixed for now), which is mean
        flow for the year, it adds it to a dictionary, where key is year,
        and value's flow.

        Parameters
        ----------
        start_year : int
            First year taken for analysis
        end_year : int
            Last year taken for analysis

        Returns
        -------
        df
            Pandas' dataframe for the given period
        """

        current_path = Path(os.getcwd()).parent
        list_of_dicts = []
        for year in range(start_year, end_year + 1):
            extra_row = None
            if self.interval == "dobowe":
                is_leap = self._is_leap_year(year)
                if year == 2023:
                    file_name = f"codz_{year}"
                    path = f"{current_path}\\data\\downloaded\\dane_hydrologiczne\\{self.interval}\\{year}\\{file_name}.csv"
                    try:
                        dicts = self.station_data_to_dict(path)
                        extra_row = {
                            "station_id": int(self.station_id),
                            "year": year,
                            "month": 4,
                            "day": 29,
                            "H": np.nan,
                            "Q": np.nan,
                            "T": np.nan,
                        }
                        dicts.insert(120, extra_row)
                        list_of_dicts.append(dicts)

                    except FileNotFoundError:
                        print(f"Missing data for: {year}")
                else:
                    for month in range(1, 13):
                        list_of_daily_dicts = []
                        if month < 10:
                            file_name = f"codz_{year}_0{month}"

                        else:
                            file_name = f"codz_{year}_{month}"

                        path = f"{current_path}\\data\\downloaded\\dane_hydrologiczne\\{self.interval}\\{year}\\{file_name}.csv"
                        try:
                            dicts = self.station_data_to_dict(path)
                            list_of_daily_dicts.append(dicts)
                        except FileNotFoundError:
                            print(f"Missing data for: {year}-{month}")
                        if not is_leap and month == 4:
                            extra_row = {
                                "station_id": int(self.station_id),
                                "year": year,
                                "month": 4,
                                "day": 29,
                                "H": np.nan,
                                "Q": np.nan,
                                "T": np.nan,
                            }
                            list_of_daily_dicts[-1].append(extra_row)
                        list_of_dicts.extend(list_of_daily_dicts)
                self._data = (
                    pd.DataFrame(list(np.concatenate(list_of_dicts).flat))
                    # .dropna()
                    .reset_index(drop=True)
                )

            elif self.interval == "miesieczne":
                file_name = f"mies_{year}"
                path = f"{current_path}\\data\\downloaded\\dane_hydrologiczne\\{self.interval}\\{year}\\{file_name}.csv"
                list_of_dicts.append(self.station_data_to_dict(path))
                df = pd.DataFrame(list(np.concatenate(list_of_dicts).flat))
                self._data = df.groupby(by=["year", "month"]).agg(
                    {
                        "H_min": "first",
                        "Q_min": "first",
                        "T_min": "first",
                        "H_mean": "first",
                        "Q_mean": "first",
                        "T_mean": "first",
                        "H_max": "first",
                        "Q_max": "first",
                        "T_max": "first",
                    }
                )

            elif self.interval == "polroczne_i_roczne":
                file_name = f"polr_{self.parameter}_{year}"
                path = f"{current_path}\\data\\downloaded\\dane_hydrologiczne\\{self.interval}\\{year}\\{file_name}.csv"
                list_of_dicts.append(self.station_data_to_dict(path))
                self._data = pd.DataFrame(list_of_dicts).dropna().reset_index(drop=True)

            else:
                pass
        return self._data

    def calculate_hydrological_days(self):
        """Calculate the day of the hydrological year.

        Returns:
        -------
            int: confirmation of execution
        """
        if isinstance(self._data, pd.DataFrame) and not self._data.empty:
            self._data["day_of_hydrological_year"] = (
                self._data.groupby("year").cumcount() + 1
            )
        return 1

    def basic_stats(self):
        """Calculate the most basic statistics for the choosen station

        The function analyzes a Panda's data frame to get min, mean and max
        values for given dataset (period) and number of measurements.

        TODO: dobowe and miesieczne

        Returns
        -------
        df
            Pandas' dataframe
        """
        if self.interval == "dobowe":
            pass

        elif self.interval == "miesieczne":
            pass

        elif self.interval == "polroczne_i_roczne":
            self._data["year_max"] = self._data[["winter_max", "summer_max"]].max(
                axis=1
            )
            self._data["year_min"] = self._data[["winter_min", "summer_min"]].min(
                axis=1
            )
            list_len = self._data.shape[0]

            if self.parameter in ["Q", "H"]:
                wwx = self._data[["winter_max", "summer_max"]].max().max()
                swx = mean(
                    list(self._data["winter_max"]) + list(self._data["summer_max"])
                )
                nwx = self._data[["winter_max", "summer_max"]].min().min()
                wsx = self._data["year_mean"].max()
                ssx = self._data["year_mean"].mean()
                nsx = self._data["year_mean"].min()
                wnx = self._data[["winter_min", "summer_min"]].max().max()
                snx = mean(
                    list(self._data["winter_min"]) + list(self._data["summer_min"])
                )
                nnx = self._data[["winter_min", "summer_min"]].min().min()
                print(
                    f"\nNumber of observations: {list_len}\n"
                    f"WW{self.parameter}: {wwx}\t SW{self.parameter}: {swx:.2f}\t NW{self.parameter}: {nwx}\n"
                    f"WS{self.parameter}: {wsx}\t SS{self.parameter}: {ssx:.2f}\t NS{self.parameter}: {nsx}\n"
                    f"WN{self.parameter}: {wnx}\t SN{self.parameter}: {snx:.2f}\t NN{self.parameter}: {nnx}\n"
                )

            else:
                max_value = self._data[["winter_max", "summer_max"]].max().max()
                mean_value = self._data["year_mean"][0]
                min_value = self._data[["winter_min", "summer_min"]].min().min()
                print(
                    f"Quantity: {list_len}; max: {max_value};\
                    mean: {mean_value:.2f}; min: {min_value}"
                )
            print(
                self._data.describe()
                .round(3)
                .drop("station_id", axis="columns")
                .drop("count", axis="index")
            )
            return wwx, swx, nwx, wsx, ssx, nsx, wnx, snx, nnx

    def calculate_daily_statistics(self):
        """Calculate statistics for each day of the hydrological year."""
        self.calculate_hydrological_days()

        # Grupowanie danych według dnia roku hydrologicznego
        stats = (
            self._data.groupby("day_of_hydrological_year")["Q"]
            .agg(["mean", "median", "max", "min", "count"])
            .reset_index()
        )

        # Zmiana nazw kolumn na bardziej opisowe
        stats.rename(
            columns={
                "mean": "Mean Flow [m³/s]",
                "median": "Median Flow [m³/s]",
                "max": "Max Flow [m³/s]",
                "min": "Min Flow [m³/s]",
                "count": "Count",
            },
            inplace=True,
        )

        return stats

    def plt_rating_curve(self):
        """Print a point graph for each Q and H pair in a dataframe

        Returns:
        -------
            int: confirmation of execution
        """
        plt.figure(figsize=(20, 10))
        sns.scatterplot(
            data=self._data,
            x="Q",
            y="H",
            hue="year",
            palette="viridis",
        )
        plt.title("Rating curve")
        plt.xlabel("Q m3*s-1")
        plt.xlabel("H cm")
        plt.xlim(left=0)
        plt.ylim(bottom=0)
        plt.grid(True)
        plt.legend()
        plt.show()
        return 1

    def plt_daily_flows(self, qlim=None):
        """Create a visualization of flows for each year, displayed one below the other.

        Returns:
        -------
            int: confirmation of execution
        """
        if qlim is None:
            qlim = self._data["Q"].max()
        self.calculate_hydrological_days()
        years = self._data["year"].unique()
        num_years = len(years)

        fig, axs = plt.subplots(
            num_years, 1, figsize=(20, 1.5 * num_years), sharex=True
        )

        for i, year in enumerate(years):
            yearly_data = self._data[self._data["year"] == year]
            sns.lineplot(
                data=yearly_data,
                x="day_of_hydrological_year",
                y="Q",
                ax=axs[i],
            )
            axs[i].set_title(f"{year}")
            axs[i].set_ylabel("Flow m3*s-1")
            axs[i].set_ylim(bottom=0, top=qlim)
            axs[i].set_xticks(range(30, 366, 30))
            axs[i].set_xticklabels(range(30, 366, 30))

        plt.xlabel("Date")
        plt.xlim(left=0, right=367)
        plt.tight_layout()
        plt.show()
        return 1

    def plt_multi_year(self):
        """Print a line graph for maximum, average and minimum values
        for the selected period

        TODO: dobowe and miesieczne.

        Returns:
        -------
            int: confirmation of execution
        """
        plt.figure(figsize=(20, 10))
        sns.lineplot(
            data=self._data,
            x="year",
            y="year_min",
            label=f"Annual min {self.parameter}",
            color="blue",
        )
        sns.lineplot(
            data=self._data,
            x="year",
            y="year_mean",
            label=f"Annual mean {self.parameter}",
            color="green",
        )
        sns.lineplot(
            data=self._data,
            x="year",
            y="year_max",
            label=f"Annual max {self.parameter}",
            color="red",
        )
        plt.xlabel("Year")
        plt.ylabel(f"{self.parameter}")
        plt.xticks(rotation=90, horizontalalignment="center")
        plt.ylim(0)
        plt.grid(True)
        plt.legend()
        plt.show()
        return 1

    def plt_histogram(self, column="year_max", bins=10):
        """Print a histogram for the selected df's column.
        Default column is 'year_max' and bo. of bins is 10.

        Parameters
        ----------
        column : str
            Column selected for analysis

        Returns:
        ----------
            int: confirmation of execution
        """
        plt.hist(self._data[column], bins=bins, color="blue", edgecolor="black")
        plt.show()
        return 1


class ExceedanceAnalysis:
    def __init__(self, df):
        """
        Inicjalizuje obiekt ExceedanceAnalysis z danymi.

        Parametry:
        df (DataFrame): DataFrame zawierający kolumnę 'year_max' z maksymalnymi wartościami przepływu dla każdego roku.
        """
        self.df = df
        self.df_ymax = df[["year_max"]].copy()
        self.probabilities = [
            0.9,
            0.8,
            0.7,
            0.6,
            0.5,
            0.2,
            0.1,
            0.05,
            0.02,
            0.01,
            0.005,
            0.002,
            0.001,
        ]

    def kolmogorov_smirnov_test(self, empirical_data, theoretical_cdf):
        """
        Przeprowadza test Kołmogorowa-Smirnowa dla danych empirycznych i teoretycznej dystrybuanty.

        :param empirical_data: Lista lub tablica z danymi empirycznymi.
        :param theoretical_cdf: Funkcja dystrybuanty teoretycznej.
        :return: Statystyka testu i p-wartość.
        """
        # Sortowanie danych empirycznych
        empirical_data = np.sort(empirical_data)

        # Obliczanie wartości dystrybuanty teoretycznej dla danych empirycznych
        theoretical_values = theoretical_cdf(empirical_data)

        # Przeprowadzanie testu Kołmogorowa-Smirnowa
        ks_statistic, p_value = kstest(empirical_data, theoretical_cdf)

        return ks_statistic, p_value

    def plot(self, return_flows, color, label):
        """
        Tworzy wykres porównujący empiryczne prawdopodobieństwo z teoretycznym rozkładem.

        Parametry:
        return_flows (ndarray): Tablica przepływów powrotnych.
        color (str): Kolor punktów empirycznych.
        label (str): Etykieta dla teoretycznego rozkładu.
        """
        df_sorted = self.df_ymax.sort_values(by="year_max")
        df_sorted["EmpiricalProbability"] = df_sorted.rank() / (len(df_sorted) + 1)
        probabilities_percent = [p * 100 for p in self.probabilities]

        plt.figure(figsize=(10, 6))
        plt.scatter(
            x=100 * (1 - df_sorted["EmpiricalProbability"]),
            y=df_sorted["year_max"],
            color=color,
            label="Prawdopodobieństwo empiryczne",
        )
        sns.lineplot(
            x=probabilities_percent,
            y=return_flows,
            marker="o",
            label=label,
        )
        plt.xscale("log")
        plt.gca().invert_xaxis()
        plt.xticks([0.1, 1, 10, 100], [0.1, 1, 10, 100])
        plt.grid(True, which="both", ls="--")
        plt.xlabel("Prawdopodobieństwo [%]")
        plt.ylabel("Przepływ")
        plt.title("Prawdopodobieństwo przewyższenia przepływu")
        plt.legend()
        plt.show()


class LogNormalAnalysis(ExceedanceAnalysis):
    def __init__(self, df):
        """
        Inicjalizuje obiekt LogNormalAnalysis z danymi.

        Parametry:
        df (DataFrame): DataFrame zawierający kolumnę 'year_max' z maksymalnymi wartościami przepływu dla każdego roku.
        """
        super().__init__(df)
        self.shape, self.loc, self.scale = lognorm.fit(self.df_ymax, floc=0)
        self.return_flows = self.calculate_return_flows(self.probabilities)

    def calculate_return_flows(self, probabilities):
        """
        Oblicza przepływy prawdopodobne dla zadanych prawdopodobieństw na podstawie dopasowanego rozkładu log-normalnego.

        Parametry:
        probabilities (list): Lista prawdopodobieństw.

        Zwraca:
        return_flows (ndarray): Tablica przepływów powrotnych.
        """
        return_flows = lognorm.ppf(
            [1 - p for p in probabilities], self.shape, self.loc, self.scale
        )
        return return_flows

    def test_ks(self):
        """
        Przeprowadza test Kołmogorowa-Smirnowa dla danych empirycznych i teoretycznego rozkładu log-normalnego.
        """
        ks_statistic, p_value = self.kolmogorov_smirnov_test(
            self.df_ymax["year_max"], lognorm(self.shape, self.loc, self.scale).cdf
        )
        print(f"Statystyka testu KS: {ks_statistic}, p-wartość: {p_value}")
        return ks_statistic, p_value

    def plot(self):
        """
        Tworzy wykres porównujący prawdopodobieństwo empiryczne z teoretycznym rozkładem log-normalnym.
        """
        super().plot(
            self.return_flows,
            color="red",
            label="Prawdopodobieństwo teoretyczne (rozkład logarytmiczno-normalny)",
        )


class GenExtremeAnalysis(ExceedanceAnalysis):
    def __init__(self, df):
        """
        Rozkład GEV jest znany również jako rozkład Fishera-Tippetta.
        Rozkład Gumbela (typ I) jest jego szczególnym przypadkiem dla λ = 0 i β = 1.
        Rozkład Weibulla (typ III) jest kolejnym szczególnym przypadkiem dla λ = 1.

        Inicjalizuje obiekt GenExtremeAnalysis z danymi.

        Parametry:
        df (DataFrame): DataFrame zawierający kolumnę 'year_max' z maksymalnymi wartościami przepływu dla każdego roku.
        """
        super().__init__(df)
        self.shape, self.loc, self.scale = genextreme.fit(self.df_ymax)
        self.return_flows = self.calculate_return_flows(self.probabilities)

    def calculate_return_flows(self, probabilities):
        """
        Oblicza przepływy prawdopodobne dla zadanych prawdopodobieństw na podstawie dopasowanego rozkładu GEV.

        Parametry:
        probabilities (list): Lista prawdopodobieństw.

        Zwraca:
        return_flows (ndarray): Tablica przepływów powrotnych.
        """
        return_flows = genextreme.ppf(
            [1 - p for p in probabilities], self.shape, loc=self.loc, scale=self.scale
        )
        return return_flows

    def test_ks(self):
        """
        Przeprowadza test Kołmogorowa-Smirnowa dla danych empirycznych i teoretycznego rozkładu log-normalnego.
        """
        ks_statistic, p_value = self.kolmogorov_smirnov_test(
            self.df_ymax["year_max"], genextreme(self.shape, self.loc, self.scale).cdf
        )
        print(f"Statystyka testu KS: {ks_statistic}, p-wartość: {p_value}")
        return ks_statistic, p_value

    def plot(self):
        """
        Tworzy wykres porównujący prawdopodobieństwo empiryczne z teoretycznym rozkładem GEV.
        """
        super().plot(
            self.return_flows,
            color="red",
            label="Prawdopodobieństwo teoretyczne (rozkład GEV)",
        )


class PearsonIIIAnalysis(ExceedanceAnalysis):
    def __init__(self, df):
        """
        Inicjalizuje obiekt PearsonIIIAnalysis z danymi.

        Parametry:
        df (DataFrame): DataFrame zawierający kolumnę 'year_max' z maksymalnymi wartościami przepływu dla każdego roku.
        """
        super().__init__(df)
        self.shape, self.loc, self.scale = pearson3.fit(self.df_ymax["year_max"])
        self.return_flows = self.calculate_return_flows(self.probabilities)

    def calculate_return_flows(self, probabilities):
        """
        Oblicza przepływy prawdopodobne dla zadanych prawdopodobieństw na podstawie dopasowanego rozkładu Pearsona typu III.

        Parametry:
        probabilities (list): Lista prawdopodobieństw.

        Zwraca:
        return_flows (ndarray): Tablica przepływów powrotnych.
        """
        return_flows = pearson3.ppf(
            [1 - p for p in probabilities], self.shape, self.loc, self.scale
        )
        return return_flows

    def test_ks(self):
        """
        Przeprowadza test Kołmogorowa-Smirnowa dla danych empirycznych i teoretycznego rozkładu log-normalnego.
        """
        ks_statistic, p_value = self.kolmogorov_smirnov_test(
            self.df_ymax["year_max"], pearson3(self.shape, self.loc, self.scale).cdf
        )
        print(f"Statystyka testu KS: {ks_statistic}, p-wartość: {p_value}")
        return ks_statistic, p_value

    def plot(self):
        """
        Tworzy wykres porównujący prawdopodobieństwo empiryczne z teoretycznym rozkładem Pearsona typu III.
        """
        super().plot(
            self.return_flows,
            color="red",
            label="Prawdopodobieństwo teoretyczne (rozkład Pearsona typu III)",
        )


class NonExceedanceAnalysis:
    def __init__(self, df):
        """
        Inicjalizuje obiekt NonexceedanceAnalysis z danymi.

        Parametry:
        df (DataFrame): DataFrame zawierający kolumnę 'year_min' z minimalnymi wartościami przepływu dla każdego roku.
        """
        self.df = df
        self.df_ymin = df[["year_min"]].copy()
        self.probabilities = [
            0.99,
            0.95,
            0.9,
            0.8,
            0.5,
            0.2,
            0.1,
            0.05,
            0.02,
            0.01,
            0.005,
            0.002,
            0.001,
        ]

    def kolmogorov_smirnov_test(self, empirical_data, theoretical_cdf):
        """
        Przeprowadza test Kołmogorowa-Smirnowa dla danych empirycznych i teoretycznej dystrybuanty.

        :param empirical_data: Lista lub tablica z danymi empirycznymi.
        :param theoretical_cdf: Funkcja dystrybuanty teoretycznej.
        :return: Statystyka testu i p-wartość.
        """
        # Sortowanie danych empirycznych
        empirical_data = np.sort(empirical_data)

        # Obliczanie wartości dystrybuanty teoretycznej dla danych empirycznych
        theoretical_values = theoretical_cdf(empirical_data)

        # Przeprowadzanie testu Kołmogorowa-Smirnowa
        ks_statistic, p_value = kstest(empirical_data, theoretical_cdf)

        return ks_statistic, p_value

    def plot(self, return_flows, color, label):
        """
        Tworzy wykres porównujący prawdopodobieństwo empiryczne z rozkładem teoretycznym.

        Parametry:
        return_flows (ndarray): Tablica przepływów prawdopodobnych.
        color (str): Kolor punktów empirycznych.
        label (str): Etykieta dla teoretycznego rozkładu.
        """
        df_sorted = self.df_ymin.sort_values(by="year_min", ascending=False)
        df_sorted["EmpiricalProbability"] = df_sorted.rank(ascending=False) / (
            len(df_sorted) + 1
        )
        probabilities_percent = [p * 100 for p in self.probabilities]

        plt.figure(figsize=(10, 6))
        plt.scatter(
            x=100 * (1 - df_sorted["EmpiricalProbability"]),
            y=df_sorted["year_min"],
            color=color,
            label="Prawdopodobieństwo empiryczne",
        )
        sns.lineplot(
            x=probabilities_percent,
            y=return_flows,
            marker="o",
            label=label,
        )
        plt.xscale("log")
        plt.gca().invert_xaxis()
        plt.xticks([0.1, 1, 10, 100], [0.1, 1, 10, 100])
        plt.grid(True, which="both", ls="--")
        plt.xlabel("Prawdopodobieństwo [%]")
        plt.ylabel("Przepływ")
        plt.title("Prawdopodobieństwo nieosiągnięcia przepływu")
        plt.legend()
        plt.show()


class FisherTippettAnalysis(NonExceedanceAnalysis):
    def __init__(self, df):
        """
        Inicjalizuje obiekt FisherTippettNonexceedanceAnalysis z danymi.

        Parametry:
        df (DataFrame): DataFrame zawierający kolumnę 'year_min' z minimalnymi wartościami przepływu dla każdego roku.
        """
        super().__init__(df)
        self.shape, self.loc, self.scale = genextreme.fit(self.df_ymin)
        self.return_flows = self.calculate_return_flows(self.probabilities)

    def calculate_return_flows(self, probabilities):
        """
        Oblicza przepływy prawdopodobne dla zadanych prawdopodobieństw na podstawie dopasowanego rozkładu Fishera-Tippetta.

        Parametry:
        probabilities (list): Lista prawdopodobieństw.

        Zwraca:
        return_flows (ndarray): Tablica przepływów powrotnych.
        """
        return_flows = genextreme.ppf(probabilities, self.shape, self.loc, self.scale)
        return return_flows

    def test_ks(self):
        """
        Przeprowadza test Kołmogorowa-Smirnowa dla danych empirycznych i teoretycznego rozkładu Fishera-Tippetta.
        """
        ks_statistic, p_value = self.kolmogorov_smirnov_test(
            self.df_ymin["year_min"], genextreme(self.shape, self.loc, self.scale).cdf
        )
        print(f"Statystyka testu KS: {ks_statistic}, p-wartość: {p_value}")
        return ks_statistic, p_value

    def plot(self):
        """
        Tworzy wykres porównujący prawdopodobieństwo empiryczne z teoretycznym rozkładem Fishera-Tippetta.
        """
        super().plot(
            self.return_flows,
            color="blue",
            label="Prawdopodobieństwo teoretyczne (rozkład Fishera-Tippetta)",
        )
