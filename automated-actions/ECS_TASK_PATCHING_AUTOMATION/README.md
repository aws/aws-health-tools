# ECS Task Patching Automation

This solution demonstrates how to use AWS Step Functions to orchestrate a serverless workflow that proactively schedules Amazon Elastic Container Service (ECS) task patching during weekends, providing organizations with critical business-hour workloads greater control over when their infrastructure gets upgraded.

## Overview

AWS regularly deploys software updates to ECS that include CVE patches and other critical fixes. Organizations often prefer to have greater control over exactly when these updates are applied, particularly for their mission-critical services. This is especially important for public sector organizations and their private sector partners who provide critical infrastructure and services to government agencies. These partnerships require strict change management processes and controlled maintenance windows to ensure continuous service delivery and maintain compliance with government security and operational standards.

This solution leverages AWS Health events to detect when AWS plans to patch your ECS tasks, then automatically schedules proactive updates to occur during the weekend before AWS's scheduled upgrade time. This gives you control over the timing of updates for your business-critical operations.

## How It Works

1. **Event Detection**: AWS Health generates an `AWS_ECS_TASK_PATCHING_RETIREMENT` event when ECS tasks need patching.
2. **Automated Response**: A CloudWatch Events rule captures this event and triggers the Step Functions state machine.
3. **Weekend Scheduling**: The state machine:
   - Calculates the time until the next weekend (Friday)
   - Waits until that calculated time
   - Automatically forces a new deployment on the affected ECS services
4. **Proactive Control**: Your tasks are updated during weekend hours before AWS's scheduled upgrade time, giving you control over when the updates occur.

## Benefits

- **Business Continuity**: Protect critical workloads from updates during business hours
- **Proactive Control**: Schedule updates on your terms, before AWS's planned upgrade time
- **Automated Management**: No manual intervention required to manage updates
- **Security Compliance**: Ensures security patches are applied promptly, but at a more convenient time
- **AWS Integration**: Seamlessly works with AWS Health and ECS managed services

## Deployment

### Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.9 or later
- AWS CDK v2 installed

### Option 1: Quick Deployment

```bash
# Clone the repository
git clone <repository-url>
cd ECS-TASK-PATCHING-AUTOMATION

# Install dependencies
pip install -r requirements.txt

# Deploy the stack
cdk deploy
```

### Option 2: Manual Deployment

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ECS-TASK-PATCHING-AUTOMATION
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate.bat
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Review and customize the deployment settings in `app.py` if needed.

5. Deploy the stack:
   ```bash
   cdk deploy
   ```

## Testing

To test the solution without waiting for an actual AWS Health event:

1. Use the provided sample event in `sampleevent.json`
2. Trigger the state machine manually through the AWS Step Functions console
3. Observe the execution flow and verify that the wait calculation works correctly

## Customization

You can modify the following aspects of the solution:

- **Target Day**: Change the day of the week when updates are applied (currently set to Friday)
- **Event Pattern**: Adjust the CloudWatch Events rule to capture different event types
- **Service Actions**: Customize the actions performed on your ECS services

## Resources Created

This solution creates the following AWS resources:

- AWS Step Functions state machine
- Lambda functions for time calculation and ECS service updates
- CloudWatch Events rule for AWS Health event detection
- IAM roles and policies with least-privilege permissions

## Cleanup

To remove all resources created by this solution:

```bash
cdk destroy
```

## License

This solution is licensed under the Apache 2.0 License.
