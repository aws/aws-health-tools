## AWS Health SHD Notifier

### Description

This tool can be used to send Service Health Dashboard (SHD) postings to Chime, Slack or an SNS topic. A notification for each update to the SHD event will be sent, as well as an optional "no update" message for ongoing events. It uses a polling approach as SHD postings do not trigger Health Events at this time. Step Functions are used to track each event and send notification updates while the issue is not resolved, including optional "no update since last message" notifications. 

### Setup and Usage

#### Pre-launch requirements - Determining your delivery endpoints
- If using SNS, create and configure the SNS topic(s) before deploying the CloudFormation stack.
- If using Chime or Slack, follow the documentation for creating and determining the endpoint string(s). 

#### Deploying the CloudFormation Stack
Choose **Launch Stack** to launch the template in the US East (N. Virginia) Region in your account:

[![Launch AWS Health SMS Notifier](../images/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=ShdNotifier&templateURL=https://s3.amazonaws.com/aws-health-tools-assets/cloudformation-templates/shd-notifier.yml)

The CloudFormation template requires the following parameters:

- **AppName** - The base name for the underlying lambda functions 

- **ChatClient** - Which Client should be used for notifications. Only one client is supported per deployment. Options are:
  - chime
  - slack
  - sns

- **EndpointArray** - An array of one or more endpoint strings for the client notifications. Examples for each client:
  - chime: ["https://hooks.chime.aws/incomingwebhooks/XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXXX?token=XXXXXXXXXXXXXXXXXXXX"]
  - slack: ["https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"]
  - sns: ["arn:aws:sns:us-east-1:XXXXXXXXXXXX:SNS_Topic_Name"]

- **Bail** - Disable sending of messages when there is no update. Allowed values:
  - 0 (Send "no update" messages every 15 minutes)
  - 1 (Send messages only when a new update has been made)

- **LambdaRate** - The frequency to check for new SHD postings or updates. Allowed values:
  - rate(1 minute)
  - rate(5 minutes)
  - rate(10 minutes)

- **MessagePrefix** - A prefix for each update message. Examples include: 
  - [SHD AUTO]
  - This is an automated notification from the AWS Service Health Dashboard. Current status can always be found at http://status.aws.amazon.com

- **RegionFilter** - An optional array of region strings to limit notifications of SHD postings to only regions of interest . Examples include:
  - ["us-west-2","us-east-1","global"]
  - ["global"]

- **DEBUG** - Control debug log level and messages. Allowed values:
  - 0 (Disable Debugging)
  - 1 (Enable debugging)

- **WaitSeconds** - Control State Machine wait period of state transition. Allowed values:
  - 60 (1 minutes - Allows Standard State machine to run for 2.5 days)
  - 300 (5 minutes - Allows Standard State machine to run for 12.5 days)
  - 600 (10 minutes - Allows Standard State machine to run for 25 days)

#### Post-CloudFormation Installation Step
Due to the CloudFormation limit on inline Lambda functions, after the CloudFormation stack has completed successfully, the **deploy.sh** script will need to be run to update the code for the Lambda functions. <br />
Syntax: **deploy.sh** _\<CF_APPNAME\>_ _\<REGION\>_ <br/>
  - *CF_APPNAME* = The *AppName* defined when deploying the CloudFormation template
  - *REGION* = The region of the deployed CloudFormation template 
 
### License
AWS Health Tools are licensed under the Apache 2.0 License.
