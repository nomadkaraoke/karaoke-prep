import logging
import yt_dlp.YoutubeDL as ydl

def extract_info_for_online_media(input_url, input_artist, input_title, logger):
    """Extracts metadata using yt-dlp, either from a URL or via search."""
    logger.info(f"Extracting info for input_url: {input_url} input_artist: {input_artist} input_title: {input_title}")
    extracted_info = None
    if input_url is not None:
        # If a URL is provided, use it to extract the metadata
        with ydl({"quiet": True}) as ydl_instance:
            extracted_info = ydl_instance.extract_info(input_url, download=False)
    else:
        # If no URL is provided, use the query to search for the top result
        ydl_opts = {"quiet": "True", "format": "bestaudio", "noplaylist": "True", "extract_flat": True}
        with ydl(ydl_opts) as ydl_instance:
            query = f"{input_artist} {input_title}"
            search_results = ydl_instance.extract_info(f"ytsearch1:{query}", download=False)
            if search_results and "entries" in search_results and search_results["entries"]:
                 extracted_info = search_results["entries"][0]
            else:
                # Raise IndexError to match the expected exception in tests
                raise IndexError(f"No search results found on YouTube for query: {input_artist} {input_title}")

    if not extracted_info:
         raise Exception(f"Failed to extract info for query: {input_artist} {input_title} or URL: {input_url}")

    return extracted_info


def parse_track_metadata(extracted_info, current_artist, current_title, persistent_artist, logger):
    """
    Parses extracted_info to determine URL, extractor, ID, artist, and title.
    Returns a dictionary with the parsed values.
    """
    parsed_data = {
        "url": None,
        "extractor": None,
        "media_id": None,
        "artist": current_artist,
        "title": current_title,
    }

    metadata_artist = ""
    metadata_title = ""

    if "url" in extracted_info:
        parsed_data["url"] = extracted_info["url"]
    elif "webpage_url" in extracted_info:
        parsed_data["url"] = extracted_info["webpage_url"]
    else:
        raise Exception(f"Failed to extract URL from input media metadata: {extracted_info}")

    if "extractor_key" in extracted_info:
        parsed_data["extractor"] = extracted_info["extractor_key"]
    elif "ie_key" in extracted_info:
        parsed_data["extractor"] = extracted_info["ie_key"]
    else:
        raise Exception(f"Failed to find extractor name from input media metadata: {extracted_info}")

    if "id" in extracted_info:
        parsed_data["media_id"] = extracted_info["id"]

    # Example: "Artist - Title"
    if "title" in extracted_info and "-" in extracted_info["title"]:
        try:
            metadata_artist, metadata_title = extracted_info["title"].split("-", 1)
            metadata_artist = metadata_artist.strip()
            metadata_title = metadata_title.strip()
        except ValueError:
             logger.warning(f"Could not split title '{extracted_info['title']}' on '-', using full title.")
             metadata_title = extracted_info["title"].strip()
             if "uploader" in extracted_info:
                 metadata_artist = extracted_info["uploader"]

    elif "uploader" in extracted_info:
        # Fallback to uploader as artist if title parsing fails
        metadata_artist = extracted_info["uploader"]
        if "title" in extracted_info:
            metadata_title = extracted_info["title"].strip()

    # If unable to parse, log an appropriate message
    if not metadata_artist or not metadata_title:
        logger.warning("Could not parse artist and title from the input media metadata.")

    if not parsed_data["artist"] and metadata_artist:
        logger.warning(f"Artist not provided as input, setting to {metadata_artist} from input media metadata...")
        parsed_data["artist"] = metadata_artist

    if not parsed_data["title"] and metadata_title:
        logger.warning(f"Title not provided as input, setting to {metadata_title} from input media metadata...")
        parsed_data["title"] = metadata_title

    if persistent_artist:
        logger.debug(
            f"Resetting artist from {parsed_data['artist']} to persistent artist: {persistent_artist} for consistency while processing playlist..."
        )
        parsed_data["artist"] = persistent_artist

    if parsed_data["artist"] and parsed_data["title"]:
        logger.info(f"Extracted url: {parsed_data['url']}, artist: {parsed_data['artist']}, title: {parsed_data['title']}")
    else:
        logger.debug(extracted_info)
        raise Exception("Failed to extract artist and title from the input media metadata.")

    return parsed_data
