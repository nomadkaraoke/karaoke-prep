This is a detailed, step-by-step plan for an IDE-based AI agent to refactor your `karaoke-gen` CLI tool into a multi-step, GPU-powered web application using Modal.

This plan prioritizes minimal refactoring of your core generation logic and focuses on wrapping it in the necessary Modal structure to achieve your goal.

-----

### **Objective:**

Transform the `karaoke-gen` Python CLI tool into a web-based solution hosted on Modal. The solution will feature a simple web interface for job submission and lyric review, with all heavy processing (audio separation, video rendering) handled by GPU-powered, serverless functions.

### **Core Principles:**

1.  **Isolate Core Logic:** Your existing processing functions are valuable. We will treat them as a library, changing as little as possible internally.
2.  **Embrace Asynchronicity:** Web requests must be fast. All long-running tasks will be "spawned" as background jobs on Modal, allowing the web UI to remain responsive.
3.  **Use Persistent Storage:** AI Models and job artifacts (audio, lyrics, videos) will be stored in a `modal.Volume` to persist them between function runs and share them across different steps.
4.  **Manage State:** The multi-step process (e.g., waiting for human lyric review) will be managed using a `modal.Dict` as a simple, serverless database to track the state of each job.

-----

### \#\# Phase 1: Setup and Initial Refactoring

**Goal:** Prepare the codebase and set up the basic Modal application structure.

**Instructions for the Agent:**

1.  **Install Modal:** Ensure the `modal` client is installed in the development environment. If not, run:

    ```bash
    pip install modal
    ```

2.  **Set Up Modal Token:** Authenticate with the Modal service by running the following command in the terminal. This will require a one-time browser login.

    ```bash
    modal setup
    ```

3.  **Create New Project Files:**

      * Create a new file named `app.py`. This will be the main entry point for our Modal application.
      * Create a file named `core.py`.

4.  **Isolate Core Logic:**

      * Move the primary processing functions from your `karaoke-gen` script into `core.py`. This includes functions for audio separation, lyrics fetching, transcription, and video generation.
      * Modify these functions to **remove all `print()` statements and `input()` prompts**. They should now accept all necessary information as function arguments and return results (like file paths or data structures) instead of printing to the console.

5.  **Create a Persistent Volume for Models:** In the project's root directory, run the following one-time command in your terminal. This creates a remote, persistent filesystem on Modal to store your large AI models so they aren't downloaded every single time.

    ```bash
    modal volume create karaoke-models
    ```

      * Next, upload your models to this volume. Create a temporary script called `upload_models.py`:
        ```python
        import modal

        volume = modal.Volume.from_name("karaoke-models")
        local_model_dir = "./path/to/your/models" # Change this path

        def upload():
            import os
            model_dest_dir = "/models"
            os.makedirs(model_dest_dir, exist_ok=True)
            for model_file in os.listdir(local_model_dir):
                source_path = os.path.join(local_model_dir, model_file)
                dest_path = os.path.join(model_dest_dir, model_file)
                with open(source_path, "rb") as f:
                    volume.write_file(dest_path, f.read())
                print(f"Uploaded {model_file}")
            volume.commit()

        if __name__ == "__main__":
            upload()
        ```
      * Run this script with `python upload_models.py`. After it completes, you can delete the script.

-----

### \#\# Phase 2: Create the Modal App and Worker Functions

**Goal:** Define the Modal application, its environment, and the GPU-powered functions that will execute the karaoke generation steps.

**Instructions for the Agent:**

1.  **Define the Modal App in `app.py`:**

      * At the top of `app.py`, define the basic app structure, including the custom Docker image, secrets, and volumes.

    <!-- end list -->

    ```python
    import modal
    import uuid
    from pathlib import Path

    # Define the environment for our functions
    karaoke_image = (
        modal.Image.debian_slim(python_version="3.10")
        .pip_install(
            "demucs", "youtube-dl", "pydub", "ffmpeg-python", "torch", "torchaudio",
            "requests", "genius", "faster-whisper", "numpy" # Add all your project's dependencies
        )
        .apt_install("ffmpeg")
    )

    # Define the Modal app
    app = modal.App("karaoke-generator-webapp")

    # Define persistent storage volumes
    model_volume = modal.Volume.from_name("karaoke-models", create_if_missing=True)
    output_volume = modal.Volume.from_name("karaoke-output", create_if_missing=True)

    # Define a serverless dictionary to hold job states
    job_status_dict = modal.Dict.from_name("karaoke-job-statuses", create_if_missing=True)

    # Mount volumes to a specific path inside the container
    VOLUME_CONFIG = {
        "/models": model_volume,
        "/output": output_volume
    }
    ```

2.  **Create the GPU Worker Function:**

      * In `app.py`, create a main processing function decorated with `@app.function`. This function will perform the first heavy step: audio separation and transcription.
      * This function must be *asynchronous* and should accept a unique `job_id` and the song details.

    <!-- end list -->

    ```python
    @app.function(
        image=karaoke_image,
        gpu="any", # Request any available GPU
        volumes=VOLUME_CONFIG,
        secrets=[modal.Secret.from_name("my-api-keys")], # Create this in the Modal UI for Genius/AudioShake/etc.
        timeout=1800 # 30 minutes
    )
    def process_part_one(job_id: str, youtube_url: str):
        from core import download_and_prep_audio, run_audio_separation, transcribe_lyrics

        job_status_dict[job_id] = {"status": "processing_audio", "progress": 10}
        
        # Paths inside the container
        output_dir = Path(f"/output/{job_id}")
        output_dir.mkdir(exist_ok=True)

        # 1. Download and Separate Audio
        original_audio_path = download_and_prep_audio(youtube_url, output_dir)
        instrumental_path, vocals_path = run_audio_separation(original_audio_path, "/models")
        
        job_status_dict[job_id] = {"status": "transcribing", "progress": 50}

        # 2. Transcribe
        transcription_data = transcribe_lyrics(vocals_path) # Assumes a function in core.py

        # 3. Save artifacts and update state
        output_volume.write_file(f"{job_id}/transcription_raw.json", transcription_data)
        output_volume.commit()
        
        job_status_dict[job_id] = {"status": "awaiting_review", "progress": 75}
        return "Awaiting lyric review."
    ```

3.  **Create the Finalization Function:**

      * Create a second function for the steps that happen *after* human review.

    <!-- end list -->

    ```python
    @app.function(
        image=karaoke_image,
        gpu="any", # Video rendering can also benefit from a GPU
        volumes=VOLUME_CONFIG,
        timeout=1800
    )
    def process_part_two(job_id: str):
        from core import generate_video_assets
        
        job_status_dict[job_id] = {"status": "rendering", "progress": 80}

        # Load corrected lyrics and instrumental from the volume
        corrected_lyrics = output_volume.read_file(f"{job_id}/lyrics_corrected.json")
        instrumental_path = f"/output/{job_id}/instrumental.wav"

        # Generate final video
        video_path = generate_video_assets(corrected_lyrics, instrumental_path)

        job_status_dict[job_id] = {"status": "complete", "progress": 100, "video_url": f"/output/{job_id}/final.mp4"}
        output_volume.commit()
        return "Job complete."
    ```

-----

### \#\# Phase 3: Build the Web Interface

**Goal:** Create API endpoints using Modal to submit jobs, check status, and handle the lyric review process.

**Instructions for the Agent:**

1.  **Create a FastAPI Web Endpoint:**

      * In `app.py`, we will create a web frontend using FastAPI, which is seamlessly integrated into Modal.

    <!-- end list -->

    ```python
    from fastapi import FastAPI, Request, Form
    from fastapi.responses import HTMLResponse, JSONResponse

    web_app = FastAPI()

    # Basic HTML for the UI
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head><title>Karaoke Gen</title></head>
    <body>
        <h1>Submit a new Karaoke Job</h1>
        <form action="/submit" method="post">
            <input type="text" name="url" placeholder="YouTube URL" size="50">
            <button type="submit">Generate</button>
        </form>
        <h2>Job Statuses</h2>
        <div id="jobs">Loading...</div>
        <script>
            async function updateJobs() {
                const response = await fetch('/jobs');
                const jobs = await response.json();
                const jobsDiv = document.getElementById('jobs');
                jobsDiv.innerHTML = '';
                for (const [job_id, data] of Object.entries(jobs)) {
                    jobsDiv.innerHTML += `<p><b>${job_id}</b>: ${data.status} (${data.progress}%)</p>`;
                    if (data.status === 'awaiting_review') {
                        jobsDiv.innerHTML += `<a href="/review/${job_id}" target="_blank">Review Lyrics</a>`;
                    }
                }
            }
            setInterval(updateJobs, 5000);
            updateJobs();
        </script>
    </body>
    </html>
    """

    @app.get("/", response_class=HTMLResponse)
    def home():
        return HTML_TEMPLATE

    @app.post("/submit")
    async def submit_job(url: str = Form(...)):
        job_id = str(uuid.uuid4())[:8]
        job_status_dict[job_id] = {"status": "queued", "progress": 0}
        
        # Spawn the long-running job in the background
        process_part_one.spawn(job_id, url)
        
        return JSONResponse({"status": "success", "job_id": job_id}, status_code=202)

    @app.get("/jobs")
    async def get_all_job_statuses():
        return dict(job_status_dict.items())

    # This is a placeholder for your React app.
    # For now, it's a simple form.
    @app.get("/review/{job_id}", response_class=HTMLResponse)
    async def review_lyrics_page(job_id: str):
        # In a real app, this would load data into your React component
        raw_lyrics = output_volume.read_file(f"{job_id}/transcription_raw.json").decode()
        return f"""
        <h1>Review Lyrics for {job_id}</h1>
        <form action="/review/{job_id}" method="post">
            <textarea name="lyrics" rows="20" cols="80">{raw_lyrics}</textarea><br>
            <button type="submit">Approve and Render Video</button>
        </form>
        """

    @app.post("/review/{job_id}")
    async def submit_review(job_id: str, lyrics: str = Form(...)):
        # Save the corrected lyrics
        output_volume.write_file(f"{job_id}/lyrics_corrected.json", lyrics.encode())
        output_volume.commit()
        
        # Spawn the second part of the job
        process_part_two.spawn(job_id)
        
        return JSONResponse({"status": "Final rendering started"}, status_code=202)
    ```

2.  **Mount the Web App:**

      * Finally, at the bottom of `app.py`, mount the FastAPI application to the Modal app.

    <!-- end list -->

    ```python
    @app.function()
    def web_endpoint():
        return web_app
    ```

-----

### \#\# Phase 4: Deployment and Iteration

**Goal:** Run the application locally for testing and deploy it for production access.

**Instructions for the Agent:**

1.  **Run for Development:** To test the application, run the following command in your terminal. This will create a temporary, live-reloading URL.

    ```bash
    modal serve app.py
    ```

      * You can now access the UI from the provided URL, submit jobs, and see the workflow in action. Check the logs in your terminal for debugging information from the worker functions.

2.  **Deploy for Production:** Once you are satisfied with the functionality, deploy it to a permanent URL.

    ```bash
    modal deploy app.py
    ```

      * Modal will provide a persistent URL for your web application. You can then point your `gen.nomadkaraoke.com` subdomain to this URL using a CNAME record in your DNS settings. Modal's documentation provides instructions for setting up custom domains.