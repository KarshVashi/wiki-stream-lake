output "ecr_repository_url" {
  value = aws_ecr_repository.producer.repository_url
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "task_family" {
  value = aws_ecs_task_definition.producer.family
}

output "container_name" {
  value = local.container_name
}

output "subnet_ids" {
  value = data.aws_subnets.default.ids
}

output "security_group_id" {
  value = aws_security_group.producer.id
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.producer.name
}
