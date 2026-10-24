-- The 10 biggest additions and 10 biggest removals of text on one day.
-- Parameter: event_date, in single quotes: '2026-10-21'.
WITH day AS (
    SELECT domain, title, user_name, is_bot, size_delta, event_time
    FROM curated_edits
    WHERE event_date = ?
      AND size_delta IS NOT NULL
),

additions AS (
    SELECT 'addition' AS kind, * FROM day ORDER BY size_delta DESC LIMIT 10
),

removals AS (
    SELECT 'removal' AS kind, * FROM day ORDER BY size_delta ASC LIMIT 10
)

SELECT * FROM additions
UNION ALL
SELECT * FROM removals
