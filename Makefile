TF ?= terraform
TF_DIR := infra
export AWS_PROFILE ?= wiki-lake

.DEFAULT_GOAL := help
.PHONY: help setup lint test init validate plan apply destroy produce run-etl stream-down

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install Python 3.12 and dev dependencies with uv
	uv sync

lint: validate ## Ruff, terraform fmt and terraform validate
	uv run ruff check .
	uv run ruff format --check .
	$(TF) fmt -check -recursive $(TF_DIR)

test: ## Run unit tests
	uv run pytest

init: ## Initialise Terraform providers
	$(TF) -chdir=$(TF_DIR) init -input=false

validate: ## Validate Terraform without touching any backend
	$(TF) -chdir=$(TF_DIR) init -backend=false -input=false >/dev/null
	$(TF) -chdir=$(TF_DIR) validate

plan: init ## Show what Terraform would change
	$(TF) -chdir=$(TF_DIR) plan

apply: init ## Apply Terraform changes (asks for confirmation)
	$(TF) -chdir=$(TF_DIR) apply

destroy: init ## Destroy everything (asks for confirmation)
	$(TF) -chdir=$(TF_DIR) destroy

# Make treats words after the target as more targets, so pass producer flags
# through ARGS, e.g. make produce ARGS="--dry-run".
produce: ## Run the producer, flags via ARGS="..." (Phase 2)
	@echo "produce is implemented in Phase 2." && exit 1

run-etl: ## Start the Glue workflow (Phase 4)
	@echo "run-etl is implemented in Phase 4." && exit 1

stream-down: ## Remove the stream and Firehose, keep the lake (Phase 3)
	@echo "stream-down is implemented in Phase 3." && exit 1
