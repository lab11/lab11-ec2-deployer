# Store Terraform state remotely in an S3 bucket
terraform {
    required_version = ">= 1.0"
    backend "s3" {
        key = "terraform/state.tfstate"
    }
}

# Using AWS
provider "aws" {
    region = var.region
    default_tags {
        tags = {
            Name = "${var.env_prefix}-${var.project_name}"
            Contact_email = var.contact_email
            Contact_name = var.contact_name
            Project = var.project_name
            Env = var.env_prefix
        }
    }
}

# Creates a virtual private cloud and subnet for the project
module "vpc" {
    source = "terraform-aws-modules/vpc/aws"
    name = "${var.env_prefix}-${var.project_name}-vpc"

    enable_dns_hostnames = true
    cidr                = var.vpc_cidr_block
    azs                 = [var.avail_zone]
    public_subnets      = [var.subnet_cidr_block]
    public_subnet_tags  = {
        Name = "${var.env_prefix}-${var.project_name}-subnet"
    }

    # vpc tags
    tags = {
        Name = "${var.env_prefix}-${var.project_name}-vpc"
    }
}

# Creates a security group with firewall rules for the project server
resource "aws_security_group" "my-project-sg" {
    name        = "${var.env_prefix}-${var.project_name}-sg"
    description = "Allow SSH traffic"
    vpc_id      = module.vpc.vpc_id

    # SSH access
    ingress {
        from_port        = 22
        to_port          = 22
        protocol         = "tcp"
        cidr_blocks      = var.ssh_approved_ips
    }

    # Allows local processes like e.g. docker to grab resources from the internet
    # will also allow ssh egress, webserver egress, etc.
    egress {
        from_port        = 0
        to_port          = 0
        protocol         = "-1"
        cidr_blocks      = ["0.0.0.0/0"]
        prefix_list_ids = []
    }

    tags = {
        Name = "${var.env_prefix}-${var.project_name}-sg"
    }
} 

# Gets the latest Amazon machine image (AMI) that matches the user-provided image_name_regex
data "aws_ami" "latest-amazon-linux-image" {
    most_recent = true
    owners = ["137112412989"]
    filter {
        name = "name"
        values = [var.image_name_regex]
    }
}

# Adds the user-provided public key to AWS (for SSH purposes)
resource "aws_key_pair" "my-key-pair" {
  key_name   = "${var.env_prefix}-${var.project_name}-${var.ssh_key_name}"
  public_key = file(var.ssh_public_key_file)
  tags = {
    Name = "${var.env_prefix}-${var.project_name}-${var.ssh_key_name}"
  }
}

# Creates the EC2 spot instance
module "ec2_instance" {
  source  = "terraform-aws-modules/ec2-instance/aws"
  version = "~> 3.0"    

  name = "${var.env_prefix}-${var.project_name}-server-${count.index+1}"

  count = var.instance_count

  create_spot_instance = var.is_spot
  spot_price           = var.spot_price_max 
  spot_type            = var.spot_type
  spot_wait_for_fulfillment = true
  spot_instance_interruption_behavior = var.spot_instance_interruption_behavior

  ami                    = data.aws_ami.latest-amazon-linux-image.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.my-key-pair.key_name
  monitoring             = false
  vpc_security_group_ids = [aws_security_group.my-project-sg.id]
  subnet_id              = module.vpc.public_subnets[0]

  associate_public_ip_address = true

  tags = {
    Name = "${var.env_prefix}-${var.project_name}-server-${count.index+1}"
  }
}
