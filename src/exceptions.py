class AppError(Exception):
    pass


class SSHConnectionError(AppError):
    pass


class EnvironmentError(AppError):
    pass


class CommandExecutionError(AppError):
    pass


class EnvironmentNotFoundError(EnvironmentError):
    pass


class EnvironmentCreationError(EnvironmentError):
    pass


class EnvironmentDeleteError(EnvironmentError):
    pass


class PackageOperationError(AppError):
    pass


class CondaNotFoundError(AppError):
    pass
