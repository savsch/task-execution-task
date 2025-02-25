from typing import Dict, Optional
import requests
from urllib.parse import urlparse

from task_executor import TaskExecutor
from task_executors.utils.exceptions import TaskValidationException
from task_executors.utils.miscutils import is_valid_url


class HttpExecutor(TaskExecutor):
    ALLOWED_METHODS = {'get', 'post', 'put', 'delete', 'head', 'options', 'patch'}
    ALLOWED_REQUEST_PARAMS = {
        'method',  # Required
        'url',  # Required
        'headers',  # Optional
        'cookies',  # Optional
        'params',  # Optional - URL query parameters
        'data',  # Optional - form data
        'json',  # Optional - JSON body
        'verify',  # Optional - SSL verification
        'timeout',  # Optional - request timeout
        'allow_redirects'  # Optional - follow redirects
    }

    @classmethod
    def validate(cls, request_args: Dict) -> None:
        if not isinstance(request_args, dict):
            raise TaskValidationException("args must be a dictionary")

        if 'method' not in request_args:
            raise TaskValidationException("'method' is required in args")
        if 'url' not in request_args:
            raise TaskValidationException("'url' is required in args")

        method = request_args['method'].lower()
        if method not in cls.ALLOWED_METHODS:
            raise TaskValidationException(
                f"Invalid HTTP method. Allowed methods: {', '.join(cls.ALLOWED_METHODS)}"
            )

        # No need for strict url validation as requests library will handle that for us

        # Validate other parameters
        for key in request_args:
            if key not in cls.ALLOWED_REQUEST_PARAMS:
                raise TaskValidationException(f"Unknown parameter: {key}")

        # Validate headers format
        if 'headers' in request_args:
            if not isinstance(request_args['headers'], dict):
                raise TaskValidationException("headers must be a dictionary")
            for k, v in request_args['headers'].items():
                if not isinstance(k, str) or not isinstance(v, str):
                    raise TaskValidationException(
                        "header keys and values must be strings"
                    )

        # Validate cookies format
        if 'cookies' in request_args:
            if not isinstance(request_args['cookies'], dict):
                raise TaskValidationException("cookies must be a dictionary")
            for k, v in request_args['cookies'].items():
                if not isinstance(k, str) or not isinstance(v, str):
                    raise TaskValidationException(
                        "cookie keys and values must be strings"
                    )

        if 'timeout' in request_args:
            try:
                timeout = float(request_args['timeout'])
                if timeout <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise TaskValidationException(
                    "timeout must be a positive number"
                )

        for bool_field in ['verify', 'allow_redirects']:
            if bool_field in request_args:
                if not isinstance(request_args[bool_field], bool):
                    raise TaskValidationException(
                        f"{bool_field} must be a boolean"
                    )

    def execute(self, timeout: Optional[float] = None) -> int:
        try:
            method = self.request_args['method'].lower()
            url = self.request_args['url']

            kwargs = {}
            for param in self.ALLOWED_REQUEST_PARAMS - {'method', 'url'}:
                if param in self.request_args:
                    kwargs[param] = self.request_args[param]

            if 'timeout' not in kwargs:
                kwargs['timeout'] = timeout if timeout else 30

            response = requests.request(method, url, **kwargs)

            self.output_handler.emit_normal_output(
                f"HTTP/{response.raw.version / 10} {response.status_code} {response.reason}\n".encode()
            )

            for name, value in response.headers.items():
                self.output_handler.emit_normal_output(
                    f"{name}: {value}\n".encode()
                )

            self.output_handler.emit_normal_output(b"\n")

            if response.content:
                self.output_handler.emit_normal_output(response.content)
                if not response.content.endswith(b"\n"):
                    self.output_handler.emit_normal_output(b"\n")

            return 0 if response.ok else 1

        except requests.RequestException as e:
            self.output_handler.emit_error_output(
                f"Request failed: {str(e)}\n".encode()
            )
            return 1
        except Exception as e:
            self.output_handler.emit_error_output(
                f"Unexpected error: {str(e)}\n".encode()
            )
            return 1

    def stop(self) -> None:
        # Nothing to do here as requests doesn't provide a way to cancel in-flight requests
        # The timeout parameter handles execution time limits
        pass