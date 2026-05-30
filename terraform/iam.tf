# 1. Create the IAM Role for EC2
resource "aws_iam_role" "ec2_app_role" {
  name = "DevOps-EC2-App-Role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

# 2. Give the Role S3 Permissions
resource "aws_iam_role_policy_attachment" "s3_full_access" {
  role       = aws_iam_role.ec2_app_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

# 3. Give the Role SNS Permissions
resource "aws_iam_role_policy_attachment" "sns_full_access" {
  role       = aws_iam_role.ec2_app_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSNSFullAccess"
}

# 4. Create the Instance Profile to attach to the servers
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "DevOps-EC2-Instance-Profile"
  role = aws_iam_role.ec2_app_role.name
}