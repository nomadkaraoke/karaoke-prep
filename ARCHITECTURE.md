# Karaoke Generator - Technical Architecture Overview

## Core Functionality

The Karaoke Generator is a comprehensive pipeline that transforms audio files (local files or YouTube URLs) into professional karaoke videos with synchronized lyrics. It handles the complete workflow from raw audio input to final deliverable files.

## Main Processing Pipeline

### 1. **Input Processing**
- **Input Sources**: Local audio files (FLAC, WAV, MP3) or YouTube URLs
- **Metadata**: Artist name and song title (can search YouTube if URL not provided)
- **File Handling**: Converts input media to WAV format for processing

### 2. **Parallel Processing Phase**
The tool runs two major operations concurrently:

#### **Audio Separation** (Compute-Intensive)
- **Models Used**: Multiple AI models for different separation tasks:
  - `model_bs_roformer_ep_317_sdr_12.9755.ckpt` (clean instrumental)
  - `htdemucs_6s.yaml` (6-stem separation)
  - `mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt` (backing vocals)
- **Hardware Requirements**: 
  - GPU acceleration preferred (uses Apple Silicon MPS, CUDA, or CPU fallback)
  - Significant processing time (12+ minutes for a ~5-minute song)
  - Large model files (requires dedicated model storage directory)
- **Output**: Multiple stems (vocals, instrumental, backing vocals, drums, bass, etc.)

#### **Lyrics Processing**
- **Lyrics Fetching**: Genius API integration for lyric retrieval
- **Transcription**: AudioShake API for timing synchronization
- **Correction**: AI-powered lyrics correction using reference sources
- **Processing Time**: ~5-6 minutes for transcription + correction

### 3. **Human Review Phase** (Interactive)
- **Web Interface**: React-based web UI launches in browser
- **Functionality**: Users review and correct automatically transcribed lyrics
- **Timing**: Allows fine-tuning of lyric timing and text accuracy
- **Critical Dependency**: Requires human interaction - cannot be fully automated

### 4. **Output Generation**
Creates multiple synchronized lyric formats:
- **LRC files** (timed lyrics for media players)
- **CDG files** (CD+Graphics karaoke format)
- **ASS/SSA files** (Advanced SubStation Alpha for video)
- **Plain text files** (reference versions)
- **Video files** with lyric overlays

### 5. **Video Production**
- **Title/End Screens**: Generated with custom branding and styling
- **Video Composition**: Combines title + karaoke content + end screen
- **Multiple Formats**:
  - 4K lossless (PCM audio)
  - 4K lossy (AAC audio)  
  - 720p compressed
  - MKV with FLAC audio (YouTube optimized)

## External API Dependencies

### **Required APIs**
1. **AudioShake API**: Core dependency for lyrics transcription/timing
   - Upload audio files (can be large - 280+ seconds in example)
   - Wait for processing completion
   - Retrieve timed transcription data

2. **Genius API**: Lyrics text retrieval
   - Search by artist/title
   - Fetch reference lyrics text

3. **YouTube Data API v3**: Video management
   - Upload videos
   - Set thumbnails
   - Check for existing videos

### **Optional Integrations**
- **Discord Webhooks**: Completion notifications
- **Email APIs**: Draft creation for delivery notifications
- **Rclone**: Cloud storage synchronization (Google Drive, Dropbox)

## User Interaction Points

### **Critical Interactive Elements**
1. **Instrumental Selection**: 
   - Terminal-based choice between separation models
   - Presents numbered options (e.g., "Choose instrumental audio file: [1]/2")
   - Requires user input to proceed

2. **Human Review Interface**:
   - Launches React web application
   - Browser-based editing of transcribed lyrics
   - Users can modify text and timing
   - Must submit reviewed data to continue processing

3. **Confirmation Prompts**:
   - Feature confirmation before finalization
   - Video quality check before proceeding
   - Manual approval gates throughout process

## Computing Requirements

### **Hardware Needs**
- **GPU/Accelerated Processing**: 
  - NVIDIA CUDA (preferred)
  - Apple Silicon MPS (Metal Performance Shaders)
  - CPU fallback available but significantly slower
- **Storage**: 
  - Large model files (multiple GB)
  - Temporary processing files during separation
  - Final output files (videos can be several GB each)
- **Memory**: Significant RAM for audio processing (8GB+ recommended)
- **CPU**: Multi-core processing for parallel operations

### **Processing Time Estimates**
Based on a ~5-minute song:
- Audio separation: ~15 minutes (GPU) / 45+ minutes (CPU)
- Lyrics transcription: ~5 minutes (API dependent)
- Human review: ~5-15 minutes (user-dependent)
- Video encoding: ~7 minutes
- Upload/organization: ~5 minutes
- **Total**: 32-47 minutes per track

### **External Dependencies**
- **FFmpeg**: Video/audio processing and encoding
- **Python 3.10+**: Runtime environment
- **PyTorch**: AI model execution framework
- **Audio Processing Libraries**: librosa, soundfile, pydub
- **Web Framework**: For human review interface
- **Rclone**: Cloud storage synchronization (optional)

## File Input/Output Structure

### **Input Files**
- **Audio Sources**: Any FFmpeg-supported format (FLAC, WAV, MP3, etc.)
- **Configuration**: 
  - Style parameters JSON (branding, colors, fonts)
  - YouTube credentials and templates
  - Email templates
- **Assets**: 
  - Background images for title/end screens
  - Custom fonts
  - Branding elements

### **Working Directory Structure**
```
Artist - Song Title/
├── Artist - Song Title (Original).wav          # Converted input
├── Artist - Song Title (Title).mov             # Generated title screen
├── Artist - Song Title (End).mov               # Generated end screen
├── Artist - Song Title (With Vocals).mkv       # Karaoke video with vocals
├── Artist - Song Title (Karaoke).lrc           # Timed lyrics
├── stems/                                       # Audio separation outputs
│   ├── Artist - Song Title (Vocals ...).flac
│   ├── Artist - Song Title (Drums ...).flac
│   └── ...
└── lyrics/                                      # Lyrics processing files
    ├── Artist - Song Title (Lyrics Genius).txt
    ├── Artist - Song Title (Lyrics Corrected).txt
    ├── Artist - Song Title (Karaoke).cdg
    └── ...
```

### **Final Output Files**
- **Video Formats**: 
  - 4K lossless MP4 (PCM audio)
  - 4K lossy MP4 (AAC audio)
  - 720p MP4 (compressed for sharing)
  - MKV with FLAC audio (YouTube optimized)
- **Karaoke Packages**:
  - CDG+MP3 ZIP (CD+Graphics format)
  - TXT+MP3 ZIP (text-based karaoke)
- **Individual Formats**: LRC, CDG, ASS subtitle files

### **Organization System**
- **Brand-coded directories**: `BRAND-####` sequence numbering
- **Automated file organization** to configured paths
- **Public sharing directory** with cloud synchronization
- **Multi-location backup** integration

## Current Architecture Limitations for Cloud Deployment

The tool currently assumes:

### **Local System Dependencies**
- Local file system access for model storage and temporary files
- Terminal-based user interaction for choices and confirmations
- Browser access on same machine for web UI components
- Local application launching (e.g., Audacity integration)
- Direct file system paths for organization and sharing

### **Interactive Elements**
- Terminal prompts requiring keyboard input
- Web browser launching on local machine
- File system browsing for path selection
- Manual approval gates that pause execution

### **Resource Management**
- Static model file paths
- Local GPU/hardware detection and usage
- Temporary file cleanup assumes local storage
- Process management tied to single-machine execution

## Cloud Deployment Challenges

Key architectural changes needed for cloud deployment:

1. **User Interface Migration**
   - Replace terminal interactions with web-based interfaces
   - Implement session management for multi-step workflows
   - Handle asynchronous processing with status updates

2. **Resource Management**
   - Dynamic GPU allocation and queuing
   - Distributed model file storage and caching
   - Scalable temporary storage management
   - Container orchestration for processing jobs

3. **Interactive Workflow Adaptation**
   - Web-based instrumental selection interface
   - Embedded lyrics review interface
   - Progress tracking and resumable workflows
   - Real-time collaboration features

4. **File Management**
   - Cloud storage integration for inputs/outputs
   - Streaming upload/download for large files
   - Multi-tenant file isolation
   - Automated cleanup and retention policies

5. **API Integration Scaling**
   - Rate limiting and quota management
   - API key rotation and security
   - Fallback providers for critical services
   - Cost optimization for external API usage

This architecture provides a foundation for understanding the current system's capabilities and the considerations needed for cloud deployment transformation. 


## Approach 1: The Managed Platform (Easier Start)

This approach uses "Platform as a Service" (PaaS) providers that specialize in running containerized applications and backend tasks, including those requiring GPUs. This abstracts away much of the server management.

A great fit for this would be Modal. It's designed almost exactly for your use case: turning Python scripts into serverless functions that can be called via an API and can have GPUs attached.

How it would work with Modal:

    Refactor karaoke-gen: You'd wrap your core processing logic in functions within a Modal script. You would use decorators to specify requirements like the GPU type (@modal.function(gpu="any")), secrets (API keys), and shared storage for your models.

    Web Frontend: You could build a simple web app using Flask or FastAPI that also runs on Modal. This app would serve your HTML/React interface.

    Job Submission: When you hit "Generate" in the web app, it calls your Modal GPU function asynchronously (my_gpu_function.spawn(...)). This immediately returns a job ID.

    State Management: The worker function updates its status in a shared dictionary or a simple database. The web app can have an endpoint that you poll from the frontend to check on the job's progress.

    Lyric Review: When the job reaches the AWAITING_REVIEW state, it saves the transcribed lyrics to storage. The web app loads this data into your React editor. When you submit your corrections, it saves the updated data and triggers the next part of the Modal function to resume the job.

Technology Stack:

    Backend/Worker: Python on Modal

    Web Framework: Flask or FastAPI (also on Modal)

    Frontend: Your existing React app, served by the web framework.

    Storage: Modal's Network File System for models and temporary files.

Pros & Cons:

    ✅ Fastest to implement: Drastically reduces infrastructure setup.

    ✅ Cost-effective for sporadic use: You only pay for the GPU while it's actively processing a job.

    ❌ Less control: You're dependent on the Modal platform's features and pricing.