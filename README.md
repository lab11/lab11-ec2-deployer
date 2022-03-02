
This example Terraform project creates a specified number of AWS EC2 spot instances with SSH enabled and provides you with their public IP addresses.

# How to use this project

* Fork or create a new branch for your project

Once you have your own version to modify, these are the steps for running the project:

* Authenticate to AWS on the command line
* Configure the Terraform backend
* Configure the Terraform project
* Run Terraform to create the instances

See the note at the end for how to clean up your project when you're done with it.

# 1. Authenticate to AWS

Terraform needs AWS credentials in order to create AWS resources. This means you will need to 1) make sure you have an AWS user on the IAM service, 2) obtain your credentials, and 3) make the credentials available to Terraform.

## Find/create your AWS IAM user

In the Lab 11 AWS web portal, navigate to the IAM service. There should be a user with your name (e.g. `meghan`) that has the appropriate permissions to create these resources (EC2 instances and VPC components). If an IAM user does not exist for you, you should create one.

## Get your IAM user credentials

You can find the secrets for your user by using the IAM service's web interface. The two secrets you want are the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

## Make the credentials available to Terraform

I prefer to do this through environment variables. I created a local file called `~/.aws/usr/meghan` which looks something like this:

```
export TF_VAR_iam_user=meghan
export TF_VAR_contact_email=mclarkk@berkeley.edu
export AWS_ACCESS_KEY_ID=***
export AWS_SECRET_ACCESS_KEY=***
```

The two "TF_VAR" variables are not required for Terraform to connect to AWS, but this project uses it to tag the various AWS resources it creates with contact info for auditing purposes.

To make my AWS credentials available to Terraform, I simply source the file, like so:

`source ~/.aws/usr/meghan`

Note that this approach does mean storing your credentials in plain text on your computer, which could be dangerous, especially if your user has broad permissions. This solution had the best balance of security and complexity for me, but look up safer alternatives if you have concerns.

# 2. Configure the Terraform Backend

Terraform stores the current state of the infrastructure as JSON in a flat file. Storing state allows it to do things like avoid recreating resources that already exist, modify existing resources with minor changes, and destroy everything it has created.

This state can be stored locally on one computer, but is best stored in the cloud. Storing the state in the cloud allows teams on different computers to synchronize their Terraform projects. It also provides better reliability and access to backups. This project is set up to use AWS S3 as the backend storage for the state file.

In AWS, make an S3 bucket. The default settings are fine. Remember the name of the bucket (e.g. `<project name>-terraform`) and the region you created it in (e.g. `us-west-1`).

Run `terraform init` in this directory to install the required AWS modules and set up the initial state. Terraform will prompt you to provide the S3 bucket name and region, which is where it will store the state of the infrastructure.

# 3. Configure the Terraform project

This Terraform project requires you to supply a number of configuration variables in a file called `terraform.tfvars`. (It must be called this for Terraform to find it automatically, otherwise you will need to specify the name of the variable file on the command line.) I have provided an example file in the repo, which looks like this:

```
# Project
env_prefix = "dev"                                              # used to name resources
project_name = "terraform-tutorial"                             # used to name resources
instance_count = 2
instance_type = "t3.nano"

# SSH Access
ssh_approved_ips = ["192.184.203.246/32", "169.229.59.10/32"]   # CIDR blocks for work and home
ssh_key_name = "meghanix@mooncake"                              # can be any string
ssh_public_key_file = "/home/meghanix/.ssh/id_ed25519.pub"
```

You should change these variables to reflect your own project and SSH access information. 

Keep in mind that if you are working with a team, there is only one set of approved IPs and one SSH key, which could cause some issues. Some options to deal with this: 1) Each team member runs `terraform apply` to change the approved IPs/SSH key to their own before accessing the server; 2) the approved IPs list contains the IP addresses of the whole team, and the first Terraform user manually adds more SSH keys in the .authorized_keys file on the server afterwards; or 3) the approved IPs list contains IP addresses of the whole team, and the team creates a new SSH key-pair for accessing this server and (securely) shares it among themselves.

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

# 4. Run Terraform

Run `terraform apply` to create the necessary AWS resources. First Terraform will show you what AWS resources it plans to create, and if you confirm, it will create those resources. 

The first time you run `terraform apply`, Terraform will **not** show you the public IP(s) of the instance(s). This is because of the way that spot instances work. The Terraform module creates a _request_ for an instance, rather than creating an EC2 instance directly like it would with an on-demand instance. That means there may not be an IP address available yet by the time the first `terraform apply` finishes. Simply run `terraform refresh` afterwards to get the public IP(s). If you ever forget the IP addresses, running `terraform refresh` will fetch the latest state of the infrastructure and list them for you.

Once you have the public IP(s), you should be able to SSH into each instance with `ssh ec2-user@<ec2_public_ip>` to confirm that the instance is up. You can then move on to configuring the server.

# Project Cleanup

The command `terraform destroy` will destroy everything Terraform has created for this project according to the state file, which can be useful for starting fresh or removing the deployment for billing purposes. Don't worry, you can easily recreate it later with another `terraform apply`. In fact, depending on how much configuration your server needs after creation, you can even `terraform destroy` every night and `terraform apply` in the morning.

If you ever want to completely decommission the deployment and erase all traces of it forever:

* Run `terraform destroy` to delete all the AWS infrastructure
* Manually delete the S3 bucket that holds the Terraform remote state
* Remove any AWS_\* and TF_VAR_\* environment variables for this project from your system