"""Configuration validation for IoControl"""

from __future__ import annotations
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import jsonschema

from .types import IoType

class ValidationLevel(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class ValidationIssue:
    """Represents a configuration validation issue"""
    level: ValidationLevel
    category: str
    message: str
    path: str
    suggestion: Optional[str] = None

class ConfigValidator:
    """Configuration validator for IoControl"""
    
    # JSON Schema for I/O configuration
    SCHEMA = {
        "type": "object",
        "required": ["io_points"],
        "properties": {
            "io_points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "io_type", "hardware_ref"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "pattern": "^[a-zA-Z][a-zA-Z0-9_]*$",
                            "minLength": 1,
                            "maxLength": 64
                        },
                        "io_type": {
                            "type": "string",
                            "enum": ["digital_input", "digital_output", "analog_input", "analog_output"]
                        },
                        "hardware_ref": {
                            "type": "string",
                            "minLength": 1
                        },
                        "critical": {"type": "boolean"},
                        "interrupt_enabled": {"type": "boolean"},
                        "pull_up": {"type": "boolean"},
                        "initial_state": {"oneOf": [{"type": "boolean"}, {"type": "number"}]},
                        "description": {"type": "string"},
                        "tags": {"type": "object"}
                    }
                }
            }
        }
    }
    
    def validate_config(self, config: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate configuration and return all issues"""
        issues = []
        
        # Schema validation
        try:
            jsonschema.validate(config, self.SCHEMA)
        except jsonschema.ValidationError as e:
            issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                category="schema",
                message=f"Schema validation failed: {e.message}",
                path=str(e.absolute_path[0]) if e.absolute_path else "root",
                suggestion="Check configuration format against examples"
            ))
            return issues  # Don't continue if schema is invalid
        
        if "io_points" in config:
            io_points = config["io_points"]
            
            # Validate individual points
            for i, point in enumerate(io_points):
                issues.extend(self._validate_point(point, f"io_points[{i}]"))
            
            # Check for conflicts and safety issues
            issues.extend(self._check_conflicts(io_points))
            issues.extend(self._check_safety_rules(io_points))
        
        return issues
    
    def _validate_point(self, point: Dict[str, Any], path: str) -> List[ValidationIssue]:
        """Validate individual I/O point"""
        issues = []
        
        # Check initial_state compatibility with io_type
        if "initial_state" in point and "io_type" in point:
            initial_state = point["initial_state"]
            io_type = point["io_type"]
            
            if io_type in ["digital_input", "digital_output"]:
                if not isinstance(initial_state, bool):
                    issues.append(ValidationIssue(
                        level=ValidationLevel.WARNING,
                        category="type_mismatch",
                        message=f"Digital I/O should have boolean initial_state, got {type(initial_state).__name__}",
                        path=f"{path}.initial_state",
                        suggestion="Use true/false for digital I/O points"
                    ))
            elif io_type in ["analog_input", "analog_output"]:
                # Check for bool first since isinstance(True, int) is True in Python
                if isinstance(initial_state, bool):
                    issues.append(ValidationIssue(
                        level=ValidationLevel.WARNING,
                        category="type_mismatch",
                        message=f"Analog I/O should have numeric initial_state, got {type(initial_state).__name__}",
                        path=f"{path}.initial_state",
                        suggestion="Use a number for analog I/O points"
                    ))
                elif not isinstance(initial_state, (int, float)):
                    issues.append(ValidationIssue(
                        level=ValidationLevel.WARNING,
                        category="type_mismatch",
                        message=f"Analog I/O should have numeric initial_state, got {type(initial_state).__name__}",
                        path=f"{path}.initial_state",
                        suggestion="Use a number for analog I/O points"
                    ))
        
        # Check for inputs with initial_state
        if "io_type" in point and point["io_type"].endswith("_input") and "initial_state" in point:
            issues.append(ValidationIssue(
                level=ValidationLevel.INFO,
                category="unnecessary_field",
                message="Input points don't need initial_state (read from hardware)",
                path=f"{path}.initial_state",
                suggestion="Remove initial_state for input points"
            ))
        
        return issues
    
    def _check_conflicts(self, io_points: List[Dict[str, Any]]) -> List[ValidationIssue]:
        """Check for conflicts between I/O points"""
        issues = []
        
        # Check duplicate names
        names_seen = set()
        for i, point in enumerate(io_points):
            if "name" in point:
                name = point["name"]
                if name in names_seen:
                    issues.append(ValidationIssue(
                        level=ValidationLevel.ERROR,
                        category="duplicate_name",
                        message=f"Duplicate I/O point name '{name}'",
                        path=f"io_points[{i}].name",
                        suggestion="Each I/O point must have a unique name"
                    ))
                names_seen.add(name)
        
        # Check duplicate hardware_ref
        hardware_refs_seen = set()
        for i, point in enumerate(io_points):
            if "hardware_ref" in point:
                hardware_ref = point["hardware_ref"]
                if hardware_ref in hardware_refs_seen:
                    issues.append(ValidationIssue(
                        level=ValidationLevel.ERROR,
                        category="duplicate_hardware",
                        message=f"Duplicate hardware_ref '{hardware_ref}'",
                        path=f"io_points[{i}].hardware_ref",
                        suggestion="Each I/O point must use a unique hardware pin"
                    ))
                hardware_refs_seen.add(hardware_ref)
        
        return issues
    
    def _check_safety_rules(self, io_points: List[Dict[str, Any]]) -> List[ValidationIssue]:
        """Check safety-related configuration rules"""
        issues = []
        
        emergency_stops = []
        critical_outputs = []
        output_points = []
        
        # Categorize points
        for i, point in enumerate(io_points):
            name = point.get("name", "").lower()
            io_type = point.get("io_type", "")
            is_critical = point.get("critical", False)
            
            if "emergency" in name and "stop" in name:
                emergency_stops.append((i, point))
            
            if io_type.endswith("_output"):
                output_points.append((i, point))
                if is_critical:
                    critical_outputs.append((i, point))
        
        # Emergency stop validation
        for i, point in emergency_stops:
            if point.get("io_type") != "digital_input":
                issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category="safety",
                    message="Emergency stop should be digital_input",
                    path=f"io_points[{i}].io_type",
                    suggestion="Emergency stops are typically digital inputs"
                ))
            
            if not point.get("critical", False):
                issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category="safety",
                    message="Emergency stop should be marked as critical",
                    path=f"io_points[{i}].critical",
                    suggestion="Set 'critical: true' for emergency stop points"
                ))
        
        # Critical output validation
        for i, point in critical_outputs:
            initial_state = point.get("initial_state")
            if initial_state is None:
                issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category="safety",
                    message="Critical output should have explicit initial_state",
                    path=f"io_points[{i}].initial_state",
                    suggestion="Set safe initial state for critical outputs"
                ))
        
        # System-level safety checks
        if output_points and not emergency_stops:
            issues.append(ValidationIssue(
                level=ValidationLevel.INFO,
                category="safety",
                message="System has outputs but no emergency stop points",
                path="io_points",
                suggestion="Consider adding emergency stop inputs for safety"
            ))
        
        return issues

def validate_io_config(config: Dict[str, Any]) -> Tuple[bool, List[ValidationIssue]]:
    """
    Validate I/O configuration
    
    Returns:
        (is_valid, issues) - is_valid is False if there are ERROR level issues
    """
    validator = ConfigValidator()
    issues = validator.validate_config(config)
    
    has_errors = any(issue.level == ValidationLevel.ERROR for issue in issues)
    is_valid = not has_errors
    
    return is_valid, issues

def print_validation_results(issues: List[ValidationIssue], show_info: bool = True):
    """Print validation results in readable format"""
    
    if not issues:
        print("Configuration validation passed - no issues found!")
        return
    
    # Group by level
    errors = [i for i in issues if i.level == ValidationLevel.ERROR]
    warnings = [i for i in issues if i.level == ValidationLevel.WARNING]
    info = [i for i in issues if i.level == ValidationLevel.INFO]
    
    # Print summary
    print(f"Validation Results:")
    print(f"   Errors: {len(errors)}")
    print(f"   Warnings: {len(warnings)}")
    print(f"   Info: {len(info)}")
    
    # Print details
    def print_issues(title, issues_list):
        if issues_list:
            print(f"\n{title}:")
            for issue in issues_list:
                print(f"   [{issue.category}] {issue.path}: {issue.message}")
                if issue.suggestion:
                    print(f"      Suggestion: {issue.suggestion}")
    
    print_issues("ERRORS (must fix)", errors)
    print_issues("WARNINGS (should fix)", warnings)
    
    if show_info:
        print_issues("INFO (consider)", info)
    
    # Final verdict
    if errors:
        print(f"\nConfiguration INVALID - {len(errors)} error(s) must be fixed")
    else:
        print(f"\nConfiguration VALID - ready to use")
        if warnings:
            print(f"   (Consider addressing {len(warnings)} warning(s))")

def validate_config_file(file_path: str) -> bool:
    """Validate a configuration file"""
    try:
        from pathlib import Path
        import json
        
        path = Path(file_path)
        with open(path, 'r') as f:
            if path.suffix.lower() in ['.yaml', '.yml']:
                import yaml
                config = yaml.safe_load(f)
            else:
                config = json.load(f)
        
        is_valid, issues = validate_io_config(config)
        print_validation_results(issues)
        return is_valid
        
    except Exception as e:
        print(f"Failed to validate configuration: {e}")
        return False

# Integration with IoManager
def add_validation_to_manager(io_manager):
    """Add validation to IoManager configuration methods"""
    
    original_configure_from_dict = io_manager.configure_from_dict
    
    async def validated_configure_from_dict(config: Dict[str, Any]) -> bool:
        """Configure with validation"""
        is_valid, issues = validate_io_config(config)
        
        print_validation_results(issues, show_info=False)
        
        if not is_valid:
            print("Configuration rejected due to validation errors")
            return False
        
        return await original_configure_from_dict(config)
    
    async def validated_configure_from_file(config_path) -> bool:
        """Configure from file with validation"""
        try:
            from pathlib import Path
            import json
            
            path = Path(config_path)
            with open(path, 'r') as f:
                if path.suffix.lower() in ['.yaml', '.yml']:
                    import yaml
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)
            
            return await validated_configure_from_dict(config)
        except Exception as e:
            print(f"Failed to load configuration from {config_path}: {e}")
            return False
    
    # Replace methods
    io_manager.configure_from_dict = validated_configure_from_dict
    io_manager.configure_from_file = validated_configure_from_file
    
    # Add validation helper
    io_manager.validate_config_file = validate_config_file