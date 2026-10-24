locals {
  raw_path      = "s3://${var.lake_bucket_name}/raw/edits/"
  curated_path  = "s3://${var.lake_bucket_name}/curated/edits/"
  scripts_s3    = "s3://${var.artifacts_bucket_name}/glue"
  job_name      = "${var.name_prefix}-curate-edits"
  crawler_name  = "${var.name_prefix}-raw-edits"
  raw_table     = "raw_edits"
  curated_table = "curated_edits"
}

resource "aws_glue_catalog_database" "lake" {
  name        = var.database_name
  description = "Wikipedia edits: raw_edits (crawled JSON) and curated_edits (Parquet)."
}

# ---------------------------------------------------------------- IAM
# One role for the crawler and the job: both are Glue, both touch the same data.

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "${var.name_prefix}-glue"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

# AWS's baseline for Glue: Data Catalog access, CloudWatch logs and metrics.
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_data" {
  statement {
    sid       = "ListLake"
    actions   = ["s3:ListBucket"]
    resources = [var.lake_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/edits/*", "curated/edits/*"]
    }
  }

  statement {
    sid       = "ReadRaw"
    actions   = ["s3:GetObject"]
    resources = ["${var.lake_bucket_arn}/raw/edits/*"]
  }

  statement {
    sid       = "WriteCurated"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.lake_bucket_arn}/curated/edits/*"]
  }

  statement {
    sid       = "ReadScriptsWriteTemp"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.artifacts_bucket_arn}/glue/*", "${var.artifacts_bucket_arn}/glue-temp/*"]
  }

  statement {
    sid       = "ListArtifacts"
    actions   = ["s3:ListBucket"]
    resources = [var.artifacts_bucket_arn]
  }
}

resource "aws_iam_role_policy" "glue_data" {
  name   = "lake-data"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_data.json
}

# Glue writes to these fixed log groups. Creating them here gives them a 7-day
# retention; otherwise Glue creates them on first run with no expiry.
resource "aws_cloudwatch_log_group" "glue" {
  for_each = toset([
    "/aws-glue/crawlers",
    "/aws-glue/jobs/output",
    "/aws-glue/jobs/error",
    "/aws-glue/jobs/logs-v2",
  ])

  name              = each.value
  retention_in_days = 7
}

# ---------------------------------------------------------------- raw: crawler

resource "aws_glue_crawler" "raw" {
  name          = local.crawler_name
  database_name = aws_glue_catalog_database.lake.name
  role          = aws_iam_role.glue.arn

  # The crawler names the table after the folder it crawls (edits), so the
  # prefix makes it raw_edits.
  table_prefix = "raw_"

  s3_target {
    path = local.raw_path
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  recrawl_policy {
    recrawl_behavior = "CRAWL_EVERYTHING"
  }

  configuration = jsonencode({
    Version = 1.0
    # One table for the whole prefix, even if hourly files differ slightly.
    Grouping = { TableGroupingPolicy = "CombineCompatibleSchemas" }
    # New partitions take the table's schema instead of their own guess.
    CrawlerOutput = { Partitions = { AddOrUpdateBehavior = "InheritFromTable" } }
  })

  depends_on = [aws_cloudwatch_log_group.glue]
}

# ---------------------------------------------------------------- curated: table in code
# Defined here rather than crawled: the schema is ours, and partition projection
# lets Athena work out the event_date partitions without a crawler or MSCK REPAIR.

resource "aws_glue_catalog_table" "curated" {
  name          = local.curated_table
  database_name = aws_glue_catalog_database.lake.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL                              = "TRUE"
    classification                        = "parquet"
    "parquet.compression"                 = "SNAPPY"
    "projection.enabled"                  = "true"
    "projection.event_date.type"          = "date"
    "projection.event_date.format"        = "yyyy-MM-dd"
    "projection.event_date.range"         = "2026-01-01,NOW"
    "projection.event_date.interval"      = "1"
    "projection.event_date.interval.unit" = "DAYS"
    "storage.location.template"           = "${local.curated_path}event_date=$${event_date}/"
  }

  partition_keys {
    name = "event_date"
    type = "string"
  }

  storage_descriptor {
    location      = local.curated_path
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = [
        ["event_id", "string"],
        ["event_time", "timestamp"],
        ["domain", "string"],
        ["wiki", "string"],
        ["type", "string"],
        ["namespace", "int"],
        ["title", "string"],
        ["user_name", "string"],
        ["is_anonymous", "boolean"],
        ["is_bot", "boolean"],
        ["is_minor", "boolean"],
        ["comment", "string"],
        ["length_old", "bigint"],
        ["length_new", "bigint"],
        ["revision_old", "bigint"],
        ["revision_new", "bigint"],
        ["size_delta", "bigint"],
      ]

      content {
        name = columns.value[0]
        type = columns.value[1]
      }
    }
  }
}

# ---------------------------------------------------------------- the Spark job

resource "aws_s3_object" "script" {
  for_each = toset(["curate_edits.py", "transforms.py"])

  bucket = var.artifacts_bucket_name
  key    = "glue/${each.value}"
  source = "${var.scripts_dir}/${each.value}"
  etag   = filemd5("${var.scripts_dir}/${each.value}") # re-upload when the file changes
}

resource "aws_glue_job" "curate" {
  name              = local.job_name
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "5.1"
  worker_type       = "G.1X" # 1 DPU per worker
  number_of_workers = 2      # the minimum; 2 DPU in total
  timeout           = 15     # minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "${local.scripts_s3}/curate_edits.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"        = "python"
    "--job-bookmark-option" = "job-bookmark-enable"
    "--extra-py-files"      = "${local.scripts_s3}/transforms.py"
    "--TempDir"             = "s3://${var.artifacts_bucket_name}/glue-temp/"
    "--database"            = aws_glue_catalog_database.lake.name
    "--raw_table"           = local.raw_table
    "--curated_path"        = local.curated_path
  }

  execution_property {
    max_concurrent_runs = 1 # two runs overwriting the same partitions would race
  }

  depends_on = [aws_s3_object.script, aws_cloudwatch_log_group.glue]
}

# ---------------------------------------------------------------- workflow
# start trigger -> crawler -> (crawler succeeded) -> job
# A workflow allows only one start trigger, so the schedule is a setting on it.

resource "aws_glue_workflow" "etl" {
  name        = "${var.name_prefix}-etl"
  description = "Crawl raw_edits, then rebuild the curated_edits partitions it touched."
}

resource "aws_glue_trigger" "start" {
  name              = "${var.name_prefix}-etl-start"
  workflow_name     = aws_glue_workflow.etl.name
  type              = var.etl_schedule == null ? "ON_DEMAND" : "SCHEDULED"
  schedule          = var.etl_schedule
  start_on_creation = var.etl_schedule != null

  actions {
    crawler_name = aws_glue_crawler.raw.name
  }
}

resource "aws_glue_trigger" "after_crawl" {
  name              = "${var.name_prefix}-etl-after-crawl"
  workflow_name     = aws_glue_workflow.etl.name
  type              = "CONDITIONAL"
  start_on_creation = true

  predicate {
    conditions {
      crawler_name = aws_glue_crawler.raw.name
      crawl_state  = "SUCCEEDED"
    }
  }

  actions {
    job_name = aws_glue_job.curate.name
  }
}
