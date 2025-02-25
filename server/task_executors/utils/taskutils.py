from typing import Dict, Type
from task_executors.echo_executor import EchoTaskExecutor
from task_executor import TaskExecutor
from task_executors.utils.exceptions import TaskValidationException

EXECUTOR_REGISTRY = {
    'echo': EchoTaskExecutor
}

def validate_params(params: Dict) -> None:
    """This will be called on the Stellar loop, so should be lightweight."""
    if not isinstance(params, dict):
        raise TaskValidationException("\"params\" must be an object (dictionary)")

    if 'type' not in params:
        raise TaskValidationException("Missing required 'type' parameter")

    task_type = params.get('type')
    executor_class = get_task_executor_from_params(params)

    if executor_class is None:
        raise TaskValidationException(f"Unknown task type: {task_type}")

    executor_class.validate(params.get("args"))


def get_task_executor_from_params(params: Dict) -> Type[TaskExecutor]:
    """
    Returns the appropriate TaskExecutor class based on the parameters.
    Raises TaskValidationException if no matching executor is found.
    """
    task_type = params.get('type')

    executor_class = EXECUTOR_REGISTRY.get(task_type)
    if executor_class is None:
        raise TaskValidationException(f"Unknown task type: {task_type}")

    return executor_class