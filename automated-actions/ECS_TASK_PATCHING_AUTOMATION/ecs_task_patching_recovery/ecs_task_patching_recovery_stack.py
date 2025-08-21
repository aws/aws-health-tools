from aws_cdk import (
    Stack,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as lambda_,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    Duration,
    RemovalPolicy,
    aws_iam as iam,
)
from constructs import Construct

class EcsTaskPatchingRecoveryStack(Stack):

    def create_state_machine_role(self) -> iam.Role:
        role = iam.Role(
            self, "StateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
        )
        return role
    
    def create_lambda_role(self) -> iam.Role:
        # Define the inline policy
        policy_document = iam.PolicyDocument(statements=[iam.PolicyStatement(
                actions=["esc:UpdateService"],
                resources=["*"]
            )])
                
        role = iam.Role(
            self, "ECSUpdateLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
            inline_policies={"ecsUpdatePolicy":policy_document}
        )
        return role

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define the lambda function to calculate the wait time
        calculate_wait_time_lambda = lambda_.Function(
            self, "CalculateWaitTimeLambda",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_inline("""
from datetime import datetime, timedelta

def handler(event, context):
    now = datetime.now()
    next_friday_in_future = (datetime(now.year, now.month, now.day) + 
                             timedelta(weeks=1)).replace(hour=0, minute=0, second=0)
    while next_friday_in_future <= now:
        next_friday_in_future += timedelta(weeks=1)
    
    wait_time = int((next_friday_in_future - now).total_seconds())
    return {"wait_time": wait_time, "Resources": event["Resources"]}
            """),
            handler="index.handler",
        )

        # Define the lambda function to update the ECS service
        update_ecs_service_lambda = lambda_.Function(
            self, "UpdateECSServiceLambda",
            runtime=lambda_.Runtime.PYTHON_3_9,
            role=self.create_lambda_role(),
            code=lambda_.Code.from_inline("""
import boto3

def handler(event, context):
    ecs = boto3.client('ecs')
    for i in range(len(event)):
        clusterandservicenames = event[i].split(" | ")
        service_name = clusterandservicenames[0]
        cluster_name = clusterandservicenames[1]
        result = ecs.update_service(cluster=cluster_name,service=service_name,forceNewDeployment=True)
                                          
    return {'status': 'success'}
            """),
            handler="index.handler",
        )

        # Define the step function
        calculate_wait_time_task = tasks.LambdaInvoke(
            self, "CalculateTimeUntilWeekend",
            lambda_function=calculate_wait_time_lambda,
            output_path="$.Payload",
        )
        ecs_update_service_task = tasks.LambdaInvoke(
            self, "UpdateECSService",
            lambda_function=update_ecs_service_lambda,
            payload=sfn.TaskInput.from_object({"resources": sfn.JsonPath.string_at("$.Resources")}),
        )


        state_machine = sfn.StateMachine(
            self, "MyStateMachine",
            definition=sfn.Chain.start(
                calculate_wait_time_task).next(sfn.Wait(
                    self, "WaitUntilWeekend",
                    time=sfn.WaitTime.seconds_path("$.wait_time"),
                )).next(ecs_update_service_task),
            timeout=Duration.hours(1000),
            role=self.create_state_machine_role(),
        )

        # Define the event bridge rule
        rule = events.Rule(
            self, "ECSTaskPatchingRetirementRule",
            event_pattern=events.EventPattern(
                source=["aws.health"],
                detail_type=["ECS Task retirement Health event"],
                detail={"eventTypeCode": ["AWS_ECS_TASK_PATCHING_RETIREMENT"]},
            ),
            targets=[targets.SfnStateMachine(state_machine)],
        )

        # Add the required permissions
        calculate_wait_time_lambda.grant_invoke(state_machine.role)
        update_ecs_service_lambda.grant_invoke(state_machine.role)
        
        # Attach the required policy to the State Machine role
        policy_statement = iam.PolicyStatement(
        	actions=["states:StartExecution"],
        	resources=[state_machine.state_machine_arn],
        	effect=iam.Effect.ALLOW
    		)

    		policy_document = iam.PolicyDocument(
        	statements=[policy_statement]
    		)

    		iam.Policy(
        	self, "StateMachinePolicy",
        	policy_name="StateMachinePolicy",
        	roles=[state_machine_role],
        	document=policy_document
    		)