"""
Custom exceptions for IMGWTools.

These exceptions provide clear error handling for library users.
"""


class IMGWError(Exception):
    """Base exception for all IMGWTools errors."""

    pass


class IMGWConnectionError(IMGWError):
    """
    Raised when connection to IMGW servers fails.

    This can happen due to:
    - Network connectivity issues
    - IMGW server downtime
    - Request timeout
    - HTTP errors (4xx, 5xx)
    """

    pass


class IMGWDataError(IMGWError):
    """
    Raised when data parsing or processing fails.

    This can happen due to:
    - Unexpected data format from IMGW
    - Corrupted ZIP files
    - Invalid CSV structure
    - Missing required fields
    """

    pass


class IMGWValidationError(IMGWError):
    """
    Raised when input validation fails.

    This can happen due to:
    - Coordinates outside Poland bounds
    - Invalid parameter values
    - Unsupported data types or intervals
    """

    pass
