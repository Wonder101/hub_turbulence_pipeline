# Aviation Weather Pipeline: Hub Turbulence Tracker 
A fully automated data pipeline ingesting live FAA pilot weather reports (PIREPs/AIREPs), filters them to major U.S. hub airports, scores turbulence severity and displays findings on a live Streamlit dashboard. Built as a personal data engineering project to practice pipeline development with operational data. 
<img width="1420" height="745" alt="Screenshot 2026-07-05 at 3 30 59 PM" src="https://github.com/user-attachments/assets/29054bbe-80e0-4e8f-86e6-66ed84a72ad4" />


## Process 
1. Extracts live AIREP/PIREP cache files from the FAA Aviation Weather Center (updated every minute)
2. Filters reports to within 100 miles of 5 major hubs: ATL, ORD, JFK, LAX, DFW
3. Scores each report's turbulence severity (Mod/Light/Neg/Unk)
4. Loads scored reports into PostgreSQL database via SQLAlchemy
5. Displays live streamlit dashboard showing active report counts, risk breakdowns, reports by hub
6. Runs automatically everyday at noon via macOS cron job (local, put on pause)

## Tech Stack 
Pipeline logic/dashboard: Python 
Ingestion, filtering, transformation: Pandas 
Vectorized haversine distance + turbulence scoring: Numpy 
PostgreSQL connection and data handling: SQLAlchemy + psycopg2 
Dashboard: Streamlit 
Scheduling: cron 

## What I Learned 
- ETL pipeline development
- NumPy vectorization for large scale distance calculations (haversine formula)
- PostgreSQL schema design informed by df.info()
