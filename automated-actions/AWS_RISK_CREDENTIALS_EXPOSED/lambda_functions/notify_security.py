import os
import boto3

TOPIC_ARN = os.environ['TOPIC_ARN']  # ARN for SNS topic to post message to

TEMPLATE = '''At {} the IAM access key {} for user {} on account {} was deleted after it was found to have been publicly exposed on the internet.
Below are summaries of the most recent actions, resource names, and resource types associated with this user over the last 24 hours.

Actions:
{}

Resource Names:
{}

Resource Types:
{}

These are summaries of only the most recent API calls made by this user. Please ensure your account remains secure by further reviewing the API calls made by this user in CloudTrail.'''

sns = boto3.client('sns')


def lambda_handler(event, context):
    account_id = event['account_id']
    username = event['username']
    deleted_key = event['deleted_key']
    time_discovered = event['time_discovered']
    event_names = event['event_names']
    resource_names = event['resource_names']
    resource_types = event['resource_types']
    subject = 'Security Alert: Exposed IAM Key For User {} On Account {}'.format(username, account_id)
    print("Generating message body...")
    event_summary = generate_summary_str(event_names) 
    rname_summary = generate_summary_str(resource_names)
    rtype_summary = generate_summary_str(resource_types)
    message = TEMPLATE.format(time_discovered,
                              deleted_key,
                              username,
                              account_id,
                              event_summary,
                              rname_summary,
                              rtype_summary
                              )
    print("Publishing message...")
    publish_msg(subject, message)


def generate_summary_str(summary_items):
    """ Generates formatted string containing CloudTrail summary info.

    Args:
        summary_items (list): List of tuples containing CloudTrail summary info.

    Returns:
        (string)
        Formatted string containing CloudTrail summary info.

    """
    return '\t' + '\n\t'.join('{}: {}'.format(item[0], item[1]) for item in summary_items)


def publish_msg(subject, message):
    """ Publishes message to SNS topic

    Args:
        subject (string): Subject of message to be published to topic
        message (string): Content of message to be published to topic

    Returns:
        (None)

    """
    try:
        sns.publish(
            TopicArn=TOPIC_ARN,
            Message=message,
            Subject=subject,
            MessageStructure='string'
        )
    except Exception as e:
        print(e)
        print('Could not publish message to SNS topic "{}"'.format(TOPIC_ARN))
        raise e
