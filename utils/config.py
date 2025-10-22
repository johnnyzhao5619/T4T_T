import configparser
import logging
import os
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)


def load_yaml(file_path: str) -> Dict[str, Any]:
    """
    Loads a YAML file and returns its content as a dictionary.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict):
            return data

        if data is None:
            logger.info(
                "YAML file '%s' is empty. Using default empty configuration.",
                file_path)
        else:
            logger.warning(
                "YAML file '%s' did not contain a mapping. "
                "Using default empty configuration.", file_path)
        return {}
    except FileNotFoundError:
        logger.error(f"YAML file not found at: {file_path}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file {file_path}: {e}")
        return {}


def save_yaml(file_path: str, data: Dict[str, Any]) -> None:
    """
    Saves a dictionary to a YAML file.
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        logger.error(f"Error saving YAML file {file_path}: {e}")


class ConfigManager:
    """
    A class responsible for managing application configuration settings from 
    a .ini file.

    This manager provides a robust way to access configuration, with built-in
    defaults, type conversion, and error handling.
    """

    def __init__(self, config_dir: str = 'config'):
        """
        Initialize the ConfigManager.

        Args:
            config_dir (str): The directory containing the configuration file.
        """
        self.config_file = os.path.join(config_dir, 'config.ini')
        self.config = configparser.ConfigParser()
        self._section_map: Dict[str, str] = {}
        self._message_bus_config: Dict[str, Any] | None = None
        self._mqtt_config: Dict[str, Any] | None = None
        self._kafka_config: Dict[str, Any] | None = None
        self.load_config()

    def load_config(self) -> None:
        """
        Loads the configuration from the .ini file.
        If the file doesn't exist, it proceeds with an empty configuration,
        allowing fallbacks to default values.
        """
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            logger.info(
                f"Configuration file not found at: {self.config_file}. "
                "Using default values.")
        self._refresh_section_map()

    def _refresh_section_map(self) -> None:
        """Build a mapping of normalized section names to their original form."""
        self._section_map = {
            self._canonical_section_key(section): section
            for section in self.config.sections()
        }

    @staticmethod
    def _canonical_section_key(section: str) -> str:
        """Normalize section names for case-insensitive lookups."""
        return ''.join(ch for ch in section.lower() if ch.isalnum())

    def _resolve_section(self, section: str) -> str:
        """Resolve a section name using the normalization map."""
        key = self._canonical_section_key(section)
        return self._section_map.get(key, section)

    @property
    def message_bus(self) -> Dict[str, Any]:
        """
        Get the [message_bus] configuration, parsed with defaults.

        Returns:
            A dictionary containing the message_bus configuration.
        """
        if self._message_bus_config is None:
            section = self._resolve_section('message_bus')
            self._message_bus_config = {
                'type':
                self.config.get(section, 'type', fallback='MQTT'),
                'active_service':
                self.config.get(section,
                                'active_service',
                                fallback='mqtt')
            }
        return self._message_bus_config

    @property
    def mqtt(self) -> Dict[str, Any]:
        """
        Get the [MQTT] configuration, parsed with defaults and type safety.

        Returns:
            A dictionary containing the MQTT connection parameters.
        """
        if self._mqtt_config is None:
            section = self._resolve_section('mqtt')
            self._mqtt_config = {
                'host':
                self.config.get(section, 'host', fallback='localhost'),
                'port':
                self._get_int('mqtt', 'port', 1883),
                'username':
                self.config.get(section, 'username', fallback=''),
                'password':
                self.config.get(section, 'password', fallback=''),
                'client_id':
                self.config.get(section, 'client_id', fallback=''),
                'reconnect_interval_max_seconds':
                self._get_int('mqtt', 'reconnect_interval_max_seconds', 60),
                'tls_enabled':
                self.config.getboolean(section,
                                       'tls_enabled',
                                       fallback=False)
            }
        return self._mqtt_config

    @property
    def kafka(self) -> Dict[str, Any]:
        """
        Get the [kafka] configuration, parsed with defaults.
        """
        if self._kafka_config is None:
            section = self._resolve_section('kafka')
            self._kafka_config = {
                'bootstrap_servers':
                self.config.get(section,
                                'bootstrap_servers',
                                fallback='localhost:9092'),
                'client_id':
                self.config.get(section,
                                'client_id',
                                fallback='t4t_client'),
                'sasl_plain_username':
                self.config.get(section,
                                'sasl_plain_username',
                                fallback=''),
                'sasl_plain_password':
                self.config.get(section,
                                'sasl_plain_password',
                                fallback=''),
                'security_protocol':
                self.config.get(section,
                                'security_protocol',
                                fallback='PLAINTEXT'),
                'sasl_mechanism':
                self.config.get(section,
                                'sasl_mechanism',
                                fallback=''),
            }
        return self._kafka_config

    def _get_int(self, section: str, key: str, fallback: int) -> int:
        """
        Safely retrieve an integer value from the configuration.

        If the section or key is missing, or if the value is not a valid
        integer, it logs a warning and returns the fallback value.

        Args:
            section (str): The section in the config file.
            key (str): The key in the section.
            fallback (int): The default value to return on failure.

        Returns:
            The integer value or the fallback.
        """
        resolved_section = self._resolve_section(section)
        try:
            return self.config.getint(resolved_section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback  # No need to log if the key simply doesn't exist
        except ValueError:
            value = self.config.get(resolved_section, key)
            logger.warning(
                f"Invalid value for '{key}' in section '[{section}]'. "
                f"Expected an integer, but got '{value}'. "
                f"Using default value: {fallback}.")
            return fallback

    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        """
        Retrieve a configuration value for a given section and key.

        Args:
            section (str): The section in the config file.
            key (str): The key in the section.
            fallback: Value to return if the section or key is not found.

        Returns:
            The value associated with the key, or the fallback value.
        """
        resolved_section = self._resolve_section(section)
        return self.config.get(resolved_section, key, fallback=fallback)

    def set(self, section: str, key: str, value: str) -> None:
        """
        Set a configuration value for a given section and key.

        Args:
            section (str): The section in the config file.
            key (str): The key in the section.
            value (str): The value to set for the key.
        """
        resolved_section = self._resolve_section(section)
        if not self.config.has_section(resolved_section):
            resolved_section = section
            if not self.config.has_section(resolved_section):
                self.config.add_section(resolved_section)
        self.config.set(resolved_section, key, value)
        self._section_map[self._canonical_section_key(resolved_section)] = (
            resolved_section)
        self.save_config()

    def save_config(self) -> None:
        """Save the current configuration to the config file."""
        # Ensure the directory exists before writing
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w') as configfile:
            self.config.write(configfile)
