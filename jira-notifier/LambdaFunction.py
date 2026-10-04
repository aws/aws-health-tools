'''
AWS Health Jira Notifier Lambda Function

This function listens for AWS Health events (e.g., EC2 scheduled maintenance, degraded hardware,
EBS volume issues) via Amazon EventBridge / CloudWatch Events and automatically creates Jira issues
for human attention and remediation.

Environment Variables:
  - JIRA_HOST: Jira instance domain (e.g., 'your-domain.atlassian.net')
  - JIRA_USER_EMAIL: User email address for API authentication
  - JIRA_API_TOKEN: API token generated from Jira (or password for Jira Server)
  - JIRA_PROJECT_KEY: Jira Project Key (e.g., 'OPS', 'IT', 'SEC')
  - JIRA_ISSUE_TYPE: Jira Issue Type (default: 'Task', or 'Incident')
  - EVENT_CATEGORY_FILTER: Optional comma-separated categories to process (e.g., 'scheduledChange,issue')
'''

import os
import json
import logging
import base64
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration from Environment Variables
JIRA_HOST = os.environ.get('JIRA_HOST', 'your-domain.atlassian.net').rstrip('/')
JIRA_USER_EMAIL = os.environ.get('JIRA_USER_EMAIL', 'user@example.com')
JIRA_API_TOKEN = os.environ.get('JIRA_API_TOKEN', '')
JIRA_PROJECT_KEY = os.environ.get('JIRA_PROJECT_KEY', 'OPS')
JIRA_ISSUE_TYPE = os.environ.get('JIRA_ISSUE_TYPE', 'Task')
EVENT_CATEGORY_FILTER = os.environ.get('EVENT_CATEGORY_FILTER', 'scheduledChange,issue')

def get_auth_header(email, token):
    credentials = f"{email}:{token}"
    encoded_creds = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    return f"Basic {encoded_creds}"

def parse_due_date(event_detail):
    """
    Extracts due date (YYYY-MM-DD) from event startTime or endTime if available.
    Used for scheduledChange maintenance deadlines (e.g., EC2 reboot by date X).
    """
    date_str = event_detail.get('endTime') or event_detail.get('startTime')
    if date_str:
        try:
            # Parse ISO 8601 format e.g. 2026-10-15T04:00:00Z
            dt = datetime.strptime(date_str.split('.')[0].rstrip('Z'), "%Y-%m-%dT%H:%M:%S")
            return dt.strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Could not parse due date from string '{date_str}': {e}")
    return None

def check_existing_issue(event_arn, auth_header):
    """
    Searches Jira for existing issues matching the unique AWS Health Event ARN to avoid duplicates.
    """
    # Sanitize ARN for JQL search
    short_arn = event_arn.split('/')[-1] if '/' in event_arn else event_arn
    jql = f'project = "{JIRA_PROJECT_KEY}" AND text ~ "{short_arn}"'
    search_url = f"https://{JIRA_HOST}/rest/api/2/search?jql={jql}"
    
    req = Request(
        search_url,
        headers={
            'Authorization': auth_header,
            'Content-Type': 'application/json',
            'User-Agent': 'AWS-Health-Jira-Notifier'
        }
    )
    try:
        with urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if res_data.get('total', 0) > 0:
                existing_key = res_data['issues'][0]['key']
                logger.info(f"Existing Jira issue found for event {short_arn}: {existing_key}")
                return existing_key
    except Exception as e:
        logger.warning(f"Error checking existing Jira issues: {e}")
    return None

def create_jira_issue(event, auth_header):
    detail = event.get('detail', {})
    event_arn = detail.get('eventArn', 'N/A')
    event_type_code = detail.get('eventTypeCode', 'AWS_HEALTH_EVENT')
    event_category = detail.get('eventTypeCategory', 'issue')
    service = detail.get('service', 'AWS')
    aws_account = event.get('account', 'N/A')
    region = event.get('region', 'N/A')
    
    # Check category filter
    if EVENT_CATEGORY_FILTER and EVENT_CATEGORY_FILTER != '*':
        allowed_categories = [c.strip() for c in EVENT_CATEGORY_FILTER.split(',')]
        if event_category not in allowed_categories:
            logger.info(f"Skipping event category '{event_category}' as it is not in allowed filter: {allowed_categories}")
            return None

    # Check for duplicate
    existing_issue = check_existing_issue(event_arn, auth_header)
    if existing_issue:
        logger.info(f"Issue {existing_issue} already exists for this event. Skipping creation.")
        return existing_issue

    # Extract description
    descriptions = detail.get('eventDescription', [])
    latest_description = descriptions[0].get('latestDescription', 'No description provided.') if descriptions else 'No description provided.'

    # Extract affected entities (e.g., EC2 Instance IDs, EBS Volume IDs)
    affected_entities = detail.get('affectedEntities', [])
    entity_values = [entity.get('entityValue') for entity in affected_entities if entity.get('entityValue')]
    entities_str = ", ".join(entity_values) if entity_values else "N/A"

    # Format Summary
    summary = f"[AWS Health] [{service}] {event_type_code}"
    if entity_values:
        summary += f" - {entity_values[0]}" if len(entity_values) == 1 else f" ({len(entity_values)} resources affected)"

    # Format Description Body
    phd_url = f"https://phd.aws.amazon.com/phd/home?region={region}#/event-log?eventID={event_arn}"
    start_time = detail.get('startTime', 'N/A')
    end_time = detail.get('endTime', 'N/A')

    jira_description = (
        f"h2. AWS Health Event Notification\n\n"
        f"*Service:* {service}\n"
        f"*Event Type:* {event_type_code}\n"
        f"*Category:* {event_category}\n"
        f"*AWS Account:* {aws_account}\n"
        f"*Region:* {region}\n"
        f"*Start Time:* {start_time}\n"
        f"*End Time / Deadline:* {end_time}\n"
        f"*Affected Resources:* {entities_str}\n\n"
        f"h3. Event Details\n"
        f"{latest_description}\n\n"
        f"h3. Actions\n"
        f"View in AWS Personal Health Dashboard: [{phd_url}]\n\n"
        f"_Event ARN: {event_arn}_"
    )

    # Build Issue Payload
    issue_fields = {
        "project": {
            "key": JIRA_PROJECT_KEY
        },
        "summary": summary,
        "description": jira_description,
        "issuetype": {
            "name": JIRA_ISSUE_TYPE
        },
        "labels": [
            "aws-health",
            service.lower(),
            event_category.lower()
        ]
    }

    # Add Due Date if available (useful for scheduledChange maintenance deadlines)
    due_date = parse_due_date(detail)
    if due_date:
        issue_fields["duedate"] = due_date
        logger.info(f"Setting Jira issue due date: {due_date}")

    # Set Priority if event is issue or scheduledChange
    if event_category == 'issue':
        issue_fields["priority"] = {"name": "High"}
    elif event_category == 'scheduledChange':
        issue_fields["priority"] = {"name": "Medium"}

    payload = json.dumps({"fields": issue_fields})
    create_url = f"https://{JIRA_HOST}/rest/api/2/issue"

    req = Request(
        create_url,
        data=payload.encode('utf-8'),
        headers={
            'Authorization': auth_header,
            'Content-Type': 'application/json',
            'User-Agent': 'AWS-Health-Jira-Notifier'
        }
    )

    try:
        with urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            issue_key = result.get('key')
            logger.info(f"Successfully created Jira issue {issue_key} for event ARN: {event_arn}")
            return issue_key
    except HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"Failed to create Jira issue. HTTP {e.code}: {e.reason}. Response: {error_body}")
        raise
    except URLError as e:
        logger.error(f"Failed to connect to Jira host '{JIRA_HOST}': {e.reason}")
        raise

def handler(event, context):
    logger.info("Received event: " + json.dumps(event))
    
    if not JIRA_API_TOKEN or JIRA_API_TOKEN == 'YOUR_JIRA_API_TOKEN':
        logger.error("JIRA_API_TOKEN environment variable is not configured.")
        return {"statusCode": 400, "body": "JIRA_API_TOKEN not configured"}

    auth_header = get_auth_header(JIRA_USER_EMAIL, JIRA_API_TOKEN)
    
    try:
        issue_key = create_jira_issue(event, auth_header)
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Processed successfully", "jiraIssueKey": issue_key})
        }
    except Exception as e:
        logger.error(f"Error processing AWS Health event for Jira: {str(e)}")
        raise e
