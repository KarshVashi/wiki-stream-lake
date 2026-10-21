locals {
  stream_name   = "${var.name_prefix}-edits"
  firehose_name = "${var.name_prefix}-edits-to-s3"
  lambda_name   = "${var.name_prefix}-transform"
}

# ---------------------------------------------------------------- Kinesis

resource "aws_kinesis_stream" "edits" {
  name             = local.stream_name
  shard_count      = var.shard_count
  retention_period = 24 # hours; records can be re-read for a day

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }
}

# ---------------------------------------------------------------- transform Lambda

data "archive_file" "transform" {
  type        = "zip"
  source_dir  = var.lambda_source_dir
  output_path = "${path.root}/build/transform_lambda.zip"
  excludes    = ["__pycache__", "__pycache__/*"]
}

resource "aws_cloudwatch_log_group" "transform" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = 7
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "transform" {
  name               = local.lambda_name
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "transform" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.transform.arn}:*"]
  }
}

resource "aws_iam_role_policy" "transform" {
  name   = "write-logs"
  role   = aws_iam_role.transform.id
  policy = data.aws_iam_policy_document.transform.json
}

resource "aws_lambda_function" "transform" {
  function_name    = local.lambda_name
  role             = aws_iam_role.transform.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.transform.output_path
  source_code_hash = data.archive_file.transform.output_base64sha256
  memory_size      = 256
  timeout          = 60 # Firehose allows up to 5 minutes; a batch takes well under a second

  depends_on = [aws_cloudwatch_log_group.transform, aws_iam_role_policy.transform]
}

# ---------------------------------------------------------------- Firehose

resource "aws_cloudwatch_log_group" "firehose" {
  name              = "/aws/kinesisfirehose/${local.firehose_name}"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_stream" "firehose" {
  name           = "DestinationDelivery"
  log_group_name = aws_cloudwatch_log_group.firehose.name
}

data "aws_iam_policy_document" "firehose_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["firehose.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "firehose" {
  name               = local.firehose_name
  assume_role_policy = data.aws_iam_policy_document.firehose_assume.json
}

data "aws_iam_policy_document" "firehose" {
  statement {
    sid = "ReadStream"
    actions = [
      "kinesis:DescribeStream",
      "kinesis:GetShardIterator",
      "kinesis:GetRecords",
      "kinesis:ListShards",
    ]
    resources = [aws_kinesis_stream.edits.arn]
  }

  statement {
    sid       = "InvokeTransform"
    actions   = ["lambda:InvokeFunction", "lambda:GetFunctionConfiguration"]
    resources = [aws_lambda_function.transform.arn, "${aws_lambda_function.transform.arn}:*"]
  }

  statement {
    sid       = "ListLakeBucket"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket", "s3:ListBucketMultipartUploads"]
    resources = [var.lake_bucket_arn]
  }

  statement {
    sid       = "WriteRawAndErrors"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload"]
    resources = ["${var.lake_bucket_arn}/raw/edits/*", "${var.lake_bucket_arn}/errors/*"]
  }

  statement {
    sid       = "WriteDeliveryLogs"
    actions   = ["logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.firehose.arn}:*"]
  }
}

resource "aws_iam_role_policy" "firehose" {
  name   = "stream-to-lake"
  role   = aws_iam_role.firehose.id
  policy = data.aws_iam_policy_document.firehose.json
}

resource "aws_kinesis_firehose_delivery_stream" "edits" {
  name        = local.firehose_name
  destination = "extended_s3"

  kinesis_source_configuration {
    kinesis_stream_arn = aws_kinesis_stream.edits.arn
    role_arn           = aws_iam_role.firehose.arn
  }

  extended_s3_configuration {
    role_arn   = aws_iam_role.firehose.arn
    bucket_arn = var.lake_bucket_arn

    # Partitioned by the hour the record ARRIVED (UTC), not when the edit happened.
    prefix              = "raw/edits/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"
    error_output_prefix = "errors/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/"

    # A file is written when 5 MB has built up or the interval passes, whichever is first.
    buffering_size     = 5
    buffering_interval = var.firehose_buffer_seconds
    compression_format = "GZIP"

    processing_configuration {
      enabled = true

      processors {
        type = "Lambda"

        parameters {
          parameter_name  = "LambdaArn"
          parameter_value = "${aws_lambda_function.transform.arn}:$LATEST"
        }
      }
    }

    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = aws_cloudwatch_log_group.firehose.name
      log_stream_name = aws_cloudwatch_log_stream.firehose.name
    }
  }

  # IAM changes take a few seconds to spread; Firehose checks its role on creation.
  depends_on = [aws_iam_role_policy.firehose]
}
