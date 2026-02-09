"""Exception classes compatible with ansible-runner."""


class AnsibleRunnerException(Exception):
    """Base exception for ftl2-runner errors."""

    pass


class ConfigurationError(AnsibleRunnerException):
    """Raised when there is a configuration error."""

    pass


class CallbackError(AnsibleRunnerException):
    """Raised when a callback function raises an exception."""

    pass
