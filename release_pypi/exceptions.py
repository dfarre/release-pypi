class SecretsNotFound(Exception):
    """Raised when necessary PyPI secrets are not found"""


class WrongGitStatus(Exception):
    """Raised when the git status is not appropriate to release"""
