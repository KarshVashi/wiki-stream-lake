variable "aws_region" {
  description = "AWS region for every resource in the project."
  type        = string
  default     = "eu-west-2"
}

variable "project" {
  description = "Project name, used as the first part of every resource name."
  type        = string
  default     = "wiki-lake"
}

variable "env" {
  description = "Environment name, used as the second part of every resource name."
  type        = string
  default     = "dev"
}

variable "alert_email" {
  description = "Address that receives budget alerts. Set in terraform.tfvars, never committed."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be a valid email address."
  }
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget for the account, in USD."
  type        = number
  default     = 10
}

variable "enable_streaming" {
  description = "Create the Kinesis stream, Firehose and transform Lambda. The stream bills per shard-hour, so make stream-down sets this to false between sessions. Passed by the Makefile."
  type        = bool
  default     = true
}

variable "firehose_buffer_seconds" {
  description = "Longest Firehose waits before writing a file to raw/edits/."
  type        = number
  default     = 120
}
