import requests
import json


class IMGWAPI:
    """
    A class to interact with the IMGW API to fetch weather and hydrological data.
    """

    def __init__(self):
        """
        Initializes the IMGWAPI instance with the base URL.
        """
        self.base_url = "https://danepubliczne.imgw.pl/api/data/"

    def establish_connection(self, url):
        """
        Establishes a connection to the IMGW API and retrieves data.

        Args:
            url (str): The URL to fetch data from.

        Returns:
            Response object: The response from the API.
        """
        r = requests.get(url)
        print("Status code:", r.status_code)
        return r

    def get_data(self, url):
        """
        Fetches data from the IMGW API and converts it to JSON.

        Args:
            url (str): The URL to fetch data from.

        Returns:
            list: A list of dictionaries containing the data from the API.
        """
        r = self.establish_connection(url)
        api_data = r.json()
        return api_data

    @staticmethod
    def save_json_to_file(data):
        """
        Saves the fetched data to a JSON file.

        Args:
            data (list): The data to save.

        Returns:
            int: Returns 1 upon successful save.
        """
        with open(
            r"../data/downloaded/imgw_api_response.json", "w", encoding="utf-8"
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return 1


class HYDRO(IMGWAPI):
    """
    A class to interact with the IMGW API to fetch hydrological data.
    """

    def __init__(self, station_id=None, data_format="json"):
        """
        Initializes the HYDRO instance with the specified parameters.

        Args:
            station_id (str): ID of the station.
            data_format (str): Format of the data (default is 'json').
        """
        super().__init__()
        self.url = f"{self.base_url}hydro2"
        self.station_id = station_id
        self.data_format = data_format
        self.data = None

    def get_hydro_data(self):
        """
        Fetches hydrological data from the IMGW API.

        Returns:
            list: A list of dictionaries containing the hydrological data from the API.
        """
        self.url += f"/id/{self.station_id}"
        self.data = self.get_data(self.url)
        return self.data


class SYNOP(IMGWAPI):
    """
    A class to interact with the IMGW API to fetch synoptic data.
    """

    def __init__(self, station_id=None, station_name=None, data_format="json"):
        """
        Initializes the SYNOP instance with the specified parameters.

        Args:
            station_id (str): ID of the station.
            station_name (str): Name of the station.
            data_format (str): Format of the data (default is 'json').
        """
        super().__init__()
        self.url = f"{self.base_url}synop"
        self.station_id = station_id
        self.station_name = station_name
        self.data_format = data_format
        self.data = None

    def get_synop_data(self):
        """
        Fetches synoptic data from the IMGW API.

        Returns:
            list: A list of dictionaries containing the synoptic data from the API.
        """
        if self.station_id is not None:
            self.url += f"/id/{self.station_id}"
        else:
            self.url += f"/station/{self.station_name}"
        self.data = self.get_data(self.url)
        return self.data


class METEO(IMGWAPI):
    """
    A class to interact with the IMGW API to fetch meteorological data.
    """

    def __init__(self, station_id=None, data_format="json"):
        """
        Initializes the METEO instance with the specified parameters.

        Args:
            station_id (str): ID of the station.
            data_format (str): Format of the data (default is 'json').
        """
        super().__init__()
        self.url = f"{self.base_url}meteo"
        self.station_id = station_id
        self.data_format = data_format
        self.data = None

    def get_meteo_data(self):
        """
        Fetches meteorological data from the IMGW API.

        Returns:
            list: A list of dictionaries containing the meteorological data from the API.
        """
        self.url += f"/id/{self.station_id}"
        self.data = self.get_data(self.url)
        return self.data


class WARNINGS(IMGWAPI):
    """
    A class to interact with the IMGW API to fetch warnings.
    """

    def __init__(self, warning_type=None, data_format="json"):
        """
        Initializes the WARNINGS instance with the specified parameters.

        Args:
            warning_type (str): warning type (hydro or meteo)
            data_format (str): Format of the data (default is 'json').
        """
        super().__init__()
        self.url = f"{self.base_url}warnings"
        self.warning_type = warning_type
        self.data_format = data_format
        self.data = None

    def get_warnings(self):
        """
        Fetches warnings from the IMGW API.

        Returns:
            list: A list of dictionaries containing the warnings from the API.
        """
        self.url += f"{self.warning_type}"
        self.data = self.get_data(self.url)
        return self.data


class PMAXTPAPI:
    """
    A class to interact with the PMAXTP IMGW's API to fetch theoretical precipitation data
    """

    def __init__(self, method=None, data_type=None, lon=None, lat=None):
        """
        Initializes the PMAXTPAPI instalce with the base URL.
        """
        self.base_url = "https://powietrze.imgw.pl/tpmax-api/point/"
        self.method = method
        self.data_type = data_type
        self.lon = lon
        self.lat = lat
        self.response = None
        self.data = None

    def establish_connection(self, url):
        """
        Establishes a connection to the PMAXTP IMGW API and retrieves data.

        Args:
            url (str): The URL to fetch data from.

        Returns:
            int: Returns 1 upon successful connection
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
            }

        self.response = requests.get(url, timeout=10, headers=headers)
        status_code = self.response.status_code
        print(f"Status code: {status_code}")
        return status_code

    def get_data(self):
        """
        Fetches data from the IMGW API and converts it to JSON.

        Args:
            url (str): The URL to fetch data from.

        Returns:
            list: A dictionary containing the data from the API.
        """
        url = f"{self.base_url}{self.method}/{self.data_type}/{self.lat}/{self.lon}"
        self.establish_connection(url)
        self.data = self.response.json()
        return 1

    def save_json_to_file(self):
        """
        Saves the fetched data to a JSON file.

        Args:
            data (list): The data to save.

        Returns:
            int: Returns 1 upon successful save.
        """
        with open(
            r"../data/downloaded/pmaxtp_imgw_api_response.json", "w", encoding="utf-8"
        ) as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)
        return 1
