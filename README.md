
A Python3 tool for creating, configuring, and destroying EC2 instances using Terraform and Ansible.

# How to use this project

* Create a new branch for your project

Once you have your own version to modify, these are the steps for running the project:

* Authenticate to AWS on the command line
* Configure the Terraform project to reflect your specific needs
* Run `ec2_instances.py create` to create the instance(s)

When you're completely done with your project and want to delete the instance(s) and supporting AWS infrastructure, run `ec2_instances.py destroy` to tear it down. You can easily recreate it with another `python ec2_instances.py create` command.

# 0. Installation Requirements

You will need to install: 
- Python 3.7+. 
- Terraform 
- Ansible

If you forget any prerequisites, the `ec2_instances.py` script will let you know.

# 1. Authenticate to AWS

Terraform needs AWS credentials in order to create AWS resources. This means you will need to 1) make sure you have an AWS user on the IAM service, 2) obtain your credentials, and 3) make the credentials available to Terraform and Ansible via environment variables.

## Find/create your AWS IAM user

In the Lab 11 AWS web portal, navigate to the IAM service. There should be a user with your name (e.g. `meghan`) that has the appropriate permissions to create these resources (EC2 instances and VPC components). If an IAM user does not exist for you, you should create one.

## Get your IAM user credentials

You can find the secrets for your user by using the IAM service's web interface. The two secrets you want are the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

## Make the credentials available to Terraform and Ansible

This project accesses the AWS credentials through environment variables. I created a local file called `~/.aws/profiles/meghan` which looks something like this:

```
export TF_VAR_iam_user=meghan
export TF_VAR_contact_email=mclarkk@berkeley.edu
export AWS_ACCESS_KEY_ID=***
export AWS_SECRET_ACCESS_KEY=***
```

The two "TF_VAR" variables are not required for Terraform to connect to AWS, but this project uses it to tag the various AWS resources it creates with contact info for auditing purposes.

To make my AWS credentials available to Terraform and Ansible, I simply source the file, like so:

`source ~/.aws/usr/meghan`

Note that this approach does mean storing your credentials in plain text on your computer, which could be dangerous, especially if your user has broad permissions. This solution had the best balance of security and complexity for me, but look up safer alternatives if you have concerns.

# 2. Configure the Project

This project requires you to supply a number of configuration variables in a file called `terraform.tfvars`. I have provided an example file in the repo, which looks like this:

```
# Project
env_prefix = "dev"                                              # used to name resources
project_name = "example-deployment"                             # used to name resources
instance_count = 2
instance_type = "t3.nano"
region = "us-west-1"
is_spot = true                                                  # choose between spot or on-demand instances

# SSH Access
ssh_approved_ips = ["192.184.203.246/32", "169.229.59.10/32"]   # CIDR blocks for work and home
ssh_key_name = "meghanix@mooncake"                              # can be any string
ssh_public_key_file = "/home/meghanix/.ssh/id_ed25519.pub"
```

You should change these variables to reflect your own project and SSH access information. 

IMPORTANT NOTE #1: For people working on a team, there is an important concept to understand. The current state of the infrastructure, managed by Terraform, is stored in an S3 bucket. This allows team members to synchronize their Terraform projects. **The project name determines where Terraform looks for the infrastructure state.** If multiple team members want to be able to modify the infrastructure, they must have the same `project_name` set in `terraform.tfvars` to synchronize their state. 

IMPORTANT NOTE #2: If you want to change the project name after you have already created infrastructure, make sure you destroy the existing infrastructure first. Otherwise the ec2_instance.py script will use Ansible to create a new remote state bucket for Terraform and the infrastructure under the old name will stay running. This would be a great thing to fix in the script someday.

IMPORTANT NOTE #3: If you are working with a team, note that there is only one set of approved IPs and one SSH key, which could cause some issues. Some options to deal with this: 1) Each team member runs `python ec2_instances.py create` to change the approved IPs/SSH key to their own before accessing the server (not great); 2) the approved IPs list contains the IP addresses of the whole team, and the first Terraform user uses Ansible to add more SSH keys in the .authorized_keys file on the server afterwards; or 3) the approved IPs list contains IP addresses of the whole team, and the team creates a new SSH key-pair for accessing this server and (securely) shares it among themselves.

## Additional variables

There are more variables you can change if desired. All possible variables are defined in `variables.tf`, along with any default values. This includes variables for the default region (us-west-1), the operating system/Amazon Machine Image for the EC2 instances (Amazon Linux), and so on. To override the defaults, simply add your definition of the variable to `terraform.tfvars`.

## Firewall rules

Another thing you will likely want to configure for your project is the firewall for your instance(s). By default, the firewall rules only allow ingress for SSH on port 22 from the IP addresses you provide. However, if you are running e.g. web services, you will likely need to open additional ports. In `main.tf`, there is a block called "aws_security_group" that contains the firewall rules. Add additional ingress blocks if needed. For example, to expose a web service running on port 80 that should be accessible from any computer, the firewall rules would become:

```
    # SSH access
    ingress {
        from_port        = 22
        to_port          = 22
        protocol         = "tcp"
        cidr_blocks      = var.my_ips
    }

    # Webserver access
    ingress {
        from_port        = 80
        to_port          = 80
        protocol         = "tcp"
        cidr_blocks      = ["0.0.0.0/0"]   # Allows any IP to access
    }

    # Allows local processes like e.g. package managers, docker to grab resources from the internet
    # will also allow ssh egress, webserver egress, etc.
    egress {
        from_port        = 0
        to_port          = 0
        protocol         = "-1"
        cidr_blocks      = ["0.0.0.0/0"]
        prefix_list_ids = []
    }
```

# 3. OPTIONAL: Post-creation Instance Configuration

After the servers are created, you will likely want to install and run things on them. Ansible is a great way to perform these fresh installation tasks automatically. With Ansible, you can install packages and libraries, start services, run Docker images, clone Git repos, transfer files, run programs, and so much more. Teaching Ansible is outside the scope of this README, but consider learning it if you're not already familiar with it. It can be the final step in truly automatic deployment of your application.

This script will look for a file called `fresh_installation_playbooks.txt` in the  `post-creation` folder. This file should contain a list of Ansible playbooks and their variables that should be run after the servers are created. The playbooks themselves should also be located in the `post-creation` folder. The script will tell you in advance what playbooks it has found (if any), and what it plans to run.

To skip this step, simply leave the `fresh_installation_playbooks.txt` file blank or delete it.

## File format

The format for `fresh_installation_playbooks.txt` is as follows. Each line specifies the name of a playbook located in the `post-creation` directory, followed by the variables you would pass to `--extra-vars`, if any. For example:

```
build-docker-image-from-git-repo.yaml repo_name=https://github.com/lab11/scarlett-chatbot
run-docker-image.yaml container_name=scarlett image_name=scarlett-slack:latest port_binding=3000:3000
```

The script will run these playbooks in order with the specified variables.

## Targeting specific hosts

In your post-creation playbooks, the hosts keyword 'all' will target all EC2 instances tagged with the project name and environment specified in `terraform.tfvars` (in other words, all the instances created by this script). You can also choose to target individual instances by their name in AWS. For example, if you create two instances and want to configure one to be a webserver and another to be a database, you can target each with `name_<server_name_in_AWS>`:

```
---
- name: Webserver play
  hosts: name_dev-example-deployment-server-1
  tasks:
    # webserver tasks

- name: Database play
  hosts: name_dev-example-deployment-server-2
  tasks:
    # database tasks
```

This works thanks to a dynamic inventory file called `post-creation/inventory_aws_ec.yaml` that is generated by this script from the template `post-creation/inventory_aws_ec.yaml.template`. If you want to change the way that the inventory is filtered or grouped, then modify the template file accordingly. 

# 4. Run the Script

Run `python ec2_instances.py create` to create the AWS resources. If you forget the IP addresses, running `python ec2_instances.py create` will fetch the latest state of the infrastructure and list them for you again.

Once you have the public IP(s), you should be able to SSH into each instance with `ssh ec2-user@<ec2_public_ip>` to confirm that the instance is up. You can then move on to configuring the server.

Note: One limitation of spot instance requests is that the AWS API does not allow users to set tags/names for the instances through the requests. This means that while on-demand instances created with this Terraform project will have names in the EC2 dashboard and tags with contact information, spot instances will not. It is strongly encouraged that you manually add name and contact email tags to spot instances. On the dashboard, you can identify which spot instances are associated with your project by their security groups and key names. Those resources will also have contact information in the tags.