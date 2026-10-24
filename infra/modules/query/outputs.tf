output "workgroup_name" {
  value = aws_athena_workgroup.lake.name
}

output "saved_queries" {
  value = sort([for query in aws_athena_named_query.saved : query.name])
}
