-- Ran in DBeaver, PostgreSQL
CREATE TABLE IF NOT EXISTS hub_turbulence_reports (
    receipt_time          TIMESTAMP,
    observation_time      TIMESTAMP,
    aircraft_ref          TEXT,
    risk_score            TEXT,
    turbulence_intensity  TEXT,
    report_type           TEXT,
    latitude              FLOAT,
    longitude             FLOAT,
    dist_atl              FLOAT,
    dist_ord              FLOAT,
    dist_jfk              FLOAT,
    dist_lax              FLOAT,
    dist_dfw              FLOAT,
    altitude_ft_msl       INTEGER,
    turbulence_type       TEXT,
    turbulence_freq       TEXT,
    icing_type            TEXT,
    icing_intensity       TEXT
);
