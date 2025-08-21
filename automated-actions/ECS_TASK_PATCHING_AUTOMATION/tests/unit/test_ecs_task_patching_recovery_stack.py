import aws_cdk as core
import aws_cdk.assertions as assertions

from ecs_task_patching_recovery.ecs_task_patching_recovery_stack import EcsTaskPatchingRecoveryStack

# example tests. To run these tests, uncomment this file along with the example
# resource in ecs_task_patching_recovery/ecs_task_patching_recovery_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = EcsTaskPatchingRecoveryStack(app, "ecs-task-patching-recovery")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
