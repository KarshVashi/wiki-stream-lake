variable "name_prefix" {
  description = "Prefix for resource names, e.g. wiki-lake-dev."
  type        = string
}

variable "aws_region" {
  description = "Region the task runs in."
  type        = string
}

variable "account_id" {
  description = "AWS account ID, used to scope IAM policies."
  type        = string
}

variable "lake_bucket_arn" {
  description = "Lake bucket: the task writes runs/ and, in replay mode, reads raw/edits/."
  type        = string
}
