output "stream_name" {
  value = aws_kinesis_stream.edits.name
}

output "stream_arn" {
  value = aws_kinesis_stream.edits.arn
}

output "firehose_name" {
  value = aws_kinesis_firehose_delivery_stream.edits.name
}

output "transform_function_name" {
  value = aws_lambda_function.transform.function_name
}
