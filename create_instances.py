import subprocess
import sys
import os
#import boto3, botocore
import importlib.util

separator = "\n"
indent = "  "
instance_config_filename = "fresh_installation_playbooks.txt"
bucket_name_prefix = "lab11-"
bucket_name_suffix = "-terraform"
s3_region = 'us-west-1'

def create_instances():
    # Check all the tool dependencies and configs
    check_prerequisites()

    # Extract helpful values from terraform.tfvars
    terraform_config = get_terraform_config()    

    # Set correct grammar for future messages about instance(s)
    s = "s"
    are = "are"
    they = "they"
    if int(terraform_config["instance_count"]) == 1:
        s = ""
        are = "is"
        they = "it"

    # Confirm that firewall rules are set
    print(subheading("Firewall rules"))
    confirm(f"Did you check terraform/main.tf to confirm that the firewall rules are correct for your instance{s}?")
    print(separator)

    # Confirm the instance configuration actions
    # print(subheading("Server configuration"))
    # print(f"Checking for {instance_config_filename}...")
    # config_playbooks = []
    # try:
    #     with open(instance_config_filename) as f:
    #         print(f"Found {instance_config_filename}")
    #         config_playbooks = f.readlines()
    # except FileNotFoundError:
    #     print(f"Could not find {instance_config_filename}.")
    # #print(config_playbooks)
    # num_config_playbooks = len(config_playbooks)
    # if num_config_playbooks == 0:
    #     confirm(f"\nAre you sure you don't want to use Ansible to automatically install or run anything on the server{s} after {they} {are} created?")
    # else:
    #     playbook_list = "\n".join(config_playbooks)
    #     confirm(f"After the instance{s} {are} created, these Ansible playbooks will be run in this order:\n{playbook_list}")
    # print(separator)

    ########################### 
    # CREATING INFRASTRUCTURE #
    ###########################

    print(heading("Creating AWS Infrastructure"))
    print(separator)

    print("Running Ansible to ensure there is an S3 bucket for the Terraform remote state...")
    # Run ansible create_s3_bucket.yaml
    os.chdir("./ansible")
    tf_bucket = get_terraform_bucket_name(terraform_config['project_name'])
    #ansible_command = subprocess.run(["ansible-playbook", "create-s3-bucket.yaml", '--extra-vars', f'bucket_name={tf_bucket}'], stdout=subprocess.PIPE, text=True)
    error_msg = "Problem creating S3 bucket for Terraform remote state."
    ansible_output = execute(["ansible-playbook", "create-s3-bucket.yaml", '--extra-vars', f'bucket_name={tf_bucket} s3_region={s3_region}'], error_msg)
    # If the bucket already exists, could be fine, could be a problem - require user confirmation to continue
    if ("Bucket already exists" in ansible_output):
        print(heading("WARNING! Confirmation Needed", sym="#", margin=" ", has_pad=False))
        print("\nWARNING: An S3 bucket for storing Terraform remote state for this project already exists!\nThere are two possibilities:\n\n" \
            + "1. S3 bucket names are global, so the name could already be taken by someone else, in which case you should change the project name to something more unique.\n" \
            + "2. This project already has infrastructure state associated with it, and Terraform will synchronize with the existing remote state.\n")
        confirm("Did you expect an existing S3 bucket for Terraform remote state for this project?")
    os.chdir("..")
    print(separator)

    print("Initializing Terraform project...")
    os.chdir("./terraform")
    # Run terraform init
    execute(["terraform", "init", f'-backend-config=bucket={tf_bucket}', f'-backend-config=region={s3_region}'], "Problem with initializing Terraform.")
    os.chdir("..")
    sys.exit()
    print(separator)

    print("Running Terraform...")
    os.chdir("./terraform")
    # Run terraform apply --auto-aprove
    # terraform_output = execute(["terraform", "apply", "--auto-approve"], "Something went wrong with 'terraform apply'")
    # # Get IP address(es) of instance(s)
    os.chdir("..")
    print(separator)

    print(f"Running Ansible to ensure the new EC2 instance{s} {are} correctly tagged...")
    os.chdir("./ansible")
    # Run ansible tag_ec2_instances
    # If something goes wrong in this step, report error and IP addresses, then exit
    os.chdir("..")
    print(separator)

    # Run instance configuration playbooks
    # if len(config_playbooks) > 0:
    #   os.chdir("./ansible")
    #     print(f"Running Ansible playbooks to configure the new instance{s}...")
    # # If something goes wrong in this step, report error and IP addresses, then exit
    # os.chdir("..")
    # print(separator)

    # Report IP addresses
    print(f"Your instance{s} {are} available at:")
    print(f"<IP{s}>")

def destroy_instances():
    # Check all the tool dependencies and configs
    check_prerequisites()

    # Extract helpful values from terraform.tfvars
    terraform_config = get_terraform_config()    
    project_name = terraform_config["project_name"]

    confirm(f"Final confirmation: Do you want to delete all instances and supporting infrastructure associated with {project_name}?")

    print(heading("Destroying AWS Infrastructure"))
    print(separator)

    # Run terraform destroy to take down project infrastructure
    print("Running Terraform destroy...")
    os.chdir("./terraform")
    # Run terraform destroy
    execute(["terraform", "destroy", "--auto-approve"], "Problem during terraform destroy.")
    os.chdir("..")
    print(separator)

    # Use Ansible to delete the terraform remote state bucket in S3
    print("Using Ansible to delete the S3 bucket for Terraform's remote state...")
    os.chdir("./ansible")
    tf_bucket = get_terraform_bucket_name(terraform_config['project_name'])
    error_msg = f"Something went wrong deleting the S3 bucket {tf_bucket}"
    execute(["ansible-playbook", "delete-s3-bucket.yaml", '--extra-vars', f'bucket_name={tf_bucket}'], error_msg)
    os.chdir("..")
    print(separator)

    # Delete the local terraform backend files
    print("Cleaning up local Terraform directory...")
    os.chdir("./terraform")
    # Delete .terraform folder, terraform.tfstate, terraform.tfstate.backup, and lock file - if present
    os.chdir("..")
    print(separator)

    print("Done.")


def check_prerequisites():
    print(heading("Welcome to the Lab11 EC2 Deployer helper script!"))
    print(separator)

    ########################## 
    # CHECKING CONFIGURATION #
    ##########################

    # check that all tools are installed
    print(subheading("Checking for Terraform installation"))
    check_installed("terraform")
    print(separator)

    print(subheading("Checking for Ansible installation"))
    check_installed("ansible")
    print(separator)

    print(subheading("Checking for boto3 and botocore Python library installations"))
    check_module("boto3")
    check_module("botocore")
    print(separator)

    # check that AWS credentials are set
    print(subheading("Checking for AWS credentials"))
    check_env_vars(["TF_VAR_iam_user", "TF_VAR_contact_email", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
    print(separator)

    # Confirm that terraform.tfvars is accurate
    print(subheading("Infrastructure configuration"))
    confirm("Did you check terraform/terraform.tfvars to make sure it reflects your project (especially the SSH credentials)?")
    print(separator)


def heading(title, sym="#", margin="   ", has_pad=True):
    mid = f"{sym}{margin}{title}{margin}{sym}"
    border = sym * len(mid)
    pad = sym + " " * (len(mid) - 2) + sym
    heading_str = f"{border}\n{pad}\n{mid}\n{pad}\n{border}" if has_pad else f"{border}\n{mid}\n{border}"
    return heading_str

def subheading(title):
    return(f"--- {title}")

def check_installed(program, indent=""):
    rc = subprocess.call(["which", program])
    if rc == 0:
        print(f"{indent}Found {program} command")
    else:
        print(f"{indent}The command {program} is missing, please install")
        sys.exit()

def check_module(module, indent=""):
    spec = importlib.util.find_spec(module)
    if spec is None:
        print(f"{indent}Python library {module} is not installed. Run 'pip install -r requirements.txt'")
        sys.exit()
    else:
        print(f"Found {module}")

def confirm(message, indent=""):
    print(f"{indent}{message}")
    try:
        ans = input(f"\n{indent} Type 'yes' to confirm: ")
        if ans.lower() != 'yes':
            print("\nExiting...")
            sys.exit()
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit()

def check_env_vars(env_vars):
    for variable in env_vars:
        ev = os.getenv(variable)
        if ev != None:
            print(f"{variable} is set")
        else:
            print(f"{variable} is not set")
            ev_list = "\n".join(env_vars)
            print(f"Please make sure the following environment variables are set: \n{ev_list}")
            sys.exit()

def get_terraform_config(tfvars_file="./terraform/terraform.tfvars"):
    terraform_config = {}
    with open(tfvars_file) as f:
        for line in f.readlines():
            if '=' in line: # only look at variable definition lines
                if '#' in line: # remove inline comments
                    line, comment = line.split('#')
                key, val = line.split("=")
                terraform_config[key.strip()] = val.strip().replace('"', '') # remove leading/trailing whitespace
    return terraform_config 

def get_terraform_bucket_name(project_name):
    return f"{bucket_name_prefix}{project_name}{bucket_name_suffix}"

def execute(cmd, err_msg):
    cmd_output = ""
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end='')
            cmd_output += line
    if p.returncode != 0:
        print(err_msg)
        sys.exit()    
    return cmd_output

if __name__=="__main__":
    usage = "\nUsage:\n\tpython ec2_instances.py create\n\tpython ec2_instances.py destroy\n"
    if len(sys.argv) != 2:
        print(usage)
        sys.exit()
    if sys.argv[1] == "create":
        create_instances()
    elif sys.argv[1] == "destroy":
        destroy_instances()
    else:
        print(usage)
        sys.exit()