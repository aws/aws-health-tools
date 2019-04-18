## AWS Health AWS_EBS_VOLUME_LOST

**Note:** This instruction is deprecated. Please refer to the [stepbystep/README](https://github.com/aws/aws-health-tools/blob/master/automated-actions/AWS_EBS_VOLUME_LOST/stepbystep/README.md) for the latest instruction.

---

### Description
Underlying hardware related to your EBS volume has failed, and the data associated with the volume is unrecoverable.
If you have an EBS snapshot of the volume, you need to restore that volume from your snapshot. 
This tools checks if the failed volume has a snapshot and is part of a root volume on an EC2 instance.
Tool will restore the instance root volume from latest snapshot automatically if it does, and upload the results to an Elasticsearch instance.
Notification on update will be sent to SNS topic assigned.

### Core Functionality Stack > [![Launch EBS VOLUME LOST Stack into N. Virginia with CloudFormation](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/images/cloudformation-launch-stack-button.png)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=AWSEBSVolLost&templateURL=https://s3.amazonaws.com/aws-health-tools-assets/cloudformation-templates/aws_ebs_vol_lost_cfn.yaml)

### Important App Stack > [![Launch IMPORTANT APP Stack into N. Virginia with CloudFormation](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/images/cloudformation-launch-stack-button.png)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=AWSEBSVolLost&templateURL=https://s3.amazonaws.com/aws-health-tools-assets/cloudformation-templates/aws_ebs_vol_lost_importantapp-cfn.yaml)

### Setup
1.  Launch the CloudFormation Core Functionality Stack (**aws_ebs_vol_lost_cfn.yaml**).
    * This template will build out the required Step and Lambda functions that will action a Personal Health Dashboard event.  It also creates a small Elasticsearch domain for visualisation.
1.  Launch the CloudFormation Important App stack (**aws_ebs_vol_lost_importantapp-cfn.yaml**).
    * This template will build out a mock application that will be impacted by an EBS service disruption.

##### Creating a Mock Event

1.  With both CloudFormation stacks completed - copy the **VolumeId** from the Outputs of the **Important App** stack.
1.  Replace all **vol-xxxxxxxxxxxxxxxxx** values in the **phd-mock-payload.json** with the copied value.
1.  Modifiy the **time** to within the past 14 days in **phd-mock-event.json**.
1.  Post the mock event to CloudWatch using the AWS CLI command **aws events put-events --entries file://phd-mock-event.json** - this will trigger a CloudWatch Rule that will in turn launch the Step Function to replace the volume.
1.  Open the Kibana dashboard (the URL can be found in the Outputs of the **Core Functionality** Stack)
1. In Kibana, under **Management > Index Patterns**, create an index pattern named **phd-events** using **PhdEventTime** as the **Time Filter**.
1. Under **Management > Saved Objects**, import **elasticsearch-objects.json**, overwriting all objects, and using **phd-events** as the new index pattern.
1. Navigate to **Dashboard > PHD Events** to see the event(s).
1. Repeat steps 1 to 4 to create additional mock events.

#### CloudFormation
Choose **Launch Stack** to launch the CloudFormation template in the US East (N. Virginia) Region in your account:

The **Core Functionality** CloudFormation template requires the following parameters:
* *SNSTopicName* - Enter the SNS topic to send notification to - this must exist in US East (N. Virginia) region
* *PublicCidr* - The public IP from which Kibana will be accessible
* *SubnetIds* - Two public subnets for Kibana access
* *VpcId* - The VPC to which the subnets belong

The **Important App** CloudFormation template requires the following parameters:
* *InstanceType* - The size of the EC2 Instance
* *KeyName* - The Keypair used to access the EC2 Instance
* *RestoreImageId* - Leave blank.  This is used by the Step Function for automatic replacement
* *SSHLocation* - The public IP from wich the EC2 Instance wil be accessible
* *SubnetId* - The subnet in which the EC2 Instance will reside
* *VpcId* - The VPC to which the subnet belongs

#### Disclaimer

These CloudFormation templates are for demo and proof-of-concept purposes only.  They and are not intended for production environments.  Amongst other deficiencies, they:
* do not follow the rule of least privileged access, and will create IAM Roles with the 'AdministratorAccess' AWS Managed policy
* will serve public traffic from the Elasticsearch domain over unencrypted HTTP connections

### License
AWS Health Tools are licensed under the Apache 2.0 License.
