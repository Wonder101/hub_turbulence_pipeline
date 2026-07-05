# Hub Turbulence Tracker — Study Guide

A complete reference for everything built and learned in this project.
Use this as a review document, interview prep, or a template for future projects.

---

## What You Built

A fully automated data pipeline that:
1. Pulls live FAA pilot weather reports from a government cache file every day at noon
2. Filters them to only reports near 5 major hub airports
3. Scores each report's turbulence severity
4. Stamps each run with a timestamp
5. Stores the results permanently in a PostgreSQL database
6. Displays a live dashboard showing metrics and a chart by hub
7. Runs itself automatically every day via a cron job — no manual intervention needed

**Stack used:** Python · Pandas · NumPy · SQLAlchemy · PostgreSQL · Streamlit · JupyterLab · cron

---

## The Full Pipeline (Architecture)

```
[FAA cache file — updates every minute]
        ↓
[pipeline.py: triggered automatically by cron at noon daily]
        ↓
[pandas: load & decompress .gz in one line]
        ↓
[NumPy haversine: compute distance to each hub for every row]
        ↓
[pandas boolean mask: keep only reports within 100 miles of a hub]
        ↓
[np.select: score each report's turbulence severity]
        ↓
[datetime: stamp each row with pipeline run time]
        ↓
[SQLAlchemy + psycopg2: insert scored rows into PostgreSQL]
        ↓
[Streamlit: live dashboard with metrics and bar chart]
```

---

## Step 1 — Loading the Data

### What it does
Pulls a gzip-compressed CSV from the FAA Aviation Weather Center, decompresses it,
and loads it into a pandas DataFrame — all in one line.

### What kind of file is this?
This is a **cache file** — not a custom API query. The AWC pre-generates a complete
snapshot of all current pilot reports every minute and makes it publicly available at
a fixed URL. You download the whole snapshot and filter it yourself client-side.
This is called **bulk file ingestion**, and the AWC recommends it over custom queries
because it reduces server load and is more reliable.

### Code
```python
import pandas as pd
import numpy as np
import os
from datetime import datetime

df = pd.read_csv(
    'https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz',
    on_bad_lines='skip'
)
```

### Key functions
| Function | What it does |
|---|---|
| `pd.read_csv(url)` | Reads a CSV from a file path or URL into a DataFrame |
| `on_bad_lines='skip'` | Silently drops malformed rows instead of crashing |

### Key concepts
- **gzip (.gz):** A compression format. Pandas automatically detects and decompresses it.
- **`on_bad_lines='skip'`:** Live government feeds occasionally contain malformed rows
  (a comma inside a raw text field breaks the CSV parser). This makes the pipeline
  defensive rather than fragile.

### Inspection functions to know
```python
df.head()           # first 5 rows
df.info()           # column names, data types, non-null counts
df.shape            # (rows, columns) as a tuple
df.columns.tolist() # all column names as a list
df['col'].unique()  # all unique values in a column

# Find completely empty columns — useful for schema cleanup
df.columns[df.isnull().all()].tolist()
```

---

## Step 2 — The Haversine Distance Function

### What it does
Computes the curved-surface distance in miles between two lat/lon points on a sphere.
Used to measure how far each pilot report is from each hub airport.

### Why not flat geometry?
The Earth is a sphere. Simple Pythagorean distance on lat/lon coordinates accumulates
large errors over long distances. Haversine corrects for curvature.

### Code
```python
def haversine(lat1, lon1, lat2, lon2):
    R = 3956  # Earth's radius in miles
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c
```

### How the math works
| Variable | What it represents |
|---|---|
| `R` | Earth's radius — converts the final angle into miles |
| `np.radians()` | Converts degrees to radians (trig functions require radians) |
| `dlat / dlon` | The angular difference in latitude and longitude between the two points |
| `a` | The haversine of the central angle — derived by applying `1 - cos(x) = 2sin²(x/2)` twice to the spherical law of cosines |
| `c` | The actual central angle in radians, recovered via `arctan2` |
| `R * c` | Arc length = radius × angle — the final distance in miles |

### Why `arctan2` and not `arcsin` or plain `arctan`?
- `arcsin` becomes numerically unstable near its domain edges (slope approaches infinity near x=1)
- plain `arctan(y/x)` requires dividing — crashes when x=0, only returns angles in (-90°, 90°)
- `arctan2(y, x)` takes y and x separately, never divides, covers the full 360°, and stays
  numerically stable everywhere

### Key concept: vectorization
When you pass an entire DataFrame column as `lat2` / `lon2`, NumPy doesn't loop row by row —
it applies the math to all rows simultaneously in a single operation.
This is called **vectorization** and is the core reason NumPy exists.

```python
# This computes distance from ATL to all 5,000 report locations at once
df['dist_atl'] = haversine(33.6407, -84.4277, df['latitude'], df['longitude'])
```

### Key concept: functions and reusability
Wrapping the formula in a `def` means you write the math once and call it 5 times
(once per hub) without copy-pasting. Each call only changes the hub coordinates.

### Key functions
| Function | What it does |
|---|---|
| `np.radians()` | Converts degrees to radians |
| `np.sin()` / `np.cos()` | Vectorized trig — operates on entire arrays |
| `np.arctan2(y, x)` | Stable inverse tangent using two separate arguments |
| `np.sqrt()` | Vectorized square root |

---

## Step 3 — Filtering to Hub Reports

### What it does
Creates a True/False column (boolean mask) marking every report within 100 miles of
at least one hub, then uses it to slice the DataFrame down to only those rows.

### Code
```python
hubs = {
    'ATL': (33.6407, -84.4277),
    'ORD': (41.9786, -87.9048),
    'JFK': (40.6399, -73.7787),
    'LAX': (33.9425, -118.4072),
    'DFW': (32.897,  -97.038),
}

for name, (hub_lat, hub_lon) in hubs.items():
    df[f'dist_{name}'] = haversine(hub_lat, hub_lon, df['latitude'], df['longitude'])

threshold = 100  # miles

near_hub_mask = (
    (df['dist_ATL'] < threshold) |
    (df['dist_ORD'] < threshold) |
    (df['dist_JFK'] < threshold) |
    (df['dist_LAX'] < threshold) |
    (df['dist_DFW'] < threshold)
)

near_ds = df[near_hub_mask].copy()
```

### Key concepts

**Boolean mask:** A column of True/False values, one per row. When passed inside `df[mask]`,
pandas keeps only the True rows and discards the rest.

**`|` vs `or`:** Python's `or` keyword works on single True/False values.
Pandas columns contain thousands of values — use `|` for row-by-row OR logic.
Always wrap each condition in parentheses or operator precedence will cause errors.

```python
# Wrong — Python doesn't know how to 'or' 5,000 values
df['dist_ATL'] < 100 or df['dist_ORD'] < 100

# Right — bitwise OR, evaluated row by row
(df['dist_ATL'] < 100) | (df['dist_ORD'] < 100)
```

**`.copy()`:** When you slice a DataFrame with a mask, pandas isn't sure if the result
is a new independent table or a window into the original. Writing new columns onto an
ambiguous slice triggers a `SettingWithCopyWarning`. `.copy()` explicitly creates a
fully independent DataFrame and eliminates the warning.

**f-strings:** `f'dist_{name}'` builds a string dynamically by inserting the variable
`name` into it. Each loop iteration produces a different column name.

### Key functions
| Function | What it does |
|---|---|
| `dict.items()` | Returns each key-value pair so you can unpack both in a for loop |
| `df[mask]` | Boolean indexing — keeps only rows where mask is True |
| `.copy()` | Creates a fully independent copy of a DataFrame slice |

---

## Step 4 — Scoring Turbulence Risk

### What it does
Assigns a human-readable risk label to each report based on its turbulence intensity,
using a vectorized if/elif/else equivalent.

### Code
```python
conditions = [
    near_ds['turbulence_intensity'] == 'MOD',
    near_ds['turbulence_intensity'] == 'LGT',
    near_ds['turbulence_intensity'] == 'NEG',
    pd.isna(near_ds['turbulence_intensity']),
]

choices = ['Moderate', 'Light', 'Negative or None', 'Unknown']

near_ds['risk_score'] = np.select(conditions, choices, default='EDGE-CASE')
```

### Key concept: np.select
`np.select` takes three arguments — all position-based:
- `conditions` — a list of boolean arrays, checked top to bottom
- `choices` — the value to assign when the condition at the same position is True
- `default` — the fallback value if no condition matches

**First match wins.** If a row satisfies multiple conditions, it gets the choice from
the first one. Always put your most severe condition at position 0.

### Key concept: NaN behavior
`NaN` is designed to never equal anything — not even itself.
```python
float('nan') == float('nan')  # False
```
You cannot catch NaN rows with `== NaN`. Use `pd.isna()` instead:
```python
pd.isna(near_ds['turbulence_intensity'])  # True for NaN rows, False for everything else
```

### Key functions
| Function | What it does |
|---|---|
| `np.select(conditions, choices, default)` | Vectorized if/elif/else across entire arrays |
| `pd.isna(series)` | Returns True for NaN values, False for everything else |
| `series.value_counts()` | Counts occurrences of each unique value — good sanity check |

---

## Step 5 — Storing in PostgreSQL

### What it does
Persists your scored DataFrame permanently in a relational database so data survives
after the notebook closes and can be queried by the dashboard.

### PostgreSQL vs MySQL/SQL Server hierarchy
```
PostgreSQL server
└── database (weather_proj)
    └── schema (public — default)
        └── tables (hub_turbulence_reports)
```
In MySQL/SQL Server, database and schema are roughly the same thing.
In PostgreSQL they are distinct layers.

### Step 5a — Create the table in DBeaver
Use `near_ds.info()` to inspect column names and data types before writing this.
```sql
CREATE TABLE IF NOT EXISTS hub_turbulence_reports (
    receipt_time          TIMESTAMP,
    observation_time      TIMESTAMP,
    aircraft_ref          TEXT,
    latitude              FLOAT,
    longitude             FLOAT,
    turbulence_intensity  TEXT,
    risk_score            TEXT,
    dist_atl              FLOAT,
    dist_ord              FLOAT,
    dist_jfk              FLOAT,
    dist_lax              FLOAT,
    dist_dfw              FLOAT,
    pipeline_run_at       TIMESTAMP
);
```

### pandas → PostgreSQL type mapping
| pandas dtype | PostgreSQL type |
|---|---|
| `object` (timestamp strings) | `TIMESTAMP` |
| `object` (text codes) | `TEXT` |
| `float64` | `FLOAT` |
| `int64` | `INTEGER` |

### Step 5b — Build the connection
```python
from sqlalchemy import create_engine

engine = create_engine('postgresql+psycopg2://username:password@localhost:5432/weather_proj')

# Force a real handshake to verify credentials
with engine.connect() as conn:
    print("connection successful")
```

### Step 5c — Push the DataFrame
```python
near_ds = near_ds.rename(columns={
    'dist_ATL': 'dist_atl',
    'dist_ORD': 'dist_ord',
    'dist_JFK': 'dist_jfk',
    'dist_LAX': 'dist_lax',
    'dist_DFW': 'dist_dfw'
})

cols_to_save = [
    'receipt_time', 'observation_time', 'aircraft_ref', 'latitude',
    'longitude', 'turbulence_intensity', 'risk_score',
    'dist_atl', 'dist_ord', 'dist_jfk', 'dist_lax', 'dist_dfw',
    'pipeline_run_at'
]

near_ds[cols_to_save].to_sql(
    name='hub_turbulence_reports',
    con=engine,
    if_exists='append',
    index=False
)
```

### Key concepts

**SQLAlchemy engine:** A configured connection object holding your credentials, host,
port, and database name. Lazy — doesn't actually connect until data needs to move.

**`if_exists` options:**
- `'fail'` — error if table already exists
- `'replace'` — drop and recreate the table every run (loses history)
- `'append'` — add new rows to existing data (correct for a live pipeline)

**`index=False`:** Stops pandas from writing its internal row numbers as an extra column.

**PostgreSQL case sensitivity gotcha:** PostgreSQL lowercases all unquoted column names
at creation time. `dist_ATL` becomes `dist_atl` in the database. Always use lowercase
snake_case for database column names to avoid mismatches.

### Key functions
| Function | What it does |
|---|---|
| `create_engine(connection_string)` | Builds a SQLAlchemy engine |
| `df.to_sql(name, con, if_exists, index)` | Writes a DataFrame to a SQL table |
| `df.rename(columns={old: new})` | Renames columns in a DataFrame |

---

## Step 6 — The Streamlit Dashboard

### What it does
Turns your database into a live webpage showing summary metrics,
a full data table, and a bar chart of reports by hub.

### Code (dashboard.py)
```python
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

st.set_page_config(page_title="Hub Turbulence Tracker", layout="wide")
st.title("Live Hub Turbulence Tracker")

engine = create_engine('postgresql+psycopg2://username:password@localhost:5432/weather_proj')

@st.cache_data(ttl=120)
def load_data():
    query = """
        SELECT *
        FROM hub_turbulence_reports
        ORDER BY observation_time DESC
    """
    return pd.read_sql(query, engine)

df = load_data()

# Summary metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric('Total Reports', len(df))
col2.metric('Moderate Risk', len(df[df['risk_score'] == 'Moderate']))
col3.metric('Light', len(df[df['risk_score'] == 'Light']))
col4.metric('Unknown Risk', len(df[df['risk_score'] == 'EDGE-CASE']))

# Full data table
st.subheader('Active Reports')
st.dataframe(df)

# Bar chart by nearest hub
dist_cols = ['dist_atl', 'dist_ord', 'dist_jfk', 'dist_lax', 'dist_dfw']
df['nearest_hub'] = df[dist_cols].idxmin(axis=1).str.replace('dist_', '').str.upper()

hub_counts = df.groupby('nearest_hub')['aircraft_ref'].count().reset_index()
hub_counts.columns = ['Hub', 'Reports']

st.subheader('Reports by Hub')
st.bar_chart(hub_counts, x='Hub', y='Reports')
```

### Run it from terminal
```bash
streamlit run dashboard.py
```

### Key concepts

**Streamlit execution model:** Every time someone interacts with the page or it
auto-refreshes, Streamlit reruns the entire script from top to bottom. Expensive
operations like database queries should always be cached.

**`@st.cache_data(ttl=120)`:** Caches the query result for 120 seconds.
`ttl` (time to live) controls how long before it re-fetches from the database.

**`axis=1` vs `axis=0`:**
- `axis=0` — operates down each column (across rows)
- `axis=1` — operates across each row (across columns)
`idxmin(axis=1)` finds the column with the smallest value in each row — the nearest hub.

**`groupby` — pandas vs SQL:**
```python
# SQL
SELECT nearest_hub, COUNT(*) FROM table GROUP BY nearest_hub;

# pandas equivalent
df.groupby('nearest_hub')['aircraft_ref'].count().reset_index()
```
`reset_index()` demotes the grouped column from the index back into a regular column.

### Key functions
| Function | What it does |
|---|---|
| `st.set_page_config()` | Sets page title and layout |
| `st.title()` / `st.subheader()` | Adds text headings to the page |
| `st.columns(n)` | Creates n side-by-side columns |
| `col.metric(label, value)` | Displays a large number with a label |
| `st.dataframe(df)` | Renders an interactive table |
| `st.bar_chart(df, x, y)` | Renders a bar chart |
| `pd.read_sql(query, engine)` | Queries a database and returns a DataFrame |
| `df.idxmin(axis=1)` | Returns the column name of the minimum value per row |
| `df.groupby(col)[col].count()` | Counts rows per group — pandas equivalent of SQL GROUP BY + COUNT |
| `.reset_index()` | Demotes the index back into a regular column after groupby |

---

## Step 7 — Automating with a Cron Job

### What it does
Makes your computer run `pipeline.py` automatically on a fixed schedule — no manual
intervention needed. Every day at noon, cron wakes up, executes your script, and
writes the output to a log file.

### What cron is
Cron is a background process (called a daemon) that runs silently on your Mac at all
times. It wakes up every minute, reads a configuration file called the crontab, and
executes any jobs whose schedule matches the current time. You never interact with
cron directly — you edit the crontab and cron reads it automatically.

### The three crontab commands
```bash
crontab -l    # list — show all your scheduled jobs (lowercase L, not number 1)
crontab -e    # edit — open the crontab in a terminal text editor
crontab -r    # remove — delete your entire crontab (careful, no confirmation)
```

To delete a single job without removing everything: use `crontab -e`, delete just
that line, and save.

### The cron line structure
Every cron line has exactly two parts: a schedule and a command.

```
[schedule] [command]
```

The schedule is always exactly 5 fields:
```
[minute] [hour] [day of month] [month] [day of week]
```

| Value | Meaning |
|---|---|
| `*` | Every possible value ("any") |
| `5` | A specific value |
| `*/5` | Every 5th value |
| `1,3,5` | A list of specific values |
| `1-5` | A range |
| Day of week | 0=Sunday, 1=Monday ... 6=Saturday |

### Reading schedule examples out loud
```bash
* * * * *       # every minute
*/5 * * * *     # every 5 minutes
0 12 * * *      # every day at noon (minute 0, hour 12)
0 9 * * 1       # every Monday at 9am
0 0 1 * *       # first day of every month at midnight
0 8 * * 1-5     # every weekday at 8am
```

Use **crontab.guru** to verify any schedule expression before saving it.

### The command half — always use full paths
Cron runs in a minimal environment with no PATH shortcuts. You cannot write `python3`
or `./pipeline.py` — cron won't know where to find them. You need absolute paths.

**Find your Python path:**
```bash
which python3
# returns something like: /opt/anaconda3/bin/python3
```

**Find your script path:**
```bash
pwd   # run this inside the folder your script lives in
# returns something like: /Users/isabella/Documents/Learning/Jupyter
# your full script path is: /Users/isabella/Documents/Learning/Jupyter/pipeline.py
```

### The full cron line — decoded
```bash
0 12 * * * /opt/anaconda3/bin/python3 /Users/isabella/Documents/Learning/Jupyter/pipeline.py >> /Users/isabella/Documents/Learning/Jupyter/pipeline.log 2>&1
```

| Part | What it means |
|---|---|
| `0 12 * * *` | Run at noon every day |
| `/opt/anaconda3/bin/python3` | Full path to Python — required because cron has no PATH |
| `/Users/isabella/.../pipeline.py` | Full path to your script |
| `>>` | Append output to a file (`>` would overwrite, losing history) |
| `/Users/isabella/.../pipeline.log` | Where all print statements go instead of the screen |
| `2>&1` | Redirect error messages (stream 2) into the same log file as normal output (stream 1). Without this, crash messages vanish silently |

### How to build a cron line from scratch (4 questions)
1. How often should this run? → fills in the 5 schedule fields
2. Which Python? → `which python3`
3. Where is the script? → `pwd` in the script's folder, add `/script_name.py`
4. Where should output go? → pick a `.log` file path near the script

### How to add a cron job step by step
```bash
# Step 1: Open crontab in terminal text editor
crontab -e

# If vim opens (screen looks strange, won't let you type):
# Press 'i' to enter insert mode
# Paste your cron line
# Press Escape
# Type :wq and press Enter to save and quit

# If nano opens (friendlier):
# Just paste your line
# Press Ctrl+X, then Y, then Enter

# Step 2: Verify it saved
crontab -l
```

### Mac permissions — critical step
Modern Macs require your terminal app to have Full Disk Access before cron jobs
can read or write files. Without this, cron silently fails with no error message.

```
System Settings → Privacy & Security → Full Disk Access
→ Toggle on Terminal (or iTerm2, whichever you use)
```

### Verifying your job ran
```bash
# Check the log file after the scheduled time
cat /Users/isabella/Documents/Learning/Jupyter/pipeline.log
```

Expected output:
```
Pipeline job date: 2026-06-28 12:00:03.284710
Pipeline starting!
Loaded 889 raw reports
Filtered to 22 hub reports
Inserted 22 rows into PostgreSQL
Pipeline completed!
```

### The pipeline_run_at timestamp
Each row inserted into PostgreSQL is stamped with the exact time the pipeline ran.
This lets you track which batch each row came from and debug duplicates later.

```python
from datetime import datetime

def run_pipeline():
    print(f"Pipeline job date: {datetime.now()}")
    ...
    near_ds['pipeline_run_at'] = datetime.now()
```

### The complete pipeline.py
```python
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import datetime

def haversine(lat1, lon1, lat2, lon2):
    R = 3956
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

def run_pipeline():
    print(f"Pipeline job date: {datetime.now()}")
    print("Pipeline starting!")

    df = pd.read_csv(
        'https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz',
        on_bad_lines='skip'
    )
    print(f"Loaded {len(df)} raw reports")

    hubs = {
        'ATL': (33.6407, -84.4277),
        'ORD': (41.9786, -87.9048),
        'JFK': (40.6399, -73.7787),
        'LAX': (33.9425, -118.4072),
        'DFW': (32.897,  -97.038),
    }
    for name, (hub_lat, hub_lon) in hubs.items():
        df[f'dist_{name}'] = haversine(hub_lat, hub_lon, df['latitude'], df['longitude'])

    threshold = 100
    mask = (
        (df['dist_ATL'] < threshold) |
        (df['dist_ORD'] < threshold) |
        (df['dist_JFK'] < threshold) |
        (df['dist_LAX'] < threshold) |
        (df['dist_DFW'] < threshold)
    )
    near_ds = df[mask].copy()
    print(f"Filtered to {len(near_ds)} hub reports")

    conditions = [
        near_ds['turbulence_intensity'] == 'MOD',
        near_ds['turbulence_intensity'] == 'LGT',
        near_ds['turbulence_intensity'] == 'NEG',
        pd.isna(near_ds['turbulence_intensity']),
    ]
    choices = ['Moderate', 'Light', 'Negative or None', 'Unknown']
    near_ds['risk_score'] = np.select(conditions, choices, default='EDGE-CASE')

    near_ds['pipeline_run_at'] = datetime.now()

    near_ds = near_ds.rename(columns={
        'dist_ATL': 'dist_atl',
        'dist_ORD': 'dist_ord',
        'dist_JFK': 'dist_jfk',
        'dist_LAX': 'dist_lax',
        'dist_DFW': 'dist_dfw'
    })

    cols_to_save = [
        'receipt_time', 'observation_time', 'aircraft_ref', 'latitude',
        'longitude', 'turbulence_intensity', 'risk_score',
        'dist_atl', 'dist_ord', 'dist_jfk', 'dist_lax', 'dist_dfw',
        'pipeline_run_at'
    ]

    engine = create_engine('postgresql+psycopg2://postgres:8319@localhost:5432/weather_proj')
    rows = near_ds[cols_to_save].to_sql(
        name='hub_turbulence_reports',
        con=engine,
        if_exists='append',
        index=False
    )
    print(f"Inserted {rows} rows into PostgreSQL")
    print("Pipeline completed!")

if __name__ == '__main__':
    run_pipeline()
```

### `if __name__ == '__main__'` explained
This is a standard Python pattern. When Python runs a file directly, it sets a special
variable called `__name__` to the string `'__main__'`. When a file is imported by
another script, `__name__` is set to the filename instead.

This means:
- `python pipeline.py` → `__name__ == '__main__'` → `run_pipeline()` executes
- `import pipeline` from another file → `__name__ == 'pipeline'` → `run_pipeline()` does NOT auto-execute

It's a safety guard that lets your file be both runnable directly and importable
as a module without side effects.

---

## Concepts to Know for Interviews

**Vectorization** — operating on entire arrays at once instead of looping row by row.
NumPy and pandas are built around this. It's faster and more readable.

**Boolean indexing** — filtering a DataFrame using a column of True/False values.
The foundation of all data filtering in pandas.

**ETL** — Extract, Transform, Load. The pattern your pipeline follows:
extract from the FAA cache file, transform with haversine + np.select, load into PostgreSQL.

**EL then T** — an alternative pattern where you load raw data first, then transform.
Your pipeline technically does this since you download everything then filter client-side.

**Bulk file ingestion** — downloading a complete pre-packaged dataset rather than
querying for specific records. What you did with the AWC cache file.

**Medallion architecture** — Bronze/Raw → Silver/Cleaned → Gold/Business-ready.
Your pipeline follows this: raw FAA data → filtered near-hub data → scored risk data.

**Upsert** — inserting new rows while skipping duplicates.
In PostgreSQL: `INSERT INTO ... ON CONFLICT DO NOTHING`.

**Schema design** — choosing the right data types before inserting data.
Use `df.info()` to inform decisions rather than guessing.

**Daemon** — a background process that runs silently and persistently.
Cron is a daemon. It never stops running — it just wakes up every minute to check
its schedule.

**Absolute path vs relative path** — a relative path like `./pipeline.py` only works
when your terminal is in the right folder. An absolute path like
`/Users/isabella/Documents/Learning/Jupyter/pipeline.py` works from anywhere.
Cron always requires absolute paths.

---

## What to Build Next

- **Upsert logic:** Add `ON CONFLICT DO NOTHING` to prevent duplicate rows when the
  pipeline runs and finds reports already in the database from a previous run.
- **DBT:** Now that you've manually built a transformation pipeline in SQL + Python,
  DBT formalizes and automates exactly this kind of work at enterprise scale.
- **Icing tracker:** You already have `icing_intensity` in your schema — extend your
  `np.select` scoring to include icing risk alongside turbulence.
- **More hubs:** Add international hubs like LHR or NRT — just add entries to the
  `hubs` dictionary and add corresponding columns to your schema.
- **Alerting:** Add logic to send yourself an email or Slack message when a Moderate
  or higher report appears near a hub. Search "Python smtplib send email" to start.
