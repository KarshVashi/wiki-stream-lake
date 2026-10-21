TF ?= terraform
TF_DIR := infra
export AWS_PROFILE ?= wiki-lake
export TF

# Which billable streams exist is set on every plan/apply, never left in tfvars.
STREAMING ?= true
TF_VARS = -var enable_streaming=$(STREAMING)

HOURS ?= 12
MINUTES ?=
KEY ?= event_id
ARGS ?=
GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

# Read one value from terraform output, only when a recipe needs it.
tf_out = $(shell $(TF) -chdir=$(TF_DIR) output -raw $(1))

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

plan: init ## Show what Terraform would change (STREAMING=true|false)
	$(TF) -chdir=$(TF_DIR) plan $(TF_VARS)

apply: init ## Apply Terraform changes, asks for confirmation (STREAMING=true|false)
	$(TF) -chdir=$(TF_DIR) apply $(TF_VARS)

destroy: init ## Destroy everything (asks for confirmation)
	$(TF) -chdir=$(TF_DIR) destroy

# Make treats words after the target as more targets, so options are passed as
# variables, e.g. make capture HOURS=3 KEY=domain, or make dry-run ARGS="...".

dry-run: ## Run the producer locally, printing instead of sending: MINUTES=1, ARGS="..."
	PYTHONPATH=src uv run python -m producer capture --dry-run \
		--duration-minutes $(or $(MINUTES),1) $(ARGS)

image: ## Build the producer image and push it to ECR, tagged with the git SHA and latest
	$(eval REPO := $(call tf_out,ecr_repository_url))
	aws ecr get-login-password --region $(call tf_out,aws_region) \
		| docker login --username AWS --password-stdin $(firstword $(subst /, ,$(REPO)))
	docker build --platform linux/arm64 -f src/producer/Dockerfile \
		-t $(REPO):$(GIT_SHA) -t $(REPO):latest .
	docker push $(REPO):$(GIT_SHA)
	docker push $(REPO):latest

capture: ## Start a capture task: HOURS=12 or MINUTES=..., KEY=event_id|domain, ARGS="--dry-run"
	uv run python scripts/run_task.py capture --hours $(HOURS) --key $(KEY) \
		$(if $(MINUTES),--minutes $(MINUTES)) -- $(ARGS)

capture-stop: ## Stop the running producer task (it still writes its summary)
	uv run python scripts/run_task.py stop

logs: ## Follow the producer task's CloudWatch logs
	aws logs tail $(call tf_out,producer_log_group) --follow --since 1h

fetch-runs: ## Copy run summaries from S3 runs/ to docs/runs/
	aws s3 sync s3://$(call tf_out,lake_bucket)/runs/ docs/runs/

stream-down: ## Remove the stream, Firehose and Lambda; keep the lake and everything else
	$(MAKE) apply STREAMING=false

run-etl: ## Start the Glue workflow (Phase 4)
	@echo "run-etl is implemented in Phase 4." && exit 1

replay: ## Start a replay task: SOURCE=raw/edits/..., RATE=2500, KEY=domain (Phase 6)
	@echo "replay is implemented in Phase 6." && exit 1
