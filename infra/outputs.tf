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
