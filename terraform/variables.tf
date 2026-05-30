variable "aws_region" {
  description = "The AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "The EC2 instance type"
  type        = string
  default     = "t3.micro" # Free tier eligible
}

variable "ami_id" {
  description = "The AMI ID for Ubuntu Server 24.04 LTS in us-east-1"
  type        = string
  default     = "ami-04b70fa74e45c3917" # Update this if you used a different Ubuntu AMI today!
}

variable "key_name" {
  description = "The name of the AWS Key Pair to use for SSH access"
  type        = string
  default     = "devops-project-key"
}

variable "db_password" {
  description = "Password for the RDS PostgreSQL database"
  type        = string
  sensitive   = true
}

variable "my_email" {
  description = "Email address for SNS alerts"
  type        = string
}

variable "bucket_name" {
  description = "Globally unique name for the S3 bucket"
  type        = string
}

variable "ami_id" {
  description = "The AMI ID for the EC2 instances (Ubuntu 24.04)"
  type        = string
  default     = "ami-04b70fa74e45c3917" # This is the us-east-1 Ubuntu 24.04 AMI
}

variable "instance_type" {
  description = "The EC2 instance type"
  type        = string
  default     = "t2.micro"
}