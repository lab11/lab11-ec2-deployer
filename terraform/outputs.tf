# Prints out the IP(s) of the EC2 instance(s)
output "ec2_public_ips" {
    value = [for e in module.ec2_instance: e.public_ip]
}