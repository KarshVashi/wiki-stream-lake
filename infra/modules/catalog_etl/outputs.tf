output "database_name" {
  value = aws_glue_catalog_database.lake.name
}

output "workflow_name" {
  value = aws_glue_workflow.etl.name
}

output "job_name" {
  value = aws_glue_job.curate.name
}

output "crawler_name" {
  value = aws_glue_crawler.raw.name
}
