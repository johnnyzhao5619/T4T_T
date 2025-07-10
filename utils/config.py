import os
import configparser


class ConfigManager:
    """A class responsible for managing application configuration settings."""
    
    def __init__(self, config_file='config/config.ini'):
        """
        Initialize the ConfigManager with a path to the configuration file.
        
        Args:
            config_file (str): Path to the configuration file. Defaults to 
                'config/config.ini'.
        """
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
        self.create_directories()
        # TODO: Implement configuration validation logic here in a future phase.

    def load_config(self):
        if os.path.exists(self.config_file):  # noqa
            self.config.read(self.config_file)
        else:
            raise FileNotFoundError(
                f"Configuration file {self.config_file} not found."
            )
    
    def create_directories(self):
        """Create necessary application directories if they do not exist."""
        directories = ['modules', 'tasks', 'logs', 'themes', 'i18n']
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
    
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
