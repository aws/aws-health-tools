# phd-automation-ebs-vol-lost

Personal Health Dashboard, EBS Volume Lost recovery Automation

Instructions :

Deploy Kibana & ES
1. Deploy CloudFormation Stack reinvent_workshop_es_alb.yml
    * Place in CIDR that is allowed to access kibana
2. Wait until Complete ( Test Kibana Login ).

Deploy StepFunctions
3. Deploy CloudFormation Stack reinvent_workshop_stepfunctions.yml
    * Enter the StackName deployed on Step 1 ans name of SNStopic for notification.

Deploy CloudWatch Evensts
4. Deploy CloudFormation Stack reinvent_workshop_events.yml
    * Enter the StackName Deployed on Step 3

Deploy App 
5. Deploy CloudFormation Stack reinvent_workshop_app.yml

Invoke Mock Event.
6. Get the Vol id of Root.
7. Modify the time and vol is of mockpayload.json
8. Invoke aws put-events using AWS CLI with the payload.

Once its invoked Import Dashboard Settings on Kibana Console to get Visualisation.

