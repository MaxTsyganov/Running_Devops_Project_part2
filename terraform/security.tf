# 1. Frontend Security Group
resource "aws_security_group" "frontend_sg" {
  name        = "frontend_sg"
  description = "Allow HTTP from internet and SSH for Ansible"
  vpc_id      = aws_vpc.main_vpc.id

  # HTTP Rule - Allowed from anywhere (0.0.0.0/0) so the public can view the site
  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # SSH Rule - Allowed from anywhere (0.0.0.0/0) ONLY because Ansible requires access from a dynamic local IP
  ingress {
    description = "SSH for Ansible (Required for local provisioning)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 2. Backend Security Group
resource "aws_security_group" "backend_sg" {
  name        = "backend_sg"
  description = "Allow inbound API traffic from Frontend and SSH for Ansible"
  vpc_id      = aws_vpc.main_vpc.id

  # API traffic ONLY allowed from the Frontend Security Group (Strict Minimal Permission)
  ingress {
    description     = "Flask API from Frontend SG only"
    from_port       = 5000
    to_port         = 5000
    protocol        = "tcp"
    security_groups = [aws_security_group.frontend_sg.id]
  }

  # SSH Rule - Allowed from anywhere (0.0.0.0/0) ONLY because Ansible requires access from a dynamic local IP
  ingress {
    description = "SSH for Ansible (Required for local provisioning)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 3. Worker Security Group
resource "aws_security_group" "worker_sg" {
  name        = "worker_sg"
  description = "Allow SSH for Ansible. No inbound app ports needed."
  vpc_id      = aws_vpc.main_vpc.id

  # SSH Rule - Allowed from anywhere (0.0.0.0/0) ONLY because Ansible requires access from a dynamic local IP
  ingress {
    description = "SSH for Ansible (Required for local provisioning)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 4. RDS PostgreSQL Security Group
resource "aws_security_group" "rds_sg" {
  name        = "rds_sg"
  description = "Allow PostgreSQL access strictly from Backend and Worker"
  vpc_id      = aws_vpc.main_vpc.id

  # Database traffic ONLY allowed from Backend SG
    ingress {
    description     = "PostgreSQL from Backend and Worker SGs"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [
      aws_security_group.backend_sg.id, 
      aws_security_group.worker_sg.id
    ]
  }
}

  # Database traffic ONLY allowed from Worker SG
  ingress {
    description     = "PostgreSQL from Worker SG"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.worker_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}