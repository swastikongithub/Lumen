-- Separate database for the test suite, so tests never touch development data.
-- Postgres runs this only when it initialises an empty data volume.
CREATE DATABASE lumen_test;
