-- Per user: share of decided A/B comparisons in which the personalized
-- answer was picked (see app/store/comparisons.py). Undecided (pending)
-- comparisons are ignored, as are legacy rows (baseline_vector NOT NULL) whose
-- "generic" arm was the rule-set defaults rather than the unconfigured prompt.
--
-- Run with: psql "$DATABASE_URL" -f scripts/personalized_choice_rate.sql
SELECT
    u.username,
    COUNT(*)                                              AS decided,
    COUNT(*) FILTER (WHERE c.chosen_kind = 'personalized') AS personalized,
    COUNT(*) FILTER (WHERE c.chosen_kind = 'generic')      AS generic,
    ROUND(100.0 * COUNT(*) FILTER (WHERE c.chosen_kind = 'personalized') / COUNT(*), 1)
                                                          AS personalized_pct
FROM (
    SELECT
        learner_id,
        CASE WHEN chosen_variant = 'a' THEN variant_a_kind ELSE variant_b_kind END AS chosen_kind
    FROM answer_comparisons
    WHERE decided_at IS NOT NULL AND baseline_vector IS NULL
) AS c
JOIN users AS u ON u.id = c.learner_id
GROUP BY u.id, u.username
ORDER BY personalized_pct DESC, decided DESC;
