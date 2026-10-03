terraform {
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
}
variable "region" { default = "us-east-2" }
variable "project" { default = "sportsworld-mhacks-2026" }
provider "aws" { region = var.region }
resource "aws_s3_bucket" "artifacts" { bucket_prefix = "${var.project}-artifacts-" }
resource "aws_s3_bucket_versioning" "artifacts" { bucket = aws_s3_bucket.artifacts.id; versioning_configuration { status = "Enabled" } }
resource "aws_cloudwatch_log_group" "backend" { name = "/sportsworld/backend"; retention_in_days = 7 }
resource "aws_ecr_repository" "backend" { name = "${var.project}-backend"; image_scanning_configuration { scan_on_push = true } }
output "artifact_bucket" { value = aws_s3_bucket.artifacts.bucket }
output "backend_repository" { value = aws_ecr_repository.backend.repository_url }
