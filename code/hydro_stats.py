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
    def __init__(self, station_id, parameter):
        self.station_id = station_id
        self.parameter = parameter
        self._data = []

    def station_data_to_dict(self, csv_path):
        """function that writes data from a csv file for a desired station to a dictionary

        Parameters
        ----------
        csv_path : str
            Path of the analyzed csv file
        station_id : int
            IMGW station id

        Returns
        -------
        dict
            Dict filled with data
        """

        # dict structure. Keys without values
        station_dict = {
            "station_id": int(self.station_id),
            "year": None,
            # "variable": None,
            "winter_min": None,
            "winter_mean": None,
            "winter_max": None,
            "summer_min": None,
            "summer_mean": None,
            "summer_max": None,
            "year_mean": None,
        }

        with open(csv_path, "r", encoding="utf-8", errors="ignore") as csv_f:
            reader = csv.reader(csv_f)
            for row in reader:
                station_id = int(row[0].replace(" ", ""))
                if self.station_id == station_id:
                    station_dict["year"] = row[3]
                    # station_dict["variable"] = row[5]
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
        return station_dict

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
        station_id : int
            IMGW station id
        param : str
            The parameter we want to analyze

        Returns
        -------
        df
            Pandas' dataframe with choosen variable for the given period
        """

        interval = "polroczne_i_roczne"
        current_path = Path(os.getcwd()).parent
        list_of_dicts = []
        for year in range(start_year, end_year):
            file_name = f"polr_{self.parameter}_{year}"
            path = f"{current_path}\\data\\downloaded\\dane_hydrologiczne\\{interval}\\{year}\\{file_name}.csv"
            list_of_dicts.append(self.station_data_to_dict(path))
            self._data = pd.DataFrame(list_of_dicts).dropna().reset_index(drop=True)
        return self._data

    def basic_stats(self):
        """Calculate the most basic statistics for the choosen station

        The function analyzes a Panda's data frame to get min, mean and max
        values for given dataset (period) and number of measurements.

        Parameters
        ----------
        input_list : list
            List of dicts

        Returns
        -------
        df
            Pandas' dataframe
        """
        # df = pd.DataFrame(self._data).dropna().reset_index(drop=True)
        self._data["year_max"] = self._data[["winter_max", "summer_max"]].max(axis=1)
        self._data["year_min"] = self._data[["winter_min", "summer_min"]].min(axis=1)
        # print(df)
        list_len = self._data.shape[0]

        if self.parameter in ["Q", "H"]:
            wwx = self._data[["winter_max", "summer_max"]].max().max()
            swx = mean(list(self._data["winter_max"]) + list(self._data["summer_max"]))
            nwx = self._data[["winter_max", "summer_max"]].min().min()
            wsx = self._data["year_mean"].max()
            ssx = self._data["year_mean"].mean()
            nsx = self._data["year_mean"].min()
            wnx = self._data[["winter_min", "summer_min"]].max().max()
            snx = mean(list(self._data["winter_min"]) + list(self._data["summer_min"]))
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
        return self._data

    def plt_annual_data(self):
        """Print a line graph for maximum, average and minimum values
        for the selected period

        Returns:
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

        Returns:
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
