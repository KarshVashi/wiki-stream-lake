variable "name_prefix" {
  description = "Prefix for resource names, e.g. wiki-lake-dev."
  type        = string
}

variable "account_id" {
  description = "AWS account ID, appended to bucket names for global uniqueness."
  type        = string
}
