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
- Flexible Input: provide just a YouTube URL, just an artist and title, or both.
- Playlist Processing: Capable of processing an entire YouTube playlist, extracting audio and lyrics for each track.
- Easy Finalisation: After manually performing your sync (e.g. using [MidiCo](https://www.midicokaraoke.com)), run `karaoke-finalise` to remux and add your title screen!

## Installation 🛠️

You'll need Python version 3.9, 3.10 or 3.11 (newer versions aren't supported by PyTorch or ONNX Runtime yet).

### Windows Prerequisites
- [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
- [FFmpeg](https://ffmpeg.org/download.html)

You can install Karaoke Prep using pip:

`pip install karaoke-prep`

You'll then also need to install a version of `audio-separator` for your hardware:

- Mac with Apple Silicon: `pip install audio-separator[silicon]`
- Linux/Windows with CUDA GPU: `pip install audio-separator[gpu]`
- Anything else: `pip install audio-separator[cpu]`

#### Install PyTorch with CUDA support

If you're trying to use CUDA for GPU acceleration, you'll also need to ensure the version of PyTorch you have installed is compatible with the CUDA version you have installed.

While PyTorch should get installed as a dependency of `karaoke-prep` anyway, you may need to install PyTorch for your CUDA version by running the installation command provided by the official install wizard: https://pytorch.org/get-started/locally/ 

#### UnicodeEncodeError

If you encounter this error: `UnicodeEncodeError: 'charmap' codec can't encode character`

Try setting the Python I/O encoding in your environment: `export PYTHONIOENCODING=utf-8`

#### Command-line newbie?

If you aren't sure what `pip` is or how to use the command line, here are some YouTube tutorials which will probably help:

- Install Python on Windows: https://www.youtube.com/watch?v=YKSpANU8jPE
- Command Line basics Windows: https://www.youtube.com/watch?v=MBBWVgE0ewk
- Install Python on Mac: https://www.youtube.com/watch?v=3-sPfR4JEQ8
- Command Line basics Mac: https://www.youtube.com/watch?v=FfT8OfMpARM

## Karaoke production guide using karaoke-prep and MidiCo

- Get a Genius API Access Token ([docs](https://docs.genius.com/)) and set it as an environment variable named `GENIUS_API_TOKEN`
- Run `karaoke-prep <Artist> <Title>` to fetch and prep the files above
- Wait for it to output at least the WAV file and lyrics (you can leave it running in the background while you sync)
- Open the WAV file in MidiCo: `(YouTube xxxxxxxxxxx).wav`
- Copy/paste the lyrics into MidiCo: `(Lyrics Processed).txt`
- Perform the lyrics sync (here's a [video](https://www.youtube.com/watch?v=63-Fk3mfZ7Q) showing me doing it) in MidiCo
- Render the video to 4k using the MidiCo "Export Movie" feature, saving it as `Artist - Title (Karaoke).mov` in the same folder
- Run `karaoke-finalise` to remux the instrumental audio and join the title clip to the start
- Upload the resulting `Artist - Title (Final Karaoke).mp4` video to YouTube!

Here's my [tutorial video with verbal explanation](https://www.youtube.com/watch?v=ZsROHgqAVHs) of the whole process, and here's a [normal speed demo](https://www.youtube.com/watch?v=63-Fk3mfZ7Q) of me doing it (8 minutes total for a single track).


## Usage 🚀

### Command Line Interface (CLI)

You can use Karaoke Prep via the command line:

```sh
usage: karaoke-prep [-h] [-v] [--log_level LOG_LEVEL] [--model_name MODEL_NAME] [--model_file_dir MODEL_FILE_DIR] [--output_dir OUTPUT_DIR] [--use_cuda] [--use_coreml]
                    [--denoise DENOISE] [--normalize NORMALIZE] [--create_track_subfolders]
                    [artist] [title] [url]

Fetch audio and lyrics for a specified song, to prepare karaoke video creation.

positional arguments:
  args                             [YouTube video or playlist URL] [Artist] [Title] of song to prep. If URL is provided, Artist and Title are optional but increase chance of fetching the correct lyrics. If Artist and Title are provided with no URL, the top YouTube search result will be fetched.

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
  --no_track_subfolders                            Optional: do NOT create a named subfolder for each track. Example: --no_track_subfolders
  --intro_background_color INTRO_BACKGROUND_COLOR  Optional: Background color for intro video (default: black). Example: --intro_background_color=#123456
  --intro_background_image INTRO_BACKGROUND_IMAGE  Optional: Path to background image for intro video. Overrides background color if provided. Example: --intro_background_image=path/to/image.jpg
  --intro_font INTRO_FONT                          Optional: Font file for intro video (default: Avenir-Next-Bold). Example: --intro_font=AvenirNext-Bold.ttf
  --intro_artist_color INTRO_ARTIST_COLOR          Optional: Font color for intro video artist text (default: #ff7acc). Example: --intro_artist_color=#123456
  --intro_title_color INTRO_TITLE_COLOR            Optional: Font color for intro video title text (default: #ffdf6b). Example: --intro_title_color=#123456
  ```


### ⭐ YouTube URL with Artist and Title

For the most consistent results, provide a specific YouTube URL along with the artist and title like so:

```
karaoke-prep "https://www.youtube.com/watch?v=YOUR_VIDEO_ID" "The Fray" "Never Say Never"
```

### Artist and Title Only

If you don't have a specific YouTube URL, just provide the artist and title. Karaoke Prep will search for and download the top YouTube result.

```
karaoke-prep "The Fray" "Never Say Never"
```

### Only YouTube URL

This will process the video at the given URL, *guessing the artist and title from the YouTube title*.
⚠️ Be aware the downloaded lyrics may be incorrect if the video title doesn't match the standard "Artist - Title" format.

```
karaoke-prep "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
```

### YouTube Playlist URL

To process a playlist, just provide the playlist URL. The script will process every video in the playlist.
⚠️ Be aware the downloaded _lyrics_ for each track may be incorrect if the video titles don't match the standard "Artist - Title" format.

```
karaoke-prep "https://www.youtube.com/playlist?list=YOUR_PLAYLIST_ID"
```

## Files produced by karaoke-prep and what to do with them

After running `karaoke-prep` you should have the following 11 files, grouped into folder(s) for each track:

- `Artist - Title (YouTube xxxxxxxxxxx).webm`
  - Original unmodified video, fetched from YouTube in the highest quality available (may not always be WebM)
  - You probably don't need this unless you're creating a custom request
- `Artist - Title (YouTube xxxxxxxxxxx).png`
  - A still image taken from 30 seconds into the video, in case that's useful for a custom background
  - You probably don't need this unless you're creating a custom request
- `Artist - Title (YouTube xxxxxxxxxxx).wav`
  - Unmodified audio from the YouTube video, converted to WAV format for compatibility
  - You should open this in MidiCo to begin syncing lyrics to make your karaoke video.
- `Artist - Title (Lyrics).txt`
  - Unmodified lyrics fetched from genius.com based on the artist/title provided
  - Depending on the song, may have lines which are too long for one karaoke screen
- `Artist - Title (Lyrics Processed).txt`
  - Lyrics from genius, split into lines no longer than 40 characters
  - You should open this and copy/paste the text into the MidiCo lyrics editor
- `Artist - Title (Vocals UVR-MDX-NET-Inst_HQ_3).mp3`
  - Vocal track from the audio, separated using the UVR Inst_HQ_3 model.
  - You probably don't need this unless you're trying to tweak the backing track
- `Artist - Title (Vocals UVR_MDXNET_KARA_2).mp3`
  - Vocal track from the audio, separated using the UVR KARA_2 model.
  - You probably don't need this unless you're trying to tweak the backing track
- `Artist - Title (Instrumental UVR-MDX-NET-Inst_HQ_3).mp3`
  - Instrumental track from the audio, separated using the UVR Inst_HQ_3 model.
  - This is typically a safe bet for the instrumental track but will not include any backing vocals.
- `Artist - Title (Instrumental UVR_MDXNET_KARA_2).mp3`
  - Instrumental track from the audio, separated using the UVR KARA_2 model.
  - This is the default choice for the finalisation step below as it usually does a good job of keeping backing vocals. However for some songs it includes far too much or is kinda glitchy, so you should check it before finalising and make a judgement call about using this vs. the Inst_HQ_3 one.
- `Artist - Title (Title).png`
  - Title screen static image; if you specify your own background image, font, color etc. this should give you a convenient way to add a title screen to the start of your video.
- `Artist - Title (Title).mov`
  - 5 second video clip version of the title screen image, ready to be joined by the finalisation step.


## Finalisation 🎥

After completing your manual sync process and rendering your `Artist - Title (Karaoke).mov` file (still using the original audio!) into the same folder, you can now run `karaoke-finalise`.

This will output some additional files:
- `Artist - Title (Karaoke).mov`
  - Karaoke video without title screen, remuxed to use the instrumental audio
- `Artist - Title (With Vocals).mov`
  - Karaoke video without title screen, using the original audio (useful for practicing!)
- `Artist - Title (Final Karaoke).mp4`
  - Final karaoke video with 5 second title screen intro, instrumental audio and converted to MP4 for compatibility and reduced file size. Upload this to YouTube!


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
