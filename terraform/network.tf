# 1. Create the main VPC
resource "aws_vpc" "main_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "DevOps-Project-VPC"
  }
}

# 2. Create the Public Subnet (For Frontend/Nginx)
resource "aws_subnet" "public_subnet" {
  vpc_id                  = aws_vpc.main_vpc.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true # Automatically assigns a Public IP to servers here
  availability_zone       = "${var.aws_region}a"

  tags = {
    Name = "DevOps-Public-Subnet"
  }
}

# 3. Create Private Subnet 1 (For Backend/Worker)
resource "aws_subnet" "private_subnet_1" {
  vpc_id            = aws_vpc.main_vpc.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "${var.aws_region}a"

  tags = {
    Name = "DevOps-Private-Subnet-1"
  }
}

# 4. Create Private Subnet 2 (Required for RDS Subnet Group)
resource "aws_subnet" "private_subnet_2" {
  vpc_id            = aws_vpc.main_vpc.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = "${var.aws_region}b" # Must be in a different AZ for RDS

  tags = {
    Name = "DevOps-Private-Subnet-2"
  }
}

# 5. Create the Internet Gateway (The Front Door)
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main_vpc.id

  tags = {
    Name = "DevOps-Internet-Gateway"
  }
}

# 6. Create the Public Route Table (The Hallway Signs)
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.main_vpc.id

  route {
    cidr_block = "0.0.0.0/0"                 # Route all internet traffic
    gateway_id = aws_internet_gateway.igw.id # Point it to the Internet Gateway
  }

  tags = {
    Name = "DevOps-Public-Route-Table"
  }
}

# 7. Associate the Route Table with the Public Subnet
resource "aws_route_table_association" "public_association" {
  subnet_id      = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public_rt.id
}