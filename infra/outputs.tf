output "name_prefix" {
  description = "Prefix used for every resource name."
  value       = local.name_prefix
}

output "lake_bucket" {
  description = "Lake bucket: raw/, curated/, errors/ and runs/."
  value       = module.storage.lake_bucket_name
}

output "athena_results_bucket" {
  description = "Athena query results, expire after 7 days."
  value       = module.storage.athena_results_bucket_name
}

output "artifacts_bucket" {
  description = "Glue scripts and other build artifacts, versioned."
  value       = module.storage.artifacts_bucket_name
}

output "budget_name" {
  description = "Monthly cost budget."
  value       = module.guardrails.budget_name
}

# Read by the Makefile and scripts/run_task.py.

output "aws_region" {
  description = "Region everything runs in."
  value       = var.aws_region
}

output "ecr_repository_url" {
  description = "Where make image pushes the producer image."
  value       = module.producer_task.ecr_repository_url
}

output "ecs_cluster" {
  description = "Cluster the producer task runs in."
  value       = module.producer_task.cluster_name
}

output "producer_task_family" {
  description = "Producer task definition family."
  value       = module.producer_task.task_family
}

output "producer_container" {
  description = "Container name inside the task definition."
  value       = module.producer_task.container_name
}

output "producer_subnets" {
  description = "Default-VPC public subnets the task runs in."
  value       = module.producer_task.subnet_ids
}

output "producer_security_group" {
  description = "Outbound-HTTPS-only security group for the task."
  value       = module.producer_task.security_group_id
}

output "producer_log_group" {
  description = "CloudWatch log group for the producer."
  value       = module.producer_task.log_group_name
}

output "edits_stream_name" {
  description = "Kinesis stream the producer writes to; null while streaming is off."
  value       = try(module.streaming[0].stream_name, null)
}

output "firehose_name" {
  description = "Firehose delivery stream from Kinesis to raw/edits/; null while streaming is off."
  value       = try(module.streaming[0].firehose_name, null)
}

output "glue_database" {
  description = "Glue Data Catalog database holding raw_edits and curated_edits."
  value       = module.catalog_etl.database_name
}

output "glue_workflow" {
  description = "Workflow that make run-etl starts: crawler, then the curate job."
  value       = module.catalog_etl.workflow_name
}

output "glue_job" {
  description = "Spark job that builds curated_edits."
  value       = module.catalog_etl.job_name
}

output "athena_workgroup" {
  description = "Workgroup to run queries in: 1 GB scan limit, results in the results bucket."
  value       = module.query.workgroup_name
}

output "saved_queries" {
  description = "Athena saved queries, one per file in sql/."
  value       = module.query.saved_queries
}

output "replay_stream_name" {
  description = "Experiment 1 replay stream; null unless REPLAY=true."
  value       = try(module.replay_stream[0].stream_name, null)
}
