// Configuration
const API_BASE_URL = 'https://nomadkaraoke--karaoke-generator-webapp-api-endpoint.modal.run/api';

// Global state
let autoRefreshInterval = null;
let logTailInterval = null;
let currentTailJobId = null;
let logFontSizeIndex = 2; // Default to 'font-md'
let autoScrollEnabled = true;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    loadJobs();
    
    // Auto-refresh checkbox handler
    const autoRefreshCheckbox = document.getElementById('auto-refresh');
    if (autoRefreshCheckbox) {
        autoRefreshCheckbox.addEventListener('change', function() {
            if (this.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });
    }
    
    // Handle form submission
    const jobForm = document.getElementById('job-form');
    if (jobForm) {
        jobForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitJob();
        });
    }
    
    // Handle modal close on outside click
    const modal = document.getElementById('log-tail-modal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeLogTailModal();
            }
        });
    }
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Escape key closes modal
        if (e.key === 'Escape') {
            closeLogTailModal();
        }
    });
});

function startAutoRefresh() {
    if (autoRefreshInterval) return; // Already running
    
    autoRefreshInterval = setInterval(() => {
        // Only refresh if not tailing logs (to avoid conflicts)
        if (!currentTailJobId) {
            loadJobsWithoutScroll();
        }
    }, 5000); // 5 second refresh
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

function loadJobsWithoutScroll() {
    // Store current scroll position
    const currentScrollY = window.scrollY;
    const currentScrollX = window.scrollX;
    
    loadJobs().then(() => {
        // Restore scroll position after update
        window.scrollTo(currentScrollX, currentScrollY);
    });
}

async function loadJobs() {
    try {
        const response = await fetch(`${API_BASE_URL}/jobs`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const jobs = await response.json();
        
        updateJobsList(jobs);
        updateStats(jobs);
        
        return jobs; // Return jobs for further use
        
    } catch (error) {
        console.error('Error loading jobs:', error);
        showError('Failed to load jobs: ' + error.message);
        return null;
    }
}

function updateJobsList(jobs) {
    const jobsList = document.getElementById('jobs-list');
    if (!jobsList) return;
    
    // Store currently expanded job details to preserve state
    const expandedJobs = new Set();
    document.querySelectorAll('.job-details.show').forEach(detail => {
        const jobId = detail.closest('.job').dataset.jobId;
        if (jobId) expandedJobs.add(jobId);
    });
    
    if (Object.keys(jobs).length === 0) {
        jobsList.innerHTML = '<p class="no-jobs">No jobs found. Submit a job above to get started!</p>';
        return;
    }
    
    const sortedJobs = Object.entries(jobs).sort((a, b) => {
        const timeA = new Date(a[1].created_at || 0);
        const timeB = new Date(b[1].created_at || 0);
        return timeB - timeA; // Most recent first
    });
    
    jobsList.innerHTML = sortedJobs.map(([jobId, job]) => {
        const expandedClass = expandedJobs.has(jobId) ? 'show' : '';
        return createJobHTML(jobId, job, expandedClass);
    }).join('');
}

function updateStats(jobs) {
    const stats = {
        total: 0,
        processing: 0,
        awaiting_review: 0,
        complete: 0,
        error: 0
    };
    
    Object.values(jobs).forEach(job => {
        stats.total++;
        const status = job.status || 'unknown';
        if (['queued', 'processing_audio', 'transcribing', 'rendering'].includes(status)) {
            stats.processing++;
        } else if (status === 'awaiting_review') {
            stats.awaiting_review++;
        } else if (status === 'complete') {
            stats.complete++;
        } else if (status === 'error') {
            stats.error++;
        }
    });
    
    // Update stat cards
    document.getElementById('stat-total').textContent = stats.total;
    document.getElementById('stat-processing').textContent = stats.processing;
    document.getElementById('stat-awaiting-review').textContent = stats.awaiting_review;
    document.getElementById('stat-complete').textContent = stats.complete;
    document.getElementById('stat-errors').textContent = stats.error;
}

function createJobHTML(jobId, job, expandedClass = '') {
    const status = job.status || 'unknown';
    const progress = job.progress || 0;
    const timestamp = job.created_at ? formatTimestamp(job.created_at) : 'Unknown';
    
    // Format track info for display
    const trackInfo = (job.artist && job.title) 
        ? `${job.artist} - ${job.title}` 
        : (job.url ? 'URL Processing' : 'Unknown Track');
    
    return `
        <div class="job" data-job-id="${jobId}">
            <div class="job-header" onclick="toggleJobDetails('${jobId}')">
                <div class="job-main-info">
                    <div class="job-title">
                        <div class="job-id-row">
                            <span class="job-id">🎵 Job ${jobId}</span>
                            <span class="job-timestamp">${timestamp}</span>
                        </div>
                        <div class="job-track-info">
                            <span class="track-name">${trackInfo}</span>
                        </div>
                    </div>
                    <div class="job-progress">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${progress}%"></div>
                        </div>
                        <span class="progress-text">${progress}%</span>
                    </div>
                </div>
                <div class="job-status">
                    <span class="status-badge status-${status}">${formatStatus(status)}</span>
                    <span class="toggle-icon">▼</span>
                </div>
            </div>
            
            <div class="job-details ${expandedClass}" id="details-${jobId}">
                <div class="job-info">
                    <p><strong>Status:</strong> ${formatStatus(status)}</p>
                    ${job.url ? `<p><strong>URL:</strong> <a href="${job.url}" target="_blank">${job.url}</a></p>` : ''}
                    ${job.artist && job.title ? `<p><strong>Track:</strong> ${job.artist} - ${job.title}</p>` : ''}
                    ${job.review_instructions ? `<div class="review-instructions"><strong>Review Instructions:</strong><br>${job.review_instructions}</div>` : ''}
                    ${job.error ? `<div class="error-details"><strong>Error:</strong><br>${job.error}</div>` : ''}
                </div>
                
                <div class="job-actions">
                    ${createJobActions(jobId, job)}
                </div>
                
                <div class="job-logs-section">
                    <button onclick="tailJobLogs('${jobId}')" class="btn btn-info">
                        📜 View Logs
                    </button>
                </div>
            </div>
        </div>
    `;
}

function createJobActions(jobId, job) {
    const status = job.status || 'unknown';
    const actions = [];
    
    // Status-specific actions
    if (status === 'awaiting_review') {
        if (job.review_url) {
            actions.push(`<a href="${job.review_url}" target="_blank" class="btn btn-success">📝 Review Lyrics</a>`);
        } else {
            actions.push(`<button onclick="reviewLyrics('${jobId}')" class="btn btn-success">📝 Review Lyrics</button>`);
        }
    }
    
    if (status === 'complete') {
        actions.push(`<button onclick="downloadVideo('${jobId}')" class="btn btn-primary">📥 Download Video</button>`);
    }
    
    if (status === 'error') {
        actions.push(`<button onclick="retryJob('${jobId}')" class="btn btn-warning">🔄 Retry</button>`);
    }
    
    // Always available actions
    actions.push(`<button onclick="deleteJob('${jobId}')" class="btn btn-danger">🗑️ Delete</button>`);
    
    return actions.join(' ');
}

function toggleJobDetails(jobId) {
    const details = document.getElementById(`details-${jobId}`);
    const toggleIcon = details.parentElement.querySelector('.toggle-icon');
    
    if (details.classList.contains('show')) {
        details.classList.remove('show');
        toggleIcon.textContent = '▼';
    } else {
        details.classList.add('show');
        toggleIcon.textContent = '▲';
    }
}

function tailJobLogs(jobId) {
    // Stop any existing tail
    stopLogTail();
    
    // Show modal for log tailing
    const modalShown = showLogTailModal(jobId);
    if (!modalShown) {
        console.error('Failed to show modal for job:', jobId);
        return;
    }
    
    currentTailJobId = jobId;
    
    // Start tailing
    logTailInterval = setInterval(() => {
        loadLogTailData(jobId);
    }, 2000); // Update every 2 seconds
    
    // Load initial data
    loadLogTailData(jobId);
}

function stopLogTail() {
    if (logTailInterval) {
        clearInterval(logTailInterval);
        logTailInterval = null;
    }
    currentTailJobId = null;
}

function showLogTailModal(jobId) {
    const modal = document.getElementById('log-tail-modal');
    const modalJobId = document.getElementById('modal-job-id');
    const modalLogs = document.getElementById('modal-logs');
    
    if (modal && modalJobId && modalLogs) {
        // Force reset any previous state completely
        modal.style.display = 'none';
        
        // Clear any existing intervals or state
        if (logTailInterval) {
            clearInterval(logTailInterval);
            logTailInterval = null;
        }
        currentTailJobId = null;
        
        // Set up modal content
        modalJobId.textContent = jobId;
        modalLogs.innerHTML = '<div class="logs-loading">Starting log tail...</div>';
        
        // Apply current font size
        updateLogsFontSize();
        
        // Reset auto-scroll state
        autoScrollEnabled = true;
        const autoScrollBtn = document.getElementById('auto-scroll-btn');
        if (autoScrollBtn) {
            autoScrollBtn.classList.add('toggle-active');
            autoScrollBtn.textContent = '🔄 Auto';
            autoScrollBtn.title = 'Auto-scroll enabled - click to disable';
        }
        
        // Force reflow and show modal
        modal.offsetHeight; // Trigger reflow
        modal.style.display = 'flex';
        
        return true;
    } else {
        console.error('Modal elements not found:', { modal: !!modal, modalJobId: !!modalJobId, modalLogs: !!modalLogs });
        return false;
    }
}

function closeLogTailModal() {
    const modal = document.getElementById('log-tail-modal');
    if (modal) {
        modal.style.display = 'none';
    }
    
    // Stop any log tailing
    stopLogTail();
    
    // Reset auto-scroll to enabled for next time
    autoScrollEnabled = true;
    const autoScrollBtn = document.getElementById('auto-scroll-btn');
    if (autoScrollBtn) {
        autoScrollBtn.classList.add('toggle-active');
        autoScrollBtn.textContent = '🔄 Auto';
        autoScrollBtn.title = 'Auto-scroll enabled - click to disable';
    }
    
    // Clear modal content to ensure fresh state
    const modalLogs = document.getElementById('modal-logs');
    if (modalLogs) {
        modalLogs.innerHTML = '';
    }
    
    const modalJobId = document.getElementById('modal-job-id');
    if (modalJobId) {
        modalJobId.textContent = '';
    }
}

async function loadLogTailData(jobId) {
    const modal = document.getElementById('log-tail-modal');
    const modalLogs = document.getElementById('modal-logs');
    
    // Check if modal is still open before proceeding
    if (!modal || modal.style.display === 'none' || !modalLogs) {
        stopLogTail();
        return;
    }
    
    // Check if user has selected text - if so, skip this update to avoid interrupting copy/paste
    const selection = window.getSelection();
    const hasSelection = selection && selection.toString().length > 0;
    
    // Also check if the selection is within the modal logs area
    let selectionInLogs = false;
    if (hasSelection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        selectionInLogs = modalLogs.contains(range.commonAncestorContainer) || 
                         modalLogs.contains(range.startContainer) || 
                         modalLogs.contains(range.endContainer);
    }
    
    if (selectionInLogs) {
        // User is selecting text in logs - skip content update but still update title
        try {
            const statusResponse = await fetch(`${API_BASE_URL}/jobs/${jobId}`);
            const status = await statusResponse.json();
            
            const modalTitle = document.querySelector('#log-tail-modal .modal-title');
            if (modalTitle) {
                modalTitle.innerHTML = `Log Tail - Job <span id="modal-job-id">${jobId}</span> - ${formatStatus(status.status)} (${status.progress || 0}%) [Selection Active]`;
            }
        } catch (error) {
            console.error('Error loading status:', error);
        }
        return;
    }
    
    try {
        const [statusResponse, logsResponse] = await Promise.all([
            fetch(`${API_BASE_URL}/jobs/${jobId}`),
            fetch(`${API_BASE_URL}/logs/${jobId}`)
        ]);
        
        const status = await statusResponse.json();
        const logs = await logsResponse.json();
        
        // Update modal title with current status - preserve structure
        const modalJobIdSpan = document.getElementById('modal-job-id');
        const modalTitle = document.querySelector('#log-tail-modal .modal-title');
        if (modalJobIdSpan && modalTitle) {
            // Keep the original structure but update the content after the job ID
            modalTitle.innerHTML = `Log Tail - Job <span id="modal-job-id">${jobId}</span> - ${formatStatus(status.status)} (${status.progress || 0}%)`;
        } else if (modalTitle) {
            // Fallback if span is missing - recreate the full structure
            modalTitle.innerHTML = `Log Tail - Job <span id="modal-job-id">${jobId}</span> - ${formatStatus(status.status)} (${status.progress || 0}%)`;
        }
        
        // Update logs
        if (logs.length === 0) {
            modalLogs.innerHTML = '<p class="no-logs">No logs available yet...</p>';
            return;
        }
        
        const logsHTML = logs.map(log => {
            const timestamp = new Date(log.timestamp).toLocaleTimeString();
            const levelClass = log.level.toLowerCase();
            return `<div class="log-entry log-${levelClass}">
                <span class="log-timestamp">${timestamp}</span>
                <span class="log-level">${log.level}</span>
                <span class="log-message">${escapeHtml(log.message)}</span>
            </div>`;
        }).join('');
        
        modalLogs.innerHTML = logsHTML;
        
        // Auto-scroll to bottom if auto-scroll is enabled
        if (autoScrollEnabled) {
            modalLogs.scrollTop = modalLogs.scrollHeight;
        }
        
    } catch (error) {
        console.error('Error loading tail data:', error);
        modalLogs.innerHTML = `<p class="error">Failed to load logs: ${error.message}</p>`;
    }
}

// Admin functions
async function refreshData() {
    await loadJobs();
    showSuccess('Data refreshed successfully');
}

async function clearErrorJobs() {
    if (!confirm('Are you sure you want to clear all error jobs?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/admin/clear-errors`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (result.status === 'success') {
            showSuccess(result.message);
            await loadJobs();
        } else {
            showError(result.message || 'Failed to clear error jobs');
        }
    } catch (error) {
        console.error('Error clearing error jobs:', error);
        showError('Failed to clear error jobs: ' + error.message);
    }
}

function exportLogs() {
    window.open(`${API_BASE_URL}/admin/export-logs`);
}

function toggleAdminPanel() {
    const panel = document.getElementById('admin-panel');
    if (panel) {
        panel.classList.toggle('show');
    }
}

// Job action functions
async function retryJob(jobId) {
    if (!confirm(`Are you sure you want to retry job ${jobId}?`)) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/retry`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (result.status === 'success') {
            showSuccess(`Job ${jobId} retry initiated`);
            await loadJobs();
        } else {
            showError(result.message || 'Failed to retry job');
        }
    } catch (error) {
        console.error('Error retrying job:', error);
        showError('Failed to retry job: ' + error.message);
    }
}

async function deleteJob(jobId) {
    if (!confirm(`Are you sure you want to delete job ${jobId}?`)) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        
        if (result.status === 'success') {
            showSuccess(`Job ${jobId} deleted`);
            await loadJobs();
        } else {
            showError(result.message || 'Failed to delete job');
        }
    } catch (error) {
        console.error('Error deleting job:', error);
        showError('Failed to delete job: ' + error.message);
    }
}

function reviewLyrics(jobId) {
    window.open(`${API_BASE_URL}/review/${jobId}`, '_blank');
}

function downloadVideo(jobId) {
    window.open(`${API_BASE_URL}/jobs/${jobId}/download`, '_blank');
}

// Form submission
async function submitJob() {
    // Prepare form data
    const formData = new FormData();
    const audioFile = document.getElementById('audio-file').files[0];
    const stylesFile = document.getElementById('styles-file').files[0];
    const stylesArchive = document.getElementById('styles-archive').files[0];
    const customStylesVisible = document.getElementById('custom-styles-section').style.display !== 'none';
    
    if (!audioFile) {
        showError('Please select an audio file');
        return;
    }
    
    formData.append('audio_file', audioFile);
    formData.append('artist', document.getElementById('artist').value);
    formData.append('title', document.getElementById('title').value);
    
    // If custom styles section is hidden or no custom styles are provided, use default styles
    if (!customStylesVisible || (!stylesFile && !stylesArchive)) {
        try {
            // Load default styles automatically
            const [defaultStylesResponse, defaultArchiveResponse] = await Promise.all([
                fetch('./karaoke-prep-styles-nomad.json'),
                fetch('./nomadstyles.zip')
            ]);
            
            if (defaultStylesResponse.ok && defaultArchiveResponse.ok) {
                const defaultStylesJson = await defaultStylesResponse.text();
                const defaultArchiveBlob = await defaultArchiveResponse.blob();
                
                // Create default style files
                const defaultStylesFile = new File([new Blob([defaultStylesJson], { type: 'application/json' })], 'karaoke-prep-styles-nomad.json', { type: 'application/json' });
                const defaultArchiveFile = new File([defaultArchiveBlob], 'nomadstyles.zip', { type: 'application/zip' });
                
                formData.append('styles_file', defaultStylesFile);
                formData.append('styles_archive', defaultArchiveFile);
            }
        } catch (error) {
            console.warn('Could not load default styles, proceeding without them:', error);
        }
    } else {
        // Use custom styles if provided
        if (stylesFile) {
            formData.append('styles_file', stylesFile);
        }
        
        if (stylesArchive) {
            formData.append('styles_archive', stylesArchive);
        }
    }
    
    const submitBtn = document.querySelector('.submit-btn');
    const originalText = submitBtn.textContent;
    
    try {
        submitBtn.textContent = 'Uploading...';
        submitBtn.disabled = true;
        
        const response = await fetch(`${API_BASE_URL}/submit-file`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            const usingCustomStyles = customStylesVisible && (stylesFile || stylesArchive);
            const stylesMessage = usingCustomStyles ? ' with custom styles' : ' with default Nomad styles';
            showSuccess(`Job submitted successfully${stylesMessage}! Job ID: ${result.job_id}`);
            
            // Clear form
            document.getElementById('audio-file').value = '';
            document.getElementById('artist').value = '';
            document.getElementById('title').value = '';
            
            // Only clear custom styles if they were visible
            if (customStylesVisible) {
                document.getElementById('styles-file').value = '';
                document.getElementById('styles-archive').value = '';
            }
            
            // Refresh jobs list immediately and scroll to it
            showInfo('Refreshing job list...');
            const jobs = await loadJobs();
            
            if (jobs) {
                // Scroll to jobs section to show the new job
                const jobsSection = document.querySelector('.jobs-section');
                if (jobsSection) {
                    jobsSection.scrollIntoView({ behavior: 'smooth' });
                }
                
                // Auto-refresh job data after 2, 5, and 10 seconds to ensure the new job shows up
                setTimeout(async () => {
                    await loadJobs();
                }, 2000);
                
                setTimeout(async () => {
                    await loadJobs();
                }, 5000);
                
                setTimeout(async () => {
                    await loadJobs();
                }, 10000);
                
                // Show info about what happens next
                setTimeout(() => {
                    showInfo('Your job is now processing. The status will update automatically as it progresses.');
                }, 2000);
                
                // Enable auto-refresh if not already enabled
                const autoRefreshCheckbox = document.getElementById('auto-refresh');
                if (autoRefreshCheckbox && !autoRefreshCheckbox.checked) {
                    autoRefreshCheckbox.checked = true;
                    startAutoRefresh();
                    setTimeout(() => {
                        showInfo('Auto-refresh enabled to track your job progress.');
                    }, 4000);
                }
            }
        } else {
            showError(result.message || 'Failed to submit job');
        }
        
    } catch (error) {
        console.error('Error submitting job:', error);
        showError('Failed to submit job: ' + error.message);
    } finally {
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    }
}

// Toggle custom styles section
function toggleCustomStyles() {
    const customSection = document.getElementById('custom-styles-section');
    const toggleBtn = document.getElementById('customize-styles-btn');
    
    if (customSection.style.display === 'none') {
        customSection.style.display = 'block';
        toggleBtn.textContent = '🎨 Use Default Styles';
        toggleBtn.title = 'Hide custom styles and use default Nomad styles';
    } else {
        customSection.style.display = 'none';
        toggleBtn.textContent = '🎛️ Customize Styles';
        toggleBtn.title = 'Show custom styles options';
        
        // Clear any selected custom files when hiding
        document.getElementById('styles-file').value = '';
        document.getElementById('styles-archive').value = '';
    }
}

// Load default styles function
async function loadDefaultStyles() {
    try {
        const [stylesResponse, archiveResponse] = await Promise.all([
            fetch('./karaoke-prep-styles-nomad.json'),
            fetch('./nomadstyles.zip')
        ]);
        
        if (!stylesResponse.ok) {
            throw new Error('Default styles file not found');
        }
        if (!archiveResponse.ok) {
            throw new Error('Default styles archive not found');
        }
        
        const stylesJson = await stylesResponse.text();
        const archiveBlob = await archiveResponse.blob();
        
        // Create files from the data
        const stylesFile = new File([new Blob([stylesJson], { type: 'application/json' })], 'karaoke-prep-styles-nomad.json', { type: 'application/json' });
        const archiveFile = new File([archiveBlob], 'nomadstyles.zip', { type: 'application/zip' });
        
        // Set the file inputs
        const stylesInput = document.getElementById('styles-file');
        const archiveInput = document.getElementById('styles-archive');
        
        const stylesDataTransfer = new DataTransfer();
        stylesDataTransfer.items.add(stylesFile);
        stylesInput.files = stylesDataTransfer.files;
        
        const archiveDataTransfer = new DataTransfer();
        archiveDataTransfer.items.add(archiveFile);
        archiveInput.files = archiveDataTransfer.files;
        
        showSuccess('Default Nomad styles and assets loaded successfully!');
        
    } catch (error) {
        console.error('Error loading default styles:', error);
        showError('Failed to load default styles: ' + error.message);
    }
}

// Load example data function
async function loadExampleData() {
    try {
        const audioResponse = await fetch('./waterloo30sec.flac');
        
        if (!audioResponse.ok) {
            throw new Error('Example audio file not found');
        }
        
        const audioBlob = await audioResponse.blob();
        
        // Create audio file from the data
        const audioFile = new File([audioBlob], 'waterloo30sec.flac', { type: 'audio/flac' });
        
        // Set the audio file input
        const audioInput = document.getElementById('audio-file');
        const audioDataTransfer = new DataTransfer();
        audioDataTransfer.items.add(audioFile);
        audioInput.files = audioDataTransfer.files;
        
        // Pre-fill the form with example data
        document.getElementById('artist').value = 'ABBA';
        document.getElementById('title').value = 'Waterloo';
        
        showSuccess('Example data loaded successfully! Audio file and metadata are ready to submit with default Nomad styles.');
        
    } catch (error) {
        console.error('Error loading example data:', error);
        showError('Failed to load example data: ' + error.message);
    }
}

// Utility functions
function formatStatus(status) {
    const statusMap = {
        'queued': 'Queued',
        'processing_audio': 'Processing Audio',
        'transcribing': 'Transcribing Lyrics',
        'awaiting_review': 'Awaiting Review',
        'rendering': 'Rendering Video',
        'complete': 'Complete',
        'error': 'Error'
    };
    return statusMap[status] || status;
}

function formatTimestamp(timestamp) {
    return new Date(timestamp).toLocaleString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showSuccess(message) {
    showNotification(message, 'success');
}

function showError(message) {
    showNotification(message, 'error');
}

function showInfo(message) {
    showNotification(message, 'info');
}

function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Add to proper notifications container
    const notificationsContainer = document.getElementById('notifications');
    if (notificationsContainer) {
        notificationsContainer.appendChild(notification);
    } else {
        // Fallback to body if container doesn't exist
        document.body.appendChild(notification);
    }
    
    // Auto-remove after 5 seconds (increased from 3 for better UX)
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// Font size and scroll control functions
const fontSizeClasses = ['font-xs', 'font-sm', 'font-md', 'font-lg', 'font-xl', 'font-xxl'];

function updateLogsFontSize() {
    const modalLogs = document.getElementById('modal-logs');
    if (!modalLogs) return;
    
    // Remove all font size classes
    fontSizeClasses.forEach(cls => modalLogs.classList.remove(cls));
    
    // Add current font size class
    modalLogs.classList.add(fontSizeClasses[logFontSizeIndex]);
}

function increaseFontSize() {
    if (logFontSizeIndex < fontSizeClasses.length - 1) {
        logFontSizeIndex++;
        updateLogsFontSize();
    }
}

function decreaseFontSize() {
    if (logFontSizeIndex > 0) {
        logFontSizeIndex--;
        updateLogsFontSize();
    }
}

function scrollToBottom() {
    const modalLogs = document.getElementById('modal-logs');
    if (modalLogs) {
        modalLogs.scrollTop = modalLogs.scrollHeight;
    }
}

function toggleAutoScroll() {
    autoScrollEnabled = !autoScrollEnabled;
    
    const autoScrollBtn = document.getElementById('auto-scroll-btn');
    if (autoScrollBtn) {
        if (autoScrollEnabled) {
            autoScrollBtn.classList.add('toggle-active');
            autoScrollBtn.textContent = '🔄 Auto';
            autoScrollBtn.title = 'Auto-scroll enabled - click to disable';
            // Scroll to bottom when enabling auto-scroll
            scrollToBottom();
        } else {
            autoScrollBtn.classList.remove('toggle-active');
            autoScrollBtn.textContent = '⏸️ Manual';
            autoScrollBtn.title = 'Auto-scroll disabled - click to enable';
        }
    }
}

function copyLogsToClipboard() {
    console.log('Copy logs function called'); // Debug log
    
    const modalLogs = document.getElementById('modal-logs');
    const jobIdElement = document.getElementById('modal-job-id');
    
    console.log('Modal logs element:', modalLogs); // Debug log
    console.log('Job ID element:', jobIdElement); // Debug log
    
    if (!modalLogs) {
        console.error('Modal logs element not found');
        showError('Unable to access logs for copying');
        return;
    }
    
    // Get job ID from element or use current tail job ID as fallback
    let jobId = 'unknown';
    if (jobIdElement && jobIdElement.textContent) {
        jobId = jobIdElement.textContent.trim();
    } else if (currentTailJobId) {
        jobId = currentTailJobId;
        console.log('Using fallback job ID from currentTailJobId:', jobId);
    } else {
        console.log('Job ID not found, using default');
    }
    
    console.log('Using job ID:', jobId); // Debug log
    
    try {
        // Get all log entries and format them as plain text
        const logEntries = modalLogs.querySelectorAll('.log-entry');
        console.log('Found log entries:', logEntries.length); // Debug log
        
        if (logEntries.length === 0) {
            // Try alternative selectors in case the structure is different
            const allText = modalLogs.textContent || modalLogs.innerText;
            if (!allText.trim()) {
                showError('No logs available to copy');
                return;
            }
            
            // If no structured log entries, just copy all text content
            const now = new Date();
            const simpleHeader = `=== Karaoke Generator Job ${jobId} Logs ===\n` +
                               `Exported: ${now.toLocaleString()}\n` +
                               `${'='.repeat(50)}\n\n`;
            
            const fullText = simpleHeader + allText;
            
            copyTextToClipboard(fullText, `Copied logs content to clipboard`);
            return;
        }
        
        // Create header with job info and timestamp
        const now = new Date();
        const exportHeader = `=== Karaoke Generator Job ${jobId} Logs ===\n` +
                           `Exported: ${now.toLocaleString()}\n` +
                           `Total log entries: ${logEntries.length}\n` +
                           `${'='.repeat(50)}\n\n`;
        
        // Extract text content from each log entry
        const logText = Array.from(logEntries).map(entry => {
            const timestamp = entry.querySelector('.log-timestamp')?.textContent || '';
            const level = entry.querySelector('.log-level')?.textContent || '';
            const message = entry.querySelector('.log-message')?.textContent || '';
            
            return `${timestamp} ${level.padEnd(8)} ${message}`;
        }).join('\n');
        
        const fullLogText = exportHeader + logText;
        
        copyTextToClipboard(fullLogText, `Copied ${logEntries.length} log entries to clipboard`);
        
    } catch (error) {
        console.error('Error copying logs to clipboard:', error);
        showError('Failed to copy logs to clipboard: ' + error.message);
    }
}

function copyTextToClipboard(text, successMessage) {
    // Try modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            console.log('Clipboard copy successful (modern API)');
            showSuccess(successMessage);
            updateCopyButtonFeedback();
        }).catch(error => {
            console.error('Modern clipboard API failed:', error);
            // Fall back to older method
            fallbackCopyTextToClipboard(text, successMessage);
        });
    } else {
        console.log('Modern clipboard API not available, using fallback');
        fallbackCopyTextToClipboard(text, successMessage);
    }
}

function fallbackCopyTextToClipboard(text, successMessage) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        
        if (successful) {
            console.log('Clipboard copy successful (fallback method)');
            showSuccess(successMessage + ' (fallback method)');
            updateCopyButtonFeedback();
        } else {
            console.error('Fallback copy command failed');
            showError('Failed to copy to clipboard');
        }
    } catch (error) {
        console.error('Fallback copy failed:', error);
        document.body.removeChild(textArea);
        showError('Copy to clipboard not supported by browser');
    }
}

function updateCopyButtonFeedback() {
    const copyBtn = document.querySelector('button[onclick="copyLogsToClipboard()"]');
    if (copyBtn) {
        const originalText = copyBtn.textContent;
        const originalClass = copyBtn.className;
        copyBtn.textContent = '✅ Copied!';
        copyBtn.className = originalClass + ' toggle-active';
        
        setTimeout(() => {
            copyBtn.textContent = originalText;
            copyBtn.className = originalClass;
        }, 2000);
    }
}

console.log('🎤 Karaoke Generator Frontend Ready!'); 