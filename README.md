# Karaoke Prep 🎶

[![PyPI version](https://badge.fury.io/py/karaoke-prep.svg)](https://badge.fury.io/py/karaoke-prep)

Prepare for karaoke video creation, by downloading audio from YouTube and lyrics from Genius for a given song.

This was created to make it easier for me to prepare the source audio, lyrics and instrumental audio so I can then do the actual karaoke creation in focus mode without internet.

## Features

- Audio Fetching: Automatically downloads audio in WAV format for the YouTube URL provided (or searches for the song/artist name and fetches the top result).
- Lyrics Fetching: Automatically fetches song lyrics from Genius.com using [LyricsGenius](https://github.com/johnwmillr/LyricsGenius).
- Audio Separation: Separates the downloaded audio into instrumental and vocal tracks, using [audio-separator](https://github.com/karaokenerds/python-audio-separator/).
- Multiple Audio Models: Runs audio separation with 2 different models (by default, `UVR_MDXNET_KARA_2` and `UVR-MDX-NET-Inst_HQ_3`) to give you options for the backing track.
- Easy Configuration: Control the tool's behavior using command-line arguments.
- Organized Outputs: Creates structured output directories for easy access to generated tracks and lyrics.
- Internet First: Completes operations which require internet first, in case user is preparing last-minute before a period of being offline!

## Installation 🛠️

You can install Karaoke Prep using pip:

`pip install karaoke-prep`


## Usage 🚀

### Command Line Interface (CLI)

You can use Karaoke Prep via the command line:

```sh
usage: karaoke-prep [-h] [-v] [--log_level LOG_LEVEL] [--model_name MODEL_NAME] [--model_file_dir MODEL_FILE_DIR] [--output_dir OUTPUT_DIR] [--use_cuda] [--use_coreml]
                    [--denoise DENOISE] [--normalize NORMALIZE] [--create_track_subfolders]
                    [artist] [title] [url]

Fetch audio and lyrics for a specified song, to prepare karaoke video creation.

positional arguments:
  artist                           Artist name for the song to prep.
  title                            Title of the song to prep.
  url                              YouTube URL of the song to prep.

options:
  -h, --help                       show this help message and exit
  -v, --version                    show program's version number and exit
  --log_level LOG_LEVEL            Optional: logging level, e.g. info, debug, warning (default: info). Example: --log_level=debug
  --model_name MODEL_NAME          Optional: model name to be used for separation (default: UVR_MDXNET_KARA_2). Example: --model_name=UVR-MDX-NET-Inst_HQ_3
  --model_file_dir MODEL_FILE_DIR  Optional: model files directory (default: /tmp/audio-separator-models/). Example: --model_file_dir=/app/models
  --output_dir OUTPUT_DIR          Optional: directory to write output files (default: <current dir>). Example: --output_dir=/app/karaoke
  --use_cuda                       Optional: use Nvidia GPU with CUDA for separation (default: False). Example: --use_cuda=true
  --use_coreml                     Optional: use Apple Silicon GPU with CoreML for separation (default: False). Example: --use_coreml=true
  --denoise DENOISE                Optional: enable or disable denoising during separation (default: True). Example: --denoise=False
  --normalize NORMALIZE            Optional: enable or disable normalization during separation (default: True). Example: --normalize=False
  --create_track_subfolders        Optional: create subfolders in the output folder for each track (default: False). Example: --create_track_subfolders=true
  ```

  Example:

```
karaoke-prep "The Fray" "Never Say Never"
```

This command will search YouTube for the specified song, download audio from the top result and lyrics from genius, then separate the audio to produce an instrumental track, ready for a karaoke video to be created by whatever process you prefer!

By default, you'll end up with files in the current folder, neatly organised e.g.

```
├── Artist - Title (Instrumental UVR-MDX-NET-Inst_HQ_3).flac
├── Artist - Title (Instrumental UVR_MDXNET_KARA_2).flac
├── Artist - Title (Lyrics).txt
├── Artist - Title (Vocals UVR-MDX-NET-Inst_HQ_3).flac
├── Artist - Title (Vocals UVR_MDXNET_KARA_2).flac
└── Artist - Title (YouTube CNUgemJBLTw).wav
```

## Requirements 📋

Python >= 3.9

Libraries: onnx, onnxruntime, numpy, soundfile, librosa, torch, wget, six

## Developing Locally

This project uses Poetry for dependency management and packaging. Follow these steps to setup a local development environment:

### Prerequisites

- Make sure you have Python 3.9 or newer installed on your machine.
- Install Poetry by following the installation guide here.

### Clone the Repository

Clone the repository to your local machine:

```
git clone https://github.com/YOUR_USERNAME/karaoke-prep.git
cd karaoke-prep
```

Replace YOUR_USERNAME with your GitHub username if you've forked the repository, or use the main repository URL if you have the permissions.

### Install Dependencies

Run the following command to install the project dependencies:

```
poetry install
```

### Activate the Virtual Environment

To activate the virtual environment, use the following command:

```
poetry shell
```

### Running the Command-Line Interface Locally

You can run the CLI command directly within the virtual environment. For example:

```
karaoke-prep 1
```

### Deactivate the Virtual Environment

Once you are done with your development work, you can exit the virtual environment by simply typing:

```
exit
```

### Building the Package

To build the package for distribution, use the following command:

```
poetry build
```

This will generate the distribution packages in the dist directory - but for now only @beveradb will be able to publish to PyPI.

## Contributing 🤝

Contributions are very much welcome! Please fork the repository and submit a pull request with your changes, and I'll try to review, merge and publish promptly!

- This project is 100% open-source and free for anyone to use and modify as they wish. 
- If the maintenance workload for this repo somehow becomes too much for me I'll ask for volunteers to share maintainership of the repo, though I don't think that is very likely

## License 📄

This project is licensed under the MIT [License](LICENSE).

- **Please Note:** If you choose to integrate this project into some other project using the default model or any other model trained as part of the [UVR](https://github.com/Anjok07/ultimatevocalremovergui) project, please honor the MIT license by providing credit to UVR and its developers!

## Credits 🙏

- [Anjok07](https://github.com/Anjok07) - Author of [Ultimate Vocal Remover GUI](https://github.com/Anjok07/ultimatevocalremovergui), which was essential for the creation of [audio-separator](https://github.com/karaokenerds/python-audio-separator/)! Thank you!

## Contact 💌

For questions or feedback, please raise an issue or reach out to @beveradb ([Andrew Beveridge](mailto:andrew@beveridge.uk)) directly.
