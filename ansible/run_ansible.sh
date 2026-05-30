#!/usr/bin/expect -f
spawn ansible-playbook -i inventory.ini playbook.yml --private-key ""C:UsersmaxmaOneDriveDesktopPython-projectsRunning ProjectRunning Project p2Running_Devops_Project_part2devops-project-key.pem"" --ask-vault-pass
expect "Vault password:"
send "11223311\r"
expect eof
