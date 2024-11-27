"""
Module: hydro_stats

Description: 
This module is used for statistical analysis of hydrological data
 
TODO:
- Translation of documentation into English
- Harmonisation of nomenclature
- Improvements to the StationData class (described further)
- Moving extreme flow calculations to new module
 
Author:
Piotr de Bever
"""

import os
from pathlib import Path
import csv
from statistics import mean
from scipy import stats
from scipy.stats import kstest, lognorm, genextreme, pearson3
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt


class StationData:
    """Class for analysing public hydrological data downloaded from the IMGW service

    TODO:
    - Calculation of the low water sequence volumes
    - Removal of outliers from the flow rating curve and estimation of its function
    - Delimitation of water zones (low, medium, high)
    """

    def __init__(self, station_id, interval="polroczne_i_roczne", parameter=None):
        self.interval = interval
        self.station_id = station_id
        self.parameter = parameter
        self._data = []
        self._h = None

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
        if self.interval == "miesieczne":
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
        if self.interval == "polroczne_i_roczne":
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

    def station_data_to_df(self, period=None):
        """Use previously downloaded data to analyse chosen period
        for a gauge station

        This function analyses previously downloaded files which have been saved
        to the default location and extracted from zip to csv. The functions goes
        through each file, row by row, looking for the desired gauge station id,
        analysing the first column and when it finds it, it takes the value in
        the 5th column. If it's equal to 15 (yeah, fixed for now), which is mean
        flow for the year, it adds it to a dictionary, where key is year,
        and value's flow.

        TODO: obsługa brakujących danych

        Parameters
        ----------
        perdiod : list
            Range of years taken for analysis

        Returns
        -------
        df
            Pandas' dataframe for the given period
        """
        if isinstance(period, int):
            period = [period, period]
        current_path = Path(os.getcwd()).parent
        list_of_dicts = []
        for year in range(period[0], period[1] + 1):
            extra_row = None
            if self.interval == "dobowe":
                is_leap = self._is_leap_year(year)
                if year == 2023:
                    file_name = f"codz_{year}"
                    path = f"{current_path}\\data\\downloaded\\dane_hydrologiczne\\{self.interval}\\{year}\\{file_name}.csv"
                    print(path)
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

    def characteristic_values(self, parameter=None):
        """Calculate the most basic statistics for the choosen station

        The function analyzes a Panda's data frame to get min, mean and max
        values for given dataset (period) and number of measurements.

        TODO: miesieczne

        Returns
        -------
        df
            Pandas' dataframe
        """
        if self.interval == "dobowe":
            self.parameter = parameter
            # Group data by year and calculate max, mean, and min for the chosen parameter
            df = (
                self._data.groupby("year")
                .agg({self.parameter: ["max", "mean", "median", "min"]})
                .reset_index()
            )

            # Rename columns for clarity
            df.columns = [
                "Year",
                f"W{self.parameter}",
                f"S{self.parameter}",
                f"Z{self.parameter}",
                f"N{self.parameter}",
            ]

            #
            wwx = df[f"W{self.parameter}"].max()
            swx = df[f"W{self.parameter}"].mean()
            zwx = df[f"W{self.parameter}"].median()
            nwx = df[f"W{self.parameter}"].min()
            wsx = df[f"S{self.parameter}"].max()
            ssx = df[f"S{self.parameter}"].mean()
            zsx = df[f"S{self.parameter}"].median()
            nsx = df[f"S{self.parameter}"].min()
            wnx = df[f"N{self.parameter}"].max()
            snx = df[f"N{self.parameter}"].mean()
            znx = df[f"N{self.parameter}"].median()
            nnx = df[f"N{self.parameter}"].min()

            # Print characteristics
            print(
                f"WW{self.parameter}: {wwx:.2f}\t SW{self.parameter}: {swx:.2f}\t ZW{self.parameter}: {zwx:.2f}\t NW{self.parameter}: {nwx:.2f}\n"
                f"WS{self.parameter}: {wsx:.2f}\t SS{self.parameter}: {ssx:.2f}\t ZS{self.parameter}: {zsx:.2f}\t NS{self.parameter}: {nsx:.2f}\n"
                f"WN{self.parameter}: {wnx:.2f}\t SN{self.parameter}: {snx:.2f}\t ZN{self.parameter}: {znx:.2f}\t NN{self.parameter}: {nnx:.2f}\n"
            )

        elif self.interval == "miesieczne":
            return None

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
                zwx = self._data[["winter_max", "summer_max"]].median().median()
                nwx = self._data[["winter_max", "summer_max"]].min().min()
                wsx = self._data["year_mean"].max()
                ssx = self._data["year_mean"].mean()
                zsx = self._data["year_mean"].median()
                nsx = self._data["year_mean"].min()
                wnx = self._data[["winter_min", "summer_min"]].max().max()
                snx = mean(
                    list(self._data["winter_min"]) + list(self._data["summer_min"])
                )
                znx = self._data[["winter_min", "summer_min"]].median().median()
                nnx = self._data[["winter_min", "summer_min"]].min().min()
                # Print characteristics
                print(
                    f"WW{self.parameter}: {wwx:.2f}\t SW{self.parameter}: {swx:.2f}\t ZW{self.parameter}: {zwx:.2f}\t NW{self.parameter}: {nwx:.2f}\n"
                    f"WS{self.parameter}: {wsx:.2f}\t SS{self.parameter}: {ssx:.2f}\t ZS{self.parameter}: {zsx:.2f}\t NS{self.parameter}: {nsx:.2f}\n"
                    f"WN{self.parameter}: {wnx:.2f}\t SN{self.parameter}: {snx:.2f}\t ZN{self.parameter}: {znx:.2f}\t NN{self.parameter}: {nnx:.2f}\n"
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
            # return wwx, swx, nwx, wsx, ssx, nsx, wnx, snx, nnx
        else:
            return None
        return wwx, swx, zwx, nwx, wsx, ssx, zsx, nsx, wnx, snx, znx, nnx

    def calculate_water_levels_frequency(self):
        """
        Calculate the frequency of water levels in specified intervals and group them by month.

        This method calculates hydrological days, groups water level data ('H') into specified intervals,
        counts occurrences of 'H' within these intervals for each month, and updates the class attribute
        with the results in a DataFrame.

        TODO: Allowing the selection of a single year for analysis
        """
        # Calculate hydrological days
        self.calculate_hydrological_days()

        # Copy data
        df = self._data[
            ["station_id", "year", "month", "day", "H", "day_of_hydrological_year"]
        ].copy()

        # Define bins based on the minimum and maximum values of 'H'
        min_h = np.floor(df["H"].min() / 10) * 10
        max_h = np.ceil(df["H"].max() / 10) * 10
        bins = range(int(min_h), int(max_h) + 10, 10)
        labels = [(i, i + 10) for i in bins[:-1]]

        # Add column with intervals
        df["H_interval"] = pd.cut(df["H"], bins=bins, labels=labels, right=False)

        # Create an empty list to store results
        results = []

        # Group data and count occurrences of 'H' in each interval and month
        for lower, upper in labels[::-1]:  # Reverse the order of intervals
            row = {"From": lower, "To": upper, "Middle": (lower + upper) * 0.5}
            total_count = 0
            for month in range(1, 13):
                count = df[
                    (df["H_interval"] == (lower, upper)) & (df["month"] == month)
                ].shape[0]
                row[month] = count
                total_count += count
            row["Number of observations"] = total_count
            results.append(row)

        # Create DataFrame from results
        grouped_df = pd.DataFrame(results)

        # Calculate stats
        df_length = len(df)
        grouped_df["Incidance [%]"] = (
            grouped_df["Number of observations"] / df_length
        ) * 100
        grouped_df["Cumulative incidance [%]"] = grouped_df["Incidance [%]"].cumsum()
        grouped_df["Cumulative frequency including higher"] = grouped_df[
            "Number of observations"
        ].cumsum()
        grouped_df["Cumulative frequency including lower"] = df_length - grouped_df[
            "Cumulative frequency including higher"
        ].shift(1, fill_value=0)
        grouped_df.loc[0, "Cumulative frequency including lower"] = df_length

        # Update the class attribute
        self._h = grouped_df
        return self._h

    def calculate_daily_statistics(self):
        """Calculate statistics for each day of the hydrological year."""
        self.calculate_hydrological_days()

        # Grupowanie danych według dnia roku hydrologicznego
        daily_stats = (
            self._data.groupby("day_of_hydrological_year")["Q"]
            .agg(["max", "mean", "median", "min", "count"])
            .reset_index()
        )

        # Zmiana nazw kolumn na bardziej opisowe
        daily_stats.rename(
            columns={
                "max": "Max Flow [m³/s]",
                "mean": "Mean Flow [m³/s]",
                "median": "Median Flow [m³/s]",
                "min": "Min Flow [m³/s]",
                "count": "Count",
            },
            inplace=True,
        )
        return daily_stats

    def calculate_monthly_statistics(self, phenomenon="Q", kind="mean"):
        """Calculate statistics for each month of the hydrological year."""

        # kopiowanie df
        df = self._data[[f"{phenomenon}_{kind}"]].copy()

        # Grupowanie danych według miesiąca roku hydrologicznego
        monthly_stats = (
            df.groupby("month")
            .agg(
                {
                    f"{phenomenon}_{kind}": [
                        "max",
                        "mean",
                        "median",
                        "min",
                        "std",
                        "count",
                    ],
                }
            )
            .reset_index()
        )

        # Spłaszczenie zagnieżdżonych nazw kolumn
        monthly_stats.columns = [
            "_".join(col).strip() if col[1] else col[0]
            for col in monthly_stats.columns.values
        ]

        # Dodanie przedziałów ufności dla `f"{var}_mean_mean"` - średniej z przepływów średnich
        confidence_level = 0.95
        z_score = stats.norm.ppf(
            (1 + confidence_level) / 2
        )  # wartość krytyczna dla poziomu ufności 95%

        # Obliczanie marginesu błędu i dodanie przedziałów ufności
        monthly_stats["CI Lower [m³/s]"] = monthly_stats[
            f"{phenomenon}_{kind}_mean"
        ] - (
            z_score
            * monthly_stats[f"{phenomenon}_{kind}_std"]
            / np.sqrt(monthly_stats[f"{phenomenon}_{kind}_count"])
        )
        monthly_stats["CI Upper [m³/s]"] = monthly_stats[
            f"{phenomenon}_{kind}_mean"
        ] + (
            z_score
            * monthly_stats[f"{phenomenon}_{kind}_std"]
            / np.sqrt(monthly_stats[f"{phenomenon}_{kind}_count"])
        )

        # Przycinanie dolnych przedziałów ufności, aby były nieujemne
        monthly_stats["CI Lower [m³/s]"] = monthly_stats["CI Lower [m³/s]"].clip(
            lower=0
        )
        return monthly_stats

    def rybczynski_method(self, x_selected, y_selected):
        """
        This method calculates the parameters of a linear function based on the Rybczyński method.
        It determines the slope and intercept of the line that fits the extreme values of 'Middle'
        and 'Cumulative frequency including higher'. It then calculates a new intercept for a
        selected point and generates a new line with the same slope passing through the selected point.

        Parameters:
        x_selected (float): The x-coordinate of the selected point.
        y_selected (float): The y-coordinate of the selected point.

        Returns:
        tuple: A tuple containing the slope (a), original intercept (b), new intercept (b_new),
            start and end values of x and y, x and y values for the original line,
            y values for the new line, and the selected x and y coordinates.
        """
        # Extreme values of 'Middle' and corresponding 'Cumulative frequency including higher'
        x_start = self._h[
            "Cumulative frequency including higher"
        ].min()  # Start of the line (smallest X value)
        x_end = self._h[
            "Cumulative frequency including higher"
        ].max()  # End of the line (largest X value)
        y_start = self._h[
            "Middle"
        ].max()  # Largest 'Middle' value (at the start of the plot)
        y_end = self._h[
            "Middle"
        ].min()  # Smallest 'Middle' value (at the end of the plot)

        # Determine the parameters of the linear function (y = ax + b)
        a = (y_end - y_start) / (x_end - x_start)  # Slope
        b = y_start - a * x_start  # Intercept with the Y-axis

        # Calculate the new intercept b_new for the selected point
        x_selected = 66
        y_selected = 145
        b_new = y_selected - a * x_selected  # New intercept with the Y-axis

        # New line with the same slope passing through the selected point
        y_new_line = a * self._h["Cumulative frequency including higher"] + b_new

        x_vals = [x_start, x_end]
        y_vals = [a * x + b for x in x_vals]

        return (
            a,
            b,
            b_new,
            x_start,
            x_end,
            y_start,
            y_end,
            x_vals,
            y_vals,
            y_new_line,
            x_selected,
            y_selected,
        )

    def find_low_sequences(self, year, flow_threshold, min_length=5, max_gap=4):
        """Znajduje ciągi wartości Q mniejszych niż zadany próg przez co najmniej określoną liczbę dni,
        uwzględniając maksymalną dozwoloną przerwę między ciągami.

        Parameters:
        -----------
        year : int
            Rok, dla którego mają zostać znalezione sekwencje.
        flow_threshold :
            float Wartość progowa przepływu Q.
        min_length : int, optional
            Minimalna długość ciągu (domyślnie 5 dni).
        max_gap : int, optional
            Maksymalna dozwolona przerwa między ciągami (domyślnie 4 dni).

        Returns:
        --------
        pd.DataFrame
            DataFrame zawierający połączone sekwencje spełniające warunki.
        """

        df_year = self._data[self._data["year"] == year]
        sequences = []
        current_sequence = []

        for index, row in df_year.iterrows():
            if row["Q"] < flow_threshold:
                current_sequence.append(row)
            else:
                if len(current_sequence) >= min_length:
                    sequences.append(current_sequence)
                current_sequence = []

        # Dodaj ostatnią sekwencję, jeśli spełnia kryterium długości
        if len(current_sequence) >= min_length:
            sequences.append(current_sequence)

        # Łączenie sekwencji, jeśli przerwa między nimi jest mniejsza niż max_gap dni
        merged_sequences = []
        previous_end_day = -1

        for sequence in sequences:
            start_day = sequence[0]["day_of_hydrological_year"]
            if previous_end_day != -1 and (start_day - previous_end_day) < max_gap:
                merged_sequences[-1].extend(sequence)
            else:
                merged_sequences.append(sequence)
            previous_end_day = sequence[-1]["day_of_hydrological_year"]

        # Sprawdzenie, czy są jakiekolwiek sekwencje
        if not merged_sequences:
            print("Brak niżówek w danym roku hydrologicznym.")
            return pd.DataFrame()

        # Wyświetlanie dat początku i końca sekwencji
        for i, sequence in enumerate(merged_sequences):
            start_date = sequence[0][["year", "month", "day"]]
            end_date = sequence[-1][["year", "month", "day"]]
            print(
                f"Sequence {i+1} starts on {start_date['year']}-{start_date['month']}-{start_date['day']}"
            )
            print(
                f"Sequence {i+1} ends on {end_date['year']}-{end_date['month']}-{end_date['day']}"
            )

        # Dodanie identyfikatorów do sekwencji i konwersja na DataFrame
        merged_sequences_df = pd.DataFrame(
            [
                dict(row, sequence_id=i + 1)
                for i, seq in enumerate(merged_sequences)
                for row in seq
            ]
        )
        return merged_sequences_df

    def plt_rating_curve(self, year=None, season=None, qlim=None, hlim=None):
        """Print a point graph for each Q and H pair in a dataframe

        Returns:
        -------
            int: confirmation of execution
        """
        if year is not None:
            df = self._data[self._data["year"] == year].copy()
        else:
            df = self._data.copy()

        if season == "winter":
            df = df[df["month"] <= 6].copy()
        elif season == "summer":
            df = df[df["month"] > 6].copy()
        elif season == "all":
            df.loc[:, "season"] = df["month"].apply(
                lambda x: "Półrocze zimowe" if x <= 6 else "Półrocze letnie"
            )
        else:
            df = df.copy()
            df.loc[:, "season"] = "viridis"

        plt.figure(figsize=(20, 10))
        sns.scatterplot(
            data=df,
            x="Q",
            y="H",
            hue="season" if season == "all" else "year",
            palette=None if season == "all" else "viridis",
            legend="full",
            s=120,
            alpha=0.85,
        )
        plt.title("Rating curve")
        plt.xlabel("Q m³s⁻¹")
        plt.ylabel("H cm")
        plt.xlim(right=hlim)
        plt.ylim(top=qlim)
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

    def plt_daily_flows_characteristics(self, qlim=None):
        """Print a line graph for maximum, mean, median and minimum values
        for the selected period

        Parameters:
        -----------
        qlim : float, optional
            Upper limit for the Y axis. If not specified, it is set to the maximum flow value Q.

        Returns:
        -------
            int: confirmation of execution
        """
        # calculate the upper limit for the Y axis
        if qlim is None:
            qlim = self._data["Q"].max()

        # Calculate daily statistics and hydrological days
        daily_stats = self.calculate_daily_statistics()
        self.calculate_hydrological_days()

        # Define plot size and colors for each line
        plt.figure(figsize=(20, 10))
        flow_stats = {
            "Max Flow [m³/s]": "red",
            "Mean Flow [m³/s]": "black",
            "Median Flow [m³/s]": "orange",
            "Min Flow [m³/s]": "blue",
        }

        # Loop through flow statistics to generate lines
        for stat, color in flow_stats.items():
            sns.lineplot(
                data=daily_stats,
                x="day_of_hydrological_year",
                y=stat,
                color=color,
                label=stat,
            )

        plt.xlabel("Days of hydrological year")
        plt.ylabel("Q [m³/s]")
        plt.xlim(left=0, right=367)
        plt.ylim(bottom=0, top=qlim)
        plt.xticks(range(30, 366, 30))
        plt.grid(True)
        plt.legend()
        plt.show()
        return 1

    def plt_confidence_interval(self, phenomenon="Q", kind="mean"):
        """Generates a graph of flows with confidence intervals.

        TODO: dzienne i roczne, inne charakterystyki

        Parameters:
        -----------
        qlim : float, optional
            Upper limit for the Y axis. If not specified, it is set to the maximum flow value Q.

        Returns:
        -------
            int: confirmation of execution
        """
        # Obliczanie miesięcznych statystyk
        monthly_stats = self.calculate_monthly_statistics(
            phenomenon=phenomenon, kind=kind
        )

        # Definiowanie rozmiaru wykresu
        plt.figure(figsize=(20, 10))

        # Tworzenie wykresu przepływów
        plt.plot(
            monthly_stats["month"],
            monthly_stats[f"{phenomenon}_{kind}_max"],
            color="red",
            label=f"{phenomenon}_{kind}_max",
        )

        plt.plot(
            monthly_stats["month"],
            monthly_stats[f"{phenomenon}_{kind}_mean"],
            color="black",
            label=f"{phenomenon}_{kind}_mean",
        )

        plt.plot(
            monthly_stats["month"],
            monthly_stats[f"{phenomenon}_{kind}_median"],
            color="orange",
            label=f"{phenomenon}_{kind}_median",
        )

        plt.plot(
            monthly_stats["month"],
            monthly_stats[f"{phenomenon}_{kind}_min"],
            color="blue",
            label=f"{phenomenon}_{kind}_min",
        )

        # Dodanie przedziałów ufności dla średniego przepływu
        plt.fill_between(
            monthly_stats["month"],
            monthly_stats["CI Lower [m³/s]"],
            monthly_stats["CI Upper [m³/s]"],
            color="gray",
            alpha=0.3,
            label="95% Confidence Interval",
        )

        # Dostosowanie etykiet i ograniczeń osi
        plt.xlabel("Month")
        plt.ylabel(f"{phenomenon}")
        plt.xlim(left=1, right=12)
        plt.ylim(bottom=0)
        plt.xticks(range(1, 13))
        plt.grid(True)
        plt.legend()
        plt.show()
        return 1

    def plt_multi_year_characteristics(self):
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
            label=f"N{self.parameter}",
            color="blue",
        )
        sns.lineplot(
            data=self._data,
            x="year",
            y="year_mean",
            label=f"S{self.parameter}",
            color="orange",
        )
        sns.lineplot(
            data=self._data,
            x="year",
            y="year_max",
            label=f"W{self.parameter}",
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
        Default column is 'year_max' and no. of bins is 10.

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

    def plt_water_level_frequency(self, method=None, x_selected=None, y_selected=None):
        """
        Plot the water levels using seaborn and matplotlib.
        This method creates a line plot for 'Cumulative Total' vs 'Middle'
        and a line plot for 'Total Count' vs 'Middle'.

        Parameters:
        method (str, optional): The method to use for plotting. Defaults to None.
        x_selected (float, optional): The x-coordinate of the selected point. Defaults to None.
        y_selected (float, optional): The y-coordinate of the selected point. Defaults to None.

        Returns:
        int: confirmation of code execution
        """
        # Plotting data
        plt.figure(figsize=(14, 8))

        # Line plot for 'Cumulative frequency including higher' vs 'Middle'
        sns.lineplot(
            data=self._h,
            x="Cumulative frequency including higher",
            y="Middle",
            marker="o",
            color="red",
            label="Krzywa sum czasów trwania stanów wód wraz z wyższymi",
        )

        # Line plot for 'Number of observations' vs 'Middle'
        plt.plot(
            self._h["Number of observations"],
            self._h["Middle"],
            linestyle="-",
            color="blue",
            label="Krzywa częstości",
        )

        if method == "rybczynski":
            (
                a,
                b,
                b_new,
                x_start,
                x_end,
                y_start,
                y_end,
                x_vals,
                y_vals,
                y_new_line,
                x_selected,
                y_selected,
            ) = self.rybczynski_method(x_selected, y_selected)

            # Adding the line connecting the extreme values of 'Middle'
            x_vals = [x_start, x_end]
            y_vals = [a * x + b for x in x_vals]
            plt.plot(
                x_vals,
                y_vals,
                linestyle="--",
                color="grey",
            )

            # New line with the same slope passing through the selected point
            plt.plot(
                self._h["Cumulative frequency including higher"],
                y_new_line,
                linestyle="--",
                color="grey",
                # label=f"Nowa linia przechodząca przez punkt ({x_selected}, {y_selected})",
            )

            # Adding horizontal lines
            max_obs_index = self._h[
                "Number of observations"
            ].idxmax()  # Index of the maximum observation

            # NTW - stan najdłużej trwający (the longest-lasting state)
            ntw = self._h.loc[max_obs_index, "Middle"]  # Corresponding 'Middle' value

            plt.axhline(
                y=y_selected - 10,  # y-position of the horizontal line
                color="red",
                linestyle="--",
                label=f"Górna granica strefy wody średniej: {y_selected:.0f} cm",
            )

            plt.axhline(
                y=ntw,  # y-position of the horizontal line
                color="blue",
                linestyle="--",
                label=f"Dolna granica strefy wody średniej: {ntw:.0f} cm",
            )

            # Fill the area below the horizontal lines
            plt.fill_between(
                self._h["Cumulative frequency including higher"],
                y_selected - 10,
                y_start,
                color="red",
                alpha=0.1,
                label="Strefa stanów wody wysokiej",
            )

            plt.fill_between(
                self._h["Cumulative frequency including higher"],
                ntw,
                y_selected - 10,
                color="green",
                alpha=0.1,
                label="Strefa stanów wody średniej",
            )
            min_y_plot = (self._h["From"].min()) - 10
            plt.fill_between(
                self._h["Cumulative frequency including higher"],
                min_y_plot,
                ntw,
                color="blue",
                alpha=0.1,
                label="Strefa stanów wody niskiej",
            )
            plt.title(
                "Wykres krzywej częstości i podział sumy czasów trwania"
                "stanów wody na strefy metodą Rybczyńskiego"
            )
        else:
            x_end = self._h[
                "Cumulative frequency including higher"
            ].max()  # największa wartość X
            min_y_plot = (self._h["From"].min()) - 10
            plt.title("Wykres krzywej częstości i sumy czasów trwania stanów wody")

        # Adding labels
        plt.xlabel("Czas [dni]")
        plt.ylabel("H [cm]")
        plt.xlim(left=0, right=x_end + 1)
        plt.ylim(bottom=min_y_plot)
        plt.legend(loc="upper right")
        plt.grid(True)
        plt.show()
        return 1

    def plot_low_sequences(self, year, flow_threshold, min_length=5, max_gap=4):
        """Wykresy danych Q dla podanego roku z wyróżnionymi sekwencjami,
        gdzie wartości Q są mniejsze niż zadany próg.

        Parameters:
        -----------
        year : int
            Rok, dla którego mają zostać wygenerowane wykresy.
        flow_threshold : float
            Wartość progowa przepływu Q.
        min_length : int, optional
            Minimalna długość ciągu (domyślnie 5 dni).
        max_gap : int, optional
            Maksymalna dozwolona przerwa między ciągami (domyślnie 4 dni).

        Returns:
        ----------
            int: confirmation of execution

        TODO: Set the default threshold as SNQ
        """

        df_year = self._data[self._data["year"] == year]
        sequences_df = self.find_low_sequences(
            year, flow_threshold, min_length, max_gap
        )

        if sequences_df.empty:
            return

        plt.figure(figsize=(20, 10))

        # Wykres oryginalnych danych Q
        plt.plot(
            df_year["day_of_hydrological_year"],
            df_year["Q"],
            label="Original Q Data",
            color="blue",
        )

        # Zakreskowanie sekwencji na czerwono, uwzględniając identyfikatory sekwencji
        for sequence_id in sequences_df["sequence_id"].unique():
            sequence_df = sequences_df[sequences_df["sequence_id"] == sequence_id]
            plt.fill_between(
                sequence_df["day_of_hydrological_year"],
                sequence_df["Q"],
                color="red",
                alpha=0.3,
                hatch="/",
            )

        # Pozioma linia q_threshold
        plt.axhline(
            y=flow_threshold,
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"flow_threshold = {flow_threshold}",
        )

        plt.xlabel("Day")
        plt.ylabel("Q (m³/s)")
        plt.title(f"Sequences of Q < {flow_threshold} in {year}")
        plt.xlim(left=0, right=367)
        plt.ylim(bottom=0)
        plt.xticks(range(30, 366, 30))
        plt.legend()
        plt.grid(True)
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
