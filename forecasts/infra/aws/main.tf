terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.70.0"
    }
  }
}

variable "profile" {
  type        = string
  default     = null
  description = "User-local AWS profile."
}

variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "market_archive_bucket" {
  type        = string
  description = "Existing shared bucket containing market-data/."
}

provider "aws" {
  profile = var.profile
  region  = var.region

  default_tags {
    tags = { Project = "coppersushi-forecast-operations" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "zone-type"
    values = ["availability-zone"]
  }
}

locals {
  name         = "coppersushi-forecast-operations"
  partition    = data.aws_partition.current.partition
  account      = data.aws_caller_identity.current.account_id
  service_arn  = "${var.region}:${local.account}"
  market_arn   = "arn:${local.partition}:s3:::${var.market_archive_bucket}"
  monthly_arn  = "arn:${local.partition}:states:${local.service_arn}:stateMachine:DeLuMonthlyFit"
  daily_arn    = "arn:${local.partition}:states:${local.service_arn}:stateMachine:DeLuDailyIssue"
  default_logs = "arn:${local.partition}:logs:${local.service_arn}:log-group:/aws/batch/job"
}

resource "aws_ecr_repository" "forecast" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_cloudwatch_log_group" "batch" {
  name              = "/coppersushi/forecast-operations/batch"
  retention_in_days = 90
}
