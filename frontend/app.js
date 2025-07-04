// Configuration
const API_BASE_URL = 'https://nomadkaraoke--karaoke-generator-webapp-api-endpoint.modal.run/api';

// Global state
let autoRefreshInterval = null;
let logTailInterval = null;
let currentTailJobId = null;
let logFontSizeIndex = 2; // Default to 'font-md'
let autoScrollEnabled = false;
let currentUser = null; // Store current user authentication data

// Authentication functions
function getAuthToken() {
    return localStorage.getItem('karaoke_auth_token');
}

function setAuthToken(token) {
    if (token) {
        localStorage.setItem('karaoke_auth_token', token);
    } else {
        localStorage.removeItem('karaoke_auth_token');
    }
}

function getAuthHeaders() {
    const token = getAuthToken();
    if (token) {
        return {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };
    }
    return {
        'Content-Type': 'application/json'
    };
}

async function authenticateUser() {
    const token = getAuthToken();
    if (!token) {
        showAuthSection();
        return false;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/auth/validate`, {
            method: 'POST',
            headers: getAuthHeaders()
        });

        if (response.ok) {
            const authData = await response.json();
            currentUser = authData;
            showMainApp(authData);
            return true;
        } else {
            // Token is invalid, clear it and show auth
            setAuthToken(null);
            currentUser = null;
            showAuthSection();
            return false;
        }
    } catch (error) {
        console.error('Authentication error:', error);
        showError('Authentication error: ' + error.message);
        showAuthSection();
        return false;
    }
}

function showAuthSection() {
    document.getElementById('auth-section').style.display = 'block';
    document.getElementById('main-app').style.display = 'none';
}

function showMainApp(authData) {
    document.getElementById('auth-section').style.display = 'none';
    document.getElementById('main-app').style.display = 'block';
    
    // Update user status bar
    updateUserStatusBar(authData);
    
    // Show admin panel if user is admin
    if (authData.admin_access) {
        document.getElementById('admin-panel').style.display = 'block';
    } else {
        document.getElementById('admin-panel').style.display = 'none';
    }
}

function updateUserStatusBar(authData) {
    const userTypeDisplay = document.getElementById('user-type-display');
    const userRemainingDisplay = document.getElementById('user-remaining-display');
    
    // Format user type for display
    const userTypeLabels = {
        'admin': '👑 Admin Access',
        'unlimited': '♾️ Unlimited Access', 
        'limited': '🎫 Limited Access',
        'stripe': '💳 Paid Access'
    };
    
    userTypeDisplay.textContent = userTypeLabels[authData.user_type] || authData.user_type;
    
    // Format remaining uses
    if (authData.remaining_uses === -1) {
        userRemainingDisplay.textContent = '';
    } else if (authData.remaining_uses === 0) {
        userRemainingDisplay.textContent = '⚠️ No uses remaining';
        userRemainingDisplay.classList.add('warning');
    } else {
        userRemainingDisplay.textContent = `${authData.remaining_uses} uses remaining`;
        userRemainingDisplay.classList.remove('warning');
    }
}

async function login(token) {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ token: token })
        });

        const result = await response.json();

        if (result.success) {
            setAuthToken(result.access_token);
            currentUser = result;
            showMainApp(result);
            showSuccess('Authentication successful! Welcome to Karaoke Generator.');
            
            // Load initial data
            await loadJobs();
            
            return true;
        } else {
            showError('Authentication failed: ' + result.message);
            return false;
        }
    } catch (error) {
        console.error('Login error:', error);
        showError('Login failed: ' + error.message);
        return false;
    }
}

async function logout() {
    try {
        // Call logout endpoint if we have a token
        const token = getAuthToken();
        if (token) {
            await fetch(`${API_BASE_URL}/auth/logout`, {
                method: 'POST',
                headers: getAuthHeaders()
            });
        }
    } catch (error) {
        console.error('Logout error:', error);
    }
    
    // Clear local data
    setAuthToken(null);
    currentUser = null;
    
    // Stop auto-refresh and uncheck the checkbox
    stopAutoRefresh();
    const autoRefreshCheckbox = document.getElementById('auto-refresh');
    if (autoRefreshCheckbox) {
        autoRefreshCheckbox.checked = false;
    }
    
    // Show auth section
    showAuthSection();
    
    showInfo('Logged out successfully');
}

// User info modal functions
function showUserInfo() {
    if (!currentUser) return;
    
    const modal = document.getElementById('user-info-modal');
    const content = document.getElementById('user-info-content');
    
    const userTypeLabels = {
        'admin': 'Administrator',
        'unlimited': 'Unlimited Access', 
        'limited': 'Limited Access',
        'stripe': 'Paid Access'
    };
    
    const remainingText = currentUser.remaining_uses === -1 
        ? 'Unlimited' 
        : `${currentUser.remaining_uses} uses remaining`;
    
    content.innerHTML = `
        <div class="user-info-grid">
            <div class="user-info-item">
                <label>Account Type:</label>
                <span>${userTypeLabels[currentUser.user_type] || currentUser.user_type}</span>
            </div>
            <div class="user-info-item">
                <label>Remaining Uses:</label>
                <span>${remainingText}</span>
            </div>
            <div class="user-info-item">
                <label>Admin Access:</label>
                <span>${currentUser.admin_access ? 'Yes' : 'No'}</span>
            </div>
            <div class="user-info-item">
                <label>Status:</label>
                <span>${currentUser.message}</span>
            </div>
        </div>
    `;
    
    modal.style.display = 'flex';
}

function closeUserInfoModal() {
    document.getElementById('user-info-modal').style.display = 'none';
}

// Token management functions (admin only)
async function showTokenManagement() {
    if (!currentUser || !currentUser.admin_access) {
        showError('Admin access required');
        return;
    }
    
    const modal = document.getElementById('token-management-modal');
    const content = document.getElementById('token-management-content');
    
    modal.style.display = 'flex';
    content.innerHTML = '<div class="token-loading">Loading tokens...</div>';
    
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/admin/tokens/list`);
        
        if (!response) return; // Auth failed, already handled
        
        if (response.ok) {
            const result = await response.json();
            displayTokenManagement(result.tokens);
        } else {
            const error = await response.json();
            content.innerHTML = `<div class="error">Error loading tokens: ${error.message}</div>`;
        }
    } catch (error) {
        console.error('Error loading tokens:', error);
        content.innerHTML = `<div class="error">Error loading tokens: ${error.message}</div>`;
    }
}

function displayTokenManagement(tokens) {
    const content = document.getElementById('token-management-content');
    
    let html = `
        <div class="token-management">
            <div class="token-create-section">
                <h4>Create New Token</h4>
                <form id="create-token-form" onsubmit="createToken(event)">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="token-type">Type:</label>
                            <select id="token-type" required>
                                <option value="unlimited">Unlimited Access</option>
                                <option value="limited">Limited Access</option>
                                <option value="stripe">Stripe Payment</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="token-value">Token:</label>
                            <input type="text" id="token-value" placeholder="Enter token value" required>
                        </div>
                        <div class="form-group">
                            <label for="token-max-uses">Max Uses:</label>
                            <input type="number" id="token-max-uses" placeholder="Leave empty for unlimited" min="1">
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="token-description">Description:</label>
                        <input type="text" id="token-description" placeholder="Optional description">
                    </div>
                    <button type="submit" class="btn btn-primary">Create Token</button>
                </form>
            </div>
            
            <div class="token-list-section">
                <h4>Existing Tokens (${tokens.length})</h4>
                <div class="token-list">
    `;
    
    if (tokens.length === 0) {
        html += '<p class="no-tokens">No tokens found.</p>';
    } else {
        tokens.forEach(token => {
            const typeLabels = {
                'unlimited': 'Unlimited',
                'limited': 'Limited',
                'stripe': 'Stripe',
                'admin': 'Admin'
            };
            
            const usageText = token.max_uses === -1 
                ? `${token.current_uses} uses`
                : `${token.current_uses}/${token.max_uses} uses`;
            
            const statusClass = token.active ? 'active' : 'revoked';
            const statusText = token.active ? 'Active' : 'Revoked';
            
            html += `
                <div class="token-item ${statusClass}">
                    <div class="token-info">
                        <div class="token-header">
                            <span class="token-value">${token.token}</span>
                            <span class="token-type">${typeLabels[token.type] || token.type}</span>
                            <span class="token-status ${statusClass}">${statusText}</span>
                        </div>
                        <div class="token-details">
                            <span class="token-usage">${usageText}</span>
                            <span class="token-jobs">${token.jobs_created} jobs</span>
                            ${token.description ? `<span class="token-description">${token.description}</span>` : ''}
                        </div>
                        ${token.last_used ? `<div class="token-last-used">Last used: ${formatTimestamp(new Date(token.last_used * 1000).toISOString())}</div>` : ''}
                    </div>
                    <div class="token-actions">
                        ${token.active ? `<button onclick="revokeToken('${token.token}')" class="btn btn-danger btn-sm">Revoke</button>` : ''}
                    </div>
                </div>
            `;
        });
    }
    
    html += `
                </div>
            </div>
        </div>
    `;
    
    content.innerHTML = html;
}

async function createToken(event) {
    event.preventDefault();
    
    const tokenType = document.getElementById('token-type').value;
    const tokenValue = document.getElementById('token-value').value.trim();
    const maxUses = document.getElementById('token-max-uses').value;
    const description = document.getElementById('token-description').value.trim();
    
    if (!tokenValue) {
        showError('Token value is required');
        return;
    }
    
    try {
        const requestData = {
            token_type: tokenType,
            token_value: tokenValue,
            description: description || null
        };
        
        if (maxUses) {
            requestData.max_uses = parseInt(maxUses);
        }
        
        const response = await authenticatedFetch(`${API_BASE_URL}/admin/tokens/create`, {
            method: 'POST',
            body: JSON.stringify(requestData)
        });
        
        if (!response) return; // Auth failed, already handled
        
        const result = await response.json();
        
        if (result.success) {
            showSuccess(result.message);
            // Clear form first before refreshing (which recreates the modal content)
            const form = document.getElementById('create-token-form');
            if (form) {
                form.reset();
            }
            // Refresh token list
            showTokenManagement();
        } else {
            showError('Error creating token: ' + result.message);
        }
    } catch (error) {
        console.error('Error creating token:', error);
        showError('Error creating token: ' + error.message);
    }
}

async function revokeToken(tokenValue) {
    if (!confirm(`Are you sure you want to revoke token "${tokenValue}"?`)) {
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/admin/tokens/${encodeURIComponent(tokenValue)}/revoke`, {
            method: 'POST'
        });
        
        if (!response) return; // Auth failed, already handled
        
        const result = await response.json();
        
        if (result.success) {
            showSuccess(result.message);
            // Refresh token list
            showTokenManagement();
        } else {
            showError('Error revoking token: ' + result.message);
        }
    } catch (error) {
        console.error('Error revoking token:', error);
        showError('Error revoking token: ' + error.message);
    }
}

function closeTokenManagementModal() {
    document.getElementById('token-management-modal').style.display = 'none';
}

// Update all API calls to include authentication headers
async function authenticatedFetch(url, options = {}) {
    const headers = {
        ...getAuthHeaders(),
        ...options.headers
    };
    
    const response = await fetch(url, {
        ...options,
        headers
    });
    
    // If we get a 401, the token has expired - redirect to login
    if (response.status === 401) {
        setAuthToken(null);
        currentUser = null;
        
        // Stop auto-refresh and uncheck the checkbox
        stopAutoRefresh();
        const autoRefreshCheckbox = document.getElementById('auto-refresh');
        if (autoRefreshCheckbox) {
            autoRefreshCheckbox.checked = false;
        }
        
        showAuthSection();
        showError('Session expired. Please log in again.');
        return null;
    }
    
    return response;
}

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    // Debug timezone information for troubleshooting timestamp issues
    console.log('🌍 Timezone Debug Info:', {
        userTimezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        timezoneOffset: new Date().getTimezoneOffset(),
        timezoneOffsetHours: new Date().getTimezoneOffset() / 60,
        localTime: new Date().toISOString(),
        localTimeString: new Date().toString(),
        localDateString: new Date().toLocaleDateString(),
        localTimeStringFormatted: new Date().toLocaleString(),
        sampleUTCParsing: parseServerTime('2024-01-01T12:00:00').toString(),
        userAgent: navigator.userAgent.substring(0, 100)
    });
    
    // Initialize authentication
    authenticateUser().then(isAuthenticated => {
        if (isAuthenticated) {
            loadJobs();
            
            // Only start auto-refresh after successful authentication
            const autoRefreshCheckbox = document.getElementById('auto-refresh');
            if (autoRefreshCheckbox && autoRefreshCheckbox.checked) {
                startAutoRefresh();
            }
        }
    });
    
    // Handle auth form submission
    const authForm = document.getElementById('auth-form');
    if (authForm) {
        authForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const token = document.getElementById('access-token').value.trim();
            if (token) {
                await login(token);
            }
        });
    }
    
    // Auto-refresh checkbox handler
    const autoRefreshCheckbox = document.getElementById('auto-refresh');
    if (autoRefreshCheckbox) {
        autoRefreshCheckbox.addEventListener('change', function() {
            // Only allow auto-refresh if user is authenticated
            if (!currentUser) {
                this.checked = false;
                showError('Please log in to use auto-refresh');
                return;
            }
            
            if (this.checked) {
                startAutoRefresh();
                showInfo('Auto-refresh enabled - jobs will update every 5 seconds');
            } else {
                stopAutoRefresh();
                showInfo('Auto-refresh disabled');
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
    
    const cacheModal = document.getElementById('cache-stats-modal');
    if (cacheModal) {
        cacheModal.addEventListener('click', function(e) {
            if (e.target === cacheModal) {
                closeCacheStatsModal();
            }
        });
    }
    
    const userInfoModal = document.getElementById('user-info-modal');
    if (userInfoModal) {
        userInfoModal.addEventListener('click', function(e) {
            if (e.target === userInfoModal) {
                closeUserInfoModal();
            }
        });
    }
    
    const tokenModal = document.getElementById('token-management-modal');
    if (tokenModal) {
        tokenModal.addEventListener('click', function(e) {
            if (e.target === tokenModal) {
                closeTokenManagementModal();
            }
        });
    }
    
    const instrumentalModal = document.getElementById('instrumental-selection-modal');
    if (instrumentalModal) {
        instrumentalModal.addEventListener('click', function(e) {
            if (e.target === instrumentalModal) {
                closeInstrumentalSelectionModal();
            }
        });
    }
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Escape key closes modals
        if (e.key === 'Escape') {
            closeLogTailModal();
            closeCacheStatsModal();
            closeFilesModal();
            closeVideoPreview();
            closeAudioPreview();
            closeTimelineModal();
            closeUserInfoModal();
            closeTokenManagementModal();
            closeInstrumentalSelectionModal();
        }
    });
});

function startAutoRefresh() {
    // Don't start auto-refresh if user is not authenticated
    if (!currentUser) {
        console.log('Auto-refresh not started: user not authenticated');
        const autoRefreshCheckbox = document.getElementById('auto-refresh');
        if (autoRefreshCheckbox) {
            autoRefreshCheckbox.checked = false;
        }
        return;
    }
    
    if (autoRefreshInterval) {
        console.log('Auto-refresh already running');
        return; // Already running
    }
    
    console.log('Starting auto-refresh (5s intervals)');
    
    // Add visual indicator
    const autoRefreshCheckbox = document.getElementById('auto-refresh');
    if (autoRefreshCheckbox) {
        autoRefreshCheckbox.parentElement.classList.add('auto-refresh-active');
    }
    
    autoRefreshInterval = setInterval(() => {
        try {
            // Check if user is still authenticated before refreshing
            if (!currentUser) {
                console.log('Auto-refresh: Stopping due to lost authentication');
                stopAutoRefresh();
                return;
            }
            
            // Only refresh if not tailing logs (to avoid conflicts)
            if (!currentTailJobId) {
                console.log('Auto-refresh: Loading jobs...');
                loadJobsWithoutScroll();
            } else {
                console.log('Auto-refresh: Skipping due to active log tail');
            }
        } catch (error) {
            console.error('Auto-refresh error:', error);
            // Don't stop auto-refresh on errors, just log them
        }
    }, 5000); // 5 second refresh
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        console.log('Stopping auto-refresh');
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
        
        // Remove visual indicator
        const autoRefreshCheckbox = document.getElementById('auto-refresh');
        if (autoRefreshCheckbox) {
            autoRefreshCheckbox.parentElement.classList.remove('auto-refresh-active');
        }
    }
}

function loadJobsWithoutScroll() {
    // Store current scroll position
    const currentScrollY = window.scrollY;
    const currentScrollX = window.scrollX;
    
    return loadJobs().then(() => {
        // Restore scroll position after update
        window.scrollTo(currentScrollX, currentScrollY);
    }).catch(error => {
        console.error('Error in loadJobsWithoutScroll:', error);
        // Don't throw the error to prevent auto-refresh from stopping
        showError('Auto-refresh failed: ' + error.message);
    });
}

async function loadJobs() {
    try {
        console.log('Loading jobs from API...');
        const response = await authenticatedFetch(`${API_BASE_URL}/jobs`);
        
        if (!response) return null; // Auth failed, already handled
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const jobs = await response.json();
        console.log(`Loaded ${Object.keys(jobs).length} jobs`);
        
        updateJobsList(jobs);
        updateStats(jobs);
        
        return jobs; // Return jobs for further use
        
    } catch (error) {
        console.error('Error loading jobs:', error);
        showError('Failed to load jobs: ' + error.message);
        
        // Still return null but don't break the calling code
        return null;
    }
}

function updateJobsList(jobs) {
    const jobsList = document.getElementById('jobs-list');
    if (!jobsList) return;
    
    if (Object.keys(jobs).length === 0) {
        jobsList.innerHTML = '<p class="no-jobs">No jobs found. Submit a job above to get started!</p>';
        return;
    }
    
    const sortedJobs = Object.entries(jobs).sort((a, b) => {
        const timeA = parseServerTime(a[1].created_at || 0);
        const timeB = parseServerTime(b[1].created_at || 0);
        return timeB - timeA; // Most recent first
    });
    
    jobsList.innerHTML = sortedJobs.map(([jobId, job]) => {
        return createJobHTML(jobId, job);
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

function createJobHTML(jobId, job) {
    const status = job.status || 'unknown';
    const progress = job.progress || 0;
    const timestamp = job.created_at ? formatTimestamp(job.created_at) : 'Unknown';
    const duration = formatDurationWithStatus(job);
    
    // Format track info for display
    const trackInfo = (job.artist && job.title) 
        ? `${job.artist} - ${job.title}` 
        : (job.url ? 'URL Processing' : 'Unknown Track');
    
    // Get timeline information
    const timelineInfo = createTimelineInfoHtml(job);
    const submittedTime = formatSubmittedTime(job);
    const totalDuration = getTotalJobDuration(job);
    const multiStageProgressBar = createMultiStageProgressBar(job);
    
    return `
        <div class="job" data-job-id="${jobId}">
            <div class="job-row">
                <div class="job-main-info">
                    <div class="job-header">
                        <div class="job-title-section">
                            <div class="job-header-line">
                                <span class="job-id">🎵 Job ${jobId}</span>
                                <div class="job-status">
                                    <span class="status-badge status-${status}">${formatStatus(status)}</span>
                                </div>
                            </div>
                            <div class="job-track-info">
                                <span class="track-name">${trackInfo}</span>
                            </div>
                        </div>
                        <div class="job-timing-section">
                            <div class="job-submitted">
                                <span class="timing-label">Submitted:</span>
                                <span class="timing-value">${submittedTime}</span>
                            </div>
                            <div class="job-duration">
                                <span class="timing-label">Duration:</span>
                                <span class="timing-value">${totalDuration}</span>
                            </div>
                        </div>
                    </div>
                    
                    ${multiStageProgressBar}
                    ${timelineInfo}
                </div>
                
                <div class="job-actions">
                    ${createJobActions(jobId, job)}
                    <button onclick="showTimelineModal('${jobId}')" class="btn btn-secondary" title="View detailed timeline">
                        ⏱️ Timeline
                    </button>
                    <button onclick="tailJobLogs('${jobId}')" class="btn btn-info">
                        📜 View Logs
                    </button>
                </div>
            </div>
        </div>
    `;
}

function formatSubmittedTime(job) {
    // Helper function to format a timestamp in user's local timezone
    const formatLocalTime = (timestamp) => {
        try {
            const submitTime = parseServerTime(timestamp);
            
            // Validate the parsed time
            if (isNaN(submitTime.getTime())) {
                console.warn('Invalid submit time:', timestamp);
                return 'Invalid Time';
            }
            
            const now = new Date();
            const diffHours = (now - submitTime) / (1000 * 60 * 60);
            
            // Format options for consistent local timezone display
            const timeOptions = {
                hour: '2-digit', 
                minute: '2-digit',
                hour12: false  // Use 24-hour format for consistency
            };
            
            const dateOptions = {
                month: 'short', 
                day: 'numeric'
            };
            
            if (diffHours < 24 && diffHours >= 0) {
                // Same day - show just time
                return submitTime.toLocaleTimeString([], timeOptions);
            } else {
                // Different day - show date and time
                return submitTime.toLocaleDateString([], dateOptions) + ' ' + 
                       submitTime.toLocaleTimeString([], timeOptions);
            }
        } catch (error) {
            console.error('Error formatting submit time:', timestamp, error);
            return 'Error';
        }
    };
    
    // Try timeline data first (most accurate submission time)
    if (job.timeline && job.timeline.length > 0 && job.timeline[0].started_at) {
        return formatLocalTime(job.timeline[0].started_at);
    }
    
    // Fallback to created_at
    if (job.created_at) {
        return formatLocalTime(job.created_at);
    }
    
    return 'Unknown';
}

function getJobEndTime(job) {
    // Helper function to determine the correct end time for a job
    const status = job.status || 'unknown';
    const finishedStates = ['complete', 'error', 'cancelled', 'failed'];
    
    // If job is not finished, use current time
    if (!finishedStates.includes(status)) {
        return new Date();
    }
    
    // For finished jobs, try to find the actual completion time
    
    // 1. Check timeline data for the last phase end time
    if (job.timeline && job.timeline.length > 0) {
        // Find the last phase with an end time
        for (let i = job.timeline.length - 1; i >= 0; i--) {
            if (job.timeline[i].ended_at) {
                return parseServerTime(job.timeline[i].ended_at);
            }
        }
    }
    
    // 2. Check for job completion timestamp (if available)
    if (job.completed_at) {
        return parseServerTime(job.completed_at);
    }
    
    // 3. Check for job finished timestamp (if available)
    if (job.finished_at) {
        return parseServerTime(job.finished_at);
    }
    
    // 4. Check for job updated timestamp (if available and status is finished)
    if (job.updated_at && finishedStates.includes(status)) {
        return parseServerTime(job.updated_at);
    }
    
    // 5. Fallback to current time (shouldn't happen for finished jobs, but safety net)
    return new Date();
}

function getTotalJobDuration(job) {
    // Try timeline summary first
    const timeline_summary = job.timeline_summary;
    if (timeline_summary && timeline_summary.total_duration_formatted) {
        return timeline_summary.total_duration_formatted;
    }
    
    // Try calculating from timeline data directly
    if (job.timeline && job.timeline.length > 0) {
        try {
            const startTime = parseServerTime(job.timeline[0].started_at);
            const endTime = getJobEndTime(job);
            const durationMs = endTime - startTime;
            
            // Debug logging for timezone issues
            if (durationMs < 0) {
                console.warn('Negative duration detected:', {
                    startTime: startTime.toISOString(),
                    endTime: endTime.toISOString(),
                    originalTimestamp: job.timeline[0].started_at,
                    durationMs,
                    userTimezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    jobStatus: job.status
                });
            }
            
            const durationSeconds = Math.floor(Math.max(0, durationMs) / 1000);
            return formatDuration(durationSeconds);
        } catch (error) {
            console.error('Error calculating timeline duration:', error, job.timeline[0]);
        }
    }
    
    // Fallback to calculating from created_at if no timeline data
    if (job.created_at) {
        try {
            const startTime = parseServerTime(job.created_at);
            const endTime = getJobEndTime(job);
            const durationMs = endTime - startTime;
            
            // Debug logging for timezone issues
            if (durationMs < 0) {
                console.warn('Negative duration detected from created_at:', {
                    startTime: startTime.toISOString(),
                    endTime: endTime.toISOString(),
                    originalTimestamp: job.created_at,
                    durationMs,
                    userTimezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    jobStatus: job.status
                });
            }
            
            const durationSeconds = Math.floor(Math.max(0, durationMs) / 1000);
            return formatDuration(durationSeconds);
        } catch (error) {
            console.error('Error calculating created_at duration:', error, job.created_at);
        }
    }
    
    return 'Unknown';
}

function createMultiStageProgressBar(job) {
    const timeline_summary = job.timeline_summary;
    const currentStatus = job.status || 'unknown';
    const timeline = job.timeline || [];
    
    // Define all possible phases in order with cleaner labels
    const allPhases = [
        { key: 'queued', label: 'Queued', shortLabel: 'Queue' },
        { key: 'processing', label: 'Processing', shortLabel: 'Process' },
        { key: 'awaiting_review', label: 'Review', shortLabel: 'Review' },
        { key: 'reviewing', label: 'Reviewing', shortLabel: 'Review' },
        { key: 'ready_for_finalization', label: 'Ready for Finalization', shortLabel: 'Ready' },
        { key: 'rendering', label: 'Rendering', shortLabel: 'Render' },
        { key: 'finalizing', label: 'Finalizing', shortLabel: 'Final' },
        { key: 'complete', label: 'Complete', shortLabel: 'Done' }
    ];
    
    let html = '<div class="job-progress-enhanced">';
    html += '<div class="multi-stage-progress-bar">';
    
    if (timeline_summary && timeline_summary.phase_durations) {
        const phaseDurations = timeline_summary.phase_durations;
        const totalDuration = timeline_summary.total_duration_seconds || 1;
        
        // Create segments for each phase that has occurred or is occurring
        let accumulatedWidth = 0;
        
        allPhases.forEach((phase) => {
            const duration = phaseDurations[phase.key];
            if (duration !== undefined && duration > 0) {
                const widthPercent = Math.max((duration / totalDuration) * 100, 8); // Minimum 8% width
                const isActive = currentStatus === phase.key;
                const isCompleted = timeline.find(t => t.status === phase.key && t.ended_at);
                
                html += `
                    <div class="progress-segment ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}" 
                         style="width: ${widthPercent}%; background-color: ${getPhaseColor(phase.key)}"
                         title="${phase.label}: ${formatDuration(duration)}">
                        <div class="segment-content">
                            <span class="segment-label">${phase.shortLabel}</span>
                            <span class="segment-duration">${formatDuration(duration)}</span>
                        </div>
                    </div>
                `;
                accumulatedWidth += widthPercent;
            }
        });
        
        // Add upcoming phases as placeholder segments
        const remainingPhases = allPhases.filter(phase => 
            !phaseDurations[phase.key] && 
            shouldShowPhase(phase.key, currentStatus)
        );
        
        if (remainingPhases.length > 0) {
            const remainingWidth = Math.max(100 - accumulatedWidth, 10);
            const segmentWidth = remainingWidth / remainingPhases.length;
            
            remainingPhases.forEach((phase) => {
                const isNext = isNextPhase(phase.key, currentStatus);
                
                html += `
                    <div class="progress-segment upcoming ${isNext ? 'next' : ''}" 
                         style="width: ${segmentWidth}%; background-color: ${getPhaseColor(phase.key, true)}"
                         title="${phase.label}: Pending">
                        <div class="segment-content">
                            <span class="segment-label">${phase.shortLabel}</span>
                            <span class="segment-duration">Pending</span>
                        </div>
                    </div>
                `;
            });
        }
    } else {
        // Fallback: simple progress based on status with elegant segments
        const progressPercent = job.progress || 0;
        const currentPhase = allPhases.find(p => p.key === currentStatus) || allPhases[0];
        
        // Show current phase
        html += `
            <div class="progress-segment active" 
                 style="width: ${Math.max(progressPercent, 15)}%; background-color: ${getPhaseColor(currentStatus)}"
                 title="${currentPhase.label}: ${progressPercent}%">
                <div class="segment-content">
                    <span class="segment-label">${currentPhase.shortLabel}</span>
                    <span class="segment-duration">${progressPercent}%</span>
                </div>
            </div>
        `;
        
        // Show remaining progress
        if (progressPercent < 100) {
            html += `
                <div class="progress-segment upcoming" 
                     style="width: ${100 - progressPercent}%; background-color: #e9ecef"
                     title="Remaining: ${100 - progressPercent}%">
                    <div class="segment-content">
                        <span class="segment-label">Remaining</span>
                        <span class="segment-duration">${100 - progressPercent}%</span>
                    </div>
                </div>
            `;
        }
    }
    
    html += '</div>';
    html += '</div>';
    
    return html;
}

function shouldShowPhase(phaseKey, currentStatus) {
    const phaseOrder = ['queued', 'processing', 'awaiting_review', 'reviewing', 'ready_for_finalization', 'rendering', 'finalizing', 'complete'];
    const currentIndex = phaseOrder.indexOf(currentStatus);
    const phaseIndex = phaseOrder.indexOf(phaseKey);
    
    // Show phases that come after the current status (except 'complete' which we handle specially)
    return phaseIndex > currentIndex && phaseKey !== 'complete';
}

function isNextPhase(phaseKey, currentStatus) {
    const phaseOrder = ['queued', 'processing', 'awaiting_review', 'reviewing', 'ready_for_finalization', 'rendering', 'finalizing', 'complete'];
    const currentIndex = phaseOrder.indexOf(currentStatus);
    const phaseIndex = phaseOrder.indexOf(phaseKey);
    
    return phaseIndex === currentIndex + 1;
}

function getPhaseColor(phase, isUpcoming = false) {
    const colors = {
        'queued': isUpcoming ? '#adb5bd' : '#6c757d',
        'processing': isUpcoming ? '#66a3ff' : '#007bff', 
        'awaiting_review': isUpcoming ? '#ffdf88' : '#ffc107',
        'reviewing': isUpcoming ? '#ff9f5c' : '#fd7e14',
        'ready_for_finalization': isUpcoming ? '#a0c4ff' : '#6c5ce7',
        'rendering': isUpcoming ? '#66d9a3' : '#28a745',
        'finalizing': isUpcoming ? '#74b9ff' : '#0984e3',
        'complete': isUpcoming ? '#66d9a3' : '#28a745',
        'error': isUpcoming ? '#ff8a9a' : '#dc3545'
    };
    return colors[phase] || (isUpcoming ? '#e9ecef' : '#6c757d');
}

function createTimelineInfoHtml(job) {
    const timeline_summary = job.timeline_summary;
    if (!timeline_summary || !timeline_summary.phase_durations) {
        return '';
    }
    
    const phases = timeline_summary.phase_durations;
    const totalDuration = timeline_summary.total_duration_formatted || '0s';
    
    // Create mini timeline visualization
    let timelineHtml = '<div class="job-timeline-mini">';
    timelineHtml += `<div class="timeline-total">Total: ${totalDuration}</div>`;
    
    if (Object.keys(phases).length > 0) {
        timelineHtml += '<div class="timeline-phases">';
        
        // Show up to 4 most significant phases
        const sortedPhases = Object.entries(phases)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 4);
        
        sortedPhases.forEach(([phase, duration]) => {
            const formattedDuration = formatDuration(duration);
            const phaseColor = getPhaseColor(phase);
            
            timelineHtml += `
                <span class="timeline-phase" style="background-color: ${phaseColor}" 
                      title="${formatStatus(phase)}: ${formattedDuration}">
                    ${getPhaseIcon(phase)} ${formattedDuration}
                </span>
            `;
        });
        
        timelineHtml += '</div>';
    }
    
    timelineHtml += '</div>';
    return timelineHtml;
}

function getPhaseIcon(phase) {
    const icons = {
        'queued': '⏳',
        'processing': '⚙️',
        'processing_audio': '🎵',
        'transcribing': '📝',
        'awaiting_review': '⏸️',
        'reviewing': '👁️',
        'ready_for_finalization': '🎵',
        'rendering': '🎬',
        'finalizing': '📦',
        'complete': '✅',
        'error': '❌'
    };
    return icons[phase] || '📋';
}

function getShortPhaseLabel(phase) {
    const shortLabels = {
        'queued': 'Queue',
        'processing': 'Process',
        'processing_audio': 'Audio',
        'transcribing': 'Lyrics',
        'awaiting_review': 'Review',
        'reviewing': 'Editing',
        'ready_for_finalization': 'Ready',
        'rendering': 'Render',
        'finalizing': 'Final',
        'complete': 'Done',
        'error': 'Error'
    };
    return shortLabels[phase] || phase;
}

// Timeline Modal Functions
async function showTimelineModal(jobId) {
    try {
        showInfo('Loading timeline data...');
        
        const response = await authenticatedFetch(`${API_BASE_URL}/jobs/${jobId}/timeline`);
        
        if (!response.ok) {
            // If timeline endpoint fails, try to get basic job data and create a simple timeline
            console.warn('Timeline endpoint failed, trying basic job data...');
            const jobResponse = await authenticatedFetch(`${API_BASE_URL}/jobs/${jobId}`);
            
            if (jobResponse && jobResponse.ok) {
                const jobData = await jobResponse.json();
                createSimpleTimelineModal(jobData);
                return;
            }
            
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const timelineData = await response.json();
        
        // Create and show the timeline modal
        createTimelineModal(timelineData);
        
    } catch (error) {
        console.error('Error loading timeline:', error);
        showError(`Error loading timeline: ${error.message}`);
    }
}

function createSimpleTimelineModal(jobData) {
    const modalHtml = `
        <div id="timeline-modal" class="modal">
            <div class="modal-content timeline-modal-content">
                <div class="modal-header">
                    <h3 class="modal-title">⏱️ Timeline for ${jobData.artist || 'Unknown'} - ${jobData.title || 'Unknown'}</h3>
                    <div class="modal-controls">
                        <button onclick="closeTimelineModal()" class="modal-close">✕</button>
                    </div>
                </div>
                <div class="modal-body">
                    <div class="timeline-summary">
                        <div class="timeline-summary-cards">
                            <div class="timeline-card">
                                <div class="timeline-card-value">${getTotalJobDuration(jobData)}</div>
                                <div class="timeline-card-label">Total Time</div>
                            </div>
                            <div class="timeline-card">
                                <div class="timeline-card-value">${formatStatus(jobData.status)}</div>
                                <div class="timeline-card-label">Current Status</div>
                            </div>
                            <div class="timeline-card">
                                <div class="timeline-card-value">${jobData.progress || 0}%</div>
                                <div class="timeline-card-label">Progress</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="simple-timeline-info">
                        <h4>Job Information</h4>
                        <p><strong>Status:</strong> ${formatStatus(jobData.status)}</p>
                        <p><strong>Progress:</strong> ${jobData.progress || 0}%</p>
                        <p><strong>Submitted:</strong> ${formatSubmittedTime(jobData)}</p>
                        <p><strong>Duration:</strong> ${getTotalJobDuration(jobData)}</p>
                        ${jobData.created_at ? `<p><strong>Created:</strong> ${formatTimestamp(jobData.created_at)}</p>` : ''}
                        <br>
                        <p><em>This job was created before detailed timeline tracking was implemented.</em></p>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove any existing timeline modal
    const existingModal = document.getElementById('timeline-modal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Show modal
    const modal = document.getElementById('timeline-modal');
    modal.style.display = 'flex';
    
    // Add click outside to close
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeTimelineModal();
        }
    });
}

function createTimelineModal(timelineData) {
    const modalHtml = `
        <div id="timeline-modal" class="modal">
            <div class="modal-content timeline-modal-content">
                <div class="modal-header">
                    <h3 class="modal-title">⏱️ Timeline for ${timelineData.artist} - ${timelineData.title}</h3>
                    <div class="modal-controls">
                        <button onclick="closeTimelineModal()" class="modal-close">✕</button>
                    </div>
                </div>
                <div class="modal-body">
                    ${createTimelineVisualizationHtml(timelineData)}
                </div>
            </div>
        </div>
    `;
    
    // Remove any existing timeline modal
    const existingModal = document.getElementById('timeline-modal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Show modal
    const modal = document.getElementById('timeline-modal');
    modal.style.display = 'flex';
    
    // Add click outside to close
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeTimelineModal();
        }
    });
}

function calculateCorrectTimelineDuration(timelineData) {
    // Use the same corrected duration logic as the main job list
    const timeline = timelineData.timeline || [];
    
    if (timeline.length === 0) {
        return '0s';
    }
    
    try {
        const startTime = parseServerTime(timeline[0].started_at);
        const endTime = getJobEndTime({
            status: timelineData.current_status,
            timeline: timeline,
            completed_at: timelineData.completed_at,
            finished_at: timelineData.finished_at,
            updated_at: timelineData.updated_at
        });
        
        const durationMs = endTime - startTime;
        const durationSeconds = Math.floor(Math.max(0, durationMs) / 1000);
        return formatDuration(durationSeconds);
    } catch (error) {
        console.error('Error calculating timeline duration:', error);
        return '0s';
    }
}

function createTimelineVisualizationHtml(timelineData) {
    const timeline = timelineData.timeline || [];
    const summary = timelineData.timeline_summary || {};
    const metrics = timelineData.performance_metrics || {};
    
    let html = '';
    
    // Calculate corrected total duration using the same logic as job list
    const correctedTotalDuration = calculateCorrectTimelineDuration(timelineData);
    
    // Summary cards
    html += `
        <div class="timeline-summary">
            <div class="timeline-summary-cards">
                <div class="timeline-card">
                    <div class="timeline-card-value">${correctedTotalDuration}</div>
                    <div class="timeline-card-label">Total time</div>
                </div>
                <div class="timeline-card">
                    <div class="timeline-card-value">${timeline.length}</div>
                    <div class="timeline-card-label">Phases complete</div>
                </div>
                <div class="timeline-card">
                    <div class="timeline-card-value">${formatStatus(timelineData.current_status)}</div>
                    <div class="timeline-card-label">Current status</div>
                </div>
            </div>
        </div>
    `;
    
    // Visual timeline
    if (timeline.length > 0) {
        html += '<div class="timeline-visualization">';
        html += '<h4>Phase Timeline</h4>';
        html += '<div class="timeline-chart">';
        
        // Calculate all phase data first, but filter out "complete" status phases for the timeline bar
        const allPhaseData = timeline.map((phase, index) => {
            const startTime = parseServerTime(phase.started_at);
            
            // Check if this is the last phase of a finished job
            const isLastPhase = index === timeline.length - 1;
            const jobFinished = ['complete', 'error', 'cancelled', 'failed'].includes(timelineData.current_status);
            const shouldInferEndTime = isLastPhase && jobFinished && !phase.ended_at;
            
            let duration, endTime, isActive;
            
            if (phase.ended_at) {
                // Phase has explicit end time
                duration = phase.duration_seconds;
                endTime = parseServerTime(phase.ended_at);
                isActive = false;
            } else if (shouldInferEndTime) {
                // Infer end time for last phase of finished job
                endTime = getJobEndTime({
                    status: timelineData.current_status,
                    timeline: timeline,
                    completed_at: timelineData.completed_at,
                    finished_at: timelineData.finished_at,
                    updated_at: timelineData.updated_at
                });
                
                // Calculate duration if not provided
                if (phase.duration_seconds) {
                    duration = phase.duration_seconds;
                } else {
                    duration = Math.floor((endTime - startTime) / 1000);
                }
                isActive = false;
            } else {
                // Phase is genuinely in progress
                endTime = new Date();
                duration = phase.duration_seconds || Math.floor((new Date() - startTime) / 1000);
                isActive = true;
            }
            
            return { phase, duration, isActive };
        });
        
        // Filter out "complete" phases for the timeline bar (they're just end states)
        const phaseData = allPhaseData.filter(({ phase }) => phase.status !== 'complete');
        
        // Calculate proper widths based on actual durations
        const totalDuration = phaseData.reduce((total, { duration }) => total + (duration || 0), 0);
        
        if (totalDuration === 0) {
            // If all phases have 0 duration, give them equal small widths
            var normalizedWidths = new Array(phaseData.length).fill(100 / phaseData.length);
        } else {
            // Calculate proportional widths, but give 0-duration phases a tiny fixed width
            const meaningfulDuration = phaseData.reduce((total, { duration }) => total + (duration >= 1 ? duration : 0), 0);
            const tinyPhases = phaseData.filter(({ duration }) => !duration || duration < 1);
            const tinyPhaseWidth = 0.5; // 0.5% each for tiny phases
            const availableWidth = 100 - (tinyPhases.length * tinyPhaseWidth);
            
            var normalizedWidths = phaseData.map(({ duration }) => {
                if (!duration || duration < 1) {
                    return tinyPhaseWidth; // Tiny width for 0-duration phases
                }
                return meaningfulDuration > 0 ? (duration / meaningfulDuration) * availableWidth : availableWidth / phaseData.length;
            });
        }
        
        // Generate HTML for each phase
        phaseData.forEach(({ phase, duration, isActive }, index) => {
            const widthPercent = normalizedWidths[index] || 0.5;
            
            html += `
                <div class="timeline-phase-bar ${isActive ? 'active' : ''}" 
                     style="width: ${widthPercent}%; background-color: ${getPhaseColor(phase.status)}">
                    <div class="timeline-phase-info">
                        <div class="timeline-phase-name">
                            ${getPhaseIcon(phase.status)} ${getShortPhaseLabel(phase.status)}
                        </div>
                        <div class="timeline-phase-duration">
                            ${duration !== undefined && duration !== null ? formatDuration(duration) : (isActive ? 'Active' : 'Unknown')}
                        </div>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        html += '</div>';
        
        // Detailed phase table
        html += '<div class="timeline-details">';
        html += '<h4>Phase Details</h4>';
        html += '<div class="timeline-table">';
        html += `
            <div class="timeline-table-header">
                <div>Phase</div>
                <div>Started</div>
                <div>Ended</div>
                <div>Duration</div>
            </div>
        `;
        
        timeline.forEach((phase, index) => {
            const startTime = formatDetailedTimestamp(phase.started_at);
            
            // Check if this is the last phase of a finished job
            const isLastPhase = index === timeline.length - 1;
            const jobFinished = ['complete', 'error', 'cancelled', 'failed'].includes(timelineData.current_status);
            const shouldInferEndTime = isLastPhase && jobFinished && !phase.ended_at;
            
            let endTime, duration, isActive;
            
            if (phase.ended_at) {
                // Phase has explicit end time
                endTime = formatDetailedTimestamp(phase.ended_at);
                duration = phase.duration_seconds ? formatDuration(phase.duration_seconds) : 'Unknown';
                isActive = false;
            } else if (shouldInferEndTime) {
                // Infer end time for last phase of finished job
                const jobEndTime = getJobEndTime({
                    status: timelineData.current_status,
                    timeline: timeline,
                    completed_at: timelineData.completed_at,
                    finished_at: timelineData.finished_at,
                    updated_at: timelineData.updated_at
                });
                endTime = formatDetailedTimestamp(jobEndTime.toISOString());
                
                // Calculate duration if not provided
                if (phase.duration_seconds) {
                    duration = formatDuration(phase.duration_seconds);
                } else {
                    const startDate = parseServerTime(phase.started_at);
                    const durationSeconds = Math.floor((jobEndTime - startDate) / 1000);
                    duration = formatDuration(Math.max(0, durationSeconds));
                }
                isActive = false;
            } else {
                // Phase is genuinely in progress
                endTime = 'In Progress';
                duration = 'In Progress';
                isActive = true;
            }
            
            html += `
                <div class="timeline-table-row ${isActive ? 'active' : ''}">
                    <div class="timeline-phase-cell">
                        ${getPhaseIcon(phase.status)} ${formatStatus(phase.status)}
                    </div>
                    <div>${startTime}</div>
                    <div>${endTime}</div>
                    <div>${duration}</div>
                </div>
            `;
        });
        
        html += '</div>';
        html += '</div>';
    }
    
    return html;
}

function formatDetailedTimestamp(isoString) {
    try {
        const date = parseServerTime(isoString);
        
        // Validate the parsed date
        if (isNaN(date.getTime())) {
            console.warn('Invalid detailed timestamp:', isoString);
            return 'Invalid Time';
        }
        
        // Format with consistent local timezone display
        return date.toLocaleString([], {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false  // Use 24-hour format for consistency
        });
    } catch (error) {
        console.error('Error formatting detailed timestamp:', isoString, error);
        return 'Error';
    }
}

function formatDuration(seconds) {
    if (seconds < 60) {
        return `${seconds}s`;
    } else if (seconds < 3600) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}m ${remainingSeconds}s`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const remainingMinutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${remainingMinutes}m`;
    }
}

function closeTimelineModal() {
    const modal = document.getElementById('timeline-modal');
    if (modal) {
        modal.remove();
    }
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
    
    if (status === 'reviewing') {
        // For reviewing status, show option to complete review (no instrumental selection yet)
        actions.push(`<button onclick="completeReview('${jobId}')" class="btn btn-success">✅ Complete Review</button>`);
        // Also allow continuing the review
        const reviewUrl = `https://lyrics.nomadkaraoke.com/?baseApiUrl=${API_BASE_URL}/corrections/${jobId}`;
        actions.push(`<a href="${reviewUrl}" target="_blank" class="btn btn-secondary">📝 Continue Review</a>`);
    }
    
    if (status === 'ready_for_finalization') {
        // For ready_for_finalization status, show option to choose instrumental and finalize
        actions.push(`<button onclick="showInstrumentalSelectionForJob('${jobId}')" class="btn btn-success">🎵 Choose Instrumental & Finalize</button>`);
    }
    
    if (status === 'complete') {
        actions.push(`<button onclick="downloadVideo('${jobId}')" class="btn btn-primary">📥 Download MP4 Video</button>`);
        actions.push(`<button onclick="downloadAll('${jobId}')" class="btn btn-success">📦 Download All Zip</button>`);
        actions.push(`<button onclick="showFilesModal('${jobId}')" class="btn btn-info">📁 View All Files</button>`);
    }
    
    if (status === 'error') {
        actions.push(`<button onclick="retryJob('${jobId}')" class="btn btn-warning">🔄 Retry</button>`);
    }
    
    // Always available actions
    actions.push(`<button onclick="deleteJob('${jobId}')" class="btn btn-danger">🗑️ Delete</button>`);
    
    return actions.join(' ');
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
        autoScrollEnabled = false;
        const autoScrollBtn = document.getElementById('auto-scroll-btn');
        if (autoScrollBtn) {
            autoScrollBtn.classList.remove('toggle-active');
            autoScrollBtn.textContent = '⏸️ Manual';
            autoScrollBtn.title = 'Auto-scroll disabled - click to enable';
        }
        
        // Force reflow and show modal
        modal.offsetHeight; // Trigger reflow
        modal.style.display = 'flex';
        
        setTimeout(async () => {
            scrollToBottom();
        }, 1000);

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
    autoScrollEnabled = false;
    const autoScrollBtn = document.getElementById('auto-scroll-btn');
    if (autoScrollBtn) {
        autoScrollBtn.classList.remove('toggle-active');
        autoScrollBtn.textContent = '⏸️ Manual';
        autoScrollBtn.title = 'Auto-scroll disabled - click to enable';
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
            const statusResponse = await authenticatedFetch(`${API_BASE_URL}/jobs/${jobId}`);
            if (!statusResponse) return;
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
            authenticatedFetch(`${API_BASE_URL}/jobs/${jobId}`),
            authenticatedFetch(`${API_BASE_URL}/logs/${jobId}`)
        ]);
        
        if (!statusResponse || !logsResponse) return; // Auth failed, already handled
        
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
            const timestamp = parseServerTime(log.timestamp).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            });
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
        const response = await authenticatedFetch(`${API_BASE_URL}/admin/clear-errors`, {
            method: 'POST'
        });
        
        if (!response) return; // Auth failed, already handled
        
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

async function viewCacheStats() {
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/admin/cache/stats`);
        
        if (!response) return; // Auth failed, already handled
        
        if (response.ok) {
            const stats = await response.json();
            showCacheStatsModal(stats);
        } else {
            const stats = await response.json();
            showError(stats.error || 'Failed to load cache stats');
        }
    } catch (error) {
        console.error('Error loading cache stats:', error);
        showError('Failed to load cache stats: ' + error.message);
    }
}

async function clearCache() {
    if (!confirm('Are you sure you want to clear old cache files (90+ days)? This cannot be undone.')) return;
    
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/admin/cache/clear`, {
            method: 'POST'
        });
        
        if (!response) return; // Auth failed, already handled
        const result = await response.json();
        
        if (result.status === 'success') {
            showSuccess(result.message);
            // Refresh cache stats if modal is open
            const modal = document.getElementById('cache-stats-modal');
            if (modal && modal.style.display !== 'none') {
                viewCacheStats();
            }
        } else {
            showError(result.message || 'Failed to clear cache');
        }
    } catch (error) {
        console.error('Error clearing cache:', error);
        showError('Failed to clear cache: ' + error.message);
    }
}

async function warmCache() {
    try {
        showInfo('Initiating cache warming...');
        
        const response = await authenticatedFetch(`${API_BASE_URL}/admin/cache/warm`, {
            method: 'POST'
        });
        
        if (!response) return; // Auth failed, already handled
        const result = await response.json();
        
        if (result.status === 'success') {
            showSuccess(result.message);
        } else {
            showError(result.message || 'Failed to warm cache');
        }
    } catch (error) {
        console.error('Error warming cache:', error);
        showError('Failed to warm cache: ' + error.message);
    }
}

async function loadAudioShakeCache() {
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/admin/cache/audioshake`);
        
        if (!response) return []; // Auth failed, return empty array
        const result = await response.json();
        
        if (response.ok && result.status === 'success') {
            return result.cached_responses;
        } else {
            console.error('Failed to load AudioShake cache:', result);
            return [];
        }
    } catch (error) {
        console.error('Error loading AudioShake cache:', error);
        return [];
    }
}

async function deleteAudioShakeCache(audioHash) {
    if (!confirm(`Are you sure you want to delete the cached AudioShake response for hash ${audioHash}?`)) return;
    
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/admin/cache/audioshake/${audioHash}`, {
            method: 'DELETE'
        });
        
        if (!response) return; // Auth failed, already handled
        const result = await response.json();
        
        if (result.status === 'success') {
            showSuccess(result.message);
            // Refresh cache stats if modal is open
            const modal = document.getElementById('cache-stats-modal');
            if (modal && modal.style.display !== 'none') {
                viewCacheStats();
            }
        } else {
            showError(result.message || 'Failed to delete cached response');
        }
    } catch (error) {
        console.error('Error deleting cached response:', error);
        showError('Failed to delete cached response: ' + error.message);
    }
}

function showCacheStatsModal(stats) {
    const modal = document.getElementById('cache-stats-modal');
    if (!modal) {
        console.error('Cache stats modal not found');
        return;
    }
    
    // Update cache stats content
    updateCacheStatsContent(stats);
    
    // Show modal
    modal.style.display = 'flex';
}

function closeCacheStatsModal() {
    const modal = document.getElementById('cache-stats-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function updateCacheStatsContent(stats) {
    const statsContainer = document.getElementById('cache-stats-content');
    if (!statsContainer) return;
    
    // Load AudioShake cache data
    const audioShakeCache = await loadAudioShakeCache();
    
    const formatBytes = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };
    
    const formatFileCount = (count) => {
        return count === 1 ? '1 file' : `${count} files`;
    };
    
    let html = `
        <div class="cache-overview">
            <h4>📊 Cache Overview</h4>
            <div class="cache-summary">
                <div class="cache-stat">
                    <span class="cache-stat-label">Total Files:</span>
                    <span class="cache-stat-value">${stats.total_files}</span>
                </div>
                <div class="cache-stat">
                    <span class="cache-stat-label">Total Size:</span>
                    <span class="cache-stat-value">${formatBytes(stats.total_size_bytes)} (${stats.total_size_gb} GB)</span>
                </div>
            </div>
        </div>
        
        <div class="cache-directories">
            <h4>📁 Cache Directories</h4>
            <div class="cache-dirs-grid">
    `;
    
    // Cache directory stats
    const dirLabels = {
        'audio_hashes': '🎵 Audio Hashes',
        'audioshake_responses': '🔊 AudioShake API',
        'models': '🤖 Model Files',
        'transcriptions': '📝 Transcriptions'
    };
    
    Object.entries(stats.cache_directories || {}).forEach(([dirName, dirStats]) => {
        const label = dirLabels[dirName] || dirName;
        html += `
            <div class="cache-dir-card">
                <div class="cache-dir-header">${label}</div>
                <div class="cache-dir-stats">
                    <div>${formatFileCount(dirStats.file_count)}</div>
                    <div>${formatBytes(dirStats.size_bytes)}</div>
                </div>
            </div>
        `;
    });
    
    html += `
            </div>
        </div>
    `;
    
    // AudioShake cache details
    if (audioShakeCache.length > 0) {
        html += `
            <div class="audioshake-cache">
                <h4>🔊 AudioShake Cache Details</h4>
                <div class="audioshake-cache-list">
        `;
        
        audioShakeCache.forEach(item => {
            const timestamp = formatTimestamp(item.timestamp);
            const shortHash = item.audio_hash.substring(0, 12) + '...';
            
            html += `
                <div class="audioshake-cache-item">
                    <div class="cache-item-info">
                        <div class="cache-item-hash">${shortHash}</div>
                        <div class="cache-item-timestamp">${timestamp}</div>
                        <div class="cache-item-size">${formatBytes(item.file_size_bytes)}</div>
                    </div>
                    <button onclick="deleteAudioShakeCache('${item.audio_hash}')" class="btn btn-danger btn-sm">
                        🗑️ Delete
                    </button>
                </div>
            `;
        });
        
        html += `
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="audioshake-cache">
                <h4>🔊 AudioShake Cache Details</h4>
                <p class="no-cache">No AudioShake responses cached yet.</p>
            </div>
        `;
    }
    
    // Cache actions
    html += `
        <div class="cache-actions">
            <h4>🛠️ Cache Management</h4>
            <div class="cache-actions-grid">
                <button onclick="clearCache()" class="btn btn-warning">
                    🧹 Clear Old Cache (90+ days)
                </button>
                <button onclick="warmCache()" class="btn btn-info">
                    🔥 Warm Cache
                </button>
                <button onclick="viewCacheStats()" class="btn btn-secondary">
                    🔄 Refresh Stats
                </button>
            </div>
        </div>
    `;
    
    statsContainer.innerHTML = html;
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
    
    // Check if user has remaining uses for retry
    if (currentUser && currentUser.remaining_uses === 0) {
        showError('You have no remaining uses. Cannot retry job.');
        return;
    }
    
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/jobs/${jobId}/retry`, {
            method: 'POST'
        });
        
        if (!response) return; // Auth failed, already handled
        
        const result = await response.json();
        
        if (result.status === 'success') {
            showSuccess(`Job ${jobId} retry initiated`);
            // Update remaining uses if provided
            if (currentUser && currentUser.remaining_uses > 0) {
                currentUser.remaining_uses -= 1;
                updateUserStatusBar(currentUser);
            }
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
        const response = await authenticatedFetch(`${API_BASE_URL}/jobs/${jobId}`, {
            method: 'DELETE'
        });
        
        if (!response) return; // Auth failed, already handled
        
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

async function reviewLyrics(jobId) {
    try {
        showNotification('Starting review server...', 'info');
        
        // Call the start review endpoint
        const response = await authenticatedFetch(`${API_BASE_URL}/review/${jobId}/start`, {
            method: 'POST'
        });
        
        if (!response) return; // Auth failed, already handled
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.review_url) {
            showNotification('Review server started! Opening review interface...', 'success');
            // Open the review interface
            window.open(result.review_url, '_blank');
        } else {
            throw new Error('No review URL returned from server');
        }
    } catch (error) {
        console.error('Error starting review:', error);
        showNotification(`Error starting review: ${error.message}`, 'error');
    }
}

async function completeReview(jobId) {
    if (!confirm('Complete the review without additional corrections? This will generate the video and move to instrumental selection.')) {
        return;
    }
    
    try {
        showInfo('Completing review and generating video...');
        
        const response = await authenticatedFetch(`${API_BASE_URL}/corrections/${jobId}/complete`, {
            method: 'POST',
            body: JSON.stringify({
                corrected_data: {} // Empty object indicates no additional corrections
            })
        });
        
        if (!response) return; // Auth failed, already handled
        
        if (response.ok) {
            const result = await response.json();
            showSuccess(result.message);
            await loadJobs(); // Refresh to show updated status
        } else {
            const error = await response.json();
            showError('Error completing review: ' + error.detail);
        }
    } catch (error) {
        console.error('Error completing review:', error);
        showError('Error completing review: ' + error.message);
    }
}

function downloadVideo(jobId) {
    const token = getAuthToken();
    if (!token) {
        showError('Authentication required for downloads');
        return;
    }
    
    // Create download URL with authentication token
    const url = `${API_BASE_URL}/jobs/${jobId}/download?token=${encodeURIComponent(token)}`;
    window.open(url, '_blank');
}

function downloadAll(jobId) {
    // Use the existing downloadAllFiles function
    downloadAllFiles(jobId);
}

// Form submission
async function submitJob() {
    // Check if user is authenticated and has remaining uses
    if (!currentUser) {
        showError('You must be logged in to submit jobs');
        return;
    }
    
    if (currentUser.remaining_uses === 0) {
        showError('You have no remaining uses. Please contact support or purchase additional access.');
        return;
    }
    
    // Determine which input mode is active
    const fileMode = document.getElementById('file-upload-mode');
    const youtubeMode = document.getElementById('youtube-url-mode');
    const isYouTubeMode = youtubeMode.classList.contains('active');
    
    const submitBtn = document.querySelector('.submit-btn');
    const originalText = submitBtn.textContent;
    
    try {
        submitBtn.disabled = true;
        
        if (isYouTubeMode) {
            // Handle YouTube URL submission
            await submitYouTubeJob(submitBtn);
        } else {
            // Handle file upload submission
            await submitFileJob(submitBtn);
        }
        
    } catch (error) {
        console.error('Error submitting job:', error);
        showError('Failed to submit job: ' + error.message);
    } finally {
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    }
}

async function submitYouTubeJob(submitBtn) {
    submitBtn.textContent = 'Processing URL...';
    
    // Get YouTube URL and validate
    const youtubeUrl = document.getElementById('youtube-url').value.trim();
    if (!youtubeUrl) {
        showError('Please enter a YouTube URL');
        return;
    }
    
    // Validate YouTube URL format
    const youtubePattern = /^https:\/\/(www\.)?(youtube\.com\/(watch\?v=|embed\/)|youtu\.be\/).+/;
    if (!youtubePattern.test(youtubeUrl)) {
        showError('Please enter a valid YouTube URL (e.g., https://www.youtube.com/watch?v=...)');
        return;
    }
    
    // Get optional cookies
    const cookies = document.getElementById('youtube-cookies').value.trim();
    
    // Prepare request data
    const requestData = {
        url: youtubeUrl
    };
    
    if (cookies) {
        requestData.cookies = cookies;
    }
    
    const response = await fetch(`${API_BASE_URL}/submit-youtube`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(requestData)
    });
    
    if (!response.ok) {
        if (response.status === 401) {
            setAuthToken(null);
            currentUser = null;
            showAuthSection();
            showError('Session expired. Please log in again.');
            return;
        }
    }
    
    const result = await response.json();
    
    if (response.status === 200) {
        showSuccess(`YouTube job submitted successfully! Job ID: ${result.job_id}`);
        
        // Update user's remaining uses if provided
        if (result.remaining_uses !== undefined) {
            currentUser.remaining_uses = result.remaining_uses;
            updateUserStatusBar(currentUser);
        }
        
        // Clear form
        document.getElementById('youtube-url').value = '';
        document.getElementById('youtube-cookies').value = '';
        
        // Hide cookies section
        const cookiesSection = document.getElementById('cookies-help-section');
        if (cookiesSection.style.display !== 'none') {
            toggleCookiesSection();
        }
        
        // Refresh jobs list and handle post-submission tasks
        await handlePostSubmission();
        
    } else {
        // Handle specific error messages for YouTube issues
        if (result.message && result.message.includes('blocked') || result.message.includes('bot')) {
            showError(`${result.message}\n\nTip: Try providing browser cookies to help bypass YouTube restrictions.`);
            // Auto-show cookies section to help user
            const cookiesSection = document.getElementById('cookies-help-section');
            if (cookiesSection.style.display === 'none') {
                toggleCookiesSection();
            }
        } else {
            showError(result.message || 'Failed to submit YouTube job');
        }
    }
}

async function submitFileJob(submitBtn) {
    submitBtn.textContent = 'Uploading...';
    
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
    
    // Create authenticated request headers for form data
    const authHeaders = {};
    const token = getAuthToken();
    if (token) {
        authHeaders['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(`${API_BASE_URL}/submit-file`, {
        method: 'POST',
        headers: authHeaders,
        body: formData
    });
    
    if (!response.ok) {
        if (response.status === 401) {
            setAuthToken(null);
            currentUser = null;
            showAuthSection();
            showError('Session expired. Please log in again.');
            return;
        }
    }
    
    const result = await response.json();
    
    if (response.status === 200) {
        const usingCustomStyles = customStylesVisible && (stylesFile || stylesArchive);
        const stylesMessage = usingCustomStyles ? ' with custom styles' : ' with default Nomad styles';
        showSuccess(`Job submitted successfully${stylesMessage}! Job ID: ${result.job_id}`);
        
        // Update user's remaining uses if provided
        if (result.remaining_uses !== undefined) {
            currentUser.remaining_uses = result.remaining_uses;
            updateUserStatusBar(currentUser);
        }
        
        // Clear form
        document.getElementById('audio-file').value = '';
        document.getElementById('artist').value = '';
        document.getElementById('title').value = '';
        
        // Only clear custom styles if they were visible
        if (customStylesVisible) {
            document.getElementById('styles-file').value = '';
            document.getElementById('styles-archive').value = '';
        }
        
        // Refresh jobs list and handle post-submission tasks
        await handlePostSubmission();
        
    } else {
        showError(result.message || 'Failed to submit job');
    }
}

async function handlePostSubmission() {
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
}

// Input mode switching functions
function switchInputMode(mode) {
    const fileTab = document.getElementById('file-mode-tab');
    const youtubeTab = document.getElementById('youtube-mode-tab');
    const fileSection = document.getElementById('file-upload-mode');
    const youtubeSection = document.getElementById('youtube-url-mode');
    
    if (mode === 'file') {
        // Switch to file upload mode
        fileTab.classList.add('active');
        youtubeTab.classList.remove('active');
        fileSection.classList.add('active');
        youtubeSection.classList.remove('active');
        
        // Clear YouTube form
        document.getElementById('youtube-url').value = '';
        document.getElementById('youtube-cookies').value = '';
        
        // Hide cookies section if visible
        const cookiesSection = document.getElementById('cookies-help-section');
        if (cookiesSection.style.display !== 'none') {
            cookiesSection.style.display = 'none';
            document.getElementById('toggle-cookies-btn').textContent = '🍪 Help with Access Issues';
        }
        
    } else if (mode === 'youtube') {
        // Switch to YouTube URL mode
        youtubeTab.classList.add('active');
        fileTab.classList.remove('active');
        youtubeSection.classList.add('active');
        fileSection.classList.remove('active');
        
        // Clear file upload form
        document.getElementById('audio-file').value = '';
        document.getElementById('artist').value = '';
        document.getElementById('title').value = '';
    }
}

// Cookies section toggle function
function toggleCookiesSection() {
    const cookiesSection = document.getElementById('cookies-help-section');
    const toggleBtn = document.getElementById('toggle-cookies-btn');
    
    if (cookiesSection.style.display === 'none') {
        cookiesSection.style.display = 'block';
        toggleBtn.textContent = '🍪 Hide Cookie Help';
    } else {
        cookiesSection.style.display = 'none';
        toggleBtn.textContent = '🍪 Help with Access Issues';
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
function parseServerTime(timestamp) {
    // Properly parse server timestamps that are in UTC and convert to local time
    if (!timestamp) return new Date();
    
    // Convert to string if it's not already
    const timestampStr = String(timestamp);
    
    try {
        // Handle various timestamp formats
        let date;
        
        // If timestamp already has timezone info (Z, +, or -), parse directly
        if (timestampStr.includes('Z') || timestampStr.includes('+') || 
            (timestampStr.includes('-') && timestampStr.lastIndexOf('-') > 10)) {
            date = new Date(timestampStr);
        } else {
            // No timezone info - assume UTC and add 'Z'
            date = new Date(timestampStr + 'Z');
        }
        
        // Validate the parsed date
        if (isNaN(date.getTime())) {
            console.warn('Invalid timestamp parsed:', timestampStr);
            return new Date(); // Return current time as fallback
        }
        
        return date;
    } catch (error) {
        console.error('Error parsing timestamp:', timestampStr, error);
        return new Date(); // Return current time as fallback
    }
}

function formatStatus(status) {
    const statusMap = {
        'queued': 'Queued',
        'processing': 'Processing',
        'processing_audio': 'Processing Audio',
        'transcribing': 'Transcribing Lyrics',
        'awaiting_review': 'Awaiting Review',
        'reviewing': 'Reviewing',
        'ready_for_finalization': 'Ready for Finalization',
        'rendering': 'Rendering Video',
        'finalizing': 'Finalizing',
        'complete': 'Complete',
        'error': 'Error'
    };
    return statusMap[status] || status;
}

function formatTimestamp(timestamp) {
    try {
        const date = parseServerTime(timestamp);
        
        // Validate the parsed date
        if (isNaN(date.getTime())) {
            console.warn('Invalid timestamp for formatting:', timestamp);
            return 'Invalid Time';
        }
        
        // Format with explicit local timezone display options
        return date.toLocaleString([], {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    } catch (error) {
        console.error('Error formatting timestamp:', timestamp, error);
        return 'Error';
    }
}

function calculateDuration(createdAt) {
    if (!createdAt) return 'Unknown';
    
    try {
        const now = new Date();
        const startTime = parseServerTime(createdAt);
        const diffMs = now - startTime;
        
        // Debug logging for timezone issues
        if (diffMs < 0) {
            console.warn('Negative duration in calculateDuration:', {
                startTime: startTime.toISOString(),
                now: now.toISOString(),
                originalTimestamp: createdAt,
                diffMs,
                userTimezone: Intl.DateTimeFormat().resolvedOptions().timeZone
            });
            return '0s'; // Handle negative durations
        }
        
        const seconds = Math.floor(diffMs / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);
        
        if (days > 0) {
            return `${days}d ${hours % 24}h`;
        } else if (hours > 0) {
            return `${hours}h ${minutes % 60}m`;
        } else if (minutes > 0) {
            return `${minutes}m ${seconds % 60}s`;
        } else {
            return `${seconds}s`;
        }
    } catch (error) {
        console.error('Error in calculateDuration:', error, createdAt);
        return 'Error';
    }
}

function formatDurationWithStatus(job) {
    const duration = getTotalJobDuration(job); // Use the corrected duration calculation
    const status = job.status || 'unknown';
    
    // Different duration labels based on status
    if (status === 'queued') {
        return `⏱️ ${duration} waiting`;
    } else if (['processing_audio', 'transcribing', 'rendering'].includes(status)) {
        return `⏳ ${duration} running`;
    } else if (status === 'awaiting_review') {
        return `⏸️ ${duration} awaiting review`;
    } else if (status === 'complete') {
        return `✅ ${duration} total`;
    } else if (status === 'error') {
        return `❌ ${duration} before error`;
    } else {
        return `📅 ${duration}`;
    }
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

// Files modal functions
async function showFilesModal(jobId) {
    try {
        showInfo('Loading files...');
        
        const response = await authenticatedFetch(`${API_BASE_URL}/jobs/${jobId}/files`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const filesData = await response.json();
        
        // Create and show the files modal
        createFilesModal(filesData);
        
    } catch (error) {
        console.error('Error loading files:', error);
        showError(`Error loading files: ${error.message}`);
    }
}

function createFilesModal(filesData) {
    const modalHtml = `
        <div id="files-modal" class="modal">
            <div class="modal-content files-modal-content">
                <div class="modal-header">
                    <h3 class="modal-title">📁 Files for ${filesData.artist} - ${filesData.title}</h3>
                    <div class="modal-controls">
                        <button onclick="downloadAllFiles('${filesData.job_id}')" class="modal-control-btn primary" title="Download all files as ZIP">
                            📦 Download All (${filesData.total_size_mb} MB)
                        </button>
                        <button onclick="closeFilesModal()" class="modal-close">✕</button>
                    </div>
                </div>
                <div class="modal-body">
                    <div class="files-summary">
                        <div class="files-stats">
                            <span class="files-stat"><strong>${filesData.total_files}</strong> files</span>
                            <span class="files-stat"><strong>${filesData.total_size_mb} MB</strong> total</span>
                            <span class="files-stat">Status: <strong>${formatStatus(filesData.status)}</strong></span>
                        </div>
                    </div>
                    
                    <div class="files-categories">
                        ${createFilesCategoriesHtml(filesData)}
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove any existing files modal
    const existingModal = document.getElementById('files-modal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Show modal
    const modal = document.getElementById('files-modal');
    modal.style.display = 'flex';
    
    // Add click outside to close
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeFilesModal();
        }
    });
}

function createFilesCategoriesHtml(filesData) {
    if (!filesData.categories || Object.keys(filesData.categories).length === 0) {
        return '<p class="no-files">No files found for this job.</p>';
    }
    
    let html = '';
    
    Object.entries(filesData.categories).forEach(([categoryId, category]) => {
        html += `
            <div class="file-category">
                <div class="file-category-header">
                    <h4>${category.name}</h4>
                    <span class="file-category-count">${category.count} files</span>
                </div>
                <p class="file-category-description">${category.description}</p>
                <div class="file-category-files">
                    ${category.files.map(file => createFileItemHtml(filesData.job_id, file)).join('')}
                </div>
            </div>
        `;
    });
    
    return html;
}

function createFileItemHtml(jobId, file) {
    const iconClass = getFileIcon(file.mime_type);
    const sizeDisplay = file.size_mb > 0.1 ? `${file.size_mb} MB` : `${Math.round(file.size / 1024)} KB`;
    
    return `
        <div class="file-item">
            <div class="file-info">
                <div class="file-name">
                    <span class="file-icon">${iconClass}</span>
                    <span class="file-name-text">${file.name}</span>
                </div>
                <div class="file-details">
                    <span class="file-size">${sizeDisplay}</span>
                    <span class="file-date">${formatFileDate(file.modified)}</span>
                </div>
            </div>
            <div class="file-actions">
                ${createFileActionButtons(jobId, file)}
            </div>
        </div>
    `;
}

function createFileActionButtons(jobId, file) {
    const buttons = [];
    
    // Download button
    buttons.push(`
        <button onclick="downloadFile('${jobId}', '${escapeHtml(file.path)}', '${escapeHtml(file.name)}')" 
                class="btn btn-sm btn-primary" title="Download this file">
            📥 Download
        </button>
    `);
    
    // Preview button for videos
    if (file.mime_type.startsWith('video/')) {
        buttons.push(`
            <button onclick="previewVideo('${jobId}', '${escapeHtml(file.path)}', '${escapeHtml(file.name)}')" 
                    class="btn btn-sm btn-secondary" title="Preview video">
                ▶️ Preview
            </button>
        `);
    }
    
    // Preview button for audio
    if (file.mime_type.startsWith('audio/')) {
        buttons.push(`
            <button onclick="previewAudio('${jobId}', '${escapeHtml(file.path)}', '${escapeHtml(file.name)}')" 
                    class="btn btn-sm btn-secondary" title="Preview audio">
                🔊 Preview
            </button>
        `);
    }
    
    return buttons.join(' ');
}

function getFileIcon(mimeType) {
    if (mimeType.startsWith('video/')) return '🎬';
    if (mimeType.startsWith('audio/')) return '🎵';
    if (mimeType.startsWith('image/')) return '🖼️';
    if (mimeType === 'application/zip') return '📦';
    if (mimeType === 'text/plain') return '📄';
    if (mimeType === 'application/json') return '📋';
    return '📁';
}

function formatFileDate(dateString) {
    try {
        const date = parseServerTime(dateString);
        
        if (isNaN(date.getTime())) {
            console.warn('Invalid file date:', dateString);
            return 'Invalid Date';
        }
        
        return date.toLocaleDateString([], {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        }) + ' ' + date.toLocaleTimeString([], {
            hour: '2-digit', 
            minute: '2-digit',
            hour12: false
        });
    } catch (error) {
        console.error('Error formatting file date:', dateString, error);
        return 'Error';
    }
}

function closeFilesModal() {
    const modal = document.getElementById('files-modal');
    if (modal) {
        modal.remove();
    }
}

// File action functions
async function downloadFile(jobId, filePath, fileName) {
    try {
        const token = getAuthToken();
        if (!token) {
            showError('Authentication required for downloads');
            return;
        }
        
        // Create download URL with authentication token
        const url = `${API_BASE_URL}/jobs/${jobId}/files/${encodeURIComponent(filePath)}?token=${encodeURIComponent(token)}`;
        
        // Create a link and trigger download
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        link.target = '_blank'; // Open in new tab to handle any potential auth redirects
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showSuccess(`Downloading ${fileName}...`);
        
    } catch (error) {
        console.error('Error downloading file:', error);
        showError(`Error downloading file: ${error.message}`);
    }
}

async function downloadAllFiles(jobId) {
    try {
        const token = getAuthToken();
        if (!token) {
            showError('Authentication required for downloads');
            return;
        }
        
        // Create download URL with authentication token
        const url = `${API_BASE_URL}/jobs/${jobId}/download-all?token=${encodeURIComponent(token)}`;
        
        // Create a link and trigger download
        const link = document.createElement('a');
        link.href = url;
        link.download = `karaoke-${jobId}-complete.zip`;
        link.target = '_blank'; // Open in new tab to handle any potential auth redirects
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showSuccess('Downloading complete package...');
        
    } catch (error) {
        console.error('Error downloading all files:', error);
        showError(`Error downloading files: ${error.message}`);
    }
}

function previewVideo(jobId, filePath, fileName) {
    const token = getAuthToken();
    if (!token) {
        showError('Authentication required for video preview');
        return;
    }
    
    // Create authenticated video URL
    const videoUrl = `${API_BASE_URL}/jobs/${jobId}/files/${encodeURIComponent(filePath)}?token=${encodeURIComponent(token)}`;
    
    const previewHtml = `
        <div id="video-preview-modal" class="modal">
            <div class="modal-content video-preview-content">
                <div class="modal-header">
                    <h3 class="modal-title">🎬 ${fileName}</h3>
                    <div class="modal-controls">
                        <button onclick="closeVideoPreview()" class="modal-close">✕</button>
                    </div>
                </div>
                <div class="modal-body">
                    <video controls class="preview-video" preload="metadata">
                        <source src="${videoUrl}" type="video/mp4">
                        <source src="${videoUrl}" type="video/x-matroska">
                        Your browser does not support the video tag.
                    </video>
                    <div class="preview-actions">
                        <button onclick="downloadFile('${jobId}', '${escapeHtml(filePath)}', '${escapeHtml(fileName)}')" 
                                class="btn btn-primary">📥 Download Video</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing preview
    const existingPreview = document.getElementById('video-preview-modal');
    if (existingPreview) {
        existingPreview.remove();
    }
    
    document.body.insertAdjacentHTML('beforeend', previewHtml);
    
    const modal = document.getElementById('video-preview-modal');
    modal.style.display = 'flex';
    
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeVideoPreview();
        }
    });
}

function previewAudio(jobId, filePath, fileName) {
    const token = getAuthToken();
    if (!token) {
        showError('Authentication required for audio preview');
        return;
    }
    
    // Create authenticated audio URL
    const audioUrl = `${API_BASE_URL}/jobs/${jobId}/files/${encodeURIComponent(filePath)}?token=${encodeURIComponent(token)}`;
    
    const previewHtml = `
        <div id="audio-preview-modal" class="modal">
            <div class="modal-content audio-preview-content">
                <div class="modal-header">
                    <h3 class="modal-title">🎵 ${fileName}</h3>
                    <div class="modal-controls">
                        <button onclick="closeAudioPreview()" class="modal-close">✕</button>
                    </div>
                </div>
                <div class="modal-body">
                    <audio controls class="preview-audio" preload="metadata">
                        <source src="${audioUrl}">
                        Your browser does not support the audio tag.
                    </audio>
                    <div class="preview-actions">
                        <button onclick="downloadFile('${jobId}', '${escapeHtml(filePath)}', '${escapeHtml(fileName)}')" 
                                class="btn btn-primary">📥 Download Audio</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing preview
    const existingPreview = document.getElementById('audio-preview-modal');
    if (existingPreview) {
        existingPreview.remove();
    }
    
    document.body.insertAdjacentHTML('beforeend', previewHtml);
    
    const modal = document.getElementById('audio-preview-modal');
    modal.style.display = 'flex';
    
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeAudioPreview();
        }
    });
}

function closeVideoPreview() {
    const modal = document.getElementById('video-preview-modal');
    if (modal) {
        modal.remove();
    }
}

function closeAudioPreview() {
    const modal = document.getElementById('audio-preview-modal');
    if (modal) {
        modal.remove();
    }
}

// Instrumental Selection Modal Functions
let selectedInstrumental = null;
let currentReviewData = null;

async function showInstrumentalSelectionModal(jobId, correctedData) {
    try {
        // Store the corrected data for later use
        currentReviewData = correctedData;
        
        const modal = document.getElementById('instrumental-selection-modal');
        const content = document.getElementById('instrumental-selection-content');
        
        modal.style.display = 'flex';
        content.innerHTML = '<div class="instrumental-loading">Loading instrumental options...</div>';
        
        // Fetch available instrumentals
        const response = await authenticatedFetch(`${API_BASE_URL}/corrections/${jobId}/instrumentals`);
        
        if (!response) return; // Auth failed, already handled
        
        if (response.ok) {
            const result = await response.json();
            displayInstrumentalOptions(result.instrumentals);
        } else {
            const error = await response.json();
            content.innerHTML = `<div class="no-instrumentals">Error loading instrumentals: ${error.detail}</div>`;
        }
    } catch (error) {
        console.error('Error loading instrumentals:', error);
        const content = document.getElementById('instrumental-selection-content');
        content.innerHTML = `<div class="no-instrumentals">Error loading instrumentals: ${error.message}</div>`;
    }
}

function displayInstrumentalOptions(instrumentals) {
    const content = document.getElementById('instrumental-selection-content');
    
    if (!instrumentals || instrumentals.length === 0) {
        content.innerHTML = `
            <div class="no-instrumentals">
                No instrumental files found. This might indicate an issue with the audio separation process.
            </div>
        `;
        return;
    }
    
    let html = '<div class="instrumental-options">';
    
    instrumentals.forEach((instrumental, index) => {
        const isRecommended = instrumental.recommended;
        const optionClasses = ['instrumental-option'];
        
        if (isRecommended) {
            optionClasses.push('recommended');
            // Auto-select the recommended option
            if (!selectedInstrumental) {
                selectedInstrumental = instrumental.filename;
                optionClasses.push('selected');
            }
        }
        
        html += `
            <div class="${optionClasses.join(' ')}" onclick="selectInstrumental('${escapeHtml(instrumental.filename)}', this)" data-filename="${escapeHtml(instrumental.filename)}">
                <div class="instrumental-header">
                    <div class="instrumental-title">
                        <div class="instrumental-type">${instrumental.type}</div>
                        <div class="instrumental-filename">${instrumental.filename}</div>
                    </div>
                    <div class="instrumental-controls">
                        <div class="audio-preview-controls">
                            <audio class="audio-preview-player" controls preload="none">
                                <source src="${API_BASE_URL}${instrumental.audio_url}" type="audio/flac">
                                Your browser does not support the audio element.
                            </audio>
                        </div>
                    </div>
                </div>
                <div class="instrumental-description">${instrumental.description}</div>
                <div class="instrumental-metadata">
                    <div class="instrumental-size">${instrumental.size_mb} MB</div>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    content.innerHTML = html;
    
    // Update confirmation button state
    updateConfirmInstrumentalButton();
}

function selectInstrumental(filename, element) {
    // Remove selection from all options
    const allOptions = document.querySelectorAll('.instrumental-option');
    allOptions.forEach(option => option.classList.remove('selected'));
    
    // Add selection to clicked option
    element.classList.add('selected');
    
    // Store selected instrumental
    selectedInstrumental = filename;
    
    // Update confirmation button
    updateConfirmInstrumentalButton();
    
    showInfo(`Selected: ${filename}`);
}

function updateConfirmInstrumentalButton() {
    const confirmBtn = document.getElementById('confirm-instrumental-btn');
    if (confirmBtn) {
        confirmBtn.disabled = !selectedInstrumental;
        if (selectedInstrumental) {
            confirmBtn.textContent = `✅ Use "${selectedInstrumental.substring(0, 30)}${selectedInstrumental.length > 30 ? '...' : ''}" & Complete`;
        } else {
            confirmBtn.textContent = '✅ Use Selected Instrumental & Complete';
        }
    }
}

async function confirmInstrumentalSelection() {
    if (!selectedInstrumental) {
        showError('Please select an instrumental track first');
        return;
    }
    
    try {
        // Get the current job ID from the stored value
        const jobId = window.currentInstrumentalJobId || getCurrentJobIdFromUrl();
        
        if (!jobId) {
            showError('Unable to determine job ID. Please refresh and try again.');
            return;
        }
        
        // Determine the current job status to know which endpoint to call
        const jobResponse = await authenticatedFetch(`${API_BASE_URL}/jobs/${jobId}`);
        if (!jobResponse) return; // Auth failed, already handled
        
        const jobData = await jobResponse.json();
        const jobStatus = jobData.status;
        
        let endpoint, requestData, infoMessage, successMessage;
        
        if (jobStatus === 'reviewing') {
            // For reviewing status: complete the review with instrumental selection
            endpoint = `/corrections/${jobId}/complete`;
            requestData = {
                corrected_data: currentReviewData || {},
                selected_instrumental: selectedInstrumental
            };
            infoMessage = 'Completing review with selected instrumental...';
            successMessage = 'Review completed with instrumental selection';
        } else if (jobStatus === 'ready_for_finalization') {
            // For ready_for_finalization status: finalize with instrumental selection
            endpoint = `/corrections/${jobId}/finalize`;
            requestData = {
                selected_instrumental: selectedInstrumental
            };
            infoMessage = 'Finalizing with selected instrumental...';
            successMessage = 'Finalization started with selected instrumental';
        } else {
            showError(`Cannot select instrumental for job in status: ${jobStatus}`);
            return;
        }
        
        showInfo(infoMessage);
        
        // Send request to the appropriate endpoint
        const response = await authenticatedFetch(`${API_BASE_URL}${endpoint}`, {
            method: 'POST',
            body: JSON.stringify(requestData)
        });
        
        if (!response) return; // Auth failed, already handled
        
        if (response.ok) {
            const result = await response.json();
            showSuccess(result.message || successMessage);
            closeInstrumentalSelectionModal();
            
            // Refresh jobs to show updated status
            await loadJobs();
        } else {
            const error = await response.json();
            showError('Error processing request: ' + error.detail);
        }
        
    } catch (error) {
        console.error('Error confirming instrumental selection:', error);
        showError('Error processing request: ' + error.message);
    }
}

function closeInstrumentalSelectionModal() {
    const modal = document.getElementById('instrumental-selection-modal');
    if (modal) {
        modal.style.display = 'none';
    }
    
    // Reset state
    selectedInstrumental = null;
    currentReviewData = null;
    window.currentInstrumentalJobId = null;
    
    // Clear modal content
    const content = document.getElementById('instrumental-selection-content');
    if (content) {
        content.innerHTML = '<div class="instrumental-loading">Loading instrumental options...</div>';
    }
    
    // Reset confirmation button
    const confirmBtn = document.getElementById('confirm-instrumental-btn');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = '✅ Use Selected Instrumental & Complete';
    }
}

function getCurrentJobIdFromUrl() {
    // This is a placeholder - you may need to implement this based on how job ID is available in your context
    // For now, we'll look for it in various places
    
    // Try to get from modal title
    const modalJobId = document.getElementById('modal-job-id');
    if (modalJobId && modalJobId.textContent) {
        return modalJobId.textContent.trim();
    }
    
    // Try to get from URL params if it's there
    const urlParams = new URLSearchParams(window.location.search);
    const jobId = urlParams.get('job_id');
    if (jobId) {
        return jobId;
    }
    
    // Try to get from the most recent job in the list that's in review state
    const jobs = Array.from(document.querySelectorAll('.job[data-job-id]'));
    for (const jobElement of jobs) {
        const statusBadge = jobElement.querySelector('.status-badge');
        if (statusBadge && statusBadge.textContent.toLowerCase().includes('review')) {
            return jobElement.getAttribute('data-job-id');
        }
    }
    
    return null;
}

async function showInstrumentalSelectionForJob(jobId) {
    try {
        showInfo('Loading instrumental options for job...');
        
        // For jobs in "reviewing" state, we assume lyrics review is complete
        // and we just need to select an instrumental and complete the job
        const correctedData = {}; // Empty object since review is assumed complete
        
        // Store the job ID for later use
        window.currentInstrumentalJobId = jobId;
        
        await showInstrumentalSelectionModal(jobId, correctedData);
        
    } catch (error) {
        console.error('Error showing instrumental selection:', error);
        showError('Error loading instrumental options: ' + error.message);
    }
}

// Debug helper function for testing timestamp parsing
window.debugTimestamp = function(timestamp) {
    console.group('🕐 Debug Timestamp Parsing:', timestamp);
    try {
        const parsed = parseServerTime(timestamp);
        const now = new Date();
        const diff = now - parsed;
        
        console.log('Original timestamp:', timestamp);
        console.log('Parsed as UTC:', parsed.toISOString());
        console.log('Parsed as local string:', parsed.toString());
        console.log('Formatted submitted time:', formatSubmittedTime({ created_at: timestamp }));
        console.log('Formatted timestamp:', formatTimestamp(timestamp));
        console.log('User timezone:', Intl.DateTimeFormat().resolvedOptions().timeZone);
        console.log('Timezone offset (minutes):', new Date().getTimezoneOffset());
        console.log('Current time UTC:', now.toISOString());
        console.log('Current time local:', now.toString());
        console.log('Difference (ms):', diff);
        console.log('Difference (seconds):', Math.floor(diff / 1000));
        console.log('Formatted duration:', formatDuration(Math.floor(Math.max(0, diff) / 1000)));
        
        if (diff < 0) {
            console.warn('⚠️ NEGATIVE DURATION DETECTED - This will show as 0s');
        }
        
        if (isNaN(parsed.getTime())) {
            console.error('⚠️ INVALID DATE DETECTED');
        }
    } catch (error) {
        console.error('Error parsing timestamp:', error);
    }
    console.groupEnd();
};

console.log('🎤 Karaoke Generator Frontend Ready!');
console.log('💡 Use debugTimestamp("your-timestamp-here") to test timestamp parsing');
console.log('🕐 Timestamps now display in your local timezone with improved error handling'); 