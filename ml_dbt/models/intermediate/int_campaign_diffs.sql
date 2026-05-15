-- Intermediate: add engineered comparison features (g1_i - g2_i, g1_i / g2_i).
-- Mirrors what the Python FeatureBuilder produces, so warehouse-side and
-- service-side feature sets stay consistent.

WITH stg AS (
    SELECT * FROM {{ ref('stg_campaigns') }}
)
SELECT
    stg.*,

    -- 20 diff features: g1_i - g2_i
    {% for i in range(1, 21) %}
    g1_{{ i }} - g2_{{ i }} AS d_{{ i }}{% if not loop.last %},{% endif %}
    {% endfor %},

    -- 20 ratio features: SAFE_DIVIDE handles zero denominators (returns NULL)
    {% for i in range(1, 21) %}
    SAFE_DIVIDE(g1_{{ i }}, NULLIF(g2_{{ i }}, 0)) AS r_{{ i }}{% if not loop.last %},{% endif %}
    {% endfor %}

FROM stg
