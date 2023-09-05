import requests
import json

def get_basics():
    
    # variables
    url = f'https://danepubliczne.imgw.pl/api/data/hydro'
    
    # execute
    r = requests.get(url)
    print("Kod stanu: ", r.status_code)
    
    # data collected from API
    api_data = r.json()

    # get keys from the first item
    api_keys = api_data[0].keys()
    print(api_keys)

    # save to json
    with open('imgw_data.json', 'w', encoding='utf-8') as f:
        json.dump(api_data, f, ensure_ascii=False, indent=4)
    return r

get_basics()
