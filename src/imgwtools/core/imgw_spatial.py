import pandas as pd
import shapefile as shp
from pyproj import Transformer
import matplotlib.pyplot as plt
from imgw_api import HYDRO, SYNOP, METEO


class StationMap:
    def __init__(self, station_id, data_type, shapefile_path):
        """
        Initialize the StationMap with station ID, data type, and shapefile path.

        :param station_id: ID of the station
        :param data_type: Type of data (hydro, synop, meteo)
        :param shapefile_path: Path to the shapefile
        :param measurement_api: API instance to fetch measurement data
        """
        self.station_id = station_id
        self.shapefile_path = shapefile_path
        self.data_type = data_type
        self.measurement_data = self.fetch_measurement_data()
        if data_type != "synop":
            self.station_name = self.measurement_data[0]["nazwa_stacji"].title()
            self.lon = self.measurement_data[0]["lon"]
            self.lat = self.measurement_data[0]["lat"]
            self.station_y, self.station_x = self.reproject_to_epsg2180(
                self.lat, self.lon
            )
        else:
            print("Synoptic data have no information on the location of the stations")

    def fetch_measurement_data(self):
        """
        Fetch measurement data based on the data type.

        :return: Measurement data
        """
        try:
            if self.data_type == "hydro":
                measurement_api = HYDRO(station_id=self.station_id)
                return measurement_api.get_hydro_data()
            elif self.data_type == "synop":
                measurement_api = SYNOP(station_id=self.station_id)
                return measurement_api.get_synop_data()
            else:
                measurement_api = METEO(station_id=self.station_id)
                return measurement_api.get_meteo_data()
        except Exception as e:
            print(f"Error fetching data: {e}")
            return []

    def reproject_to_epsg2180(self, lat, lon):
        """
        Reproject latitude and longitude to EPSG:2180.

        :param lat: Latitude
        :param lon: Longitude
        :return: Reprojected coordinates (x, y)
        """
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:2180")
        y, x = transformer.transform(lat, lon)
        return y, x

    def plot_map(self):
        """
        Plot the map with the station location.
        """
        try:
            sf = shp.Reader(self.shapefile_path)
            plt.figure()
            for shape in sf.shapeRecords():
                x = [i[0] for i in shape.shape.points[:]]
                y = [i[1] for i in shape.shape.points[:]]
                plt.plot(x, y)

            plt.plot(
                self.station_x, self.station_y, "ro"
            )  # 'ro' means red color, circle marker
            if self.data_type == "hydro":
                plt.title(f"{self.station_name} hydrological station")
            else:
                plt.title(f"{self.station_name} meteorological station")
            plt.xlabel("Longitude")
            plt.ylabel("Latitude")
            plt.show()
        except Exception as e:
            print(f"Error plotting map: {e}")

    def plot_stations_from_csv(self, csv_path):
        """
        Plot all stations from a CSV file on the map.

        :param csv_path: Path to the CSV file
        """
        try:
            data = pd.read_csv(csv_path)
            sf = shp.Reader(self.shapefile_path)
            plt.figure()
            for shape in sf.shapeRecords():
                x = [i[0] for i in shape.shape.points[:]]
                y = [i[1] for i in shape.shape.points[:]]
                plt.plot(x, y)

            for index, row in data.iterrows():
                if row["X"] != "NA" and row["Y"] != "NA":
                    station_y, station_x = self.reproject_to_epsg2180(
                        float(row["Y"]), float(row["X"])
                    )
                plt.plot(
                    station_x, station_y, "ro"
                )  # 'ro' means red color, circle marker

            plt.title("Hydrological Stations")
            plt.xlabel("Longitude")
            plt.ylabel("Latitude")
            plt.show()
        except Exception as e:
            print(f"Error plotting stations from CSV: {e}")
