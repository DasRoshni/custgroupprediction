-- Staging layer: clean, leakage-stripped, DQ-gated view over the staging table.
-- Drops post-campaign columns (g1_21, g2_21, c_28) so downstream models cannot
-- accidentally see the answer. The leakage guard at the DATA layer.

SELECT
    -- Group 1 pre-campaign features (20)
    g1_1,  g1_2,  g1_3,  g1_4,  g1_5,
    g1_6,  g1_7,  g1_8,  g1_9,  g1_10,
    g1_11, g1_12, g1_13, g1_14, g1_15,
    g1_16, g1_17, g1_18, g1_19, g1_20,

    -- Group 2 pre-campaign features (20)
    g2_1,  g2_2,  g2_3,  g2_4,  g2_5,
    g2_6,  g2_7,  g2_8,  g2_9,  g2_10,
    g2_11, g2_12, g2_13, g2_14, g2_15,
    g2_16, g2_17, g2_18, g2_19, g2_20,

    -- Comparison pre-campaign features (27)
    c_1,  c_2,  c_3,  c_4,  c_5,
    c_6,  c_7,  c_8,  c_9,  c_10,
    c_11, c_12, c_13, c_14, c_15,
    c_16, c_17, c_18, c_19, c_20,
    c_21, c_22, c_23, c_24, c_25,
    c_26, c_27,

    -- Target as INT64 (staging stores it as STRING)
    SAFE_CAST(target AS INT64) AS target,

    -- Lineage carried through for traceability
    _ingested_at,
    _source,
    _sourcefile_hash,
    _record_hash

FROM {{ source('marketing', 'campaigns_stg') }}
WHERE _dq_status = 'PASSED'
  AND IFNULL(_is_duplicate, FALSE) = FALSE
