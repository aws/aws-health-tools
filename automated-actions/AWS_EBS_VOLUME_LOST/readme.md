## AWS Health AWS_EBS_VOLUME_LOST

### Description
Underlying hardware related to your EBS volume has failed, and the data associated with the volume is unrecoverable.
If you have an EBS snapshot of the volume, you need to restore that volume from your snapshot. 
This tools checks if the failed volume has a snapshot and is part of a root volume on an EC2 instance.
Tool will restore the instance root volume from latest snapshot automatically if it does.
Notification on update will be sent to SNS topic assigned.

[![Launch Stack into N. Virginia with CloudFormation](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/images/cloudformation-launch-stack-button.png)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=AWSEBSVolLost&templateURL=https://s3.amazonaws.com/aws-health-tools-assets/cloudformation-templates/aws_ebs_vol_lost_cloudformation.yaml)

### Setup
1. Launch a cloudformation stack from template in region where you would like to monitor the volume : aws_ebs_vol_lost_cloudformation.yaml.
2. Place in SNS topic to send update to SNSTopic parameter.


#### CloudFormation
Choose **Launch Stack** to launch the CloudFormation template in the US East (N. Virginia) Region in your account:

The CloudFormation template requires the following parameters:

*SNS topic* - Enter the SNS topic to send notification to.

### License
AWS Health Tools are licensed under the Apache 2.0 License.
