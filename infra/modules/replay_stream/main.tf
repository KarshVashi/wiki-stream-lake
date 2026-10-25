# A stream for Experiment 1 only: the producer resends captured events into it
# fast enough to throttle a shard. Nothing reads from it, so replayed data never
# reaches the lake. It bills per shard-hour, so it exists only while needed.

variable "name_prefix" {
  description = "Prefix for resource names, e.g. wiki-lake-dev."
  type        = string
}

variable "shard_count" {
  description = "Provisioned shards in the replay stream."
  type        = number
  default     = 4
}

resource "aws_kinesis_stream" "replay" {
  name             = "${var.name_prefix}-replay" # matches the producer task role's stream pattern
  shard_count      = var.shard_count
  retention_period = 24

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }
}

output "stream_name" {
  value = aws_kinesis_stream.replay.name
}
