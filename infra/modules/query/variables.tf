variable "name_prefix" {
  description = "Prefix for resource names, e.g. wiki-lake-dev."
  type        = string
}

variable "database_name" {
  description = "Glue database the saved queries run against."
  type        = string
}

variable "results_bucket_name" {
  description = "Bucket Athena writes query results to."
  type        = string
}

variable "sql_dir" {
  description = "Local folder of .sql files, each registered as a saved query."
  type        = string
}

variable "bytes_scanned_cutoff" {
  description = "Athena cancels any query in the workgroup that scans more than this many bytes."
  type        = number
  default     = 1073741824 # 1 GB
}
