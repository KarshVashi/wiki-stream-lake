-- Edits per minute for one day. Parameter: event_date, in single quotes: '2026-10-21'.
SELECT
    date_trunc('minute', event_time) AS minute,
    count(*) AS edits,
    count_if(is_bot) AS bot_edits
FROM curated_edits
WHERE event_date = ?
GROUP BY 1
ORDER BY 1
