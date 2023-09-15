import os
import csv
import statistics
import seaborn as sns
import matplotlib.pyplot as plt

def analyse_last_30yrs(station_id, param):
    '''Use previously downloaded data to analyse last 30 years
    for a choosen gauge station

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
    dict
        Dict with information about the flow (value) in a given year (key)
    '''

    start_year = 2023 - 30
    stop_year = 2023
    interval = 'polroczne_i_roczne'
    current_path = os.getcwd()
    param_dict = {}
    for year in range(start_year, stop_year):
        file_name = f'polr_{param}_{year}'
        path = f'{current_path}\\data\\downloaded\\{interval}\\{year}\\{file_name}.csv'
        with open(path, 'r', encoding='utf-8', errors='ignore') as csv_f:
            reader = csv.reader(csv_f)
            for row in reader:
                id = int(row[0].replace(' ', ''))
                perdiod = int(row[4])
                if station_id == id and perdiod == 15:
                    param_dict[year] = float(row[7])
                    break
    basic_stats(list(param_dict))
    return param_dict


def basic_stats(input_list):
    '''Calculate the most basic statistics of the data string

    The function analyzes a list containing floating-point 
    numbers, then gives its length, maximum, mean, minimum 
    values and standard deviation

    Parameters
    ----------
    input_list : list
        List with numeric values
    '''
    list_len = len(input_list)
    max_value = max(input_list)
    mean_value = statistics.mean(input_list)
    min_value = min(input_list)
    std_dev = statistics.pstdev(input_list)

    print(f'Quantity: {list_len}; max: {max_value}; mean: {mean_value:.2f};\
          min: {min_value}; standard deviation: {std_dev:.2f}')
    return 1


# plot data
measurements_by_year = analyse_last_30yrs(149180020, 'Q')  # random gauge station
sns.barplot(x = list(measurements_by_year.keys()),
            y = list(measurements_by_year.values()))
plt.xticks(rotation=90, horizontalalignment='center')
plt.show()
