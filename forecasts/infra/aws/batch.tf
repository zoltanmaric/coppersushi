resource "aws_vpc" "batch" {
  cidr_block           = "10.70.0.0/24"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = local.name }
}

resource "aws_internet_gateway" "batch" {
  vpc_id = aws_vpc.batch.id
}

resource "aws_subnet" "batch" {
  count = 2

  vpc_id            = aws_vpc.batch.id
  availability_zone = data.aws_availability_zones.available.names[count.index]
  cidr_block        = cidrsubnet(aws_vpc.batch.cidr_block, 2, count.index)
}

resource "aws_route_table" "batch" {
  vpc_id = aws_vpc.batch.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.batch.id
  }
}

resource "aws_route_table_association" "batch" {
  count = length(aws_subnet.batch)

  subnet_id      = aws_subnet.batch[count.index].id
  route_table_id = aws_route_table.batch.id
}

resource "aws_security_group" "batch" {
  name        = local.name
  description = "Outbound HTTPS for forecast jobs"
  vpc_id      = aws_vpc.batch.id

  egress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_batch_compute_environment" "forecast" {
  name  = local.name
  type  = "MANAGED"
  state = "ENABLED"

  compute_resources {
    type               = "FARGATE"
    max_vcpus          = 8
    subnets            = aws_subnet.batch[*].id
    security_group_ids = [aws_security_group.batch.id]
  }

  depends_on = [aws_route_table_association.batch]
}

resource "aws_batch_job_queue" "forecast" {
  name     = local.name
  priority = 1
  state    = "ENABLED"

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.forecast.arn
  }
}
