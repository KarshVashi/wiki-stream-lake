-- Edits per wiki, across every day in the curated table.
SELECT
    domain,
    count(*) AS edits
FROM curated_edits
GROUP BY domain
ORDER BY edits DESC
LIMIT 20
