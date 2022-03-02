# Project
variable env_prefix {}
variable project_name {}
variable instance_count {}
variable instance_type {}

# SSH Access
variable ssh_approved_ips {}
variable ssh_key_name {}
variable ssh_public_key_file {}

# Can be set in terraform.tfvars, however...
# Preferably set through environment variable TF_VAR_iam_user and TF_VAR_contact_email
# along with the AWS secrets associated with that user
# See the README for details
variable iam_user {}
variable contact_email {}

# Operating system
variable image_name_regex {
    default = "amzn2-ami-kernel-*-hvm-*-x86_64-gp2"
}

# Spot request
variable spot_price_max {
    default = "0.05" # 0.05 dollar/hour x 730 hours/month = 36.50 dollars/month max
}
variable spot_type {
    default =  "one-time" # "one-time" or "persistent"
}

# Networking info
variable region {
    default = "us-west-1"
}
variable avail_zone {
    default = "us-west-1b"
}
variable vpc_cidr_block {
    default = "10.0.0.0/16"
}
variable subnet_cidr_block {
    default = "10.0.10.0/24"
}