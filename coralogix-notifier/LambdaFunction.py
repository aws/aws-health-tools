import os
import time
import logging
import json
import urllib.error
from urllib.request import Request, urlopen

CORALOGIX_LOG_URL = os.getenv('CORALOGIX_LOG_URL')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')
APP_NAME = os.getenv('APP_NAME')
SUB_SYSTEM = os.getenv('SUB_SYSTEM')

WARN = 4
TIMEOUT = os.getenv('CORALOGIX_TIMEOUT_HTTP', 30)
RETRIES = os.getenv('CORALOGIX_RETRIES_HTTP', 2)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    message = {
        "privateKey": str(PRIVATE_KEY),
        "applicationName": str(APP_NAME),
        "subsystemName": str(SUB_SYSTEM),
        "logEntries": [{"timestamp": (time.time() * 1000), "severity": WARN, "text": event}]
    }
    jsondata = json.dumps(message).encode('utf-8')
    for attempt in range(int(RETRIES)):
        try:
            req = Request(CORALOGIX_LOG_URL)
            req.add_header('Content-Type', 'application/json; charset=utf-8')
            req.add_header('Content-Length', len(jsondata))
            response = urlopen(req, data=jsondata,timeout=TIMEOUT)
            if response.getcode() == 200:
                logger.info("Health log published to Coralogix successfully 200 OK")
                return True
            else:
                logger.error("health log publish failed, status code %d, %b", response.getcode(), response.read)
        except urllib.error.URLError as e:
            logger.error("URL Error %s", e)
        except urllib.error.HTTPError as e:
            logger.error("HTTP Error %s", e)
        logger.info("attempt number %d", attempt + 1)
        time.sleep(5)
