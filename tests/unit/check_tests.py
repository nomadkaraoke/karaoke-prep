#!/usr/bin/env python3
"""
Simple script to check for syntax errors in test files.
This doesn't run the actual tests but helps verify that the test files are valid Python.
"""

import os
import sys
import importlib.util
import traceback

def check_file(file_path):
    """Check a Python file for syntax errors."""
    try:
        # Try to compile the file to check for syntax errors
        with open(file_path, 'r') as f:
            source = f.read()
        compile(source, file_path, 'exec')
        print(f"✓ {file_path} - No syntax errors")
        return True
    except Exception as e:
        print(f"✗ {file_path} - Error: {e}")
        traceback.print_exc()
        return False

def main():
    """Check all test files for syntax errors."""
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Add the project root to the Python path
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    sys.path.insert(0, project_root)
    
    # Get all Python files in the directory
    test_files = [f for f in os.listdir(script_dir) if f.startswith('test_') and f.endswith('.py')]
    
    # Check each file
    success = True
    for file in test_files:
        file_path = os.path.join(script_dir, file)
        if not check_file(file_path):
            success = False
    
    # Check conftest.py
    conftest_path = os.path.join(script_dir, 'conftest.py')
    if os.path.exists(conftest_path):
        if not check_file(conftest_path):
            success = False
    
    if success:
        print("\nAll test files passed syntax check!")
        return 0
    else:
        print("\nSome test files have syntax errors.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
