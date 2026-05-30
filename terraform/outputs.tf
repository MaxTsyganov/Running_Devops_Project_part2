# ── IPs for Ansible Inventory ──

output "frontend_public_ip" {
  description = "The Public IP of the Nginx server"
  value       = aws_instance.frontend.public_ip
}

output "backend_private_ip" {
  description = "The Private IP of the Python API server"
  value       = aws_instance.backend.private_ip
}

output "worker_private_ip" {
  description = "The Private IP of the Python Worker server"
  value       = aws_instance.worker.private_ip
}

# ── Dynamic Configuration for Application (.env) ──

output "rds_endpoint" {
  description = "The RDS connection endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "s3_bucket_name" {
  description = "The dynamically generated S3 bucket name"
  value       = aws_s3_bucket.app_bucket.id
}

output "sns_topic_arn" {
  description = "The ARN for the SNS Topic"
  value       = aws_sns_topic.alerts.arn
}

output "backend_public_ip" {
  value = aws_instance.backend.public_ip
}

output "worker_public_ip" {
  value = aws_instance.worker.public_ip
}

# ===================================================
# Auto-Generate Ansible Inventory File
# ===================================================
resource "local_file" "ansible_inventory" {
  filename = "../ansible/inventory.ini"
  content  = <<-EOT
    [frontend]
    ${aws_instance.frontend.public_ip}

    [backend]
    ${aws_instance.backend.public_ip} private_ip=${aws_instance.backend.private_ip}

    [worker]
    ${aws_instance.worker.public_ip}
  EOT
}

# ===================================================
# Auto-Generate Ansible Variables File
# ===================================================
resource "local_file" "ansible_vars" {
  filename = "../ansible/vars.yml"
  content  = <<-EOT
    backend_private_ip: "${aws_instance.backend.private_ip}"
    rds_endpoint: "${aws_db_instance.postgres.address}"
    s3_bucket_name: "${aws_s3_bucket.app_bucket.bucket}"
    sns_topic_arn: "${aws_sns_topic.alerts.arn}"
  EOT
}