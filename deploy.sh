#!/bin/bash
set -e

# --- 1. Pre-flight Checks ---
# Ensure required tools are present
command -v terraform >/dev/null 2>&1 || { echo "Terraform is not installed. Aborting."; exit 1; }
command -v ansible-playbook >/dev/null 2>&1 || { echo "Ansible is not installed. Aborting."; exit 1; }

echo "--- Infrastructure Deployment Started ---"

# --- 2. User Inputs ---
read -p "Enter AWS Key Pair Name: " USER_KEY_NAME
read -p "Enter full path to .pem file: " USER_PEM_PATH
read -p "Enter S3 Bucket name (lowercase, hyphens only): " USER_BUCKET
read -p "Enter email for SNS alerts: " USER_EMAIL
read -s -p "Enter Ansible Vault Password: " VAULT_PASS
echo ""

# --- 3. Generate Terraform Vars ---
cat <<EOF > terraform/terraform.tfvars
key_name    = "${USER_KEY_NAME}"
bucket_name = "${USER_BUCKET}"
my_email    = "${USER_EMAIL}"
EOF

# --- 4. Deploy Infrastructure ---
echo "--- Initializing and Applying Terraform ---"
cd terraform
terraform init -input=false
# Use -auto-approve for automation, but warn the user
terraform apply -auto-approve
cd ..

# --- 5. Health Check & Wait ---
echo "--- Waiting for EC2 instances to initialize (60s) ---"
sleep 60

# --- 6. Configure Application (Ansible) ---
echo "--- Running Ansible Playbook ---"
cd ansible

# Create vault file securely
echo "$VAULT_PASS" > .vault_tmp
chmod 600 .vault_tmp

# Use export to prevent 'world writable' warnings and run playbook
export ANSIBLE_CONFIG=/dev/null
export ANSIBLE_HOST_KEY_CHECKING=False

# Run playbook: wslpath handles the Windows/Linux path bridging perfectly
ansible-playbook -i inventory.ini playbook.yml \
    --private-key "$(wslpath -u "${USER_PEM_PATH}")" \
    --vault-password-file .vault_tmp

# Cleanup secrets
rm -f .vault_tmp
unset VAULT_PASS

cd ..
echo "--- Deployment finished successfully! ---"