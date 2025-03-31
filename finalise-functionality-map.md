# Pre-Refactor Finalise Functionality Map

This document maps the functionality in the original `old_finalise.py` file, organized by major functional areas with specific line ranges.

## Class Definition and Initialization

- **Class Definition**: Lines 23-23
- **Initialization and Configuration**: Lines 23-140
  - Logging setup: Lines 46-64
  - FFmpeg path and command setup: Lines 67-77
  - Configuration parameters: Lines 79-107
  - Feature flags: Lines 109-114
  - File naming conventions: Lines 116-137
  - Codec detection: Line 129

## Configuration and Validation

- **Input Files Validation**: Lines 142-171
- **Output Filenames Preparation**: Lines 173-187
- **User Interaction Utilities**: Lines 189-210
- **Feature Validation**: Lines 212-271

## YouTube Integration

- **YouTube Authentication**: Lines 273-292
- **YouTube Channel ID Retrieval**: Lines 294-305
- **Video Existence Check**: Lines 307-345
- **Video Deletion**: Lines 347-364
- **Title Handling**: Lines 366-371
- **Video Upload**: Lines 373-434

## Folder Organization and Branding

- **Brand Code Generation**: Lines 436-454
- **Discord Notifications**: Lines 456-460
- **File Organization**: Lines 589-607
- **Public Share Directory Management**: Lines 609-652
- **Remote Sync (rclone)**: Lines 654-668
- **Sharing Link Generation**: Lines 682-702
- **Existing Brand Code Extraction**: Lines 704-715

## File Discovery and Processing

- **With Vocals File Finding**: Lines 462-502
- **Instrumental Audio Selection**: Lines 504-562
- **Artist and Title Extraction**: Lines 564-587

## Video Processing (FFmpeg Operations)

- **Command Execution Wrapper**: Lines 589-596
- **Video Remuxing with Instrumental Audio**: Lines 598-606
- **MOV to MP4 Conversion**: Lines 608-616
- **Lossless MP4 Encoding**: Lines 618-629
- **Lossy MP4 Encoding**: Lines 631-639
- **MKV Encoding**: Lines 641-649
- **720p Version Encoding**: Lines 651-661
- **Concatenation Filter Preparation**: Lines 663-675
- **Final Video File Creation**: Lines 677-716

## CDG/TXT Creation (Karaoke File Formats)

- **CDG ZIP File Creation**: Lines 718-783
- **TXT ZIP File Creation**: Lines 785-816

## Distribution and Notifications

- **Discord Notification Posting**: Lines 670-680
- **Email Integration**: Lines 738-809
  - Gmail Authentication: Lines 738-757
  - Email Draft Creation: Lines 759-783
  - Email Template Testing: Lines 785-797

## Codec Detection

- **AAC Codec Detection**: Lines 799-813

## Main Processing Flow

- **Process Method (Main Workflow)**: Lines 815-886
  - Feature validation: Line 821
  - File discovery: Lines 823-827
  - Output preparation: Lines 829-830
  - CDG/TXT creation: Lines 832-835
  - Video processing: Line 837
  - Optional features execution: Line 839
  - Result compilation: Lines 841-861
  - Email notification: Line 863 