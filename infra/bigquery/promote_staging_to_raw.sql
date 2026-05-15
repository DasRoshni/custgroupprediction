-- Promote validated rows from staging to raw.
-- Runs after the DQ validator has updated _dq_status on the loaded batch.
-- Idempotent: rows already in raw (matched by _record_hash) are skipped.
--
-- A "batch" is identified by _sourcefile_hash (one source file = one load).
--
-- Parameters (substitute before running):
--   ${PROJECT_ID}        — GCP project
--   ${SOURCEFILE_HASH}   — SHA-256 of the source file to promote

MERGE `${PROJECT_ID}.marketing.campaigns_raw` AS R
USING (
  SELECT
    g1_1, g1_2, g1_3, g1_4, g1_5, g1_6, g1_7, g1_8, g1_9, g1_10,
    g1_11, g1_12, g1_13, g1_14, g1_15, g1_16, g1_17, g1_18, g1_19, g1_20, g1_21,
    g2_1, g2_2, g2_3, g2_4, g2_5, g2_6, g2_7, g2_8, g2_9, g2_10,
    g2_11, g2_12, g2_13, g2_14, g2_15, g2_16, g2_17, g2_18, g2_19, g2_20, g2_21,
    c_1, c_2, c_3, c_4, c_5, c_6, c_7, c_8, c_9, c_10,
    c_11, c_12, c_13, c_14, c_15, c_16, c_17, c_18, c_19, c_20,
    c_21, c_22, c_23, c_24, c_25, c_26, c_27, c_28,
    SAFE_CAST(target AS INT64) AS target,
    _record_hash
  FROM `${PROJECT_ID}.marketing.campaigns_stg`
  WHERE _sourcefile_hash = '${SOURCEFILE_HASH}'
    AND _dq_status        = 'PASSED'
    AND IFNULL(_is_duplicate, FALSE) = FALSE
) AS S
ON FALSE  -- never match: we only insert
WHEN NOT MATCHED THEN
  INSERT (
    g1_1, g1_2, g1_3, g1_4, g1_5, g1_6, g1_7, g1_8, g1_9, g1_10,
    g1_11, g1_12, g1_13, g1_14, g1_15, g1_16, g1_17, g1_18, g1_19, g1_20, g1_21,
    g2_1, g2_2, g2_3, g2_4, g2_5, g2_6, g2_7, g2_8, g2_9, g2_10,
    g2_11, g2_12, g2_13, g2_14, g2_15, g2_16, g2_17, g2_18, g2_19, g2_20, g2_21,
    c_1, c_2, c_3, c_4, c_5, c_6, c_7, c_8, c_9, c_10,
    c_11, c_12, c_13, c_14, c_15, c_16, c_17, c_18, c_19, c_20,
    c_21, c_22, c_23, c_24, c_25, c_26, c_27, c_28,
    target
  )
  VALUES (
    S.g1_1, S.g1_2, S.g1_3, S.g1_4, S.g1_5, S.g1_6, S.g1_7, S.g1_8, S.g1_9, S.g1_10,
    S.g1_11, S.g1_12, S.g1_13, S.g1_14, S.g1_15, S.g1_16, S.g1_17, S.g1_18, S.g1_19, S.g1_20, S.g1_21,
    S.g2_1, S.g2_2, S.g2_3, S.g2_4, S.g2_5, S.g2_6, S.g2_7, S.g2_8, S.g2_9, S.g2_10,
    S.g2_11, S.g2_12, S.g2_13, S.g2_14, S.g2_15, S.g2_16, S.g2_17, S.g2_18, S.g2_19, S.g2_20, S.g2_21,
    S.c_1, S.c_2, S.c_3, S.c_4, S.c_5, S.c_6, S.c_7, S.c_8, S.c_9, S.c_10,
    S.c_11, S.c_12, S.c_13, S.c_14, S.c_15, S.c_16, S.c_17, S.c_18, S.c_19, S.c_20,
    S.c_21, S.c_22, S.c_23, S.c_24, S.c_25, S.c_26, S.c_27, S.c_28,
    S.target
  );
