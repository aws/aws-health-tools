#!/bin/bash
# Updates the Lambda functions that are too big to be inlined in the CloudFormation Template

set -e
APPNAME=$1
REGION=$2
if [ $# -lt 2 ]; then
  echo 1>&2 "$0: not enough arguments."
  echo 1>&2 "Usage: $0 <CF_APPNAME> <REGION>"
  echo 1>&2 "  CF_APPNAME: The name of the deployed CloudFormation template to update"
  echo 1>&2 "  REGION: The region of the deployed CloudFormation template"
  exit 2
fi

AWS_VERSION=$(aws --version)
AWS_COMMAND_FLAGS=""

# check if aws version is 2.x
# we need to stop the command from waiting for user input
if [[ $AWS_VERSION == *"aws-cli/2"* ]]; then
  AWS_COMMAND_FLAGS="--no-cli-pager"
fi

createOrUpdate () {
    FUNC_NAME=$1
    SOURCE=$2
    cp "$SOURCE" index.py
    zip "$FUNC_NAME.zip" index.py
    aws lambda update-function-code --function-name "$FUNC_NAME" --zip-file "fileb://$FUNC_NAME.zip" --region "$REGION" $AWS_COMMAND_FLAGS
    rm "$FUNC_NAME.zip"
    rm index.py
}
createOrUpdate "$APPNAME-Chat-Post" "Health-Event-Chat-Post-LambdaFn.py"
createOrUpdate "$APPNAME-Poller" "Health-Event-Poller-LambdaFn.py"
createOrUpdate "$APPNAME-Status" "Health-Event-Status-LambdaFn.py"
createOrUpdate "$APPNAME-Iterator" "Health-Event-Iterator-LambdaFn.py"
