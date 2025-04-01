# KaraokePrep Unit Tests

This directory contains unit tests for the `KaraokePrep` class in the `karaoke_prep` module.

## Test Structure

The tests are organized into logical groups:

- `test_initialization.py`: Tests for initialization and basic functionality
- `test_file_operations.py`: Tests for file operations (copy, download, convert)
- `test_metadata.py`: Tests for metadata extraction and parsing
- `test_lyrics.py`: Tests for lyrics processing
- `test_audio.py`: Tests for audio processing and separation
- `test_video.py`: Tests for video creation and processing
- `test_async.py`: Tests for async methods

## Running the Tests

### Prerequisites

First, activate the conda environment:

```bash
conda activate karaoke-prep
```

Then install the required test dependencies:

```bash
pip install -r requirements-test.txt
```

### Running All Tests

To run all tests with coverage reporting:

```bash
./run_tests.py
```

### Checking Test Files for Syntax Errors

If you don't have pytest installed, you can still check the test files for syntax errors:

```bash
./check_tests.py
```

This will verify that all test files are valid Python code without actually running the tests.

### Running Specific Tests

To run a specific test file:

```bash
./run_tests.py test_initialization.py
```

To run a specific test class:

```bash
./run_tests.py test_initialization.py::TestInitialization
```

To run a specific test method:

```bash
./run_tests.py test_initialization.py::TestInitialization::test_init_with_defaults
```

## Test Coverage

The tests aim to provide comprehensive coverage of the `KaraokePrep` class functionality. When running the tests with the `run_tests.py` script, a coverage report will be displayed showing which parts of the code are covered by the tests.
