## AWS Direct Connect Maintenance Notifier

### Description
This tool can be used to send Direct Connect maintenance notifications to SNS topic when a Direct Connect maintenance is scheduled by using AWS Lambda and AWS CloudWatch Events. SNS topic subscribers (for example, web servers, email addresses, Amazon SQS queues, or AWS Lambda functions) can consume or receive the message or notification over one of the supported protocols (Amazon SQS, HTTP/S, email, SMS, Lambda) when they are subscribed to the topic. More information about SNS is available here: http://docs.aws.amazon.com/sns/latest/dg/welcome.html

### Setup and Usage

#### Setup using CloudFormation 

Choose **Launch Stack** to launch the AWS Direct Connect Maintenance Notifier template in the US West (Oregon) Region in your account. Please note that you need to launch this stack in just one region, you'll still be notified of the Direct Connects in other regions:
 
<a href="https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=DXMaintNotify&templateURL=https://s3.amazonaws.com/aws-health-tools-assets/cloudformation-templates/DX_Notifier.json" title="Launch Stack"><img src="../images/cloudformation-launch-stack.png" alt="Launch Stack" /></a>

Please update the region and the stack name according to your requirements.

Here is a sample of the notification you receive when there is a maintenance schduled on your Direct Connect resource:

---------------------
Planned maintenance has been scheduled on an AWS Direct Connect router in Seattle, WA. During this maintenance window, your AWS Direct Connect services associated with this event may become unavailable.

This maintenance is scheduled to avoid disrupting redundant connections at the same time.

If you encounter any problems with your connection after the end of this maintenance window, please contact us at https://aws.amazon.com/support. For more details, please see https://phd.aws.amazon.com/phd/home?region=us-west-2#/dashboard/open-issues

Region: us-west-2
<br>Account Id: xxxxxxxxxxxx

Affected Resources:
<br>dxcon-xxxxxxxx
<br>dxvif-xxxxxxxx

Start Time: Thu, 6 Jul 2017 08:30:00 GMT 
<br>End Time: Thu, 6 Jul 2017 12:30:00 GMT

-------------------

#### Manual setup

1. Create an IAM role for the Lambda function to use. Attach the [IAM policy](IAMPolicy) to the role in the IAM console.
Documentation on how to create an IAM policy is available here: http://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_create.html
Documentation on how to create an IAM role for Lambda is available here: http://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-service.html#roles-creatingrole-service-console

2. Create a Lambda JavaScript function by using the [sample](LambdaFunction.js) provided and choose the IAM role created in step 1. Update the configuration section of the script with the SNS topic ARN.
More information about Lambda is available here: http://docs.aws.amazon.com/lambda/latest/dg/getting-started.html

3. Create a CloudWatch Events rule to trigger the Lambda function created in step 2 for AWS Health events.
Documentation on how to create AWS Health CloudWatch Events rules is available here: http://docs.aws.amazon.com/health/latest/ug/cloudwatch-events-health.html

More information about AWS Health is available here: http://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html

Note that this is a just an example of how to set up automation with AWS Health, Amazon CloudWatch Events, and AWS Lambda. We recommend testing the example and tailoring it to your environment before using it in your production environment.

### License
AWS Health Tools are licensed under the Apache 2.0 License.


