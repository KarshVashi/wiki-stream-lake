# Every query in this workgroup: writes results to our bucket, is cancelled past
# the scan limit, and reports bytes scanned to CloudWatch. "Enforced" means a
# user's own client settings cannot override any of this.
resource "aws_athena_workgroup" "lake" {
  name          = var.name_prefix
  description   = "Queries over wiki_lake, with a per-query scan limit."
  force_destroy = true # also deletes saved queries and history on destroy

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.bytes_scanned_cutoff

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }

    result_configuration {
      output_location = "s3://${var.results_bucket_name}/results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# One saved query per file in sql/, named after the file.
resource "aws_athena_named_query" "saved" {
  for_each = fileset(var.sql_dir, "*.sql")

  name        = trimsuffix(each.value, ".sql")
  workgroup   = aws_athena_workgroup.lake.name
  database    = var.database_name
  query       = file("${var.sql_dir}/${each.value}")
  description = trimprefix(split("\n", file("${var.sql_dir}/${each.value}"))[0], "-- ")
}
