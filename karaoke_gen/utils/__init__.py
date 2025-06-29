import re

def sanitize_filename(filename):
    """Replace or remove characters that are unsafe for filenames."""
    if filename is None:
        return None
    # Replace problematic characters with underscores
    for char in ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]:
        filename = filename.replace(char, "_")
    # Remove any trailing periods or spaces
    filename = filename.rstrip(". ") # Added period here as well
    # Remove any leading periods or spaces
    filename = filename.lstrip(". ")
    # Replace multiple underscores with a single one
    filename = re.sub(r'_+', '_', filename)
    # Replace multiple spaces with a single one
    filename = re.sub(r' +', ' ', filename)
    return filename
