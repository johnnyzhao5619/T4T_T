import os
import configparser


class ConfigManager:
    """A class responsible for managing application configuration settings."""

    def __init__(self, config_dir='config'):
        """
        Initialize the ConfigManager.
        Args:
            config_dir (str): The absolute path to the configuration directory.
        """
        # Construct the absolute path to the config.ini file
        self.config_file = os.path.join(config_dir, 'config.ini')
        self.config = configparser.ConfigParser()
        self.load_config()
        # TODO: Implement configuration validation logic here in a future phase.

    def load_config(self):
        """
        Loads the configuration from the .ini file.
        If the file doesn't exist, it raises a FileNotFoundError.
        """
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            # This provides a clearer error message if the config is missing
            raise FileNotFoundError(
                f"Configuration file not found at: {self.config_file}")

    def get(self, section, key, fallback=None):
        """
        Retrieve a configuration value for a given section and key.
        
        Args:
            section (str): The section in the config file.
            key (str): The key in the section.
            fallback: Value to return if the section or key is not found. 
                Defaults to None.
        
        Returns:
            The value associated with the key in the specified section, or 
                the fallback value.
        """
        return self.config.get(section, key, fallback=fallback)

    def set(self, section, key, value):
        """
        Set a configuration value for a given section and key.
        
        Args:
            section (str): The section in the config file.
            key (str): The key in the section.
            value: The value to set for the key.
        """
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
        self.save_config()

    def save_config(self):
        """Save the current configuration to the config file."""
        with open(self.config_file, 'w') as configfile:
            self.config.write(configfile)
