output "lake_bucket_name" {
  value = aws_s3_bucket.this["lake"].id
}

output "lake_bucket_arn" {
  value = aws_s3_bucket.this["lake"].arn
}

output "athena_results_bucket_name" {
  value = aws_s3_bucket.this["athena_results"].id
}

output "athena_results_bucket_arn" {
  value = aws_s3_bucket.this["athena_results"].arn
}

output "artifacts_bucket_name" {
  value = aws_s3_bucket.this["artifacts"].id
}

output "artifacts_bucket_arn" {
  value = aws_s3_bucket.this["artifacts"].arn
}
