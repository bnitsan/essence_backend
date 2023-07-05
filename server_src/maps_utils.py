import os
import googlemaps
import pandas as pd
import math

google_maps_api = os.getenv('GOOGLE_MAPS_API')
if not google_maps_api:
    with open('../google_maps_api.txt', 'r') as f:
        google_maps_api = f.read().strip()

gmaps = googlemaps.Client(key=google_maps_api)

# dataframe with column 'address' from list
# locations = ['Svinesund', 'Kristiansand', 'Bergen', 'Trondheim', 'North Cape', 'Kirkenes']

def get_lat_long(locations):
    df = pd.DataFrame(locations, columns=['address'])

    for index, row in df.iterrows():
        location = row['address'] # replace 'address' with the name of the column that contains the location data
        geocode_result = gmaps.geocode(location)
        if geocode_result:
            latitude = geocode_result[0]['geometry']['location']['lat']
            longitude = geocode_result[0]['geometry']['location']['lng']
            df.at[index, 'latitude'] = latitude
            df.at[index, 'longitude'] = longitude

def get_center_lat_long(df):
    center_lat = df['latitude'].mean()
    center_long = df['longitude'].mean()
    return center_lat, center_long

def get_distance_moments(df):
    # apply x = cos(lat) * cos(lon), y = cos(lat) * sin(lon), z = sin(lat) on df, add as columns
    df['x'] = df.apply(lambda row: math.cos(math.radians(row['latitude'])) * math.cos(math.radians(row['longitude'])), axis=1)
    df['y'] = df.apply(lambda row: math.cos(math.radians(row['latitude'])) * math.sin(math.radians(row['longitude'])), axis=1)
    df['z'] = df.apply(lambda row: math.sin(math.radians(row['latitude'])), axis=1)
    