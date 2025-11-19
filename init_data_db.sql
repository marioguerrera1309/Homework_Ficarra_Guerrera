CREATE TABLE IF NOT EXISTS flights (
    code VARCHAR(50) PRIMARY KEY,
    airport_code VARCHAR(10) NOT NULL,
    country VARCHAR(100) NOT NULL
);
CREATE TABLE IF NOT EXISTS interests (
    email VARCHAR(255) NOT NULL,
    airport_code VARCHAR(10) NOT NULL,
    PRIMARY KEY (email, airport_code)
);