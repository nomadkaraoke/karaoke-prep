#!/usr/bin/env python3
import os
import sys
import importlib.util

def check_file(file_path):
    """Check if a Python file can be imported without errors."""
    try:
        spec = importlib.util.spec_from_file_location("module.name", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(f"✅ {file_path} - OK")
        return True
    except Exception as e:
        print(f"❌ {file_path} - ERROR: {e}")
        return False

def main():
    """Check all test files in the current directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_files = [f for f in os.listdir(current_dir) if f.startswith("test_") and f.endswith(".py")]
    
    if not test_files:
        print("No test files found.")
        return 0
    
    print(f"Checking {len(test_files)} test files...")
    
    success = True
    for file_name in sorted(test_files):
        file_path = os.path.join(current_dir, file_name)
        if not check_file(file_path):
            success = False
    
    if success:
        print("\nAll test files are valid Python code.")
        return 0
    else:
        print("\nSome test files have errors. Please fix them before running the tests.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
