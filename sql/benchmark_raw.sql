-- Benchmark, JSON side: the same aggregation as benchmark_curated, over one day of
-- raw gzip JSON. raw_edits is partitioned by arrival time, so the day is chosen with
-- the arrival partitions. Parameters: year, month, day. They are text, so type each
-- one in single quotes: '2026', '10', '21'.
SELECT
    domain,
    count(*) AS edits,
    count_if(is_bot) AS bot_edits,
    sum(length_new - length_old) AS net_bytes_added
FROM raw_edits
WHERE year = ?
  AND month = ?
  AND day = ?
GROUP BY domain
ORDER BY edits DESC
LIMIT 20
