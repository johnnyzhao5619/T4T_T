class ServiceInterface:
    """Abstract base class for a manageable service."""

    def start(self):
        """Starts the service. This may be a blocking call."""
        raise NotImplementedError

    def stop(self):
        """Stops the service."""
        raise NotImplementedError
