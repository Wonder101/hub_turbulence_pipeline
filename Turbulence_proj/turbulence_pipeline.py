import pandas as pd 
import numpy as np 
from sqlalchemy import create_engine 
from datetime import datetime

def haversine(lat1, lon1, lat2, lon2): 
    R = 3956 
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1,lon1,lat2,lon2])
    dlat = lat2 - lat1 
    dlon = lon2 - lon1 
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2 
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c 

def run_pipeline(): 
    print(f'Pipeline job date: {datetime.now()}')
    print('Pipeline starting!') 

    # Extract 
    df = pd.read_csv('https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz', on_bad_lines = 'skip')
    print(f'Loaded {len(df)} raw reports')

    # Transform: distance columns 
    hubs = {
        'ATL': (33.6407, -84.4277),
        'ORD': (41.9786, -87.9048),
        'JFK': (40.6399, -73.7787),
        'LAX': (33.9425, -118.4072),
        'DFW': (32.897,  -97.038),
    }
    for name, (hub_lat, hub_lon) in hubs.items(): 
        df[f'dist_{name}'] = haversine(hub_lat, hub_lon, df['latitude'], df['longitude'])
    
    # Transform: filter to near hubs 
    threshold = 100 
    mask = ( 
        (df['dist_ATL'] < threshold) | 
        (df['dist_ORD'] < threshold) |
        (df['dist_JFK'] < threshold) | 
        (df['dist_LAX'] < threshold) | 
        (df['dist_DFW'] < threshold) 
    )
    near_ds = df[mask].copy() 
    print(f'Filtered to {len(near_ds)} hub reports')

    # Transform: risk scoring 
    conditions = [ 
        near_ds['turbulence_intensity'] == 'MOD', 
        near_ds['turbulence_intensity'] == 'LGT', 
        near_ds['turbulence_intensity'] == 'NEG', 
        pd.isna(near_ds['turbulence_intensity']),
    ]
    choices = ['Moderate', 'Light', 'Negative or None', 'Unknown']
    near_ds['risk_score'] = np.select(conditions, choices, default = 'EDGE-CASE')

    # Transform: rename columns 
    near_ds = near_ds.rename(columns = {
        'dist_ATL': 'dist_atl',
        'dist_ORD': 'dist_ord',
        'dist_JFK': 'dist_jfk',
        'dist_LAX': 'dist_lax',
        'dist_DFW': 'dist_dfw'
    })

    # Load 
    cols_to_save = [
        'receipt_time', 'observation_time', 'aircraft_ref', 'latitude', 
        'longitude', 'turbulence_intensity', 'risk_score', 
        'dist_atl', 'dist_ord', 'dist_jfk', 'dist_lax', 'dist_dfw'
    ]
    
    from dotenv import load_dotenv
    import os 
    load_dotenv()
    engine = create_engine(f'postgresql+psycopg2://{os.getenv("DB_USER")}:{os.getenv("DB_PASSWORD")}@localhost:5432/weather_proj') 
    rows = near_ds[cols_to_save].to_sql(
        name='hub_turbulence_reports', 
        con=engine,
        if_exists='append',
        index=False
    )
    print(f'Inserted {rows} rows into PostgreSQL') 
    print('Pipeline completed!')

# Checks whether the current script is being run directly or being imported as module into another script 
# If run directly, __name__ is set to __main__ 
# If imported into another script, __name__ is set to the actual filename
if __name__ == '__main__': 
    run_pipeline()

# reminder for how to build cron jobs: 
# [minute: 0-59][hour: 0-23][day: 1-31][months: 1-12][weekday: 0-6]