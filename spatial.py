import shapefile as shp
from pyproj import Transformer
import matplotlib.pyplot as plt
from imgw_api import HYDRO


class StationMap:
    def __init__(self, station_id, shapefile_path):
        self.station_id = station_id
        self.shapefile_path = shapefile_path
        self.hydro_data = self.fetch_hydro_data()
        self.lon = self.hydro_data[0]["lon"]
        self.lat = self.hydro_data[0]["lat"]
        self.station_y, self.station_x = self.reproject_to_epsg2180(self.lat, self.lon)

    def fetch_hydro_data(self):
        hydro_api = HYDRO(station_id=self.station_id)
        return hydro_api.get_hydro_data()

    def reproject_to_epsg2180(self, lat, lon):
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:2180")
        y, x = transformer.transform(lat, lon)
        return y, x

    def plot_map(self):
        sf = shp.Reader(self.shapefile_path)
        plt.figure()
        for shape in sf.shapeRecords():
            x = [i[0] for i in shape.shape.points[:]]
            y = [i[1] for i in shape.shape.points[:]]
            plt.plot(x, y)

        plt.plot(
            self.station_x, self.station_y, "ro"
        )  # 'ro' means red color, circle marker
        plt.title("Hydrological Stations in Poland")
        plt.xlabel("Longitude")
        plt.ylabel("Latitude")
        plt.show()
