from ipaddress import ip_address
import subprocess
import sys
import os
#import boto3, botocore
import importlib.util
import re

from rsa import PrivateKey

separator = "\n"
indent = "  "
ansible_dir = "./ansible"
terraform_dir = "./terraform"
post_creation_dir = "./post-creation"
instance_config_file = "fresh_installation_playbooks.txt"
bucket_name_prefix = "lab11-"
bucket_name_suffix = "-terraform"
s3_region = 'us-west-1'
terraform_output_var = "ec2_public_ips"
inventory_template = "inventory_aws_ec2.yaml.template"
inventory_filename = "inventory_aws_ec2.yaml"

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

    # Confirm the post-creation configuration
    print(subheading("Server configuration"))
    os.chdir(post_creation_dir)
    print(f"Checking for {instance_config_file}...")
    config_playbooks = []
    try:
        with open(instance_config_file) as f:
            print(f"Found {instance_config_file}")
            config_playbooks = f.readlines()
        config_playbooks = [get_filename_and_vars(pb_info) for pb_info in config_playbooks]
    except FileNotFoundError:
        print(f"Could not find {instance_config_file}.")
    num_config_playbooks = len(config_playbooks)
    print(f"{num_config_playbooks} Ansible playbooks found.")
    if num_config_playbooks == 0:
        confirm(f"\nAre you sure you don't want to use Ansible to automatically install or run anything on the server{s} after {they} {are} created?")
    else:
        playbook_list = "\n".join(["   " + p[0].strip() for p in config_playbooks])
        confirm(f"\nAfter the instance{s} {are} created, these Ansible playbooks will be run in this order:\n\n{playbook_list}")
    os.chdir('..')
    print(separator)

    ########################### 
    # CREATING INFRASTRUCTURE #
    ###########################

    print(heading("Creating AWS Infrastructure"))
    print(separator)

    print("Running Ansible to ensure there is an S3 bucket for the Terraform remote state...")
    # Run ansible create_s3_bucket.yaml
    os.chdir(ansible_dir)
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
        confirm("Did you expect existing state for this project?")
    os.chdir("..")
    print(separator)

    print("Initializing Terraform project...")
    os.chdir(terraform_dir)
    # Run terraform init
    execute(["terraform", "init", f'-backend-config=bucket={tf_bucket}', f'-backend-config=region={s3_region}'], "Problem initializing Terraform.")
    os.chdir("..")
    print(separator)

    print("Running Terraform...")
    os.chdir(terraform_dir)
    # Run terraform apply --auto-aprove
    terraform_output = execute(["terraform", "apply", "--auto-approve"], "Something went wrong with 'terraform apply'")
    # # Get IP address(es) of instance(s)
    ip_output_block_matcher = re.compile("ec2_public_ips = \[[^\]]*\]")
    ip_output_blocks = ip_output_block_matcher.findall(terraform_output)
    if len(ip_output_blocks) == 0:
        print("Could not find IP addresses in Terraform output! Exiting...")
        sys.exit()
    ip_addr_matcher = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
    public_ip_addresses = ip_addr_matcher.findall(ip_output_blocks[-1])
    os.chdir("..")
    print(separator)

    print(f"Running Ansible to ensure the new EC2 instance{s} {are} correctly tagged...")
    os.chdir(ansible_dir)
    # prepare the variables
    project_name = terraform_config["project_name"]
    env_prefix = terraform_config["env_prefix"]
    region = terraform_config["region"]
    IAM_user = os.getenv("TF_VAR_iam_user")
    contact_email = os.getenv("TF_VAR_contact_email")
    # Run ansible-playbook tag_ec2_instances.yaml --extra-vars "project_name={project_name} contact_email={contact_email}" etc.
    ansible_vars = f"project_name={project_name} contact_email={contact_email} env={env_prefix} region={region} IAM_user={IAM_user}"
    # Run command. If something goes wrong in this step, report error and IP addresses, then exit
    error_msg = summary_string(tf_bucket, public_ip_addresses) + "\n\nERROR: Something went wrong while tagging instances."
    ansible_output = execute(["ansible-playbook", "tag-ec2-instances.yaml", '--extra-vars', ansible_vars], error_msg)
    os.chdir("..")
    print(separator)

    # Create dynamic inventory file
    os.chdir(post_creation_dir)
    print(f"Generating dynamic EC2 inventory file for Ansible...")
    inventory_file_contents = get_dynamic_inventory_str(inventory_template, project_name, env_prefix, region)
    with open(inventory_filename, 'w') as f:
        f.write(inventory_file_contents)
    os.chdir("..")
    print(separator)

    # Run instance configuration playbooks
    os.chdir(post_creation_dir)
    if len(config_playbooks) > 0:
        print(f"Running Ansible playbooks to configure the new instance{s}...")
        ssh_private_key_file = get_private_key_file(terraform_config["ssh_public_key_file"])
        for (pb, pb_vars) in config_playbooks:
            error_msg = summary_string(tf_bucket, public_ip_addresses) + f"\n\nERROR: Something went wrong executing {pb}. Server configuration may not have completed."
            if len(pb_vars) == 0:
                execute(["ansible-playbook", pb, '--private-key', ssh_private_key_file], error_msg)
            else:
                execute(["ansible-playbook", pb, '--private-key', ssh_private_key_file, "--extra-vars", pb_vars], error_msg)
    # If something goes wrong in this step, report error and IP addresses, then exit
    os.chdir("..")
    print(separator)

    # Report IP addresses
    print(summary_string(tf_bucket, public_ip_addresses, s, are))



############################# 
# DESTROYING INFRASTRUCTURE #
#############################
def destroy_instances():
    # Check all the tool dependencies and configs
    check_prerequisites()

    # Extract helpful values from terraform.tfvars
    terraform_config = get_terraform_config()    
    project_name = terraform_config["project_name"]

    print("")
    print(subheading("Final confirmation"))
    confirm(f"Do you want to delete all instances and supporting infrastructure associated with {project_name}?")
    print(separator)

    print(heading("Destroying AWS Infrastructure"))
    print(separator)

    # Run terraform destroy to take down project infrastructure
    print("Running Terraform destroy...")
    os.chdir(terraform_dir)
    # Run terraform destroy
    execute(["terraform", "destroy", "--auto-approve"], "Problem during terraform destroy.")
    os.chdir("..")
    print(separator)

    # Use Ansible to delete the terraform remote state bucket in S3
    print("Using Ansible to delete the S3 bucket for Terraform's remote state...")
    os.chdir(ansible_dir)
    tf_bucket = get_terraform_bucket_name(terraform_config['project_name'])
    error_msg = f"Something went wrong deleting the S3 bucket {tf_bucket}"
    execute(["ansible-playbook", "delete-s3-bucket.yaml", '--extra-vars', f'bucket_name={tf_bucket}'], error_msg)
    os.chdir("..")
    print(separator)

    # Delete the local terraform backend files
    print("Cleaning up local Terraform directory...")
    os.chdir(terraform_dir)
    # Delete .terraform folder, terraform.tfstate, terraform.tfstate.backup, and lock file - if present
    existing_files = execute(["ls", "-la"], print_to_terminal=False)
    files_to_delete = [".terraform", ".terraform.tfstate", ".terraform.tfstate.backup", ".terraform.lock.hcl"]
    for filename in files_to_delete:
        if filename in existing_files:
            print(f"removing {filename}")
            execute(["rm", "-rf", filename])
    os.chdir("..")
    print(separator)

    # Delete the dynamic inventory file
    print("Cleaning up inventory file in post-creation directory...")
    os.chdir(post_creation_dir)
    print(f"removing {inventory_filename}")
    execute(["rm", inventory_filename])
    os.chdir('..')
    print(separator)

    print("Done.")

########################## 
# CHECKING CONFIGURATION #
##########################
def check_prerequisites():
    print(heading("Welcome to the Lab11 EC2 Deployer script!"))
    print(separator)

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
    confirm("Did you check terraform/terraform.tfvars to make sure it reflects your project and access credentials?")
    print(separator)



########################## 
#    HELPER FUNCTIONS    #
##########################

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
        print(f"Did not find {module}, running 'pip install -r requirements.txt'")
        execute(["pip", "install", "-r", "requirements.txt"])
        spec = importlib.util.find_spec(module)
        if spec is None:
            print(f"{indent}Python library {module} is not installed. Run 'pip install -r requirements.txt'")
            sys.exit()
        else:
            print(f"Found {module}")
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

def execute(cmd, err_msg="", print_to_terminal=True):
    if err_msg == "":
        err_msg = f"Error while executing {cmd}"
    cmd_output = ""
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            if print_to_terminal:
                print(line, end='')
            cmd_output += line
    if p.returncode != 0:
        print("\n" + err_msg)
        sys.exit()    
    return cmd_output

def summary_string(bucket_name, ip_list, s, are):
    s = heading("Summary", margin="          ")
    s += "\n\n"
    s += terraform_state_summary_string(bucket_name)
    s += "\n\n"
    s += ip_address_summary_string(ip_list, s, are)
    return s

def terraform_state_summary_string(bucket_name):
    return f"Terraform remote state for this project is stored in the following S3 bucket:\n{bucket_name}"

def ip_address_summary_string(ip_list, a, are):
    s = f"Your instance{s} {are} available at:\n"
    s += "\n".join(ip_list)
    s += "\n\n"
    s += "SSH access: ssh ec2-user@<ip_address>"
    s += "If the key is not your default SSH key: ssh ec2-user@<ip_address> -i <private_key_path>"
    return s

def get_dynamic_inventory_str(inventory_template_file, project, env, region):
    with open(inventory_template_file, 'r') as f:
        print(f"Found {inventory_template_file}")
        template_str = f.read()
    macros = {"ENV": env, "PROJECT": project, "REGION": region}
    for macro in macros:
        template_str = template_str.replace(macro, macros[macro])
    return template_str

# takes in a string, one line from the instance_config_file
# SHOULD be a playbook filename, with optional extra-vars. 
# E.g.:
# paybookname.yaml
# or
# playbookname.yaml var1=val var2=val
# etc.
def get_filename_and_vars(pb_info):
    pb_info = pb_info.strip()
    playbook_info_regex = '(^(.+.ya?ml)(\s+[a-zA-Z]+[a-zA-Z\d_]*=[\S]+.*)*$)'
    valid_playbook_info = re.compile(playbook_info_regex)
    matches = re.search(valid_playbook_info, pb_info)
    if matches:
        pb_filename = matches.group(2)
        extra_vars = ''
        if matches.group(3) is not None:
            extra_vars = matches.group(3).strip()
    else:
        raise PostCreationFileFormatError(f"\nProblem parsing the format of {instance_config_file} on the following line:\n\n\t{pb_info}\n")
    return (pb_filename, extra_vars)

def get_private_key_file(public_key_file):
    error_msg = "\nERROR: Could not guess the SSH private key filename from the public key filename in terraform.tfvars." \
                + "\nCannot run Ansible on the remote servers."
    private_key_file = ""
    if public_key_file[-4:] == ".pub":
        # get the public key directory from the full public key file path
        public_key_dir = public_key_file[:public_key_file.rfind('/')+1]
        private_key_prefix = public_key_file[public_key_file.rfind('/')+1:].replace(".pub", "")
        print(public_key_dir)
        print(private_key_prefix)
        # get all files in the public key directory    
        nearby_files = os.listdir(public_key_dir)
        print(nearby_files)
        print(len(nearby_files))
        candidate = ""
        num_candidates_found = 0
        for nf in nearby_files:
            if private_key_prefix in nf and ".pub" not in nf:
                candidate = nf
                num_candidates_found += 1
        if num_candidates_found == 1:
            private_key_file = public_key_dir + candidate
        else:
            raise PrivateKeyDetectionError(error_msg)
    else:
        raise PrivateKeyDetectionError(error_msg)
    return private_key_file

class PrivateKeyDetectionError(Exception):
    pass

class PostCreationFileFormatError(Exception):
    pass

if __name__=="__main__":
    usage = "\nUsage:\n\tpython ec2_deployer.py apply\n\tpython ec2_deployer.py destroy\n"
    if len(sys.argv) != 2:
        print(usage)
        sys.exit()
    if sys.argv[1] == "apply":
        create_instances()
    elif sys.argv[1] == "destroy":
        destroy_instances()
    else:
        print(usage)
        sys.exit()