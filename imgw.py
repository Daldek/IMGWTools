import wget


def compose_url_filename(data_type, data_period_type, year, month):
    # works only for hydrological data

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
    print(f)
    return url, f


public_data_url = 'https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne'

# these should be user's input. Currently fixed values for testing purpose
data_type = 'dane_hydrologiczne'  # unchangeable for now

while True:
# the while loop is used for error handling.
# If incorrect data is entered, the while loop interrupts the program

    # First input
    # User selects whether they wants daily, monthly or (semi-)annual data
    data_period_type = input('Choose: "dobowe", "miesieczne" or "polroczne_i_roczne": ')
    if data_period_type not in ['dobowe', 'miesieczne', 'polroczne_i_roczne']:
        print('Wrong input')
        break
    
    # Second input
    # The year range was limited to the years 1951-2022 due to the availability of data
    # Hydrological years (November to October)
    year = input('Range of (hydrological) years from 1951 to 2022: ')
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
    # In the case of daily data, user must indicate the month of interest
    # Months numbered by hydrological year
    if data_period_type == 'dobowe':
        month = input('Numerical values from 1 (November) to 12 (October): ')  # range 1-12
        try:
            month = int(month)
        except ValueError:
            print('The value given is not an integer')
            break
        else:
            if month < 1 or month > 12:
                print("Wrong input")
                break
    else:
        month = ''
    
    # Fourth input
    # In the case of (semi)annual data, the user has to indicate which variable of interest
    if data_period_type == 'polroczne_i_roczne':
        data_variable = input('Choose: "T" - temperature, "Q" - flow, "H" - depth: ')
        if data_variable not in ['T', 'Q', 'H']:
            print('Wrong input')
            break

    # get data from IMGW
    url, f = compose_url_filename(data_type, data_period_type, year, month)
    wget.download(url, f)

    continuation = input('\nEnter "q" to exit ')
    if continuation == 'q':
        break
