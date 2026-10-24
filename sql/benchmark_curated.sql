-- Benchmark, Parquet side: the same aggregation as benchmark_raw, over one day of
-- curated Parquet. Parameter: event_date, in single quotes: '2026-10-21'.
-- Remove the WHERE line to measure the effect of partition pruning on its own.
SELECT
    domain,
    count(*) AS edits,
    count_if(is_bot) AS bot_edits,
    sum(size_delta) AS net_bytes_added
FROM curated_edits
WHERE event_date = ?
GROUP BY domain
ORDER BY edits DESC
LIMIT 20
