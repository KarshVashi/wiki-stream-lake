-- Share of edits made by bots, for wikis with at least 100 edits.
SELECT
    domain,
    count(*) AS edits,
    count_if(is_bot) AS bot_edits,
    round(100.0 * count_if(is_bot) / count(*), 1) AS bot_percent
FROM curated_edits
WHERE type IN ('edit', 'new')
GROUP BY domain
HAVING count(*) >= 100
ORDER BY edits DESC
LIMIT 20
