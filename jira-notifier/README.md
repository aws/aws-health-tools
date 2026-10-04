## AWS Health Jira Notifier

### Description

This tool automatically creates Jira tickets when AWS Health events (such as EC2 degraded hardware notifications, scheduled instance reboots, RDS maintenance, or EBS volume degradation) are published. It uses **AWS Lambda** and **Amazon EventBridge / CloudWatch Events** to deliver notifications directly to your Jira project with assigned due dates matching AWS maintenance deadlines.

---

### Key Features
* **Automated Ticket Creation**: Converts AWS Health event details into structured Jira issues (Tasks or Incidents).
* **Maintenance Deadlines (`duedate`)**: Automatically extracts maintenance deadlines (`endTime`/`startTime`) from `scheduledChange` events and maps them to Jira's `duedate` field.
* **Resource Identification**: Lists affected EC2 Instance IDs, EBS Volume IDs, or ARNs directly in the ticket summary and body.
* **Deduplication**: Checks Jira via JQL prior to issue creation to prevent duplicate tickets for the same AWS event ARN.
* **Configurable Category Filtering**: Filter events by category (`scheduledChange`, `issue`, `accountNotification`, or all).

---

### Prerequisites & Jira Setup

1. **Jira API Token**:
   - Log into [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
   - Click **Create API token**, label it (e.g. `aws-health-notifier`), and copy the generated token.

2. **Jira User & Project**:
   - Ensure your Jira user email has permission to create issues in your target Jira project (e.g., `OPS` project key).

---

### Deployment Options

#### Option A: AWS Setup via CloudFormation

Deploy using CloudFormation with the template in `cfn-templates/jira-notifier.yml` (or `.json`).

The template requires the following parameters:

* `JiraHost`: Your Jira domain (e.g., `mycompany.atlassian.net`).
* `JiraUserEmail`: The email address for Jira API authentication.
* `JiraApiToken`: Your generated Jira API token.
* `JiraProjectKey`: Jira project key (e.g., `OPS`).
* `JiraIssueType`: Jira issue type (default: `Task`).
* `EventCategoryFilter`: Filter categories (default: `scheduledChange,issue`).

---

#### Option B: AWS Manual Setup

1. **IAM Policy**:
   - Create an IAM role for Lambda and attach the policy in [IAMPolicy](IAMPolicy).

2. **Lambda Function**:
   - Create a Python 3.11 Lambda function using [LambdaFunction.py](LambdaFunction.py).
   - Configure the following environment variables:
     * `JIRA_HOST` = `mycompany.atlassian.net`
     * `JIRA_USER_EMAIL` = `devops@mycompany.com`
     * `JIRA_API_TOKEN` = `<your-api-token>`
     * `JIRA_PROJECT_KEY` = `OPS`
     * `JIRA_ISSUE_TYPE` = `Task`
     * `EVENT_CATEGORY_FILTER` = `scheduledChange,issue`

3. **EventBridge Rule**:
   - Create an EventBridge rule for `source: ["aws.health"]` and set the target to the Lambda function created in step 2.

---

### License
AWS Health Tools are licensed under the Apache 2.0 License.
