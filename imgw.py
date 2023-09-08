import wget
import os
import shutil

def check_zip_file_presence(file_name):
    current_path = os.getcwd()

    status = os.path.isfile(current_path + '/data/downloaded/' + file_name)

    if status is True:
        print("This file has already been downloaded")
    return status


def compose_url_filename(data_type, interval, year, month):
    '''Function for creating a url

    This function so far only works for hydrological data.
    The task of this function is to compose the url to the file we are interested in.
    This is done based on the information entered by user.

    Parameters
    ----------
    data_type : str
        Choice between hydrological and meteorological data (in preparation).
    interval : str
        Daily, monthly, half-yearly and annual (these two are grouped together in the file).
    year : int
        Years from 1951 to 2022
    month : int
        Months by hydrological year with the 1st month being November 
        and the 12th month being October. A value of 13 is given if only phenomena in 
        a given year are to be collected

    Returns
    -------
    str
        Composed url for downloading the file
    '''

    if interval == 'dobowe':
        if month < 10:
            month = f'0{month}'  # the month number must always consist of 2 digits
        if month == 13:
            url = f'{public_data_url}/{data_type}/{interval}/{year}/zjaw_{year}.zip'
            f = f'zjaw_{year}.zip'
        else:
            url = f'{public_data_url}/{data_type}/{interval}/{year}/codz_{year}_{month}.zip'
            f = f'codz_{year}_{month}.zip'
    elif interval == 'miesieczne':
        url = f'{public_data_url}/{data_type}/{interval}/{year}/mies_{year}.zip'
        f = f'mies_{year}.zip'
    else:
        url = f'{public_data_url}/{data_type}/{interval}/{year}/polr_{data_variable}_{year}.zip'
        f = f'polr_{data_variable}_{year}.zip'
    
    print('URL address: ', url)
    print('File name: ', f, '\n')
    return url, f


def move_zips():
    '''Function to move all downloaded files

    The function does not take any arguments. All downloaded files will be automatically moved to 
    a new "temp" folder after the task is completed in order to maintain order 

    TODO: perhaps the destination folder should be named differently or be in a different
    location (user's folder?). It would also be useful to have another function to check whether
    a file already exists and whether it is necessary to download this data again
    '''
    # Move all downloaded zip files to a temp folder
    # create a list of all zipped files
    zip_files = [f for f in os.listdir() if '.zip' in f.lower()]

    # create new folder if does not exist yet
    print('Creating a folder for downloaded files... ')
    try:
        os.mkdir('data/downloaded')
    except FileExistsError:
        print('The folder already exists')

    # move the files
    for zip_file in zip_files:
        new_path = 'data/downloaded/' + zip_file
        shutil.move(zip_file, new_path)
    return 1


def unzip_file(file_name):
    '''
    TODO: extracting all newly downloaded files and placing them in the 'temp' folder.
    These files should be temporary and deleted after the script has finished
    executing in order not to duplicate information in different formats. Optionally,
    zip files can be deleted instead so that they are not unzipped every time we 
    want to analyse anything. Currently, data analysis is not possible, but is planned
    '''

    print('Creating a folder for unziped files... ')
    try:
        os.mkdir('data/downloaded/temp')
    except FileExistsError:
        print('The folder already exists')

    shutil.unpack_archive('data/downloaded/' + file_name, 'data/downloaded/temp')
    return 1

public_data_url = 'https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne'
downloaded_files = []

# this should be user's input. Currently unchangeable for testing purpose
data_type = 'dane_hydrologiczne'

while True:
# the while loop is used for error handling.
# If incorrect data is entered, the while loop interrupts the program

    # First input
    # User selects whether they wants daily, monthly or (semi-)annual data
    interval = input('Choose: "dobowe", "miesieczne" or "polroczne_i_roczne": ')
    if interval not in ['dobowe', 'miesieczne', 'polroczne_i_roczne']:
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
    if interval == 'dobowe':
        month = input('Numerical values from 1 (November) to 12 (October), 13 - phenomena: ')
        try:
            month = int(month)
        except ValueError:
            print('The value given is not an integer')
            break
        else:
            if month < 1 or month > 13:
                print("Wrong input")
                break
    else:
        month = ''
    
    # Fourth input
    # In the case of (semi)annual data, the user has to indicate which variable of interest
    if interval == 'polroczne_i_roczne':
        data_variable = input('Choose: "T" - temperature, "Q" - flow, "H" - depth: ')
        if data_variable not in ['T', 'Q', 'H']:
            print('Wrong input')
            break

    # get data from IMGW
    url, f = compose_url_filename(data_type, interval, year, month)
    if check_zip_file_presence(f) is True:
        pass
    else:
        wget.download(url, f)
        downloaded_files.append(f)

    continuation = input('\nEnter "q" to exit or press "Enter" to continue: ')
    if continuation == 'q':
        break

if downloaded_files:
    # move the newly downloaded files
    move_zips()
    # extract them
    unzip_files = input('\nEnter "y" to extract all newly downloaded files: ')
    if unzip_files == 'y':
        # list comprehension instead of "for" loop
        [unzip_file(downloaded_file) for downloaded_file in downloaded_files]
