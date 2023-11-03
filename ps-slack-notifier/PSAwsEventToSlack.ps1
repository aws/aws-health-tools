# PowerShell script file to be executed as a AWS Lambda function.
#
# When executing in Lambda the following variables will be predefined.
#   $LambdaInput - A PSObject that contains the Lambda function input data.
#   $LambdaContext - An Amazon.Lambda.Core.ILambdaContext object that contains information about the currently running Lambda environment.
#
# The last item in the PowerShell pipeline will be returned as the result of the Lambda function.
#
# To include PowerShell modules with your Lambda function, like the AWSPowerShell.NetCore module, add a "#Requires" statement
# indicating the module and version.

#Requires -Modules @{ModuleName='AWSPowerShell.NetCore';ModuleVersion='3.3.335.0'}

$jsonInput = (ConvertTo-Json -InputObject $LambdaInput -Compress -Depth 5)
$title =  "AWS Health Event : "+($LambdaInput.detail.eventTypeCategory)+" : "+($LambdaInput.detail.service)
$message = $LambdaInput.detail.eventDescription.latestDescription
$message += "<https://phd.aws.amazon.com/phd/home?region=us-east-1#/event-log?eventID=" + $($LambdaInput.detail.eventArn) + "|Click here> for details."
$payload = @{
        "attachments" = @(@{
                "color" = "danger"
                "title" = $title
                "text"  = $message
            })
        "icon_emoji"  = ":rain_cloud:"
    }
ConvertTo-Json -Compress -InputObject $payload
Invoke-WebRequest -UseBasicParsing `
    -Uri "https://hooks.slack.com/services/XXXX/XXXX/XXXX" `
    -Method "POST" `
    -Body (ConvertTo-Json -Compress -InputObject $payload)
Write-Output $jsonInput