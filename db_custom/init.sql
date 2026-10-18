CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
-- нужен для триграммного индекса по синонимам (db_importer/schema.sql); сам импортёр CREATE EXTENSION пропускает
CREATE EXTENSION IF NOT EXISTS pg_trgm;
