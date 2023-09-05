import wget

public_data_url = 'https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne'

# these should be user's input. Currently fixed values for testing purpose
data_type = 'dane_hydrologiczne'
data_period_type = 'dobowe'  # optional: "dobowe", "miesieczne" or "polroczne_i_roczne"
year = 1992
if data_period_type == 'dobowe':
    month = 10  # range 1-12
if data_period_type == 'polroczne_i_roczne':
    data_variable = 'Q'  # optional: "H" or "T"

# join variables to address
if data_period_type == 'dobowe':
    if month < 10:
        month = f'0{month}'
    url = f'{public_data_url}/{data_type}/{data_period_type}/{year}/codz_{year}_{month}.zip'
    f = f'codz_{year}_{month}.zip'
elif data_period_type == 'miesieczne':
    url = f'{public_data_url}/{data_type}/{data_period_type}/{year}/mies_{year}.zip'
    f = f'mies_{year}.zip'
else:
    url = f'{public_data_url}/{data_type}/{data_period_type}/{year}/polr_{data_variable}_{year}.zip'
    f = f'polr_{data_variable}_{year}.zip'

print(url)

# get data from IMGW
wget.download(url, f)
