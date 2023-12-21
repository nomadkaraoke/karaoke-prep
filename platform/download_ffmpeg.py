import requests


def download_file(url, filename):
    # Send a GET request to the URL
    response = requests.get(url, stream=True)

    # Check if the request was successful
    if response.status_code == 200:
        # Open a file with the specified filename in binary write mode
        with open(filename, "wb") as file:
            # Write the content of the response to the file
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print("Download completed.")
    else:
        print(f"Failed to download. Status code: {response.status_code}")


# URL of the file to be downloaded
url = "https://github.com/karaokenerds/karaoke-prep/releases/download/v0.8.3/ffmpeg.exe"
# Filename to save the downloaded file
filename = "ffmpeg.exe"

# Call the function to download the file
download_file(url, filename)
