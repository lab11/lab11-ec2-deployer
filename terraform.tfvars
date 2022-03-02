# Project
env_prefix = "dev"                                              # used to name resources
project_name = "terraform-tutorial"                             # used to name resources
instance_count = 2
instance_type = "t3.nano"
is_spot = true                                                  # choose between spot or on-demand instances

# SSH Access
ssh_approved_ips = ["192.184.203.246/32", "169.229.59.10/32"]   # CIDR blocks for work and home
ssh_key_name = "meghanix@mooncake"                              # can be any string
ssh_public_key_file = "/home/meghanix/.ssh/id_ed25519.pub"