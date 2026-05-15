-- Custom singular test: the curated mart MUST NOT contain post-campaign columns.
-- Returns 1+ rows => test FAILS.
-- Uses INFORMATION_SCHEMA so it checks the actual built table.

SELECT column_name
FROM `{{ target.project }}.{{ target.dataset }}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'campaigns_curated'
  AND column_name IN ('g1_21', 'g2_21', 'c_28')
