import wget
import os
import shutil


def file_path(file_name):
    """Function for creating the destination path of a downloaded file

    In order to keep the file structure identical with IMGW,
    the function creates its destination path based on the file name
    and returns it as str

    Parameters
    ----------
    file_name : str
        Name of downloaded zip file

    Returns
    -------
    str
        Composed destination path
    """
    if file_name[:4] == "codz" or file_name[:4] == "zjaw":
        year = file_name[5:9]
        interval = "dobowe"
    elif file_name[:4] == "mies":
        year = file_name[5:9]
        interval = "miesieczne"
    else:
        year = file_name[7:11]
        interval = "polroczne_i_roczne"

    current_path = os.getcwd()
    path = f"{current_path}\\data\\downloaded\\{interval}\\{year}\\{file_name}"
    return path


def check_zip_file_presence(file_name):
    """
    TODO: newly downloaded files should be saved directly to
    the destination folder, so we can skip 'status_1'
    """
    status_1 = os.path.isfile(file_path(file_name))  # main folder
    status_2 = os.path.isfile(file_name)  # destination folder

    if status_1 is True or status_2 is True:  # can I make it shorter?
        print("This file has already been downloaded")
        status = True
    else:
        status = False
    return status


def compose_url_filename(public_data_url, data_type, interval, year, var):
    """Function for creating a url

    This function so far only works for hydrological data.
    The task of this function is to compose the url to the file we are interested in.
    This is done based on the information entered by user.

    Parameters
    ----------
    public_data_url : str
        Address of the IMGW website with hydrological measurement and observation data
    data_type : str
        Choice between hydrological and meteorological data (in preparation).
    interval : str
        Daily, monthly, half-yearly and annual (these two are grouped together in the file).
    year : int
        Years from 1951 to 2022
    var : int
        Months by hydrological year with the 1st month being November
        and the 12th month being October. A value of 13 is given if only phenomena in
        a given year are to be collected. If polroczne_i_roczne has been choosen,
        user can specify if their would like to get T, Q or H data.

    Returns
    -------
    str
        Composed url for downloading the file
    str
        file name
    """

    if interval == "dobowe":
        if var < 10:
            var = f"0{var}"  # the month number must always consist of 2 digits
        if var == 13:
            url = f"{public_data_url}/{data_type}/{interval}/{year}/zjaw_{year}.zip"
            f = f"zjaw_{year}.zip"
        else:  # I assume that 'else' is 11 or 12. This will be validated later
            url = (
                f"{public_data_url}/{data_type}/{interval}/{year}/codz_{year}_{var}.zip"
            )
            f = f"codz_{year}_{var}.zip"
    elif interval == "miesieczne":
        url = f"{public_data_url}/{data_type}/{interval}/{year}/mies_{year}.zip"
        f = f"mies_{year}.zip"
    else:
        """third option is 'polroczne_i_roczne'. Maybe this should another elif
        and new 'else' should be created to quit script if the input's wrong?"""
        var = var.upper()
        url = f"{public_data_url}/{data_type}/{interval}/{year}/polr_{var}_{year}.zip"
        f = f"polr_{var}_{year}.zip"

    print("URL address: ", url)
    print("File name: ", f, "\n")
    return url, f


def move_zips():
    """Function to move all downloaded files

    The function does not take any arguments. All downloaded files will be automatically moved to
    a new "temp" folder after the task is completed in order to maintain order

    TODO: perhaps the destination folder should be named differently or be in a different
    location (user's folder?). It would also be useful to have another function to check whether
    a file already exists and whether it is necessary to download this data again
    """
    # Move all downloaded zip files to a temp folder
    # create a list of all zipped files
    zip_files = [f for f in os.listdir() if ".zip" in f.lower()]

    # move the files
    for zip_file in zip_files:
        new_path = file_path(zip_file)
        try:
            os.makedirs(os.path.dirname(new_path))
        except FileExistsError:
            pass
        shutil.move(zip_file, new_path)
    return 1


def unzip_file(file_name):
    """
    TODO: These files should be temporary and deleted after the script has finished
    executing in order not to duplicate information in different formats. Optionally,
    zip files can be deleted instead so that they are not unzipped every time we
    want to analyse anything. Currently, data analysis is not possible, but is planned
    """

    zip_file_path = file_path(file_name)
    dir_path = os.path.dirname(zip_file_path)  # needed?
    shutil.unpack_archive(file_path(file_name), dir_path)
    return 1


def get_period(start_year, end_year, public_data_url, data_type, var, downloads_list):
    # Downloading 'polroczne_i_roczne' data for last 30 years
    end_year += 1
    interval = "polroczne_i_roczne"
    for year in range(start_year, end_year):
        url, f = compose_url_filename(public_data_url, data_type, interval, year, var)
        if check_zip_file_presence(f) is True:
            pass
        else:
            wget.download(url, f)
        downloads_list.append(f)
    return 1


public_data_url = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"
downloaded_files = []

# this should be user's input. Currently unchangeable for testing purpose
data_type = "dane_hydrologiczne"

while True:
    # the while loop is used for error handling.
    # If incorrect data is entered, the while loop interrupts the program

    # First input
    # User selects whether they wants daily, monthly or (semi-)annual data
    interval = input(
        f'Choose: "dobowe", "miesieczne" or "polroczne_i_roczne" or\n'
        f'type "all" to get "polroczne_i_roczne" from 1951 to 2023 or\n'
        f'press "Enter" to get "polroczne_i_roczne" from last 30 yrs: '
    ).lower()
    if interval == "":
        print("Semi-annual and annual data for the last 30 years will be pulled")
        break
    elif interval == "all":
        print("The entire range of data will be pulled")
        break
    elif interval not in ["dobowe", "miesieczne", "polroczne_i_roczne"]:
        print("Wrong input")
        break
    else:
        pass

    # Second input
    # The year range was limited to the years 1951-2023 due to the availability of data
    # Hydrological years (November to October)
    year = input("Desired (hydrological) year from 1951 to 2023: ")
    try:
        year = int(year)
    except ValueError:
        print("The value given is not an integer")
        break
    else:
        year = int(year)
        if year < 1951 or year > 2023:
            print("Year given out of data range")
            break

    # Third input
    # In the case of daily data, user must indicate the month of interest
    # Months numbered by hydrological year
    if interval == "dobowe":
        var = input(
            "Numerical values from 1 (November) to 12 (October), 13 - phenomena: "
        )
        try:
            var = int(var)
        except ValueError:
            print("The value given is not an integer")
            break
        else:
            if var < 1 or var > 13:
                print("Wrong input")
                break
    elif interval == "polroczne_i_roczne":
        var = input('Choose: "T" - temperature, "Q" - flow, "H" - depth: ').lower()
        if var not in ["t", "q", "h"]:
            print("Wrong input")
    else:
        var = ""

    # get data from IMGW
    url, f = compose_url_filename(public_data_url, data_type, interval, year, var)
    if check_zip_file_presence(f) is True:
        pass
    else:
        wget.download(url, f)
        downloaded_files.append(f)

    continuation = input('\nEnter "q" to quit or press "Enter" to continue: ').lower()
    if continuation == "q":
        break

if interval == "":
    start = 2023 - 30
    end = 2023
    get_period(start, end, public_data_url, data_type, "Q", downloaded_files)
elif interval == "all":
    get_period(1951, 2023, public_data_url, data_type, "Q", downloaded_files)
else:
    pass

if downloaded_files:
    # move the newly downloaded files
    move_zips()
    # extract them
    unzip_files = input(
        f'\nEnter "y" to extract all newly downloaded files or\n'
        f'press "Enter" to quit '
    ).lower()
    if unzip_files == "y":
        # list comprehension instead of "for" loop
        [unzip_file(downloaded_file) for downloaded_file in downloaded_files]
