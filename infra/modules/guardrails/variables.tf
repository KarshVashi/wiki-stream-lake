variable "name_prefix" {
  description = "Prefix for resource names, e.g. wiki-lake-dev."
  type        = string
}

variable "monthly_limit_usd" {
  description = "Monthly cost budget in USD."
  type        = number
}

variable "alert_email" {
  description = "Address that receives budget alerts."
  type        = string
  sensitive   = true
}
