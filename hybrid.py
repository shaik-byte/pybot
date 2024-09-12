import os
import boto3
import logging
import paramiko
from io import StringIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    CallbackContext,
    MessageHandler,
    filters
)
from kubernetes import client, config
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
TOKEN = 'Your bot token'
BOT_USERNAME = 'Your bot username'
AWS_ACCESS_KEY_ID = 'AWS access key'
AWS_SECRET_ACCESS_KEY = 'AWS secret key'
AWS_REGION = 'AWS regions'

# Hardcoded PEM file content (Ensure proper format and no extra spaces or characters)
PEM_CONTENT = "your PEM"

# AWS Regions
AWS_REGIONS = {
    "US East (N. Virginia)": "us-east-1",
    "US East (Ohio)": "us-east-2",
    "US West (N. California)": "us-west-1",
    "US West (Oregon)": "us-west-2",
    "Africa (Cape Town)": "af-south-1",
    "Asia Pacific (Hong Kong)": "ap-east-1",
    "Asia Pacific (Hyderabad)": "ap-south-2",
    "Asia Pacific (Mumbai)": "ap-south-1",
    "Asia Pacific (Osaka)": "ap-northeast-3",
    "Asia Pacific (Seoul)": "ap-northeast-2",
    "Asia Pacific (Singapore)": "ap-southeast-1",
    "Asia Pacific (Sydney)": "ap-southeast-2",
    "Asia Pacific (Tokyo)": "ap-northeast-1",
    "Canada (Central)": "ca-central-1",
    "Europe (Frankfurt)": "eu-central-1",
    "Europe (Ireland)": "eu-west-1",
    "Europe (London)": "eu-west-2",
    "Europe (Milan)": "eu-south-1",
    "Europe (Paris)": "eu-west-3",
    "Europe (Spain)": "eu-south-2",
    "Europe (Stockholm)": "eu-north-1",
    "Europe (Zurich)": "eu-central-2",
    "Middle East (Bahrain)": "me-south-1",
    "Middle East (UAE)": "me-central-1",
    "South America (São Paulo)": "sa-east-1"
}

# Step 1: Authenticate with AWS and list EKS clusters
def authenticate_aws(region_name):
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=region_name
    )
    return session

def list_eks_clusters(eks_client):
    response = eks_client.list_clusters()
    clusters = response['clusters']
    return clusters

# Step 2: Get kubeconfig for the EKS cluster
def get_kubeconfig(cluster_name, eks_client):
    cluster_info = eks_client.describe_cluster(name=cluster_name)
    cluster_endpoint = cluster_info['cluster']['endpoint']
    cluster_ca = cluster_info['cluster']['certificateAuthority']['data']
    
    kubeconfig_content = f"""
apiVersion: v1
clusters:
- cluster:
    server: {cluster_endpoint}
    certificate-authority-data: {cluster_ca}
  name: {cluster_name}
contexts:
- context:
    cluster: {cluster_name}
    user: aws
  name: {cluster_name}
current-context: {cluster_name}
kind: Config
preferences: {{}}
users:
- name: aws
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1alpha1
      command: aws-iam-authenticator
      args:
        - "token"
        - "-i"
        - "{cluster_name}"
"""
    return kubeconfig_content

def write_kubeconfig(cluster_name, eks_client):
    kubeconfig = get_kubeconfig(cluster_name, eks_client)
    with open('kubeconfig', 'w') as f:
        f.write(kubeconfig)
    os.environ['KUBECONFIG'] = os.path.abspath('kubeconfig')

# Step 3: Configure Kubernetes client and interact with the cluster
def configure_kubernetes_client():
    config.load_kube_config()
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    return v1, apps_v1

def list_kubernetes_resources(v1, apps_v1):
    # List Deployments
    deployments = apps_v1.list_deployment_for_all_namespaces(watch=False)
    deployment_list = [f"{dep.metadata.name} - {dep.spec.replicas} replicas" for dep in deployments.items]

    # List Pods
    pods = v1.list_pod_for_all_namespaces(watch=False)
    pod_list = [f"{pod.metadata.name} - IP: {pod.status.pod_ip}, Port: {pod.spec.containers[0].ports[0].container_port}" for pod in pods.items if pod.spec.containers[0].ports]

    # Combine deployment and pod lists
    message = "Deployments:\n" + "\n".join(deployment_list) + "\n\n" + "Pods:\n" + "\n".join(pod_list)
    return message

def list_pods(v1):
    pods = v1.list_pod_for_all_namespaces(watch=False)
    return [pod.metadata.name for pod in pods.items]

async def get_pod_logs(v1, pod_name):
    try:
        logs = v1.read_namespaced_pod_log(name=pod_name, namespace='default')
        return logs
    except client.exceptions.ApiException as e:
        return f"Error fetching logs: {e}"

# Function to list all AWS resources in the specified region
def list_all_aws_resources(session):
    resources = {}

    # EC2 Instances with status
    ec2_client = session.client('ec2')
    instances = ec2_client.describe_instances()
    resources['EC2 Instances'] = [
        f"{instance['InstanceId']} ({instance['State']['Name']})"
        for reservation in instances['Reservations']
        for instance in reservation['Instances']
    ]
    
    # S3 Buckets
    s3_client = session.client('s3')
    buckets = s3_client.list_buckets()
    resources['S3 Buckets'] = [bucket['Name'] for bucket in buckets['Buckets']]
    
    # Lambda Functions
    lambda_client = session.client('lambda')
    functions = lambda_client.list_functions()
    resources['Lambda Functions'] = [function['FunctionName'] for function in functions['Functions']]
    
    return resources

# Function to create an EC2 instance
def create_ec2_instance(session):
    ec2_client = session.client('ec2')
    
    # Modify these parameters according to your requirements
    instance = ec2_client.run_instances(
        ImageId='ami-0e86e20dae9224db8',  # Example AMI ID for Amazon Linux 2
        InstanceType='t2.micro',
        KeyName='mlops',  # Replace with your key pair name
        MinCount=1,
        MaxCount=1
    )
    
    instance_id = instance['Instances'][0]['InstanceId']
    return instance_id

# Function to destroy an EC2 instance
def destroy_ec2_instance(session, instance_id):
    ec2_client = session.client('ec2')
    ec2_client.terminate_instances(InstanceIds=[instance_id])

# Function to start an EC2 instance
def start_ec2_instance(session, instance_id):
    ec2_client = session.client('ec2')
    ec2_client.start_instances(InstanceIds=[instance_id])

# Function to stop an EC2 instance
def stop_ec2_instance(session, instance_id):
    ec2_client = session.client('ec2')
    ec2_client.stop_instances(InstanceIds=[instance_id])

# Function to connect to an EC2 instance using SSH
def connect_to_ec2(instance_ip, command):
    try:
        key = paramiko.RSAKey.from_private_key(StringIO(PEM_CONTENT))
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Update the username to 'ubuntu'
        ssh.connect(hostname=instance_ip, username="ubuntu", pkey=key)

        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode('utf-8')
        ssh.close()

        return output
    except paramiko.ssh_exception.NoValidConnectionsError as e:
        return f"Connection failed: {e}"
    except Exception as e:
        return f"Error connecting to EC2 instance: {e}"

# Function to get AWS billing data
def get_billing_data():
    cost_explorer = boto3.client('ce', 
        aws_access_key_id=AWS_ACCESS_KEY_ID, 
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY, 
        region_name=AWS_REGION)

    today = datetime.utcnow()
    first_day_of_current_month = today.replace(day=1)
    first_day_of_last_month = (first_day_of_current_month - timedelta(days=1)).replace(day=1)
    last_day_of_last_month = first_day_of_current_month - timedelta(days=1)

    # Month-to-date cost
    mtd_cost = cost_explorer.get_cost_and_usage(
        TimePeriod={'Start': first_day_of_current_month.strftime('%Y-%m-%d'), 'End': today.strftime('%Y-%m-%d')},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost']
    )['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']

    # Last month's cost for the same time period
    last_month_same_period_cost = cost_explorer.get_cost_and_usage(
        TimePeriod={'Start': first_day_of_last_month.strftime('%Y-%m-%d'), 'End': (first_day_of_last_month + (today - first_day_of_current_month)).strftime('%Y-%m-%d')},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost']
    )['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']

    # Total forecasted cost for the current month
    forecasted_cost = cost_explorer.get_cost_forecast(
        TimePeriod={'Start': today.strftime('%Y-%m-%d'), 'End': (today.replace(day=1) + timedelta(days=32)).replace(day=1).strftime('%Y-%m-%d')},
        Metric='UNBLENDED_COST',
        Granularity='MONTHLY'
    )['Total']['Amount']

    # Last month's total cost
    last_month_total_cost = cost_explorer.get_cost_and_usage(
        TimePeriod={'Start': first_day_of_last_month.strftime('%Y-%m-%d'), 'End': last_day_of_last_month.strftime('%Y-%m-%d')},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost']
    )['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']

    return {
        "Month-to-date cost": mtd_cost,
        "Last month's cost for the same period": last_month_same_period_cost,
        "Total forecasted cost for the current month": forecasted_cost,
        "Last month's total cost": last_month_total_cost
    }

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Hello there, Welcome to Pykube bot, <::> I am here to server you!')
    logger.info('Bot started by user: %s', update.message.from_user.username)

async def list_resources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    eks_client = authenticate_aws(AWS_REGION)
    clusters = list_eks_clusters(eks_client)
    if clusters:
        cluster_name = clusters[0]  # Using the first cluster from the list
        write_kubeconfig(cluster_name, eks_client)

        v1, apps_v1 = configure_kubernetes_client()
        resources_message = list_kubernetes_resources(v1, apps_v1)

        await update.message.reply_text(resources_message)
    else:
        await update.message.reply_text("No EKS clusters found.")
    logger.info('List resources command executed by user: %s', update.message.from_user.username)

async def deploy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Usage: /deploy <docker_image> <pod_name> <deployment_name>")
        return

    docker_image, pod_name, deployment_name = args

    eks_client = authenticate_aws(AWS_REGION)
    clusters = list_eks_clusters(eks_client)
    if clusters:
        cluster_name = clusters[0]  # Using the first cluster from the list
        write_kubeconfig(cluster_name, eks_client)

        v1, apps_v1 = configure_kubernetes_client()
        deployment_message = create_deployment(v1, apps_v1, docker_image, pod_name, deployment_name)

        await update.message.reply_text(deployment_message)
    else:
        await update.message.reply_text("No EKS clusters found.")
    logger.info('Deploy command executed by user: %s', update.message.from_user.username)

async def list_pods_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    eks_client = authenticate_aws(AWS_REGION)
    clusters = list_eks_clusters(eks_client)
    if clusters:
        cluster_name = clusters[0]
        write_kubeconfig(cluster_name, eks_client)

        v1, _ = configure_kubernetes_client()
        pods = list_pods(v1)

        # Create inline keyboard with pod options
        keyboard = [[InlineKeyboardButton(f"pod-{pod}", callback_data=f"pod-{pod}")] for pod in pods]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text('Select a pod to get its logs:', reply_markup=reply_markup)
    else:
        await update.message.reply_text("No EKS clusters found.")
    logger.info('List pods command executed by user: %s', update.message.from_user.username)

async def pod_logs_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    pod_name = query.data.split('-')[1]  # Extract pod name from callback data

    eks_client = authenticate_aws(AWS_REGION)
    clusters = list_eks_clusters(eks_client)
    if clusters:
        cluster_name = clusters[0]
        write_kubeconfig(cluster_name, eks_client)

        v1, _ = configure_kubernetes_client()
        logs = await get_pod_logs(v1, pod_name)

        await query.edit_message_text(text=f"Logs for pod {pod_name}:\n{logs}")
    else:
        await query.edit_message_text(text="No EKS clusters found.")
    logger.info('Pod logs command executed by user: %s', query.from_user.username)

# Command to list all AWS resources
async def list_all_resources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = authenticate_aws(AWS_REGION)

    resources = list_all_aws_resources(session)
    resources_message = "\n".join([f"{key}: {', '.join(value)}" for key, value in resources.items()])

    await update.message.reply_text(resources_message)
    logger.info('List all resources command executed by user: %s', update.message.from_user.username)

# Command to create an EC2 instance
async def create_ec2_instance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = authenticate_aws(AWS_REGION)

    instance_id = create_ec2_instance(session)

    await update.message.reply_text(f"EC2 instance created with ID: {instance_id}")
    logger.info('Create EC2 instance command executed by user: %s', update.message.from_user.username)

# Command to destroy an EC2 instance
async def destroy_ec2_instance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = authenticate_aws(AWS_REGION)

    ec2_client = session.client('ec2')
    instances = ec2_client.describe_instances()

    # Extract instance details including state
    instance_details = [
        (instance['InstanceId'], instance['State']['Name'])
        for reservation in instances['Reservations']
        for instance in reservation['Instances']
    ]

    if not instance_details:
        await update.message.reply_text("No EC2 instances found.")
        return

    # Create inline keyboard with instance options including state
    keyboard = [[InlineKeyboardButton(f"{instance_id} - {state}", callback_data=f'i-{instance_id}')] for instance_id, state in instance_details]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text('Select an EC2 instance to destroy:', reply_markup=reply_markup)
    logger.info('Destroy EC2 instance command executed by user: %s', update.message.from_user.username)

async def destroy_ec2_instance_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    instance_id = query.data.split('-', 1)[1]  # Extract the instance ID from the callback data

    session = authenticate_aws(AWS_REGION)

    destroy_ec2_instance(session, instance_id)

    await query.edit_message_text(text=f"EC2 instance {instance_id} has been terminated.")
    logger.info('EC2 instance destroyed by user: %s', query.from_user.username)

# Command to start an EC2 instance
async def start_ec2_instance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = authenticate_aws(AWS_REGION)

    ec2_client = session.client('ec2')
    instances = ec2_client.describe_instances()

    # Extract stopped instance details
    instance_details = [
        (instance['InstanceId'], instance['State']['Name'])
        for reservation in instances['Reservations']
        for instance in reservation['Instances']
        if instance['State']['Name'] == 'stopped'
    ]

    if not instance_details:
        await update.message.reply_text("No stopped EC2 instances found.")
        return

    # Create inline keyboard with instance options for starting
    keyboard = [[InlineKeyboardButton(f"{instance_id} - {state}", callback_data=f's-{instance_id}')] for instance_id, state in instance_details]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text('Select an EC2 instance to start:', reply_markup=reply_markup)
    logger.info('Start EC2 instance command executed by user: %s', update.message.from_user.username)

async def start_ec2_instance_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    instance_id = query.data.split('-', 1)[1]  # Extract the instance ID from the callback data

    session = authenticate_aws(AWS_REGION)

    start_ec2_instance(session, instance_id)

    await query.edit_message_text(text=f"EC2 instance {instance_id} has been started.")
    logger.info('EC2 instance started by user: %s', query.from_user.username)

# Command to stop an EC2 instance
async def stop_ec2_instance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = authenticate_aws(AWS_REGION)

    ec2_client = session.client('ec2')
    instances = ec2_client.describe_instances()

    # Extract running instance details
    instance_details = [
        (instance['InstanceId'], instance['State']['Name'])
        for reservation in instances['Reservations']
        for instance in reservation['Instances']
        if instance['State']['Name'] == 'running'
    ]

    if not instance_details:
        await update.message.reply_text("No running EC2 instances found.")
        return

    # Create inline keyboard with instance options for stopping
    keyboard = [[InlineKeyboardButton(f"{instance_id} - {state}", callback_data=f'stop-{instance_id}')] for instance_id, state in instance_details]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text('Select an EC2 instance to stop:', reply_markup=reply_markup)
    logger.info('Stop EC2 instance command executed by user: %s', update.message.from_user.username)

async def stop_ec2_instance_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    instance_id = query.data.split('-', 1)[1]  # Extract the instance ID from the callback data

    session = authenticate_aws(AWS_REGION)

    stop_ec2_instance(session, instance_id)

    await query.edit_message_text(text=f"EC2 instance {instance_id} has been stopped.")
    logger.info('EC2 instance stopped by user: %s', query.from_user.username)

# Command to connect to an EC2 instance
async def connect_ec2_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = authenticate_aws(AWS_REGION)

    ec2_client = session.client('ec2')
    instances = ec2_client.describe_instances()

    # Extract instance details including IP address
    instance_details = [
        (instance['InstanceId'], instance['PublicIpAddress'])  # Use PublicIpAddress instead of PrivateIpAddress
        for reservation in instances['Reservations']
        for instance in reservation['Instances']
        if 'PublicIpAddress' in instance
    ]

    if not instance_details:
        await update.message.reply_text("No EC2 instances found.")
        return

    global selected_instance_id
    selected_instance_id = ''

    # Create inline keyboard with instance options including IP address
    keyboard = [[InlineKeyboardButton(f"{instance_id} - {ip}", callback_data=f'c-{instance_id}')] for instance_id, ip in instance_details]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text('Select an EC2 instance to connect:', reply_markup=reply_markup)
    logger.info('Connect EC2 instance command executed by user: %s', update.message.from_user.username)

async def connect_ec2_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    global selected_instance_id
    selected_instance_id = query.data.split('-', 1)[1]  # Extract the instance ID from the callback data

    await query.edit_message_text(text=f"Selected EC2 instance {selected_instance_id}. Now you can send any Linux command to execute on the selected EC2 instance.")
    logger.info('EC2 instance selected by user: %s', query.from_user.username)

async def command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global selected_instance_id

    if not selected_instance_id:
        await update.message.reply_text("Please select an EC2 instance first.")
        return

    session = authenticate_aws(AWS_REGION)

    ec2_client = session.client('ec2')
    instance = ec2_client.describe_instances(InstanceIds=[selected_instance_id])
    instance_ip = instance['Reservations'][0]['Instances'][0]['PublicIpAddress']  # Use Public IP Address

    command = update.message.text.strip()
    output = connect_to_ec2(instance_ip, command)

    await update.message.reply_text(output)
    logger.info('Command executed on EC2 instance by user: %s', update.message.from_user.username)

# New command to list AWS regions and handle selection
async def list_resources_by_region_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Create inline keyboard with AWS region options
    keyboard = [[InlineKeyboardButton(region, callback_data=f'region-{code}')] for region, code in AWS_REGIONS.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text('Select an AWS region to list resources:', reply_markup=reply_markup)
    logger.info('List resources by region command executed by user: %s', update.message.from_user.username)

async def region_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    region_code = query.data.split('-', 1)[1]  # Extract the region code from the callback data

    session = authenticate_aws(region_code)

    resources = list_all_aws_resources(session)
    resources_message = "\n".join([f"{key}: {', '.join(value)}" for key, value in resources.items()])

    await query.edit_message_text(text=f"Resources in region {region_code}:\n{resources_message}")
    logger.info('Resources listed for region: %s by user: %s', region_code, query.from_user.username)

# Command to get billing data
async def billing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        billing_data = get_billing_data()
        billing_message = (
            f"Month-to-date cost: ${billing_data['Month-to-date cost']}\n"
            f"Last month's cost for the same period: ${billing_data['Last month\'s cost for the same period']}\n"
            f"Total forecasted cost for the current month: ${billing_data['Total forecasted cost for the current month']}\n"
            f"Last month's total cost: ${billing_data['Last month\'s total cost']}"
        )

        await update.message.reply_text(billing_message)
        logger.info('Billing data command executed by user: %s', update.message.from_user.username)
    except Exception as e:
        await update.message.reply_text(f"Error retrieving billing data: {e}")
        logger.error('Billing data command failed: %s', e)

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list_resources", list_resources))
    application.add_handler(CommandHandler("deploy", deploy))
    application.add_handler(CommandHandler("list_pods", list_pods_command))
    application.add_handler(CommandHandler("list_all_resources", list_all_resources_command))
    application.add_handler(CommandHandler("create_ec2_instance", create_ec2_instance_command))
    application.add_handler(CommandHandler("destroy_ec2_instance", destroy_ec2_instance_command))
    application.add_handler(CommandHandler("start_ec2_instance", start_ec2_instance_command))
    application.add_handler(CommandHandler("stop_ec2_instance", stop_ec2_instance_command))
    application.add_handler(CommandHandler("connect_ec2", connect_ec2_command))
    application.add_handler(CommandHandler("list_resources_by_region", list_resources_by_region_command))
    application.add_handler(CommandHandler("billing", billing_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler))

    # Register callback handlers with specific patterns
    application.add_handler(CallbackQueryHandler(pod_logs_callback, pattern=r'^pod-'))
    application.add_handler(CallbackQueryHandler(destroy_ec2_instance_callback, pattern=r'^i-'))
    application.add_handler(CallbackQueryHandler(start_ec2_instance_callback, pattern=r'^s-'))
    application.add_handler(CallbackQueryHandler(stop_ec2_instance_callback, pattern=r'^stop-'))
    application.add_handler(CallbackQueryHandler(connect_ec2_callback, pattern=r'^c-'))
    application.add_handler(CallbackQueryHandler(region_callback, pattern=r'^region-'))

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()
