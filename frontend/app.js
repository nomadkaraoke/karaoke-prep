// Configuration
const API_BASE_URL = 'https://nomadkaraoke--karaoke-generator-webapp-api-endpoint.modal.run/api';

// Global variables
let autoRefreshInterval;
let currentJobs = {};
let currentLogs = {};
let currentStats = {};

// DOM elements
const submitForm = document.getElementById('submitForm');
const audioFileInput = document.getElementById('audioFile');
const artistInput = document.getElementById('artistInput');
const titleInput = document.getElementById('titleInput');
const submitBtn = document.getElementById('submitBtn');
const submitStatus = document.getElementById('submitStatus');
const jobsContainer = document.getElementById('jobs');
const statsContainer = document.getElementById('stats');
const autoRefreshCheckbox = document.getElementById('autoRefresh');

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    console.log('🎤 Karaoke Generator Frontend Initialized');
    
    // Set up form submission
    submitForm.addEventListener('submit', handleSubmit);
    
    // Set up auto-refresh
    autoRefreshCheckbox.addEventListener('change', toggleAutoRefresh);
    
    // Initial data load
    refreshData();
    
    // Start auto-refresh if enabled
    if (autoRefreshCheckbox.checked) {
        startAutoRefresh();
    }
});

// Handle form submission
async function handleSubmit(event) {
    event.preventDefault();
    
    const audioFile = audioFileInput.files[0];
    const artist = artistInput.value.trim();
    const title = titleInput.value.trim();
    
    if (!audioFile) {
        showStatus('Please select an audio file', 'error');
        return;
    }
    
    if (!artist || !title) {
        showStatus('Please enter both artist name and song title', 'error');
        return;
    }
    
    if (!isValidAudioFile(audioFile)) {
        showStatus('Please select a valid audio file (MP3, WAV, FLAC, etc.)', 'error');
        return;
    }
    
    try {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Uploading...';
        showStatus('Uploading file and starting processing...', 'info');
        
        // Create FormData for file upload
        const formData = new FormData();
        formData.append('audio_file', audioFile);
        formData.append('artist', artist);
        formData.append('title', title);
        
        const response = await fetch(`${API_BASE_URL}/submit-file`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.status === 'success') {
            showStatus(`Job submitted successfully! Job ID: ${result.job_id}`, 'success');
            
            // Reset form
            audioFileInput.value = '';
            artistInput.value = '';
            titleInput.value = '';
            
            // Refresh data to show new job
            setTimeout(refreshData, 1000);
        } else {
            showStatus(result.message || 'Failed to submit job', 'error');
        }
        
    } catch (error) {
        console.error('Submit error:', error);
        showStatus(`Error: ${error.message}`, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '🎤 Generate Karaoke';
    }
}

// Refresh all data
async function refreshData() {
    console.log('🔄 Refreshing data...');
    
    try {
        // Fetch all data in parallel
        const [jobsResponse, logsResponse, statsResponse] = await Promise.all([
            fetch(`${API_BASE_URL}/jobs`).catch(err => ({ ok: false, error: err })),
            fetch(`${API_BASE_URL}/logs`).catch(err => ({ ok: false, error: err })),
            fetch(`${API_BASE_URL}/stats`).catch(err => ({ ok: false, error: err }))
        ]);
        
        // Process jobs
        if (jobsResponse.ok) {
            currentJobs = await jobsResponse.json();
        } else {
            console.warn('Failed to fetch jobs:', jobsResponse.error);
        }
        
        // Process logs
        if (logsResponse.ok) {
            currentLogs = await logsResponse.json();
        } else {
            console.warn('Failed to fetch logs:', logsResponse.error);
        }
        
        // Process stats
        if (statsResponse.ok) {
            currentStats = await statsResponse.json();
        } else {
            console.warn('Failed to fetch stats:', statsResponse.error);
        }
        
        // Update UI
        updateStatsDisplay();
        updateJobsDisplay();
        
    } catch (error) {
        console.error('Refresh error:', error);
        showStatus(`Error refreshing data: ${error.message}`, 'error');
    }
}

// Update statistics display
function updateStatsDisplay() {
    if (!currentStats || Object.keys(currentStats).length === 0) {
        statsContainer.innerHTML = '<div class="stat-card"><div class="stat-number">-</div><div>No stats available</div></div>';
        return;
    }
    
    const statsHTML = `
        <div class="stat-card">
            <div class="stat-number">${currentStats.total || 0}</div>
            <div>Total Jobs</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">${currentStats.processing || 0}</div>
            <div>Processing</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">${currentStats.awaiting_review || 0}</div>
            <div>Awaiting Review</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">${currentStats.complete || 0}</div>
            <div>Complete</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">${currentStats.error || 0}</div>
            <div>Errors</div>
        </div>
    `;
    
    statsContainer.innerHTML = statsHTML;
}

// Update jobs display
function updateJobsDisplay() {
    if (!currentJobs || Object.keys(currentJobs).length === 0) {
        jobsContainer.innerHTML = '<p>No jobs found. Submit a YouTube URL to get started!</p>';
        return;
    }
    
    const jobsHTML = Object.entries(currentJobs)
        .sort(([, a], [, b]) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
        .map(([jobId, job]) => createJobHTML(jobId, job))
        .join('');
    
    jobsContainer.innerHTML = jobsHTML;
}

// Create HTML for a single job
function createJobHTML(jobId, job) {
    const status = job.status || 'unknown';
    const progress = job.progress || 0;
    const createdAt = job.created_at ? new Date(job.created_at).toLocaleString() : 'Unknown';
    
    // Get logs for this job
    const jobLogs = currentLogs[jobId] || [];
    
    // Determine status class
    const statusClass = getStatusClass(status);
    
    // Create actions based on status
    const actions = createJobActions(jobId, job);
    
    // Create logs section
    const logsSection = createLogsSection(jobId, jobLogs);
    
    return `
        <div class="job ${statusClass}">
            <div class="job-header">
                <h4>🎵 Job ${jobId}</h4>
                <span class="timestamp">Created: ${createdAt}</span>
            </div>
            
            <div class="job-info">
                <p><strong>Status:</strong> ${formatStatus(status)}</p>
                ${job.url ? `<p><strong>URL:</strong> <a href="${job.url}" target="_blank">${job.url}</a></p>` : ''}
                ${job.error ? `<div class="error-details"><strong>Error:</strong><br>${job.error}</div>` : ''}
            </div>
            
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${progress}%"></div>
            </div>
            <div class="progress-text">${progress}%</div>
            
            ${actions}
            ${logsSection}
        </div>
    `;
}

// Get CSS class for job status
function getStatusClass(status) {
    const statusMap = {
        'queued': 'processing',
        'processing_audio': 'processing',
        'transcribing': 'processing',
        'awaiting_review': 'awaiting_review',
        'rendering': 'processing',
        'complete': 'complete',
        'error': 'error'
    };
    
    return statusMap[status] || 'processing';
}

// Format status for display
function formatStatus(status) {
    const statusMap = {
        'queued': '⏳ Queued',
        'processing_audio': '🎵 Processing Audio',
        'transcribing': '📝 Transcribing Lyrics',
        'awaiting_review': '👀 Awaiting Review',
        'rendering': '🎬 Rendering Video',
        'complete': '✅ Complete',
        'error': '❌ Error'
    };
    
    return statusMap[status] || `⚠️ ${status}`;
}

// Create job action buttons
function createJobActions(jobId, job) {
    const status = job.status || 'unknown';
    let actions = [];
    
    // Always show delete button
    actions.push(`<button onclick="deleteJob('${jobId}')" class="btn btn-danger">🗑️ Delete</button>`);
    
    // Status-specific actions
    if (status === 'awaiting_review') {
        actions.push(`<button onclick="reviewLyrics('${jobId}')" class="btn btn-success">📝 Review Lyrics</button>`);
    }
    
    if (status === 'complete' && job.video_url) {
        actions.push(`<button onclick="downloadVideo('${jobId}')" class="btn btn-success">📥 Download Video</button>`);
    }
    
    if (status === 'error') {
        actions.push(`<button onclick="retryJob('${jobId}')" class="btn">🔄 Retry</button>`);
    }
    
    // Toggle logs button
    actions.push(`<button onclick="toggleLogs('${jobId}')" class="toggle-details">📋 Toggle Logs</button>`);
    
    return `<div class="job-actions">${actions.join('')}</div>`;
}

// Create logs section
function createLogsSection(jobId, logs) {
    if (!logs || logs.length === 0) {
        return `<div id="logs-${jobId}" class="job-details hidden"><p>No logs available for this job.</p></div>`;
    }
    
    const logsHTML = logs.map(log => {
        const timestamp = new Date(log.timestamp).toLocaleTimeString();
        const levelClass = log.level.toLowerCase();
        
        return `<div class="log-entry ${levelClass}">
            <span class="timestamp">${timestamp}</span>
            <span class="log-message">${escapeHtml(log.message)}</span>
        </div>`;
    }).join('');
    
    return `<div id="logs-${jobId}" class="job-details hidden">${logsHTML}</div>`;
}

// Job action functions
async function deleteJob(jobId) {
    if (!confirm(`Are you sure you want to delete job ${jobId}?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showStatus(`Job ${jobId} deleted successfully`, 'success');
            refreshData();
        } else {
            throw new Error(`Failed to delete job: ${response.status}`);
        }
    } catch (error) {
        console.error('Delete error:', error);
        showStatus(`Error deleting job: ${error.message}`, 'error');
    }
}

async function reviewLyrics(jobId) {
    try {
        // Open lyrics review in a new window/tab
        const reviewUrl = `${API_BASE_URL}/review/${jobId}`;
        window.open(reviewUrl, '_blank');
        
        showStatus('Lyrics review page opened in new tab', 'info');
    } catch (error) {
        console.error('Review error:', error);
        showStatus(`Error opening review: ${error.message}`, 'error');
    }
}

async function retryJob(jobId) {
    try {
        const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/retry`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showStatus(`Job ${jobId} retry initiated`, 'success');
            refreshData();
        } else {
            throw new Error(`Failed to retry job: ${response.status}`);
        }
    } catch (error) {
        console.error('Retry error:', error);
        showStatus(`Error retrying job: ${error.message}`, 'error');
    }
}

async function downloadVideo(jobId) {
    try {
        const downloadUrl = `${API_BASE_URL}/jobs/${jobId}/download`;
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = `karaoke-${jobId}.mp4`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showStatus('Download started', 'success');
    } catch (error) {
        console.error('Download error:', error);
        showStatus(`Error downloading video: ${error.message}`, 'error');
    }
}

// Admin functions
async function clearErrorJobs() {
    if (!confirm('Are you sure you want to clear all error jobs?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/admin/clear-errors`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showStatus('Error jobs cleared successfully', 'success');
            refreshData();
        } else {
            throw new Error(`Failed to clear errors: ${response.status}`);
        }
    } catch (error) {
        console.error('Clear errors error:', error);
        showStatus(`Error clearing error jobs: ${error.message}`, 'error');
    }
}

async function exportLogs() {
    try {
        const response = await fetch(`${API_BASE_URL}/admin/export-logs`);
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `karaoke-logs-${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
            
            showStatus('Logs exported successfully', 'success');
        } else {
            throw new Error(`Failed to export logs: ${response.status}`);
        }
    } catch (error) {
        console.error('Export error:', error);
        showStatus(`Error exporting logs: ${error.message}`, 'error');
    }
}

// UI utility functions
function toggleLogs(jobId) {
    const logsElement = document.getElementById(`logs-${jobId}`);
    if (logsElement) {
        logsElement.classList.toggle('hidden');
    }
}

function toggleAutoRefresh() {
    if (autoRefreshCheckbox.checked) {
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
}

function startAutoRefresh() {
    stopAutoRefresh(); // Clear any existing interval
    autoRefreshInterval = setInterval(refreshData, 5000);
    console.log('Auto-refresh started (5s interval)');
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
        console.log('Auto-refresh stopped');
    }
}

function showStatus(message, type = 'info') {
    submitStatus.textContent = message;
    submitStatus.className = `status-message ${type}`;
    
    // Auto-clear success/info messages after 5 seconds
    if (type === 'success' || type === 'info') {
        setTimeout(() => {
            submitStatus.textContent = '';
            submitStatus.className = 'status-message';
        }, 5000);
    }
}

// Utility functions
function isValidAudioFile(file) {
    const validTypes = [
        'audio/mpeg',
        'audio/wav', 
        'audio/wave',
        'audio/x-wav',
        'audio/flac',
        'audio/x-flac',
        'audio/mp4',
        'audio/m4a',
        'audio/aac',
        'audio/ogg',
        'audio/webm'
    ];
    
    // Check MIME type
    if (validTypes.includes(file.type)) {
        return true;
    }
    
    // Also check file extension as fallback
    const fileName = file.name.toLowerCase();
    const validExtensions = ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.webm'];
    
    return validExtensions.some(ext => fileName.endsWith(ext));
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Error handling for unhandled promises
window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
    showStatus('An unexpected error occurred', 'error');
});

// Log when frontend is ready
console.log('🎤 Karaoke Generator Frontend Ready!'); 