import streamlit as st 
import pandas as pd 
from sqlalchemy import create_engine 

# Step A: Set up page configuration 
st.set_page_config(page_title="Hub Turbulence Tracker", layout="wide") 
st.title("Live Hub Turbulence Tracker") 

# Step B: Connect database 
from dotenv import load_dotenv
import os 
load_dotenv()
engine = create_engine(f'postgresql+psycopg2://{os.getenv("DB_USER")}:{os.getenv("DB_PASSWORD")}@localhost:5432/weather_proj') 

# Step C: Query data 
@st.cache_data(ttl=60) # ttl (time to live) to get new results from the database, we can do 120 seconds since the actual API updates every minute
def load_data(): 
    query = """ 
        select * 
        from hub_turbulence_reports 
        order by observation_time desc 
    """ 
    return pd.read_sql(query, engine) 
df = load_data() 

# Step D: Summary metrics across the top 
col1, col2, col3, col4 = st.columns(4) 
col1.metric('Total Reports', len(df)) 
col2.metric('Moderate Risk', len(df[df['risk_score'] == 'Moderate']))
col3.metric('Light', len(df[df['risk_score'] == 'Light'])) 
col4.metric('Unknown Risk', len(df[df['risk_score'] == 'EDGE-CASE']))

# Step E: Find the nearest hub for each report 
dist_cols = ['dist_atl', 'dist_ord', 'dist_jfk', 'dist_lax', 'dist_dfw']
df['nearest_hub'] = df[dist_cols].idxmin(axis=1).str.replace('dist_', '').str.upper() 

# Step F: Full data table 
st.subheader('Active Reports') 
st.dataframe(df)

# Step G: Count reports per hub
hub_counts = df.groupby('nearest_hub')['aircraft_ref'].count().reset_index() 
# .reset_index use: when you run a group by the columns you grouped up disappear from the main body of the data set
# this renders them useless. If we want to keep using them we can use reset_index to bring them back out of the index role.
hub_counts.columns = ['Hub', 'Reports'] 

# Step H: Draw the chart 
st.subheader('Reports by Hub') 
st.bar_chart(hub_counts, x='Hub', y='Reports') 
