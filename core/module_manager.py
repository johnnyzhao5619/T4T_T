import os
import json
import shutil
import zipfile
from typing import Dict, Optional, List
from utils.signals import a_signal


class ModuleManager:
    """
    Manages the discovery of available task modules.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ModuleManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, module_path: str = 'modules/'):
        """
        Initializes the ModuleManager, discovers and registers modules.
        
        Args:
            module_path (str): The path to the directory containing modules.
        """
        # Prevent re-initialization
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.module_path = module_path
        self.modules: Dict[str, Dict[str, str]] = {}
        self.discover_modules()
        self._initialized = True

    def discover_modules(self):
        """
        Scans the modules directory to find and register valid modules.
        A valid module is a sub-directory containing both:
        - [module_name]_template.py
        - [module_name]_template.json
        """
        print(f"Discovering modules in '{self.module_path}'...")
        self.modules.clear()  # Clear existing modules before rediscovery
        if not os.path.isdir(self.module_path):
            print(
                f"Warning: Module directory not found at '{self.module_path}'")
            os.makedirs(self.module_path, exist_ok=True)

        for module_name in os.listdir(self.module_path):
            module_dir = os.path.join(self.module_path, module_name)
            if os.path.isdir(module_dir):
                py_template_path = os.path.join(module_dir,
                                                f"{module_name}_template.py")
                json_template_path = os.path.join(
                    module_dir, f"{module_name}_template.json")

                if os.path.isfile(py_template_path) and os.path.isfile(
                        json_template_path):
                    self.modules[module_name] = {
                        'py_template': py_template_path,
                        'json_template': json_template_path,
                        'path': module_dir
                    }
                    print(
                        f"  -> Discovered and registered module: '{module_name}'"
                    )
                else:
                    print(
                        f"  -> Skipping directory '{module_name}': missing required template files."
                    )
        print("Module discovery complete.")
        a_signal.modules_updated.emit()

    def get_module_names(self) -> List[str]:
        """
        Returns a list of all registered module names.

        Returns:
            List[str]: A list of module names.
        """
        return list(self.modules.keys())

    def get_module_templates(self,
                             module_name: str) -> Optional[Dict[str, str]]:
        """
        Retrieves the template paths for a given module.

        Args:
            module_name (str): The name of the module.

        Returns:
            Optional[Dict[str, str]]: A dictionary with 'py_template' and 'json_template' paths,
                                      or None if the module is not found.
        """
        return self.modules.get(module_name)

    def import_module(self, zip_path: str) -> bool:
        """
        Imports a module from a .zip file.

        Args:
            zip_path (str): The path to the .zip file.

        Returns:
            bool: True if import was successful, False otherwise.
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Extract to a temporary directory to inspect contents
                temp_extract_dir = os.path.join(self.module_path,
                                                "temp_extract")
                zip_ref.extractall(temp_extract_dir)

                # Find the module directory inside the extracted files
                extracted_items = os.listdir(temp_extract_dir)
                if not extracted_items:
                    shutil.rmtree(temp_extract_dir)
                    return False

                module_name = extracted_items[0]
                source_module_dir = os.path.join(temp_extract_dir, module_name)

                if not os.path.isdir(source_module_dir):
                    # If the zip file does not contain a subdirectory, use the zip file name as the module name
                    module_name = os.path.splitext(
                        os.path.basename(zip_path))[0]
                    source_module_dir = temp_extract_dir

                # Move the module to the main modules directory
                destination_dir = os.path.join(self.module_path, module_name)
                if os.path.exists(destination_dir):
                    shutil.rmtree(destination_dir)

                shutil.move(source_module_dir, destination_dir)

                # Cleanup the temporary directory if it's not the source
                if source_module_dir != temp_extract_dir:
                    shutil.rmtree(temp_extract_dir)

            self.discover_modules()
            return True
        except Exception as e:
            print(f"Error importing module: {e}")
            # Clean up temp dir on error
            if 'temp_extract_dir' in locals() and os.path.exists(
                    temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            return False

    def export_module(self, module_name: str, destination_path: str) -> bool:
        """
        Exports a module as a .zip file.

        Args:
            module_name (str): The name of the module to export.
            destination_path (str): The path to save the .zip file.

        Returns:
            bool: True if export was successful, False otherwise.
        """
        module_info = self.modules.get(module_name)
        if not module_info:
            return False

        module_dir = module_info['path']
        try:
            with zipfile.ZipFile(destination_path, 'w',
                                 zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(module_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Arcname is the name of the file in the archive
                        arcname = os.path.relpath(file_path,
                                                  os.path.dirname(module_dir))
                        zipf.write(file_path, arcname)
            return True
        except Exception as e:
            print(f"Error exporting module: {e}")
            return False


# Singleton instance for global access
module_manager = ModuleManager()
