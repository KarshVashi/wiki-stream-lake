locals {
  name           = "${var.name_prefix}-producer"
  container_name = "producer"
  # Any stream this project creates: the main edits stream and the replay stream.
  stream_arns = "arn:aws:kinesis:${var.aws_region}:${var.account_id}:stream/${var.name_prefix}-*"
}

# ---------------------------------------------------------------- image

resource "aws_ecr_repository" "producer" {
  name                 = local.name
  image_tag_mutability = "MUTABLE" # the task definition runs the "latest" tag
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "producer" {
  repository = aws_ecr_repository.producer.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 3 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}

# ---------------------------------------------------------------- network
# The default VPC's subnets are public. With a public IP the task reaches
# Wikimedia, Kinesis, S3, ECR and CloudWatch directly, so no NAT gateway.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# Terraform removes the allow-all egress rule AWS adds to new security groups,
# so the only traffic allowed is the HTTPS rule below. No inbound rules.
resource "aws_security_group" "producer" {
  name        = local.name
  description = "Producer task: outbound HTTPS only, nothing inbound"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.producer.id
  description       = "HTTPS to Wikimedia and AWS APIs"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# ---------------------------------------------------------------- logs

resource "aws_cloudwatch_log_group" "producer" {
  name              = "/ecs/${local.name}"
  retention_in_days = 7
}

# ---------------------------------------------------------------- IAM

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

# Execution role: used by ECS itself to pull the image and ship logs.
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "execution" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # this action does not support resource-level permissions
  }

  statement {
    sid = "EcrPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.producer.arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.producer.arn}:*"]
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "pull-image-and-write-logs"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}

# Task role: used by the producer code.
resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "WriteToProjectStreams"
    actions   = ["kinesis:PutRecords"]
    resources = [local.stream_arns]
  }

  statement {
    sid       = "WriteRunSummaries"
    actions   = ["s3:PutObject"]
    resources = ["${var.lake_bucket_arn}/runs/*"]
  }

  statement {
    sid       = "ReplayReadRaw"
    actions   = ["s3:GetObject"]
    resources = ["${var.lake_bucket_arn}/raw/edits/*"]
  }

  statement {
    sid       = "ReplayListRaw"
    actions   = ["s3:ListBucket"]
    resources = [var.lake_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/edits/*"]
    }
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "producer"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# ---------------------------------------------------------------- ECS
# A cluster and a task definition only. No service: each run is started with
# run-task and stops itself when its duration ends.

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_task_definition" "producer" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256 # 0.25 vCPU, the smallest Fargate size
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([{
    name                   = local.container_name
    image                  = "${aws_ecr_repository.producer.repository_url}:latest"
    essential              = true
    readonlyRootFilesystem = true
    stopTimeout            = 120 # seconds between SIGTERM and SIGKILL, the Fargate maximum
    # Overridden by every run-task call; this default is a harmless one-minute dry run.
    command     = ["capture", "--dry-run", "--duration-minutes", "1"]
    environment = [{ name = "AWS_REGION", value = var.aws_region }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.producer.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = local.container_name
      }
    }
  }])
}
