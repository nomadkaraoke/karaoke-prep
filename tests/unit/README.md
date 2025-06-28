# Unit Tests for KaraokePrep

This directory contains unit tests for the KaraokePrep class.

## Test Files

The tests are organized into the following files:

- `test_initialization.py`: Tests for initialization and basic functionality
- `test_file_operations.py`: Tests for file operations (copy, download, convert)
- `test_metadata.py`: Tests for metadata extraction and parsing
- `test_lyrics.py`: Tests for lyrics processing
- `test_audio.py`: Tests for audio processing and separation
- `test_video.py`: Tests for video creation and processing
- `test_async.py`: Tests for async methods

## Running the Tests

To run the tests, you need to have the test dependencies installed:

```bash
pip install -r requirements-test.txt
```

Then you can run the tests with:

```bash
python run_tests.py
```

This will run all the tests and generate a coverage report.

## Checking Test Files

If you want to check if the test files are valid Python code without running the tests, you can use:

```bash
python check_tests.py
```

This will check if all the test files can be imported without errors.

## Test Coverage

The tests aim to cover all the functionality of the KaraokePrep class. The coverage report will show you which parts of the code are covered by the tests.
