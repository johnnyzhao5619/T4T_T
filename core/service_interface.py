class ServiceInterface:
    """Abstract base class for a manageable service."""

    def start(self):
        """Starts the service. This may be a blocking call."""
        raise NotImplementedError

    def stop(self):
        """Stops the service."""
        raise NotImplementedError

    def disconnect_signals(self):
        """Disconnects any signal bindings created by the service."""
        # Optional hook for services that attach to Qt signals.
        # Implementations can override this to release resources when the
        # service is stopped or replaced.
        return
