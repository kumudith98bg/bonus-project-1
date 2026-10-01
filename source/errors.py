"""Errors that the command-line program can explain without a stack trace."""


class RAError(Exception):
    def __init__(self, category, message, position=None):
        super().__init__(message)
        self.category = category
        self.message = message
        self.position = position


def format_error(error):
    if isinstance(error, RAError):
        location = ""
        if error.position is not None:
            location = (f" at line {error.position['line']}, "
                        f"column {error.position['column']}")
        return f"{error.category} error{location}: {error.message}"
    return f"Error: {error}"
