import tkinter as tk
from tkinter import messagebox
from imgw_api import PMAXTPAPI  # Upewnij się, że ścieżka importu jest poprawna

def fetch_data():
    method = method_entry.get()
    data_type = data_type_entry.get()
    lon = lon_entry.get()
    lat = lat_entry.get()

    if not method or not data_type or not lon or not lat:
        messagebox.showerror("Błąd", "Wszystkie pola muszą być wypełnione!")
        return

    try:
        api = PMAXTPAPI(method=method, data_type=data_type, lon=lon, lat=lat)
        api.get_data()
        api.save_json_to_file()
        messagebox.showinfo("Sukces", "Dane zostały pobrane i zapisane do pliku JSON.")
    except Exception as e:
        messagebox.showerror("Błąd", f"Wystąpił błąd podczas pobierania danych: {e}")

# Tworzenie głównego okna aplikacji
root = tk.Tk()
root.title("PMAXTP API - Pobieranie danych")

# Etykiety i pola tekstowe dla parametrów
tk.Label(root, text="Metoda:").grid(row=0, column=0, padx=10, pady=5)
method_entry = tk.Entry(root)
method_entry.grid(row=0, column=1, padx=10, pady=5)

tk.Label(root, text="Typ danych:").grid(row=1, column=0, padx=10, pady=5)
data_type_entry = tk.Entry(root)
data_type_entry.grid(row=1, column=1, padx=10, pady=5)

tk.Label(root, text="Długość geograficzna:").grid(row=2, column=0, padx=10, pady=5)
lon_entry = tk.Entry(root)
lon_entry.grid(row=2, column=1, padx=10, pady=5)

tk.Label(root, text="Szerokość geograficzna:").grid(row=3, column=0, padx=10, pady=5)
lat_entry = tk.Entry(root)
lat_entry.grid(row=3, column=1, padx=10, pady=5)

# Przycisk do pobierania danych
fetch_button = tk.Button(root, text="Pobierz dane", command=fetch_data)
fetch_button.grid(row=4, column=0, columnspan=2, pady=10)

# Uruchomienie pętli głównej aplikacji
root.mainloop()