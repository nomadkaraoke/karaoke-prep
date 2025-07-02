# Karaoke Generator 🎶 🎥 🚀

![PyPI - Version](https://img.shields.io/pypi/v/karaoke-gen)
![Python Version](https://img.shields.io/badge/python-3.10+-blue)
![Tests](https://github.com/nomadkaraoke/karaoke-gen/workflows/Test%20and%20Publish/badge.svg)
![Test Coverage](https://codecov.io/gh/nomadkaraoke/karaoke-gen/branch/main/graph/badge.svg)

Generate karaoke videos with instrumental audio and synchronized lyrics. Handles the entire process from downloading audio and lyrics to creating the final video with title screens, uploading the resulting video to YouTube.

## Overview

Karaoke Generator is a comprehensive tool for creating high-quality karaoke videos. It automates the entire workflow:

1. **Download** audio and lyrics for a specified song
2. **Separate** audio stems (vocals, instrumental)
3. **Synchronize** lyrics with the audio
4. **Generate** title and end screens
5. **Combine** everything into a polished final video
6. **Organize** and **share** the output files

## Installation

```bash
pip install karaoke-gen
```

## Quick Start

```bash
# Generate a karaoke video from a YouTube URL
karaoke-gen "https://www.youtube.com/watch?v=dQw4w9WgXcQ" "Rick Astley" "Never Gonna Give You Up"

# Or let it search YouTube for you
karaoke-gen "Rick Astley" "Never Gonna Give You Up"
```

## Workflow Options

Karaoke Gen supports different workflow options to fit your needs:

```bash
# Run only the preparation phase (download, separate stems, create title screens)
karaoke-gen --prep-only "Rick Astley" "Never Gonna Give You Up"

# Run only the finalisation phase (must be run in a directory prepared by the prep phase)
karaoke-gen --finalise-only

# Skip automatic lyrics transcription/synchronization (for manual syncing)
karaoke-gen --skip-transcription "Rick Astley" "Never Gonna Give You Up"

# Skip audio separation (if you already have instrumental)
karaoke-gen --skip-separation --existing-instrumental="path/to/instrumental.mp3" "Rick Astley" "Never Gonna Give You Up"
```

## Advanced Features

### Audio Processing

```bash
# Specify custom audio separation models
karaoke-gen --clean_instrumental_model="model_name.ckpt" "Rick Astley" "Never Gonna Give You Up"
```

### Lyrics Handling

```bash
# Use a local lyrics file instead of fetching from online
karaoke-gen --lyrics_file="path/to/lyrics.txt" "Rick Astley" "Never Gonna Give You Up"

# Adjust subtitle timing
karaoke-gen --subtitle_offset_ms=500 "Rick Astley" "Never Gonna Give You Up"
```

### Finalisation Options

```bash
# Enable CDG ZIP generation
karaoke-gen --enable_cdg --style_params_json="path/to/style.json" "Rick Astley" "Never Gonna Give You Up"

# Enable TXT ZIP generation
karaoke-gen --enable_txt "Rick Astley" "Never Gonna Give You Up"

# Upload to YouTube
karaoke-gen --youtube_client_secrets_file="path/to/client_secret.json" --youtube_description_file="path/to/description.txt" "Rick Astley" "Never Gonna Give You Up"

# Organize files with brand code
karaoke-gen --brand_prefix="BRAND" --organised_dir="path/to/Tracks-Organized" "Rick Astley" "Never Gonna Give You Up"
```

## Full Command Reference

For a complete list of options:

```bash
karaoke-gen --help
```

## Development

### Running Tests

The project uses pytest for testing with unit and integration tests:

```bash
# Run all tests (unit tests first, then integration tests)
pytest

# Run only unit tests (fast feedback during development)
pytest -m "not integration"

# Run only integration tests (comprehensive end-to-end testing)
pytest -m integration
```

Unit tests run quickly and provide fast feedback, while integration tests are slower but test the full workflow end-to-end.

## License

MIT
