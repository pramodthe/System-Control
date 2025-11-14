#!/usr/bin/env python3
"""
Setup Verification Script for Voice-Controlled Computer Assistant

This script verifies that all requirements are met before running the main application.
It checks:
- Environment configuration (.env file and API key)
- Python version compatibility
- Required dependencies
"""

import os
import sys
from pathlib import Path


def check_env_file_exists():
    """
    Check if .env file exists in the project root.
    
    Returns:
        tuple: (bool: success, str: message)
    """
    env_path = Path(".env")
    if env_path.exists():
        return True, ".env file found"
    else:
        return False, ".env file not found. Create it by copying .env.example:\n  cp .env.example .env"


def check_api_key_configured():
    """
    Verify that GOOGLE_API_KEY is set and non-empty.
    
    Returns:
        tuple: (bool: success, str: message)
    """
    # Try to load from .env file
    env_path = Path(".env")
    if not env_path.exists():
        return False, "Cannot check API key: .env file missing"
    
    # Read .env file and look for GOOGLE_API_KEY
    api_key = None
    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('GOOGLE_API_KEY='):
                    api_key = line.split('=', 1)[1].strip()
                    break
    except Exception as e:
        return False, f"Error reading .env file: {e}"
    
    if not api_key:
        return False, "GOOGLE_API_KEY not found in .env file"
    
    return validate_api_key_format(api_key)


def validate_api_key_format(api_key):
    """
    Validate that the API key has a valid format.
    
    Args:
        api_key: The API key string to validate
        
    Returns:
        tuple: (bool: success, str: message)
    """
    # Check if it's the placeholder value
    if api_key == "your-api-key-here":
        return False, "GOOGLE_API_KEY is still set to placeholder value. Replace it with your actual API key from https://aistudio.google.com/apikey"
    
    # Check if it's empty
    if not api_key or len(api_key.strip()) == 0:
        return False, "GOOGLE_API_KEY is empty. Set it to your actual API key from https://aistudio.google.com/apikey"
    
    # Basic format check - Google API keys typically start with "AIza" and are around 39 characters
    if len(api_key) < 20:
        return False, "GOOGLE_API_KEY appears to be too short. Verify you copied the complete key from https://aistudio.google.com/apikey"
    
    return True, "GOOGLE_API_KEY is configured"



def check_python_version():
    """
    Check if Python version is 3.12 or higher.
    
    Returns:
        tuple: (bool: success, str: message)
    """
    current_version = sys.version_info
    required_version = (3, 12)
    
    if current_version >= required_version:
        return True, f"Python {current_version.major}.{current_version.minor}.{current_version.micro} (>= 3.12 required)"
    else:
        return False, f"Python {current_version.major}.{current_version.minor}.{current_version.micro} found, but 3.12 or higher is required. Please upgrade Python."


def check_dependencies():
    """
    Test import of all required packages.
    
    Returns:
        tuple: (bool: all_success, list: results with (package_name, success, message))
    """
    required_packages = [
        ('dotenv', 'python-dotenv'),
        ('google.genai', 'google-genai'),
        ('pyaudio', 'pyaudio'),
        ('PIL', 'pillow'),
        ('cv2', 'opencv-python'),
        ('mss', 'mss'),
        ('pynput', 'pynput'),
        ('pyautogui', 'pyautogui'),
    ]
    
    results = []
    all_success = True
    missing_packages = []
    
    for import_name, package_name in required_packages:
        try:
            __import__(import_name)
            results.append((package_name, True, f"{package_name} is installed"))
        except ImportError:
            results.append((package_name, False, f"{package_name} is missing"))
            missing_packages.append(package_name)
            all_success = False
    
    return all_success, results, missing_packages



def print_check_result(check_name, success, message):
    """
    Print a formatted check result with colored output.
    
    Args:
        check_name: Name of the check being performed
        success: Boolean indicating if check passed
        message: Detailed message about the check result
    """
    status_icon = "✅" if success else "❌"
    print(f"{status_icon} {check_name}: {message}")


def print_header(text):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_section(text):
    """Print a formatted section header."""
    print(f"\n{text}")
    print("-" * len(text))


def main():
    """
    Main function to run all verification checks.
    
    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    print_header("Voice Assistant Setup Verification")
    
    all_checks_passed = True
    errors = []
    
    # Check 1: Environment file
    print_section("Environment Configuration")
    env_exists, env_msg = check_env_file_exists()
    print_check_result("Environment file", env_exists, env_msg)
    if not env_exists:
        all_checks_passed = False
        errors.append(env_msg)
    
    # Check 2: API Key
    api_key_ok, api_key_msg = check_api_key_configured()
    print_check_result("API Key", api_key_ok, api_key_msg)
    if not api_key_ok:
        all_checks_passed = False
        errors.append(api_key_msg)
    
    # Check 3: Python version
    print_section("Python Environment")
    python_ok, python_msg = check_python_version()
    print_check_result("Python version", python_ok, python_msg)
    if not python_ok:
        all_checks_passed = False
        errors.append(python_msg)
    
    # Check 4: Dependencies
    print_section("Dependencies")
    deps_ok, dep_results, missing_packages = check_dependencies()
    for package_name, success, message in dep_results:
        print_check_result(package_name, success, message)
    
    if not deps_ok:
        all_checks_passed = False
        error_msg = f"Missing dependencies: {', '.join(missing_packages)}. Install them with:\n  uv sync"
        errors.append(error_msg)
    
    # Final summary
    print_section("Summary")
    if all_checks_passed:
        print("✅ All checks passed! Your setup is complete.")
        print("\nYou can now run the Voice Assistant with:")
        print("  uv run python main_file.py")
        return 0
    else:
        print("❌ Setup verification failed. Please fix the following issues:\n")
        for i, error in enumerate(errors, 1):
            print(f"{i}. {error}")
        print("\nAfter fixing these issues, run this script again to verify:")
        print("  uv run python verify_setup.py")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
