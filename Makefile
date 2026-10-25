TF ?= terraform
TF_DIR := infra
export AWS_PROFILE ?= wiki-lake
export TF

# Which billable streams exist, and the Firehose buffer, are set on every
# plan/apply, never left in tfvars, so each command states them.
STREAMING ?= true
REPLAY ?= false
BUFFER ?= 120
TF_VARS = -var enable_streaming=$(STREAMING) -var enable_replay_stream=$(REPLAY) \
	-var firehose_buffer_seconds=$(BUFFER)

HOURS ?= 12
MINUTES ?=
KEY ?= event_id
ARGS ?=
CPU ?=
GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

# Read one value from terraform output, only when a recipe needs it.
tf_out = $(shell $(TF) -chdir=$(TF_DIR) output -raw $(1))

.DEFAULT_GOAL := help
.PHONY: help setup lint test init validate plan apply destroy \
	image capture capture-stop logs replay dry-run fetch-runs run-etl backfill stream-down \
	job-status benchmark count dupes freshness

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

plan: init ## Show what Terraform would change (STREAMING, REPLAY, BUFFER)
	$(TF) -chdir=$(TF_DIR) plan $(TF_VARS)

apply: init ## Apply Terraform changes, asks first (STREAMING=true, REPLAY=false, BUFFER=120)
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
		$(if $(MINUTES),--minutes $(MINUTES)) $(if $(CPU),--cpu $(CPU)) -- $(ARGS)

capture-stop: ## Stop the running producer task (it still writes its summary)
	uv run python scripts/run_task.py stop

logs: ## Follow the producer task's CloudWatch logs
	aws logs tail $(call tf_out,producer_log_group) --follow --since 1h

fetch-runs: ## Copy run summaries from S3 runs/ to docs/runs/ and print them as a table
	aws s3 sync s3://$(call tf_out,lake_bucket)/runs/ docs/runs/
	@uv run python scripts/runs_table.py

stream-down: ## Remove the stream, Firehose and Lambda; keep the lake and everything else
	$(MAKE) apply STREAMING=false

run-etl: ## Start the Glue workflow: crawl raw_edits, then rebuild touched curated partitions
	aws glue start-workflow-run --name $(call tf_out,glue_workflow)
	@echo "Watch it in the Glue console: ETL > Workflows > $(call tf_out,glue_workflow) > History"

backfill: ## Rebuild one event_date partition from raw, ignoring bookmarks: DATE=YYYY-MM-DD
	@test -n "$(DATE)" || (echo "Usage: make backfill DATE=YYYY-MM-DD" && exit 1)
	aws glue start-job-run --job-name $(call tf_out,glue_job) --arguments \
		'{"--backfill_date":"$(DATE)","--job-bookmark-option":"job-bookmark-disable"}'


job-status: ## Show the curate job's last runs: state, seconds, DPU-seconds
	aws glue get-job-runs --job-name $(call tf_out,glue_job) --max-items 5 --output table \
		--query 'JobRuns[].{started:StartedOn,state:JobRunState,seconds:ExecutionTime,dpu_seconds:DPUSeconds,backfill:Arguments."--backfill_date"}'

# ---------------------------------------------------------------- experiments

replay: ## Experiment 1: resend raw data into the replay stream. SOURCE=raw/edits/... RATE=2500 KEY=domain MINUTES=10 CPU=
	@test -n "$(SOURCE)" || (echo "Usage: make replay SOURCE=raw/edits/year=YYYY/month=MM/day=DD/ [RATE=2500] [KEY=domain]" && exit 1)
	uv run python scripts/run_task.py replay --source $(SOURCE) --rate $(or $(RATE),2500) \
		--key $(if $(filter command line,$(origin KEY)),$(KEY),domain) \
		--minutes $(or $(MINUTES),10) $(if $(CPU),--cpu $(CPU))

benchmark: ## Experiment 2: data scanned on JSON vs Parquet for one day. DATE=YYYY-MM-DD
	@test -n "$(DATE)" || (echo "Usage: make benchmark DATE=YYYY-MM-DD" && exit 1)
	uv run python scripts/athena.py benchmark --date $(DATE)

count: ## Experiment 3: rows in curated_edits for one day. DATE=YYYY-MM-DD
	@test -n "$(DATE)" || (echo "Usage: make count DATE=YYYY-MM-DD" && exit 1)
	uv run python scripts/athena.py count --date $(DATE)

dupes: ## Experiment 3: event_ids stored more than once (should be 0)
	uv run python scripts/athena.py dupes

freshness: ## Experiment 4: delay to the first S3 file, file count and size for a run. RUN=docs/runs/....json
	@test -n "$(RUN)" || (echo "Usage: make freshness RUN=docs/runs/<summary>.json" && exit 1)
	uv run python scripts/freshness.py $(RUN)
