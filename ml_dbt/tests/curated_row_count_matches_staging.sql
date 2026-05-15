-- Custom singular test: curated row count must equal staging PASSED rows.
-- Returns 1+ rows => test FAILS (counts don't match).

WITH counts AS (
  SELECT
    (SELECT COUNT(*) FROM {{ ref('campaigns_curated') }}) AS curated_n,
    (SELECT COUNT(*) FROM {{ source('marketing', 'campaigns_stg') }}
      WHERE _dq_status = 'PASSED'
        AND IFNULL(_is_duplicate, FALSE) = FALSE) AS stg_passed_n
)
SELECT curated_n, stg_passed_n
FROM counts
WHERE curated_n != stg_passed_n
