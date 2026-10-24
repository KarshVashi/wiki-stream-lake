variable "name_prefix" {
  description = "Prefix for resource names, e.g. wiki-lake-dev."
  type        = string
}

variable "database_name" {
  description = "Glue Data Catalog database."
  type        = string
  default     = "wiki_lake"
}

variable "lake_bucket_name" {
  description = "Lake bucket: the job reads raw/edits/ and writes curated/edits/."
  type        = string
}

variable "lake_bucket_arn" {
  description = "ARN of the lake bucket."
  type        = string
}

variable "artifacts_bucket_name" {
  description = "Bucket the Glue scripts are uploaded to."
  type        = string
}

variable "artifacts_bucket_arn" {
  description = "ARN of the artifacts bucket."
  type        = string
}

variable "scripts_dir" {
  description = "Local folder holding curate_edits.py and transforms.py."
  type        = string
}

variable "etl_schedule" {
  description = "Cron expression for the workflow, e.g. cron(0 6 * * ? *). Null means on demand only."
  type        = string
  default     = null
}
