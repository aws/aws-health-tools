## Using the high availability endpoint python demo

To build and run this demo:

1. Download / clone the repo [AWS Health high availability endpoint demo](https://github.com/aws/aws-health-tools/high-availability-endpoint) from GitHub

2. Install python 3

See the [Python 3 Installation & Setup Guide](https://realpython.com/installing-python/) for steps on installing Python for Linux, macOS and Windows

3. Navigate to the python demo project directory in a command line window:

```
cd python
```

4. Create a virtual environment by running the following commands:

```
pip3 install virtualenv 
virtualenv -p python3 v-aws-health-env
```

NOTE: For Python 3.3 and newer you can use the built-in [venv module](https://docs.python.org/3/library/venv.html) to create a virtual environment, instead of installing virtualenv.

```
python3 -m venv v-aws-health-env
```

5. Activate the virtual environment by running the command:

```
source v-aws-health-env/bin/activate
```

6. Install dependencies by running the command:

```
pip install -r requirements.txt
```

7. Set the AWS credentials:

[Configure AWS credentials](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html). e.g. using profiles or environment variables

```
export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
export AWS_SESSION_TOKEN="your-aws-token"
```

8. Enter the following command to run the demo:

```
python3 main.py
```

The output will look something like:

```
INFO:botocore.credentials:Found credentials in environment variables.
INFO:root:Details: {'arn': 'arn:aws:health:global::event/SECURITY/AWS_SECURITY_NOTIFICATION/AWS_SECURITY_NOTIFICATION_0e35e47e-2247-47c4-a9a5-876544042721', 'service': 'SECURITY', 'eventTypeCode': 'AWS_SECURITY_NOTIFICATION', 'eventTypeCategory': 'accountNotification', 'region': 'global', 'startTime': datetime.datetime(2020, 8, 19, 23, 30, 42, 476000, tzinfo=tzlocal()), 'lastUpdatedTime': datetime.datetime(2020, 8, 20, 20, 44, 9, 547000, tzinfo=tzlocal()), 'statusCode': 'open', 'eventScopeCode': 'PUBLIC'}, description: {'latestDescription': 'This is the second notice regarding TLS requirements on FIPS endpoints.\n\nWe are in the process of updating all AWS Federal Information Processing Standard (FIPS) endpoints across all AWS regions to Transport Layer Security (TLS) version 1.2 by March 31, 2021 . In order to avoid an interruption in service, we encourage you to act now, by ensuring that you connect to AWS FIPS endpoints at a TLS version of 1.2. If your client applications fail to support TLS 1.2 it will result in connection failures when TLS versions below 1.2 are no longer supported.\n\nBetween now and March 31, 2021 AWS will remove TLS 1.0 and TLS 1.1 support from each FIPS endpoint where no connections below TLS 1.2 are detected over a 30-day period. After March 31, 2021 we may deploy this change to all AWS FIPS endpoints, even if there continue to be customer connections detected at TLS versions below 1.2. \n\nWe will provide additional updates and reminders on the AWS Security Blog, with a ‘TLS’ tag [1]. If you need further guidance or assistance, please contact AWS Support [2] or your Technical Account Manager (TAM). Additional information is below.\n\nHow can I identify clients that are connecting with TLS 1.0/1.1?\nFor customers using S3 [3], Cloudfront [4] or Application Load Balancer [5] you can use your access logs to view the TLS connection information for these services, and identify client connections that are not at TLS 1.2. If you are using the AWS Developer Tools on your clients, you can find information on how to properly configure your client’s TLS versions by visiting Tools to Build on AWS [7] or our associated AWS Security Blog has a link for each unique code language [7].\n\nWhat is Transport Layer Security (TLS)?\nTransport Layer Security (TLS Protocols) are cryptographic protocols designed to provide secure communication across a computer network [6].\n\nWhat are AWS FIPS endpoints? \nAll AWS services offer Transport Layer Security (TLS) 1.2 encrypted endpoints that can be used for all API calls. Some AWS services also offer FIPS 140-2 endpoints [9] for customers that require use of FIPS validated cryptographic libraries. \n\n[1] https://aws.amazon.com/blogs/security/tag/tls/\n[2] https://aws.amazon.com/support\n[3] https://docs.aws.amazon.com/AmazonS3/latest/dev/LogFormat.html\n[4] https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/AccessLogs.html\n[5] https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-access-logs.html\n[6] https://aws.amazon.com/tools\n[7] https://aws.amazon.com/blogs/security/tls-1-2-to-become-the-minimum-for-all-aws-fips-endpoints\n[8] https://en.wikipedia.org/wiki/Transport_Layer_Security\n[9] https://aws.amazon.com/compliance/fips'}
```

9. Deactive the virtual environment

Lastly, when you have finished with everything you can deactivate the environment by running the following command:

```
deactivate
```

## References

* [Boto3 Python SDK AWS Health doco](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/health.html#Health.Client)
* The library used in this demo for DNS lookups - dnspython [doco](https://dnspython.readthedocs.io/en/stable/) and [source code](https://github.com/rthalley/dnspython/)

## License

AWS Health Tools are licensed under the Apache 2.0 License
