import requests
import json
from statistics import mean


def establish_connection(data_type):
    url = 'https://danepubliczne.imgw.pl/api/data/' + data_type
    
    # establish connection with IMGW
    r = requests.get(url)
    print("Status code: ", r.status_code)
    return r

def get_data(data_type):
    r = establish_connection(data_type)

    # data to json
    api_data = r.json()

    # get dict keys from the first item
    api_keys = api_data[0].keys()
    print(api_keys)
    return api_data


def save_json_to_file(r):
    with open('imgw_data.json', 'w', encoding='utf-8') as f:
        json.dump(r, f, ensure_ascii=False, indent=4)
    return 1


def calc_average(r, variable):
    vars = []
    for x in r:
        vars.append(float(x[variable]))
    average = mean(vars)
    return average

data_type = input('Hydro or synop?: ')
response = get_data(data_type)
# var = input('Variable: ')
# print(calc_average(response, var))
