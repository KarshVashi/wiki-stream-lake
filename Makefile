TF ?= terraform
TF_DIR := infra
export AWS_PROFILE ?= wiki-lake

.DEFAULT_GOAL := help
.PHONY: help setup lint test init validate plan apply destroy \
	image capture capture-stop logs replay dry-run fetch-runs run-etl stream-down

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-13s %s\n", $$1, $$2}'

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

# Make treats words after the target as more targets, so options are passed as
# variables, e.g. make capture HOURS=3 KEY=domain, or make dry-run ARGS="...".

dry-run: ## Run the producer locally, printing instead of sending (Phase 2)
	@echo "dry-run is implemented in Phase 2." && exit 1

image: ## Build and push the producer image to ECR (Phase 2)
	@echo "image is implemented in Phase 2." && exit 1

capture: ## Start a capture task: HOURS=12 or MINUTES=..., KEY=event_id|domain (Phase 2)
	@echo "capture is implemented in Phase 2." && exit 1

capture-stop: ## Stop the running capture task (Phase 2)
	@echo "capture-stop is implemented in Phase 2." && exit 1

logs: ## Follow the producer task's logs (Phase 2)
	@echo "logs is implemented in Phase 2." && exit 1

fetch-runs: ## Copy run summaries from S3 runs/ to docs/runs/ (Phase 2)
	@echo "fetch-runs is implemented in Phase 2." && exit 1

stream-down: ## Remove the stream and Firehose, keep the lake (Phase 3)
	@echo "stream-down is implemented in Phase 3." && exit 1

run-etl: ## Start the Glue workflow (Phase 4)
	@echo "run-etl is implemented in Phase 4." && exit 1

replay: ## Start a replay task: SOURCE=raw/edits/..., RATE=2500, KEY=domain (Phase 6)
	@echo "replay is implemented in Phase 6." && exit 1
