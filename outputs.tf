# Prints out the IP of the EC2 instance
output "ec2_public_ip_1" {
    value = module.ec2_instance[0].public_ip
}

output "ec2_public_ip_2" {
    value = module.ec2_instance[1].public_ip
}