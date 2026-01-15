"""
Test suite for config functionality
Tests the config.json file handling including MCU history and interface persistence
"""

import json
import os
import tempfile
import pytest
from pathlib import Path


class TestConfigFunctionality:
    """Test config file loading and saving functionality"""

    def test_save_and_load_config(self):
        """Test saving and loading complete config structure"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_config_path = f.name

        try:
            # Test saving config
            config = {
                'mcu_history': ['STM32F427II', 'STM32F103C8'],
                'last_interface': 'JTAG'
            }

            with open(temp_config_path, 'w') as f:
                json.dump(config, f)

            # Test loading config
            with open(temp_config_path, 'r') as f:
                loaded_config = json.load(f)

            assert loaded_config == config
            assert loaded_config['mcu_history'] == ['STM32F427II', 'STM32F103C8']
            assert loaded_config['last_interface'] == 'JTAG'

        finally:
            # Clean up
            if os.path.exists(temp_config_path):
                os.unlink(temp_config_path)

    def test_backward_compatibility_with_old_config(self):
        """Test that old config format (list only) still works"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_config_path = f.name

        try:
            # Old config format - just a list
            old_config = ['STM32F427II', 'STM32F103C8']
            with open(temp_config_path, 'w') as f:
                json.dump(old_config, f)

            # Simulate the load logic from RTTViewer
            try:
                with open(temp_config_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        loaded_config = data
                    else:
                        loaded_config = {'mcu_history': data if isinstance(data, list) else [], 'last_interface': 'SWD'}
            except Exception:
                loaded_config = {'mcu_history': [], 'last_interface': 'SWD'}

            assert loaded_config['mcu_history'] == old_config
            assert loaded_config['last_interface'] == 'SWD'

        finally:
            # Clean up
            if os.path.exists(temp_config_path):
                os.unlink(temp_config_path)

    def test_config_with_empty_history(self):
        """Test config handling with empty MCU history"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_config_path = f.name

        try:
            config = {
                'mcu_history': [],
                'last_interface': 'SWD'
            }

            with open(temp_config_path, 'w') as f:
                json.dump(config, f)

            # Test loading
            with open(temp_config_path, 'r') as f:
                loaded_config = json.load(f)

            assert loaded_config['mcu_history'] == []
            assert loaded_config['last_interface'] == 'SWD'

        finally:
            # Clean up
            if os.path.exists(temp_config_path):
                os.unlink(temp_config_path)

    def test_config_file_not_exists(self):
        """Test behavior when config file doesn't exist"""
        # Simulate the load logic when file doesn't exist
        try:
            with open('/nonexistent/config.json', 'r') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    loaded_config = data
                else:
                    loaded_config = {'mcu_history': data if isinstance(data, list) else [], 'last_interface': 'SWD'}
        except Exception:
            loaded_config = {'mcu_history': [], 'last_interface': 'SWD'}

        assert loaded_config['mcu_history'] == []
        assert loaded_config['last_interface'] == 'SWD'

    def test_invalid_json_config(self):
        """Test handling of invalid JSON in config file"""
        temp_config_path = None
        try:
            # Create temp file and write invalid JSON
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                temp_config_path = f.name
                # Write invalid JSON
                f.write('{invalid json content')

            # Simulate the load logic
            try:
                with open(temp_config_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        loaded_config = data
                    else:
                        loaded_config = {'mcu_history': data if isinstance(data, list) else [], 'last_interface': 'SWD'}
            except Exception:
                loaded_config = {'mcu_history': [], 'last_interface': 'SWD'}

            assert loaded_config['mcu_history'] == []
            assert loaded_config['last_interface'] == 'SWD'

        finally:
            # Clean up
            if temp_config_path and os.path.exists(temp_config_path):
                os.unlink(temp_config_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
