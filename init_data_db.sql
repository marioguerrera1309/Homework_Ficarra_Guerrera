CREATE TABLE IF NOT EXISTS flights (
    icao24 VARCHAR(50) PRIMARY KEY,
    callsign VARCHAR(50),
    est_departure_airport VARCHAR(10), --aeroporto di partenza
    est_arrival_airport VARCHAR(10),   --aeroporto di arrivo
    first_seen_utc VARCHAR(30),
    last_seen_utc VARCHAR(30),
    ingestion_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS interests (
    email VARCHAR(255) NOT NULL,
    airport_code VARCHAR(10) NOT NULL,
    high_value INTEGER,
    low_value INTEGER,
    PRIMARY KEY (email, airport_code)
    CONSTRAINT chk_thresholds CHECK (high_value IS NULL OR low_value IS NULL OR high_value > low_value)
);