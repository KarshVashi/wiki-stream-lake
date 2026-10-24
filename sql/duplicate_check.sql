-- Any event_id stored more than once. Must return zero rows.
SELECT
    event_id,
    count(*) AS copies
FROM curated_edits
GROUP BY event_id
HAVING count(*) > 1
