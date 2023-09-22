import os
import csv
from statistics import mean
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt


def station_data_to_dict(csv_path, station_id):
    '''function that writes data from a csv file for a desired station to a dictionary

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
    '''

    # dict structure. Keys without values
    station_dict = {
        'id' : int(station_id),
        'year' : None,
        'variable' : None,
        'winter_min' : None,
        'winter_mean': None,
        'winter_max' : None,
        'summer_min' : None,
        'summer_mean': None,
        'summer_max' : None,
        'year_mean' : None
    }

    with open(csv_path, 'r', encoding='utf-8', errors='ignore') as csv_f:
            reader = csv.reader(csv_f)
            for row in reader:
                id = int(row[0].replace(' ', ''))
                if station_id == id:
                    station_dict['year'] = row[3]
                    station_dict['variable'] = row[5]
                    if int(row[4]) == 13:
                        if int(row[6]) == 1:
                            station_dict['winter_min'] = float(row[7])
                        elif int(row[6]) == 2:
                            station_dict['winter_mean'] = float(row[7])
                        elif int(row[6]) == 3:
                            station_dict['winter_max'] = float(row[7])
                        else:
                            pass
                    elif int(row[4]) == 14:
                        if int(row[6]) == 1:
                            station_dict['summer_min'] = float(row[7])
                        elif int(row[6]) == 2:
                            station_dict['summer_mean'] = float(row[7])
                        elif int(row[6]) == 3:
                            station_dict['summer_max'] = float(row[7])
                        else:
                            pass
                    elif int(row[4]) == 15:
                        station_dict['year_mean'] = float(row[7])
                    else:
                        pass
    return station_dict


def analyse_period(start_year, end_year, station_id, param):
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

    interval = 'polroczne_i_roczne'
    current_path = os.getcwd()
    list_of_dicts = []
    for year in range(start_year, end_year):
        file_name = f'polr_{param}_{year}'
        path = f'{current_path}\\data\\downloaded\\{interval}\\{year}\\{file_name}.csv'
        list_of_dicts.append(station_data_to_dict(path, station_id))
    return list_of_dicts


def basic_stats(input_list, param):
    '''Calculate the most basic statistics for a choosen station

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
    '''
    df = pd.DataFrame(input_list)
    list_len = df.shape[0]
    
    if param == 'Q':
        WWQ = df[['winter_max', 'summer_max']].max().max()
        SWQ = mean(list(df['winter_max']) + list(df['summer_max']))
        NWQ = df[['winter_max', 'summer_max']].min().min()
        WSQ = df['year_mean'].max()
        SSQ = df['year_mean'][0]
        NSQ = df['year_mean'].min()
        WNQ = df[['winter_min', 'summer_min']].max().max()
        SNQ = mean(list(df['winter_min']) + list(df['summer_min']))
        NNQ = df[['winter_min', 'summer_min']].min().min()
        print(f'Number of observations: {list_len}\n'
              f'WWQ: {WWQ}\t SWQ: {SWQ:.2f}\t NWQ: {NWQ}\n'
              f'WSQ: {WSQ}\t SSQ: {SSQ:.2f}\t NSQ: {NSQ}\n'
              f'WNQ: {WNQ}\t SNQ: {SNQ:.2f}\t NNQ: {NNQ}\n')
    else:
        max_value = df[['winter_max', 'summer_max']].max().max()
        mean_value = df['year_mean'][0]
        min_value = df[['winter_min', 'summer_min']].min().min()
        print(f'Quantity: {list_len}; max: {max_value};\
              mean: {mean_value:.2f}; min: {min_value}')
    print(df.describe().round(2).drop('id', axis='columns'))
    return df


# plot data
start = 2022-30
end = 2022
df = basic_stats(analyse_period(start, end, 149180020, 'Q'), 'Q')
sns.barplot(x = list(df['year']),
            y = list(df['year_mean']))
plt.xticks(rotation=90, horizontalalignment='center')
plt.show()
