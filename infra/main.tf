locals {
  # Every resource is named ${project}-${env}-<thing>. Buckets also add the account ID.
  name_prefix = "${var.project}-${var.env}"
}

# Modules are added phase by phase: storage and guardrails in Phase 1,
# streaming in Phase 3, catalog_etl in Phase 4, query in Phase 5.
