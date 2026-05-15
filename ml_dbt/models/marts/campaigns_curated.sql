-- Curated mart: the canonical feature table consumed by training and
-- (eventually) by Vertex AI Pipelines / batch scoring jobs.
-- Materialized as a clustered table for fast filtered scans.

{{ config(
    materialized='table',
    cluster_by=['target'],
    description='Final feature set: 67 pre-campaign + 20 diffs + 20 ratios + target. No leakage.'
) }}

SELECT * FROM {{ ref('int_campaign_diffs') }}
