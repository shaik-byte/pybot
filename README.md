AWS & Kubernetes Chatbot
This chatbot interacts with AWS and Kubernetes services, allowing users to manage cloud resources through a Telegram interface. It supports various AWS and Kubernetes operations like listing resources, deploying applications, and managing EC2 instances.

Features
Manage AWS EC2 instances: Create, destroy, start, stop, and connect to EC2 instances.
List AWS and Kubernetes resources: List all resources or region-specific resources.
Deploy Kubernetes applications: Deploy applications using Kubernetes YAML files.
Retrieve AWS billing information: Get a summary of your AWS billing.

**Available Endpoints**

1. /start
Description: Initiates the bot and sends a welcome message.
Usage: This is the first command to start interacting with the bot.
2. /list_resources
Description: Lists all AWS resources (EC2, S3, etc.) in the default region.
Usage: Run this command to retrieve a summary of the resources you currently have in AWS.
3. /deploy
Description: Deploys a Kubernetes application.
Usage: This command will prompt you for a deployment name and image name, then deploy the application using a Kubernetes YAML file.
4. /list_pods
Description: Lists all Kubernetes pods in the cluster.
Usage: Use this to retrieve a list of all running pods. You can then select a pod to get more information or view its logs.
5. /list_all_resources
Description: Lists all resources (both AWS and Kubernetes).
Usage: This command provides a combined list of all AWS and Kubernetes resources.
6. /create_ec2_instance
Description: Creates a new EC2 instance.
Usage: Use this command to create an EC2 instance by specifying instance type, key pair, etc.
7. /destroy_ec2_instance
Description: Destroys an existing EC2 instance.
Usage: This command will list your EC2 instances and allow you to select one to terminate.
8. /start_ec2_instance
Description: Starts an EC2 instance.
Usage: Lists all stopped instances and allows you to start one.
9. /stop_ec2_instance
Description: Stops a running EC2 instance.
Usage: Use this command to list running instances and stop one.
10. /connect_ec2
Description: Connects to an EC2 instance via SSH.
Usage: This command will connect you to an EC2 instance using its SSH credentials.
11. /list_resources_by_region
Description: Lists AWS resources by a specified region.
Usage: This command prompts you to choose a region, and then lists all AWS resources in that region.
12. /billing
Description: Retrieves AWS billing information.
Usage: Use this command to get a summary of your current AWS bill, including the breakdown by service.


![image](https://github.com/user-attachments/assets/92a016ba-506d-4b15-96ca-f3a9d17958b1)

![image](https://github.com/user-attachments/assets/e0ce0e54-fbba-4d02-9f58-aab0354c8e4f)

![image](https://github.com/user-attachments/assets/1258ff23-366e-4c0a-9427-45a6d39bf0e7)

![image](https://github.com/user-attachments/assets/719d8b35-856d-4512-9ee7-5eaa22be0d77)

![image](https://github.com/user-attachments/assets/795494fa-5c5e-44ed-ba80-0f809deab942)

![image](https://github.com/user-attachments/assets/13c141a7-8d02-47ab-87c1-976b7637c91c)

![image](https://github.com/user-attachments/assets/db9da69b-3b00-4c59-9e11-791f2ceac3ae)

![image](https://github.com/user-attachments/assets/41709e28-33df-4099-bedc-1ff2cd75a063)







