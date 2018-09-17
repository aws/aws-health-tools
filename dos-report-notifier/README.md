## DOS Report SNS Topic Notifier

### Description
This tool can be used to send custom notifications to a SNS topic when an AWS DOS report is generated using AWS Health, AWS Lambda and Amazon CloudWatch Events. SNS topic subscribers (for example, web servers, email addresses, Amazon SQS queues, or AWS Lambda functions) can consume or receive the message or notification over one of the supported protocols (Amazon SQS, HTTP/S, email, SMS, Lambda) when they are subscribed to the topic. More information about SNS is available here: http://docs.aws.amazon.com/sns/latest/dg/welcome.html

### Setup and Usage

#### Setup using CloudFormation 

Choose **Launch Stack** to launch this template in the US East (N. Virginia) Region in your account:
 
<a href="https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=AWSHealthSNSTopicPublisher&templateURL=https://s3.amazonaws.com/aws-health-tools-assets/cloudformation-templates/dos-report-notifier.json" title="Launch Stack"><img src="../images/cloudformation-launch-stack.png" alt="Launch Stack" /></a>

Please update the region and the SNS topic name according to your requirements.

More information about AWS Health is available here: http://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html

Note that this is a just an example of how to set up automation with AWS Health, Amazon CloudWatch Events, and AWS Lambda. We recommend testing the example and tailoring it to your environment before using it in your production environment.

### License
AWS Health Tools are licensed under the Apache 2.0 License.

