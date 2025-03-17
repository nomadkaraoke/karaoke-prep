# Karaoke Gen

Generate karaoke videos with synchronized lyrics. Handles the entire process from downloading audio and lyrics to creating the final video with title screens.

## Overview

Karaoke Gen is a comprehensive tool for creating high-quality karaoke videos. It automates the entire workflow:

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

# Process multiple tracks in bulk from a CSV file
karaoke-bulk input.csv --style_params_json=style.json
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

## Python API

Karaoke Gen can also be used as a Python library:

```python
import asyncio
from karaoke_gen import KaraokeController, ProjectConfig

async def generate_karaoke():
    # Create a configuration
    config = ProjectConfig(
        artist="Rick Astley",
        title="Never Gonna Give You Up",
        input_media="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        output_dir="output",
        create_track_subfolders=True,
    )
    
    # Create a controller
    controller = KaraokeController(config)
    
    # Process the track
    tracks = await controller.process()
    
    # Print the output files
    for track in tracks:
        print(f"Final video: {track.final_video}")

# Run the async function
asyncio.run(generate_karaoke())
```

## Architecture

Karaoke Gen has a modular architecture with the following components:

- **Controller**: Orchestrates the entire process
- **Services**: Handle specific aspects of the process
  - **Media Service**: Downloads and extracts media
  - **Audio Service**: Separates and processes audio
  - **Lyrics Service**: Fetches and synchronizes lyrics
  - **Video Service**: Renders video with synchronized lyrics
  - **Distribution Service**: Organizes and shares the output files
- **Utilities**: Common utility functions for file handling, logging, etc.

## Full Command Reference

For a complete list of options:

```bash
karaoke-gen --help
karaoke-bulk --help
```

## License

MIT
