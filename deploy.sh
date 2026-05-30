#!/bin/bash
# Stop the script immediately if any command fails
set -e

# Check if Terraform and Ansible are installed before starting
command -v terraform >/dev/null 2>&1 || { echo "Terraform is not installed. Aborting."; exit 1; }
command -v ansible-playbook >/dev/null 2>&1 || { echo "Ansible is not installed. Aborting."; exit 1; }

echo "Starting infrastructure deployment..."

# Gather required information from the user
read -p "Enter AWS Key Pair Name: " USER_KEY_NAME
read -p "Enter full path to .pem file: " USER_PEM_PATH
read -p "Enter S3 Bucket name (lowercase, hyphens only): " USER_BUCKET
read -p "Enter email for SNS alerts: " USER_EMAIL
read -s -p "Enter Ansible Vault Password: " VAULT_PASS
echo ""

# Create a variable file for Terraform using the user inputs
cat <<EOF > terraform/terraform.tfvars
key_name    = "${USER_KEY_NAME}"
bucket_name = "${USER_BUCKET}"
my_email    = "${USER_EMAIL}"
EOF

# Initialize and run Terraform to build the AWS infrastructure
echo "Initializing and Applying Terraform..."
cd terraform
terraform init -input=false
terraform apply -auto-approve
cd ..

# Wait for the EC2 servers to fully start up before configuring them
echo "Waiting for EC2 instances to initialize (60 seconds)..."
sleep 60

# Run Ansible to install and configure the application on the servers
echo "Running Ansible Playbook..."
cd ansible

# Save the Vault password to a temporary file for Ansible to read securely
echo "$VAULT_PASS" > .vault_tmp
chmod 600 .vault_tmp

# Suppress warnings about folder permissions
export ANSIBLE_CONFIG=/dev/null
export ANSIBLE_HOST_KEY_CHECKING=False

# Execute the playbook, converting the Windows path to a format Linux understands
ansible-playbook -i inventory.ini playbook.yml \
    --private-key "$(wslpath -u "${USER_PEM_PATH}")" \
    --vault-password-file .vault_tmp

# Delete the temporary password file to keep things secure
rm -f .vault_tmp
unset VAULT_PASS

cd ..
echo "Deployment finished successfully!"