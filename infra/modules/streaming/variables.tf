variable "name_prefix" {
  description = "Prefix for resource names, e.g. wiki-lake-dev."
  type        = string
}

variable "lake_bucket_arn" {
  description = "Lake bucket that Firehose writes raw/edits/ and errors/ into."
  type        = string
}

variable "shard_count" {
  description = "Provisioned shards in the edits stream."
  type        = number
  default     = 2
}

variable "firehose_buffer_seconds" {
  description = "Longest Firehose waits before writing a file to S3 (Experiment 4 changes this)."
  type        = number
  default     = 120
}

variable "lambda_source_dir" {
  description = "Folder holding the transform Lambda's code."
  type        = string
}
