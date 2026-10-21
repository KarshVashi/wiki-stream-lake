locals {
  # Every resource is named ${project}-${env}-<thing>. Buckets also add the account ID.
  name_prefix = "${var.project}-${var.env}"
}

data "aws_caller_identity" "current" {}

module "storage" {
  source = "./modules/storage"

  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
}

module "guardrails" {
  source = "./modules/guardrails"

  name_prefix       = local.name_prefix
  monthly_limit_usd = var.monthly_budget_usd
  alert_email       = var.alert_email
}

module "producer_task" {
  source = "./modules/producer_task"

  name_prefix     = local.name_prefix
  aws_region      = var.aws_region
  account_id      = data.aws_caller_identity.current.account_id
  lake_bucket_arn = module.storage.lake_bucket_arn
}
