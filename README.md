# 3-Tier AWS Application - Automated DevOps Deployment

This project takes a manual 3-tier web application deployment on AWS and makes it completely automatic using Terraform and Ansible.

## Project Architecture

The application runs on three separate Ubuntu servers in AWS:
1. **Frontend Server:** Runs Nginx to serve the website.
2. **Backend Server:** Runs a Python Flask API to connect the website to the database and storage.
3. **Worker Server:** Runs a background Python script that checks the database for new tasks and processes them.

### AWS Services Used
* **Networking:** VPC, Public Subnet, Internet Gateway, Route Tables.
* **Servers:** 3 EC2 instances.
* **Database:** RDS PostgreSQL.
* **Storage:** S3 Bucket for file uploads.
* **Notifications:** SNS Topic for sending email alerts.
* **Security:** IAM Roles and Security Groups.

### Architecture Decision: Public Subnets
To keep the project in the AWS Free Tier and avoid paying the hourly cost for a NAT Gateway, all three servers are placed in a Public Subnet. Security is maintained entirely through AWS Security Groups. The backend server and the database cannot be accessed directly from the internet; they only accept traffic from our specific servers.

## Tool Responsibilities

### What Terraform Does (Infrastructure)
Terraform is responsible for building the physical cloud environment. It creates the VPC, the subnets, the security rules, the IAM roles, the three EC2 servers, the RDS database, the S3 bucket, and the SNS topic. 

### What Ansible Does (Configuration)
Ansible is responsible for configuring the servers after they are created. It logs into the servers to install packages (like Python and Nginx), copies the application code, sets up the virtual environments, injects the dynamic AWS links into the code, and starts the background services.

## Secret Management and Variables

Passwords and secret keys are never uploaded to GitHub.

* **Terraform Variables:** We use a file called `terraform.tfvars` to pass information. A safe template called `terraform.tfvars.example` is included in the code. Users must copy this file, rename it to `terraform.tfvars`, and enter their own database password and email address.
* **Ansible Variables:** We use a file called `vars.yml` in the ansible folder to pass the database password and AWS links to the servers.

## Terraform State Management

The Terraform state file (`terraform.tfstate`) acts as a live map of the AWS environment. For this project, the state is managed locally on the computer running the code. 

Because the state file contains the master database password in plain text, it is a security risk. All `.tfstate` files have been added to the `.gitignore` file so they are never accidentally uploaded to version control.

---

## How to Run the Project

### Step 1: Build the Infrastructure with Terraform
1. Open a terminal and navigate to the `terraform` folder.
2. Copy `terraform.tfvars.example` and rename it to `terraform.tfvars`. Fill in your email, a database password, and an S3 bucket name.
3. Run the following commands:
   `terraform init`
   `terraform apply`
4. Type `yes` to confirm. When it finishes, copy the IP addresses it prints on the screen.

### Step 2: Configure the Servers with Ansible
1. Navigate to the `ansible` folder.
2. Open the `inventory.ini` file. Update the public IP addresses for the frontend, backend, and worker. Also update the private_ip variable on the backend line.
3. Open the `vars.yml` file and enter your database password, the RDS endpoint link (make sure to remove the port [:5432] from the end of the the endpoint, Python add it automatically), the S3 bucket name, and the SNS ARN link.
4. Run the following command:
   `ansible-playbook -i inventory.ini playbook.yml`

---

## How to Check if the System Works

Once Ansible finishes without any errors, the website is live.
1. Open a web browser and go to the Frontend Public IP address.
2. **Test the Database:** Add a new item on the website. It should appear at the bottom with a "pending" status, and you should receive an email alert.
3. **Test S3:** Upload a file through the website. You should see a green success message and receive another email.
4. **Test the Worker:** Wait about 30 seconds and refresh the webpage. The item's status should change from "pending" to "done".

---

## How to Delete the Environment

When you are finished testing, you must delete the environment so AWS does not charge you money.
1. Navigate to the `terraform` folder.
2. Run the following command:
   `terraform destroy`
3. Type `yes` to confirm. This will safely delete all servers, databases, and networks.