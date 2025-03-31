# Karaoke Prep Functionality Map

This document maps the functionality in the original `old_prep.py` file, showing the line ranges for different functional components.

## Class Definition and Initialization
- **Class Definition**: Lines 25-1808
- **Constructor `__init__`**: Lines 26-306
  - Parameter initialization: Lines 26-91
  - Logger setup: Lines 92-123
  - Basic parameters: Lines 125-133
  - Audio processing parameters: Lines 135-141
  - Input/Output parameters: Lines 143-148
  - Lyrics parameters: Lines 150-160
  - Style parameters and loading: Lines 162-237
  - Title/End format setup: Lines 239-280
  - Video settings: Lines 282-286
  - FFmpeg configuration: Lines 288-296
  - Debug logging: Lines 298-302
  - Initialization of output directory: Lines 304-306

## Helper Methods
- **`parse_region`**: Lines 308-315 - Parses region string to tuple
- **`sanitize_filename`**: Lines 530-536 - Sanitizes filenames for safe use
- **`hex_to_rgb`**: Lines 1181-1184 - Converts hex color to RGB tuple
- **`_file_exists`**: Lines 1499-1505 - Checks if file exists and logs result
- **`_transform_text`**: Lines 1174-1181 - Transforms text based on specified type

## Media Information Extraction
- **`extract_info_for_online_media`**: Lines 317-330 - Extracts info from online media
- **`parse_single_track_metadata`**: Lines 332-382 - Parses metadata from extracted info

## Media Handling
- **`copy_input_media`**: Lines 384-401 - Copies local media file
- **`download_video`**: Lines 403-427 - Downloads video from URL
- **`extract_still_image_from_video`**: Lines 429-436 - Extracts still image from video
- **`convert_to_wav`**: Lines 438-462 - Converts media to WAV format

## Lyrics Processing
- **`find_best_split_point`**: Lines 464-497 - Finds optimal split points for long lines
- **`process_line`**: Lines 499-532 - Processes lyrics lines for optimal display
- **`transcribe_lyrics`**: Lines 538-637 - Handles lyrics transcription via external module
- **`backup_existing_outputs`**: Lines 538-599 - Backs up existing outputs to versioned folder

## Audio Separation
- **`separate_audio`**: Lines 601-653 - Separates audio using audio-separator
- **`process_audio_separation`**: Lines 1186-1311 - Main audio separation process
- **`_create_stems_directory`**: Lines 1313-1318 - Creates stems directory
- **`_separate_clean_instrumental`**: Lines 1320-1344 - Separates clean instrumental
- **`_separate_other_stems`**: Lines 1346-1379 - Separates other stems
- **`_separate_backing_vocals`**: Lines 1381-1405 - Separates backing vocals
- **`_generate_combined_instrumentals`**: Lines 1407-1429 - Combines instrumentals with backing vocals
- **`_normalize_audio_files`**: Lines 1431-1457 - Normalizes audio files
- **`_normalize_audio`**: Lines 1459-1497 - Performs audio normalization

## Output Path Handling
- **`setup_output_paths`**: Lines 655-677 - Sets up output paths for track

## Video and Image Generation
- **`_create_gradient_mask`**: Lines 679-718 - Creates gradient mask for text coloring
- **`calculate_text_size_to_fit`**: Lines 720-771 - Calculates text size to fit in region
- **`_render_text_in_region`**: Lines 773-876 - Renders text in specified region
- **`_draw_bounding_box`**: Lines 878-887 - Draws bounding box around region
- **`create_video`**: Lines 889-934 - Creates video with title, artist, and text
- **`_handle_existing_image`**: Lines 936-960 - Handles existing image for video
- **`_create_background`**: Lines 962-972 - Creates or loads background image
- **`_render_all_text`**: Lines 974-1000 - Renders all text elements on image
- **`_save_output_files`**: Lines 1002-1017 - Saves output image files and creates video
- **`_create_video_from_image`**: Lines 1019-1032 - Creates video from static image
- **`create_title_video`**: Lines 1133-1149 - Creates title video
- **`create_end_video`**: Lines 1151-1167 - Creates end video

## Main Processing Methods
- **`prep_single_track`**: Lines 1507-1661 - Prepares a single track
- **`shutdown`**: Lines 1663-1690 - Handles shutdown signals gracefully
- **`process_playlist`**: Lines 1692-1708 - Processes a playlist
- **`process_folder`**: Lines 1710-1748 - Processes a folder of audio files
- **`process`**: Lines 1750-1782 - Main entry point for processing

## Concurrency and Error Handling
- Signal handling in `prep_single_track`: Lines 1508-1510, 1655-1659
- Task management: Lines 1580-1606
- Exception handling: Throughout methods

## External Dependencies
- Media handling: yt-dlp.YoutubeDL
- Audio processing: audio_separator.separator
- Image processing: PIL (Image, ImageDraw, ImageFont)
- Lyrics transcription: lyrics_transcriber
- Audio manipulation: pydub.AudioSegment
- System utilities: os, sys, re, glob, logging, tempfile, shutil, asyncio, signal, time, fcntl, errno, psutil
- Others: dotenv, json, datetime 