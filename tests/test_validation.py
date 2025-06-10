"""Tests for IoControl configuration validation"""

import pytest
from unittest.mock import AsyncMock

from iocontrol.validation import (
    ConfigValidator, 
    validate_io_config, 
    ValidationLevel,
    add_validation_to_manager
)


class TestConfigValidator:
    """Test cases for ConfigValidator"""
    
    def test_valid_config(self):
        """Test validation of a valid configuration"""
        config = {
            "io_points": [
                {
                    "name": "pump_main",
                    "io_type": "digital_output",
                    "hardware_ref": "mcp.chip0.pin0",
                    "critical": True,
                    "initial_state": False,
                    "description": "Main pump"
                },
                {
                    "name": "temp_sensor", 
                    "io_type": "analog_input",
                    "hardware_ref": "mcp.chip1.pin0",
                    "description": "Temperature sensor"
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert is_valid
        # Should have at most INFO level issues
        assert all(issue.level != ValidationLevel.ERROR for issue in issues)
    
    def test_missing_required_fields(self):
        """Test validation catches missing required fields"""
        config = {
            "io_points": [
                {
                    "name": "incomplete_point",
                    # Missing io_type and hardware_ref
                    "description": "Incomplete point"
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert not is_valid
        assert any(issue.level == ValidationLevel.ERROR for issue in issues)
    
    def test_invalid_io_type(self):
        """Test validation catches invalid io_type"""
        config = {
            "io_points": [
                {
                    "name": "invalid_point",
                    "io_type": "invalid_type",
                    "hardware_ref": "mcp.chip0.pin0"
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert not is_valid
        assert any("invalid_type" in issue.message for issue in issues)
    
    def test_invalid_name_pattern(self):
        """Test validation catches invalid names"""
        config = {
            "io_points": [
                {
                    "name": "123_invalid",  # Can't start with number
                    "io_type": "digital_output",
                    "hardware_ref": "mcp.chip0.pin0"
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert not is_valid
        assert any("123_invalid" in issue.message for issue in issues)
    
    def test_duplicate_names(self):
        """Test validation catches duplicate names"""
        config = {
            "io_points": [
                {
                    "name": "duplicate_name",
                    "io_type": "digital_output",
                    "hardware_ref": "mcp.chip0.pin0"
                },
                {
                    "name": "duplicate_name",  # Duplicate!
                    "io_type": "digital_input",
                    "hardware_ref": "mcp.chip0.pin1"
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert not is_valid
        assert any("duplicate" in issue.message.lower() for issue in issues)
    
    def test_duplicate_hardware_ref(self):
        """Test validation catches duplicate hardware references"""
        config = {
            "io_points": [
                {
                    "name": "point_1",
                    "io_type": "digital_output",
                    "hardware_ref": "mcp.chip0.pin0"
                },
                {
                    "name": "point_2",
                    "io_type": "digital_input",
                    "hardware_ref": "mcp.chip0.pin0"  # Duplicate hardware!
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert not is_valid
        assert any("duplicate" in issue.message.lower() and "hardware" in issue.message.lower() for issue in issues)
    
    def test_initial_state_type_mismatch(self):
        """Test validation handles initial_state type mismatches"""
        config = {
            "io_points": [
                {
                    "name": "digital_point",
                    "io_type": "digital_output",
                    "hardware_ref": "mcp.chip0.pin0",
                    "initial_state": 123  # Should be boolean - schema will catch this as error
                },
                {
                    "name": "analog_point",
                    "io_type": "analog_output", 
                    "hardware_ref": "mcp.chip0.pin1",
                    "initial_state": "not_a_number"  # Should be numeric - schema will catch this as error
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        # Schema validation will make this invalid due to type constraints
        assert not is_valid
        # Should have schema validation errors
        assert any(issue.level == ValidationLevel.ERROR for issue in issues)
        assert any("schema" in issue.category.lower() for issue in issues)
    
    def test_initial_state_business_logic_warnings(self):
        """Test validation provides warnings for initial_state business logic issues"""
        config = {
            "io_points": [
                {
                    "name": "digital_point",
                    "io_type": "digital_output",
                    "hardware_ref": "mcp.chip0.pin0",
                    "initial_state": 1.5  # Number for digital (warning, but schema allows it)
                },
                {
                    "name": "analog_point",
                    "io_type": "analog_output", 
                    "hardware_ref": "mcp.chip0.pin1",
                    "initial_state": True  # Boolean for analog (warning, but schema allows it)
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert is_valid  # Should be valid but with warnings
        # Should have 2 business logic warnings now
        warning_issues = [i for i in issues if i.level == ValidationLevel.WARNING]
        assert len(warning_issues) == 2
        # Check that we get both type mismatch warnings
        assert any("digital" in issue.message.lower() and "boolean" in issue.message.lower() for issue in warning_issues)
        assert any("analog" in issue.message.lower() and "numeric" in issue.message.lower() for issue in warning_issues)
    
    def test_input_with_initial_state(self):
        """Test validation flags inputs with initial_state as info"""
        config = {
            "io_points": [
                {
                    "name": "input_point",
                    "io_type": "digital_input",
                    "hardware_ref": "mcp.chip0.pin0",
                    "initial_state": True  # Inputs don't need this
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert is_valid
        assert any(issue.level == ValidationLevel.INFO for issue in issues)
    
    def test_safety_emergency_stop_validation(self):
        """Test emergency stop safety validation"""
        config = {
            "io_points": [
                {
                    "name": "emergency_stop",
                    "io_type": "digital_output",  # Should be input
                    "hardware_ref": "mcp.chip0.pin0",
                    "critical": False  # Should be critical
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert is_valid  # Warnings don't invalidate
        
        # Should have warnings about emergency stop configuration
        warning_messages = [i.message for i in issues if i.level == ValidationLevel.WARNING]
        assert any("emergency stop" in msg.lower() for msg in warning_messages)
    
    def test_critical_output_without_initial_state(self):
        """Test critical outputs without initial_state get warnings"""
        config = {
            "io_points": [
                {
                    "name": "critical_pump",
                    "io_type": "digital_output",
                    "hardware_ref": "mcp.chip0.pin0",
                    "critical": True
                    # Missing initial_state
                }
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert is_valid
        assert any("critical output" in issue.message.lower() for issue in issues)
    
    def test_system_without_emergency_stops(self):
        """Test system with outputs but no emergency stops gets info"""
        config = {
            "io_points": [
                {
                    "name": "some_pump",
                    "io_type": "digital_output",
                    "hardware_ref": "mcp.chip0.pin0"
                },
                {
                    "name": "some_valve",
                    "io_type": "digital_output", 
                    "hardware_ref": "mcp.chip0.pin1"
                }
                # No emergency stops
            ]
        }
        
        is_valid, issues = validate_io_config(config)
        assert is_valid
        assert any("emergency stop" in issue.message.lower() for issue in issues)
    
    def test_empty_config(self):
        """Test validation of empty/minimal config"""
        config = {"io_points": []}
        
        is_valid, issues = validate_io_config(config)
        assert is_valid
        assert len(issues) == 0
    
    def test_missing_io_points(self):
        """Test config without io_points section"""
        config = {}
        
        is_valid, issues = validate_io_config(config)
        assert not is_valid
        assert any(issue.level == ValidationLevel.ERROR for issue in issues)


class TestValidationIntegration:
    """Test integration with IoManager"""
    
    @pytest.fixture
    def mock_io_manager(self):
        """Create a mock IoManager for testing"""
        class MockIoManager:
            def __init__(self):
                self.original_configure_called = False
                self.original_config = None
            
            async def configure_from_dict(self, config):
                self.original_configure_called = True
                self.original_config = config
                return True
        
        return MockIoManager()
    
    def test_add_validation_to_manager(self, mock_io_manager):
        """Test adding validation to IoManager"""
        add_validation_to_manager(mock_io_manager)
        
        # Should have validation methods added
        assert hasattr(mock_io_manager, 'validate_config_file')
        assert callable(mock_io_manager.configure_from_dict)
        assert callable(mock_io_manager.configure_from_file)
    
    @pytest.mark.asyncio
    async def test_validated_configure_with_valid_config(self, mock_io_manager):
        """Test validation integration with valid config"""
        add_validation_to_manager(mock_io_manager)
        
        valid_config = {
            "io_points": [
                {
                    "name": "test_point",
                    "io_type": "digital_output",
                    "hardware_ref": "mcp.chip0.pin0"
                }
            ]
        }
        
        result = await mock_io_manager.configure_from_dict(valid_config)
        assert result is True
        assert mock_io_manager.original_configure_called
        assert mock_io_manager.original_config == valid_config
    
    @pytest.mark.asyncio
    async def test_validated_configure_with_invalid_config(self, mock_io_manager, capsys):
        """Test validation integration rejects invalid config"""
        add_validation_to_manager(mock_io_manager)
        
        invalid_config = {
            "io_points": [
                {
                    "name": "123_invalid",  # Invalid name
                    "io_type": "invalid_type",  # Invalid type
                    "hardware_ref": "mcp.chip0.pin0"
                }
            ]
        }
        
        result = await mock_io_manager.configure_from_dict(invalid_config)
        assert result is False
        assert not mock_io_manager.original_configure_called
        
        # Should print validation errors
        captured = capsys.readouterr()
        assert "Configuration rejected" in captured.out


class TestValidationOutput:
    """Test validation output formatting"""
    
    def test_print_validation_results_no_issues(self, capsys):
        """Test output when no issues found"""
        from iocontrol.validation import print_validation_results
        
        print_validation_results([])
        captured = capsys.readouterr()
        assert "no issues found" in captured.out
    
    def test_print_validation_results_with_issues(self, capsys):
        """Test output formatting with various issue types"""
        from iocontrol.validation import print_validation_results, ValidationIssue
        
        issues = [
            ValidationIssue(
                level=ValidationLevel.ERROR,
                category="test",
                message="Test error",
                path="test.path",
                suggestion="Fix this"
            ),
            ValidationIssue(
                level=ValidationLevel.WARNING, 
                category="test",
                message="Test warning",
                path="test.path"
            ),
            ValidationIssue(
                level=ValidationLevel.INFO,
                category="test", 
                message="Test info",
                path="test.path"
            )
        ]
        
        print_validation_results(issues)
        captured = capsys.readouterr()
        
        assert "Errors: 1" in captured.out
        assert "Warnings: 1" in captured.out
        assert "Info: 1" in captured.out
        assert "Test error" in captured.out
        assert "Test warning" in captured.out
        assert "Test info" in captured.out
        assert "Fix this" in captured.out
        assert "INVALID" in captured.out


if __name__ == "__main__":
    pytest.main([__file__])