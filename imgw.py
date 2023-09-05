import wget

public_data_url = 'https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne'

# these should be user's input. Currently fixed values for testing purpose
data_type = 'dane_hydrologiczne'  # unchangeable for now

while True:
    # First input
    data_period_type = input('Choose: "dobowe", "miesieczne" or "polroczne_i_roczne": ')
    if data_period_type not in ['dobowe', 'miesieczne', 'polroczne_i_roczne']:
        print('Wrong input')
        break
    
    # Second input
    year = input('Range of years from 1951 to 2022: ')
    try:
        year = int(year)
    except ValueError:
        print('The value given is not an integer')
        break
    else:
        year = int(year)
        if year < 1951 or year > 2022:
            print("Year given out of data range")
            break
    
    # Third input
    if data_period_type == 'dobowe':
        month = input('Numerical values from 1 to 12: ')  # range 1-12
        try:
            month = int(month)
        except ValueError:
            print('The value given is not an integer')
            break
        else:
            if month < 1 or month > 12:
                print("Wrong input")
                break
    
    # Fourth input
    if data_period_type == 'polroczne_i_roczne':
        data_variable = input('Choose: "T", "Q" or "H": ')
        if data_variable not in ['T', 'Q', 'H']:
            print('Wrong input')
            break

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
    break
