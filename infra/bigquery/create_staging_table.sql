-- Creates the staging table with daily partitioning and clustering.
-- Run via:
--   bq query --use_legacy_sql=false --project_id=<PROJECT> < create_staging_table.sql
-- Mirrors staging_schema.json — keep both in sync.

CREATE SCHEMA IF NOT EXISTS `${PROJECT_ID}.marketing`
OPTIONS (
  location = 'US',
  description = 'Marketing campaign analytics — staging and curated layers'
);

CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.marketing.campaigns_stg`
(
  -- Group 1 features (NULLABLE in staging; validated at promotion)
  -- All features FLOAT64 to match real CSV data (avoids INT-vs-FLOAT load errors).
  g1_1  FLOAT64, g1_2  FLOAT64, g1_3  FLOAT64, g1_4  FLOAT64, g1_5  FLOAT64,
  g1_6  FLOAT64, g1_7  FLOAT64, g1_8  FLOAT64, g1_9  FLOAT64, g1_10 FLOAT64,
  g1_11 FLOAT64, g1_12 FLOAT64, g1_13 FLOAT64, g1_14 FLOAT64, g1_15 FLOAT64,
  g1_16 FLOAT64, g1_17 FLOAT64, g1_18 FLOAT64, g1_19 FLOAT64, g1_20 FLOAT64,
  g1_21 FLOAT64,  -- POST-CAMPAIGN — drop before training

  g2_1  FLOAT64, g2_2  FLOAT64, g2_3  FLOAT64, g2_4  FLOAT64, g2_5  FLOAT64,
  g2_6  FLOAT64, g2_7  FLOAT64, g2_8  FLOAT64, g2_9  FLOAT64, g2_10 FLOAT64,
  g2_11 FLOAT64, g2_12 FLOAT64, g2_13 FLOAT64, g2_14 FLOAT64, g2_15 FLOAT64,
  g2_16 FLOAT64, g2_17 FLOAT64, g2_18 FLOAT64, g2_19 FLOAT64, g2_20 FLOAT64,
  g2_21 FLOAT64,  -- POST-CAMPAIGN — drop before training

  c_1  FLOAT64, c_2  FLOAT64, c_3  FLOAT64, c_4  FLOAT64, c_5  FLOAT64,
  c_6  FLOAT64, c_7  FLOAT64, c_8  FLOAT64, c_9  FLOAT64, c_10 FLOAT64,
  c_11 FLOAT64, c_12 FLOAT64, c_13 FLOAT64, c_14 FLOAT64, c_15 FLOAT64,
  c_16 FLOAT64, c_17 FLOAT64, c_18 FLOAT64, c_19 FLOAT64, c_20 FLOAT64,
  c_21 FLOAT64, c_22 FLOAT64, c_23 FLOAT64, c_24 FLOAT64, c_25 FLOAT64,
  c_26 FLOAT64, c_27 FLOAT64,
  c_28 FLOAT64,  -- POST-CAMPAIGN — drop before training

  target STRING,  -- raw string; cast to INT64 during promotion

  -- Lineage
  _ingested_at      TIMESTAMP NOT NULL OPTIONS(description='Load timestamp (UTC)'),
  _source           STRING    NOT NULL OPTIONS(description='Basename of source file'),
  _sourcefile_hash  STRING             OPTIONS(description='SHA-256 of source file'),
  _record_hash      STRING             OPTIONS(description='SHA-256 of business payload for dedup'),

  -- Data quality
  _dq_status    STRING            OPTIONS(description='PENDING | PASSED | FAILED'),
  _dq_errors    ARRAY<STRING>     OPTIONS(description='List of failed DQ rule codes'),
  _is_duplicate BOOL              OPTIONS(description='True if record already promoted')
)
PARTITION BY DATE(_ingested_at)
CLUSTER BY _sourcefile_hash, _dq_status
OPTIONS (
  description = 'Staging table for marketing campaign comparisons. Permissive types; DQ-gated before promotion to campaigns_raw.',
  partition_expiration_days = 90,
  require_partition_filter = FALSE,
  labels = [('env', 'prod'), ('domain', 'marketing'), ('layer', 'staging')]
);
