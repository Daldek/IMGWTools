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
            r"./data/downloaded/imgw_api_response.json", "w", encoding="utf-8"
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
        Fetches hydrological data from the IMGW API.

        Returns:
            list: A list of dictionaries containing the hydrological data from the API.
        """
        if self.station_id is not None:
            self.url += f"/id/{self.station_id}"
        else:
            self.url += f"/station/{self.station_name}"
        self.data = self.get_data(self.url)
        return self.data
