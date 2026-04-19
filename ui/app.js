// cairnsearch - Enterprise Document Search v3.1
// Complete JavaScript implementation with conversation context support

const API = '/api';

// Application State
const state = {
    query: '',
    mode: 'search',
    aiContext: 'search',
    results: [],
    sources: [],
    savedSearches: [],
    recentSearches: [],
    folders: [],
    currentBrowsePath: '/',
    indexedFiles: [],
    filesPage: 1,
    filesPageSize: 20,
    filesTotalPages: 1,
    watcherEnabled: false,
    currentSettingsTab: 'indexing',
    currentDocument: null,
    // Conversation history for follow-up questions
    conversationHistory: []
};

// File Type Icons
const ICONS = {
    pdf: '📄', docx: '📝', doc: '📝', txt: '📃', md: '📑', html: '🌐',
    xlsx: '📊', xls: '📊', csv: '📊', json: '📋', xml: '📋',
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', default: '📁'
};

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('cairnsearch v3.1 initializing...');
    
    // Load saved data
    loadSavedData();
    
    // Initialize theme
    initTheme();
    
    // Setup search input
    setupSearchInput();
    
    // Setup keyboard shortcuts
    setupKeyboardShortcuts();
    
    // Render UI components
    renderRecentSearches();
    renderSavedSearches();
    renderFolders();
    loadStats();
    loadAIConfigUI();
    loadRAGConfigUI();
    
    console.log('cairnsearch ready');
});

function loadSavedData() {
    try {
        state.savedSearches = JSON.parse(localStorage.getItem('savedSearches') || '[]');
        state.recentSearches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        state.folders = JSON.parse(localStorage.getItem('indexedFolders') || '[]');
    } catch (e) {
        console.error('Error loading saved data:', e);
    }
}

function setupSearchInput() {
    var searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                performSearch();
            } else if (e.key === 'Enter' && e.shiftKey) {
                e.preventDefault();
                setSearchMode('ai');
                performSearch();
            }
        });
    }
    
    // Follow-up input
    var followupInput = document.getElementById('followup-input');
    if (followupInput) {
        followupInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                askFollowup();
            }
        });
    }
}

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        if (e.key === '/' && !isInputFocused()) {
            e.preventDefault();
            var input = document.getElementById('search-input');
            if (input) input.focus();
        }
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            toggleCommandPalette();
        }
        if (e.key === 'Escape') {
            closeAllModals();
        }
    });
}

function isInputFocused() {
    var el = document.activeElement;
    return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA');
}

// ============================================
// THEME
// ============================================

function initTheme() {
    var theme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', theme);
}

function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme');
    var next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    showToast('Theme: ' + next, 'info');
}

// ============================================
// VIEW SWITCHING
// ============================================

function switchView(view) {
    console.log('Switching to view:', view);
    
    document.querySelectorAll('.nav-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-view') === view);
    });
    
    document.querySelectorAll('.view').forEach(function(v) {
        v.classList.toggle('active', v.id === 'view-' + view);
    });
    
    if (view === 'settings') {
        loadStats();
    }
    if (view === 'history') {
        renderChatHistory();
    }
    if (view === 'documents') {
        loadIndexedFiles();
    }
}

// ============================================
// SETTINGS TABS
// ============================================

function switchSettingsTab(tab) {
    state.currentSettingsTab = tab;
    
    document.querySelectorAll('.settings-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-tab') === tab);
    });
    
    document.querySelectorAll('.settings-panel').forEach(function(p) {
        p.classList.toggle('active', p.id === 'panel-' + tab);
    });
}

// ============================================
// SEARCH MODE
// ============================================

function setSearchMode(mode) {
    console.log('Setting search mode:', mode);
    state.mode = mode;
    
    // Clear conversation history when switching modes
    if (mode === 'search') {
        state.conversationHistory = [];
    }
    
    document.querySelectorAll('.mode-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-mode') === mode);
    });
    
    var searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.placeholder = mode === 'ai' 
            ? 'Ask a question about your documents...' 
            : 'Search your documents...';
    }
}

function setAIContext(context) {
    state.aiContext = context;
    document.querySelectorAll('.context-chip').forEach(function(chip) {
        chip.classList.toggle('active', chip.getAttribute('data-context') === context);
    });
}

// ============================================
// SEARCH
// ============================================

function performSearch() {
    var searchInput = document.getElementById('search-input');
    if (!searchInput) return;
    
    var query = searchInput.value.trim();
    if (!query) {
        showToast('Please enter a search query', 'error');
        return;
    }
    
    console.log('Performing search:', query, 'mode:', state.mode);
    state.query = query;
    addToRecent(query);
    
    // Hide empty state, show skeleton
    hideElement('empty-state');
    showElement('skeleton-loader');
    hideElement('ai-answer-section');
    hideElement('search-results-section');
    
    // Update header
    var label = document.getElementById('results-label');
    var timeEl = document.getElementById('results-time');
    if (label) label.textContent = state.mode === 'ai' ? 'AI Answer' : 'Search Results';
    if (timeEl) timeEl.textContent = '';
    
    if (state.mode === 'ai') {
        // Clear conversation history for new topic
        state.conversationHistory = [];
        askAI(query);
    } else {
        search(query);
    }
}

function search(query) {
    var startTime = Date.now();
    
    fetch(API + '/search?q=' + encodeURIComponent(query))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            hideElement('skeleton-loader');
            
            var elapsed = Date.now() - startTime;
            var timeEl = document.getElementById('results-time');
            if (timeEl) timeEl.textContent = elapsed.toFixed(2) + 'ms';
            
            state.results = data.results || [];
            renderSearchResults(state.results, query);
        })
        .catch(function(err) {
            hideElement('skeleton-loader');
            showElement('empty-state');
            showToast('Search failed: ' + err.message, 'error');
        });
}

function renderSearchResults(results, query) {
    var container = document.getElementById('results-list');
    var section = document.getElementById('search-results-section');
    
    if (!container) return;
    
    container.innerHTML = '';
    
    if (!results || results.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No results found for "' + escapeHtml(query) + '"</p></div>';
        showElement('search-results-section');
        return;
    }
    
    var label = document.getElementById('results-label');
    if (label) label.textContent = results.length + ' Results';
    
    results.forEach(function(result) {
        var icon = ICONS[result.file_type] || ICONS.default;
        var card = document.createElement('div');
        card.className = 'result-card result-item';
        card.tabIndex = 0;
        card.dataset.docId = result.id;
        card.onclick = function(e) { 
            if (!e.target.closest('.result-actions')) {
                openPreview(result.id); 
            }
        };
        
        var snippetsHtml = (result.snippets || []).slice(0, 2).map(function(s) {
            return '<p class="snippet">' + s + '</p>';
        }).join('');
        
        card.innerHTML = 
            '<div class="result-header">' +
                '<span class="result-icon">' + icon + '</span>' +
                '<span class="result-title">' + escapeHtml(result.filename) + '</span>' +
                '<span class="result-score">' + Math.round((result.score || 0) * 100) + '%</span>' +
            '</div>' +
            '<div class="result-snippets">' + snippetsHtml + '</div>' +
            '<div class="result-meta">' +
                '<span>' + (result.file_type || '') + '</span>' +
                (result.page_count ? '<span>' + result.page_count + ' pages</span>' : '') +
                (result.doc_author ? '<span>' + result.doc_author + '</span>' : '') +
            '</div>' +
            '<div class="result-actions">' +
                '<button class="btn-xs" onclick="event.stopPropagation(); summarizeDocument(' + result.id + ')" title="Summarize">📝</button>' +
                '<button class="btn-xs" onclick="event.stopPropagation(); findSimilarDocs(' + result.id + ')" title="Similar">🔍</button>' +
                '<button class="btn-xs" onclick="event.stopPropagation(); openDocumentChat(' + result.id + ')" title="Chat">💬</button>' +
            '</div>';
        
        container.appendChild(card);
    });
    
    showElement('search-results-section');
}

// ============================================
// AI SEARCH WITH CONVERSATION CONTEXT
// ============================================

function askAI(query) {
    var startTime = Date.now();
    
    // Show AI section with loading
    showElement('ai-answer-section');
    showElement('ai-loading');
    hideElement('skeleton-loader');
    
    var body = document.getElementById('ai-answer-body');
    if (body) body.innerHTML = '';
    
    var sourcesList = document.getElementById('sources-list');
    if (sourcesList) sourcesList.innerHTML = '';
    
    var sourcesCount = document.getElementById('sources-count');
    if (sourcesCount) sourcesCount.textContent = '0';
    
    // Build request with conversation history for context
    var requestBody = { 
        question: query,
        conversation_history: state.conversationHistory
    };
    
    if (state.aiContext === 'all') {
        requestBody.use_all_docs = true;
    }
    
    fetch(API + '/rag/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        hideElement('ai-loading');
        
        var elapsed = Date.now() - startTime;
        var timeEl = document.getElementById('results-time');
        if (timeEl) timeEl.textContent = elapsed.toFixed(2) + 'ms';
        
        var answer = data.answer || 'No answer generated';
        
        // Display answer
        if (body) {
            body.innerHTML = formatAIResponse(answer);
        }
        
        // Update conversation history for follow-up context
        state.conversationHistory.push({ role: 'user', content: query });
        state.conversationHistory.push({ role: 'assistant', content: answer });
        
        // Keep only last 6 messages (3 exchanges) to prevent context overflow
        if (state.conversationHistory.length > 6) {
            state.conversationHistory = state.conversationHistory.slice(-6);
        }
        
        // Display sources
        state.sources = data.sources || [];
        renderSources(state.sources);
        
        // Save to history
        saveToChatHistory(query, answer, state.sources);
    })
    .catch(function(err) {
        hideElement('ai-loading');
        if (body) {
            body.innerHTML = '<div style="color: var(--error)">Error: ' + escapeHtml(err.message) + '</div>';
        }
        showToast('AI query failed: ' + err.message, 'error');
    });
}

function askFollowup() {
    var input = document.getElementById('followup-input');
    if (!input) return;
    
    var query = input.value.trim();
    if (!query) return;
    
    input.value = '';
    
    // Update main search input
    var searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.value = query;
    
    state.query = query;
    addToRecent(query);
    
    // Ask AI with existing conversation history for context
    askAI(query);
}

function formatAIResponse(text) {
    if (!text) return '';
    
    // Convert markdown-like formatting
    text = escapeHtml(text);
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    text = text.replace(/`(.*?)`/g, '<code>$1</code>');
    text = text.replace(/\n/g, '<br>');
    
    return text;
}

function renderSources(sources) {
    var list = document.getElementById('sources-list');
    var count = document.getElementById('sources-count');
    
    if (!list) return;
    
    list.innerHTML = '';
    
    if (!sources || sources.length === 0) {
        if (count) count.textContent = '0';
        return;
    }
    
    if (count) count.textContent = sources.length;
    
    sources.forEach(function(source) {
        var icon = ICONS[source.file_type || getFileType(source.filename)] || ICONS.default;
        var chip = document.createElement('span');
        chip.className = 'source-chip';
        chip.onclick = function() { openFile(source.file_path); };
        chip.innerHTML = '<span class="source-icon">' + icon + '</span>' + escapeHtml(source.filename || source.file_path.split('/').pop());
        list.appendChild(chip);
    });
}

// ============================================
// RECENT & SAVED SEARCHES
// ============================================

function addToRecent(query) {
    state.recentSearches = state.recentSearches.filter(function(q) { return q !== query; });
    state.recentSearches.unshift(query);
    state.recentSearches = state.recentSearches.slice(0, 10);
    localStorage.setItem('recentSearches', JSON.stringify(state.recentSearches));
    renderRecentSearches();
}

function renderRecentSearches() {
    var container = document.getElementById('recent-searches');
    if (!container) return;
    
    if (state.recentSearches.length === 0) {
        container.innerHTML = '<div class="empty-message">No recent searches</div>';
        return;
    }
    
    container.innerHTML = '';
    state.recentSearches.forEach(function(query) {
        var item = document.createElement('div');
        item.className = 'recent-item';
        item.textContent = query;
        item.onclick = function() { useSearch(query); };
        container.appendChild(item);
    });
}

function renderSavedSearches() {
    var container = document.getElementById('saved-searches');
    if (!container) return;
    
    if (state.savedSearches.length === 0) {
        container.innerHTML = '<div class="empty-message">No saved searches</div>';
        return;
    }
    
    container.innerHTML = '';
    state.savedSearches.forEach(function(query) {
        var item = document.createElement('div');
        item.className = 'saved-item';
        item.textContent = query;
        item.onclick = function() { useSearch(query); };
        container.appendChild(item);
    });
}

function useSearch(query) {
    var searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.value = query;
        switchView('search');
        performSearch();
    }
}

function saveCurrentSearch() {
    var searchInput = document.getElementById('search-input');
    if (!searchInput || !searchInput.value.trim()) {
        showToast('No search to save', 'warning');
        return;
    }
    
    var query = searchInput.value.trim();
    if (state.savedSearches.includes(query)) {
        showToast('Search already saved', 'info');
        return;
    }
    
    state.savedSearches.unshift(query);
    localStorage.setItem('savedSearches', JSON.stringify(state.savedSearches));
    renderSavedSearches();
    showToast('Search saved', 'success');
}

// ============================================
// CHAT HISTORY
// ============================================

function saveToChatHistory(question, answer, sources) {
    try {
        var history = JSON.parse(localStorage.getItem('chatHistory') || '[]');
        history.unshift({
            question: question,
            answer: answer,
            sources: sources,
            timestamp: new Date().toISOString()
        });
        history = history.slice(0, 50); // Keep last 50
        localStorage.setItem('chatHistory', JSON.stringify(history));
    } catch (e) {
        console.error('Error saving chat history:', e);
    }
}

function renderChatHistory() {
    var container = document.getElementById('history-list');
    if (!container) return;
    
    try {
        var history = JSON.parse(localStorage.getItem('chatHistory') || '[]');
        
        if (history.length === 0) {
            container.innerHTML = '<div class="no-history-message">No chat history yet. Ask AI some questions!</div>';
            return;
        }
        
        container.innerHTML = '';
        history.forEach(function(item) {
            var div = document.createElement('div');
            div.className = 'history-item';
            div.innerHTML = 
                '<div class="history-question">' + escapeHtml(item.question) + '</div>' +
                '<div class="history-answer">' + escapeHtml(item.answer.substring(0, 200)) + '...</div>' +
                '<div class="history-time">' + formatDate(item.timestamp) + '</div>';
            div.onclick = function() {
                useSearch(item.question);
                setSearchMode('ai');
            };
            container.appendChild(div);
        });
    } catch (e) {
        console.error('Error rendering chat history:', e);
    }
}

function clearChatHistory() {
    if (!confirm('Clear all chat history?')) return;
    localStorage.removeItem('chatHistory');
    renderChatHistory();
    showToast('History cleared', 'success');
}

// ============================================
// FOLDERS
// ============================================

function renderFolders() {
    var container = document.getElementById('folders-list');
    if (!container) return;
    
    container.innerHTML = '<div style="padding: 12px; color: var(--text-muted);">Loading folders...</div>';
    
    // Load folders from backend
    fetch(API + '/folders')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var folders = data.folders || [];
            state.folders = folders;
            
            container.innerHTML = '';
            
            if (folders.length === 0) {
                container.innerHTML = '<div style="padding: 12px; color: var(--text-muted);">No folders added yet</div>';
                return;
            }
            
            folders.forEach(function(folder, idx) {
                var item = document.createElement('div');
                item.className = 'folder-item';
                var isMissing = folder.missing ? ' <span style="color: var(--error);">(missing)</span>' : '';
                item.innerHTML = 
                    '<span class="folder-path">' + escapeHtml(folder.path) + isMissing + '</span>' +
                    '<span class="folder-count">' + (folder.count || 0) + ' files</span>' +
                    '<button onclick="removeFolder(\'' + escapeAttr(folder.path) + '\')" title="Remove">×</button>';
                container.appendChild(item);
            });
        })
        .catch(function(err) {
            container.innerHTML = '<div style="padding: 12px; color: var(--error);">Error loading folders: ' + escapeHtml(err.message) + '</div>';
        });
}

function openFolderBrowser() {
    var modal = document.getElementById('folder-modal');
    if (modal) {
        modal.classList.remove('hidden');
        browsePath('/');
    }
}

function closeFolderBrowser() {
    var modal = document.getElementById('folder-modal');
    if (modal) modal.classList.add('hidden');
}

function browsePath(path) {
    state.currentBrowsePath = path;
    
    var breadcrumb = document.getElementById('folder-breadcrumb');
    if (breadcrumb) {
        var parts = path.split('/').filter(Boolean);
        var crumbs = '<span onclick="browsePath(\'/\')" style="cursor:pointer">/</span>';
        var current = '';
        parts.forEach(function(part) {
            current += '/' + part;
            var p = current;
            crumbs += ' <span onclick="browsePath(\'' + escapeAttr(p) + '\')" style="cursor:pointer">' + escapeHtml(part) + '</span> /';
        });
        breadcrumb.innerHTML = crumbs;
    }
    
    fetch(API + '/folders/browse?path=' + encodeURIComponent(path))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var list = document.getElementById('folder-contents');
            if (!list) return;
            
            // Update current browse path from server response
            if (data.path) {
                state.currentBrowsePath = data.path;
            }
            
            list.innerHTML = '';
            
            // Add parent directory option if available
            if (data.parent) {
                var parentItem = document.createElement('div');
                parentItem.className = 'folder-item-browse parent-folder';
                parentItem.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg><span>.. (Parent Directory)</span>';
                parentItem.onclick = function() { browsePath(data.parent); };
                list.appendChild(parentItem);
            }
            
            (data.folders || []).forEach(function(folder) {
                // Handle both object format {name, path} and string format
                var folderName = typeof folder === 'object' ? folder.name : folder;
                var folderPath = typeof folder === 'object' ? folder.path : null;
                
                var item = document.createElement('div');
                item.className = 'folder-item-browse';
                item.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg><span>' + escapeHtml(folderName) + '</span>';
                
                // Use the path from the server response if available, otherwise construct it
                if (folderPath) {
                    item.onclick = function() { browsePath(folderPath); };
                } else {
                    var newPath = state.currentBrowsePath + (state.currentBrowsePath.endsWith('/') ? '' : '/') + folderName;
                    item.onclick = function() { browsePath(newPath); };
                }
                list.appendChild(item);
            });
            
            // Show message if no folders found
            if ((data.folders || []).length === 0 && !data.parent) {
                var emptyMsg = document.createElement('div');
                emptyMsg.className = 'empty-folder-msg';
                emptyMsg.textContent = 'No accessible subfolders';
                list.appendChild(emptyMsg);
            }
        })
        .catch(function(err) {
            showToast('Error browsing folders: ' + err.message, 'error');
        });
}

function selectCurrentFolder() {
    var path = state.currentBrowsePath;
    
    if (!path || path === '/') {
        showToast('Please navigate to a specific folder first', 'warning');
        return;
    }
    
    fetch(API + '/folders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        renderFolders();  // Refresh from backend
        closeFolderBrowser();
        showToast('Folder added: ' + path, 'success');
        
        // Ask if user wants to index now
        if (confirm('Folder added. Do you want to start indexing now?')) {
            indexFolder(path);
        }
    })
    .catch(function(err) {
        showToast('Error adding folder: ' + err.message, 'error');
    });
}

// Index a specific folder with progress tracking
function indexFolder(folderPath) {
    showToast('Starting indexing...', 'info');
    
    fetch(API + '/index/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: folderPath })
    })
    .then(function(r) { return r.json(); })
    .then(function(result) {
        if (result && result.session_id) {
            // Show the progress panel and subscribe to updates
            showIndexingProgress({
                session_id: result.session_id,
                status: 'scanning',
                folder_path: result.path,
                total_files: result.files_queued,
                processed_files: 0,
                successful_files: 0,
                warning_files: 0,
                failed_files: 0,
                overall_percent: 0,
                files_per_second: 0,
                estimated_remaining_seconds: null,
                current_file: null,
                is_paused: false
            });
            subscribeToProgress(result.session_id);
            showToast('Indexing ' + result.files_queued + ' files...', 'success');
        } else if (result) {
            showToast(result.message || 'Indexing started', 'info');
        }
    })
    .catch(function(err) {
        showToast('Error starting index: ' + err.message, 'error');
    });
}

function removeFolder(path) {
    if (!path) return;
    
    fetch(API + '/folders', { 
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path })
    })
        .then(function(r) { return r.json(); })
        .then(function() {
            renderFolders();
            showToast('Folder removed', 'success');
        })
        .catch(function(err) {
            showToast('Error removing folder: ' + err.message, 'error');
        });
}

// Drag and Drop handlers
function handleDragOver(e) {
    e.preventDefault();
    e.currentTarget.classList.add('dragover');
}

function handleDragLeave(e) {
    e.currentTarget.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('dragover');
    showToast('Use the Browse Folders button to select folders', 'info');
}

// ============================================
// INDEXING
// ============================================

function startIndexing() {
    // First, fetch the user's configured folders from the backend
    fetch(API + '/folders')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var folders = data.folders || [];
            
            if (folders.length === 0) {
                showToast('No folders configured. Please add folders in Settings > Indexing first.', 'warning');
                return;
            }
            
            showToast('Starting indexing for ' + folders.length + ' folder(s)...', 'info');
            
            // Index each configured folder (for now, just the first one to show progress)
            // In future, could queue multiple folders
            var folder = folders[0];
            
            return fetch(API + '/index/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: folder.path })
            }).then(function(r) { return r.json(); });
        })
        .then(function(result) {
            if (result && result.session_id) {
                // Show the progress panel and subscribe to updates
                showIndexingProgress({
                    session_id: result.session_id,
                    status: 'scanning',
                    folder_path: result.path,
                    total_files: result.files_queued,
                    processed_files: 0,
                    successful_files: 0,
                    warning_files: 0,
                    failed_files: 0,
                    overall_percent: 0,
                    files_per_second: 0,
                    estimated_remaining_seconds: null,
                    current_file: null,
                    is_paused: false
                });
                subscribeToProgress(result.session_id);
                showToast('Indexing ' + result.files_queued + ' files...', 'success');
            } else if (result) {
                showToast(result.message || 'Indexing started', 'info');
            }
        })
        .catch(function(err) {
            showToast('Error starting index: ' + err.message, 'error');
        });
}

// Keep old poll function for backward compatibility but it's no longer used
function pollIndexProgress() {
    // Now using SSE-based progress tracking instead
    checkIndexingSessions();
}

function clearIndex() {
    if (!confirm('This will delete all indexed documents. Continue?')) return;
    
    fetch(API + '/index', { method: 'DELETE' })
        .then(function(r) { return r.json(); })
        .then(function() {
            showToast('Index cleared', 'success');
            loadStats();
        })
        .catch(function(err) {
            showToast('Error clearing index: ' + err.message, 'error');
        });
}

function toggleFileWatcher() {
    state.watcherEnabled = !state.watcherEnabled;
    var btn = document.getElementById('btn-watcher');
    
    fetch(API + '/watcher/' + (state.watcherEnabled ? 'start' : 'stop'), { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function() {
            if (btn) btn.querySelector('span').textContent = state.watcherEnabled ? 'Disable Auto-Watch' : 'Enable Auto-Watch';
            showToast('File watcher ' + (state.watcherEnabled ? 'enabled' : 'disabled'), 'success');
        })
        .catch(function(err) {
            state.watcherEnabled = !state.watcherEnabled;
            showToast('Error toggling watcher: ' + err.message, 'error');
        });
}

// ============================================
// STATS
// ============================================

function loadStats() {
    fetch(API + '/status')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            setElement('stat-docs', data.documents || data.indexed_count || 0);
            setElement('stat-chunks', data.chunks || data.vector_count || 0);
            setElement('stat-pending', data.pending || 0);
            setElement('stat-errors', data.errors || data.failed_count || 0);
            setElement('doc-total-count', data.documents || data.indexed_count || 0);
            setElement('doc-chunk-count', data.chunks || data.vector_count || 0);
        })
        .catch(function(err) {
            console.error('Error loading stats:', err);
        });
}

// ============================================
// INDEXED FILES (DOCUMENTS VIEW)
// ============================================

function loadIndexedFiles() {
    var container = document.getElementById('documents-table-body');
    if (!container) return;
    
    container.innerHTML = '<tr><td colspan="6" style="padding: 40px; text-align: center; color: var(--text-muted);">Loading documents...</td></tr>';
    
    fetch(API + '/index/documents?page=' + state.filesPage + '&page_size=' + state.filesPageSize)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            state.indexedFiles = data.documents || [];
            state.filesTotalPages = data.total_pages || 1;
            setElement('doc-total-count', data.total || 0);
            
            var types = {};
            state.indexedFiles.forEach(function(f) { if (f.file_type) types[f.file_type] = true; });
            setElement('doc-type-count', Object.keys(types).length);
            
            renderIndexedFiles();
            updatePagination();
        })
        .catch(function(err) {
            container.innerHTML = '<tr><td colspan="6"><div style="padding: 40px; text-align: center; color: var(--error);">Error: ' + escapeHtml(err.message) + '</div></td></tr>';
        });
}

function renderIndexedFiles() {
    var container = document.getElementById('documents-table-body');
    if (!container) return;
    
    if (state.indexedFiles.length === 0) {
        container.innerHTML = '<tr class="empty-row"><td colspan="6"><div class="empty-table-state">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>' +
            '<p>No documents indexed yet</p>' +
            '<button class="btn btn-primary btn-sm" onclick="switchView(\'settings\')">Add Folders</button></div></td></tr>';
        return;
    }
    
    container.innerHTML = '';
    state.indexedFiles.forEach(function(file) {
        var icon = ICONS[file.file_type] || ICONS.default;
        var tr = document.createElement('tr');
        tr.onclick = function(e) { if (!e.target.closest('.doc-actions')) openDocumentModal(file); };
        tr.innerHTML = 
            '<td class="col-icon">' + icon + '</td>' +
            '<td class="col-name"><div class="doc-name">' + escapeHtml(file.filename) + '</div><div class="doc-path">' + escapeHtml(formatPath(file.file_path)) + '</div></td>' +
            '<td class="col-type"><span class="doc-type-badge">' + (file.file_type || '-').toUpperCase() + '</span></td>' +
            '<td class="col-chunks"><span class="doc-chunks-count">' + (file.chunk_count || '-') + '</span></td>' +
            '<td class="col-date"><span class="doc-date">' + formatDate(file.indexed_at) + '</span></td>' +
            '<td class="col-actions"><div class="doc-actions">' +
                '<button class="doc-action-btn" onclick="event.stopPropagation(); reindexDocument(' + file.id + ')" title="Re-index"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg></button>' +
                '<button class="doc-action-btn primary" onclick="event.stopPropagation(); openFile(\'' + escapeAttr(file.file_path) + '\')" title="Open">Open</button></div></td>';
        container.appendChild(tr);
    });
}

function updatePagination() {
    var pageInfo = document.getElementById('files-page-info');
    if (pageInfo) pageInfo.textContent = 'Page ' + state.filesPage + ' of ' + state.filesTotalPages;
}

function filterIndexedFiles(query) {
    var rows = document.querySelectorAll('#documents-table-body tr:not(.empty-row)');
    rows.forEach(function(row) {
        var text = row.textContent.toLowerCase();
        row.style.display = !query || text.includes(query.toLowerCase()) ? '' : 'none';
    });
}

function filterByType(type) {
    var rows = document.querySelectorAll('#documents-table-body tr:not(.empty-row)');
    rows.forEach(function(row) {
        var badge = row.querySelector('.doc-type-badge');
        var rowType = badge ? badge.textContent.toLowerCase() : '';
        row.style.display = !type || rowType === type.toLowerCase() ? '' : 'none';
    });
}

function sortIndexedFiles(sortBy) {
    state.indexedFiles.sort(function(a, b) {
        if (sortBy === 'name') return (a.filename || '').localeCompare(b.filename || '');
        if (sortBy === 'date') return new Date(b.indexed_at) - new Date(a.indexed_at);
        if (sortBy === 'type') return (a.file_type || '').localeCompare(b.file_type || '');
        return 0;
    });
    renderIndexedFiles();
}

function prevFilesPage() { if (state.filesPage > 1) { state.filesPage--; loadIndexedFiles(); } }
function nextFilesPage() { if (state.filesPage < state.filesTotalPages) { state.filesPage++; loadIndexedFiles(); } }

function exportIndexedFiles() {
    var data = state.indexedFiles.map(function(f) { return f.file_path; }).join('\n');
    var blob = new Blob([data], { type: 'text/plain' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'indexed-files.txt'; a.click();
    URL.revokeObjectURL(url);
    showToast('Exported ' + state.indexedFiles.length + ' files', 'success');
}

// ============================================
// DOCUMENT MODAL
// ============================================

function openDocumentModal(doc) {
    state.currentDocument = doc;
    var modal = document.getElementById('document-modal');
    var title = document.getElementById('doc-modal-title');
    var body = document.getElementById('doc-modal-body');
    
    if (title) title.textContent = doc.filename;
    if (body) {
        body.innerHTML = 
            '<div class="doc-detail-section"><div class="doc-detail-label">File Path</div><div class="doc-detail-path">' + escapeHtml(doc.file_path) + '</div></div>' +
            '<div class="doc-detail-section"><div class="doc-detail-label">File Type</div><div class="doc-detail-value">' + (doc.file_type || 'Unknown').toUpperCase() + '</div></div>' +
            '<div class="doc-detail-section"><div class="doc-detail-label">Indexed</div><div class="doc-detail-value">' + formatDate(doc.indexed_at) + '</div></div>' +
            '<div class="doc-detail-section"><div class="doc-detail-label">Chunks</div><div class="doc-chunks-preview" id="doc-chunks-list">Loading chunks...</div></div>';
        loadDocumentChunks(doc.id);
    }
    if (modal) modal.classList.remove('hidden');
}

function loadDocumentChunks(docId) {
    var container = document.getElementById('doc-chunks-list');
    if (!container) return;
    
    fetch(API + '/rag/chunks/' + docId)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.chunks || data.chunks.length === 0) {
                container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">No chunks found. Try re-indexing.</div>';
                return;
            }
            container.innerHTML = '';
            data.chunks.slice(0, 5).forEach(function(chunk) {
                var div = document.createElement('div');
                div.className = 'chunk-preview';
                div.innerHTML = '<div class="chunk-preview-index">Chunk ' + (chunk.chunk_index + 1) + '</div><div>' + escapeHtml(chunk.content.substring(0, 200)) + '...</div>';
                container.appendChild(div);
            });
            if (data.chunks.length > 5) {
                var more = document.createElement('div');
                more.style.cssText = 'font-size: 0.8rem; color: var(--text-muted); margin-top: 8px;';
                more.textContent = '...and ' + (data.chunks.length - 5) + ' more chunks';
                container.appendChild(more);
            }
        })
        .catch(function(err) {
            container.innerHTML = '<div style="color: var(--error);">Error: ' + escapeHtml(err.message) + '</div>';
        });
}

function closeDocumentModal() {
    var modal = document.getElementById('document-modal');
    if (modal) modal.classList.add('hidden');
    state.currentDocument = null;
}

function reindexCurrentDocument() {
    if (state.currentDocument) { reindexDocument(state.currentDocument.id); closeDocumentModal(); }
}

function openCurrentDocument() {
    if (state.currentDocument) openFile(state.currentDocument.file_path);
}

function reindexDocument(docId) {
    showToast('Re-indexing document...', 'info');
    fetch(API + '/rag/reindex-document', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        showToast(data.message || 'Document re-indexed', 'success');
        loadIndexedFiles();
    })
    .catch(function(err) {
        showToast('Error: ' + err.message, 'error');
    });
}

// ============================================
// ERRORS & PATTERNS
// ============================================

function viewErrors() {
    var modal = document.getElementById('error-modal');
    var list = document.getElementById('error-list');
    if (!modal || !list) return;
    
    list.innerHTML = '<div style="padding: 20px; text-align: center;">Loading...</div>';
    modal.classList.remove('hidden');
    
    fetch(API + '/index/errors')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.errors || data.errors.length === 0) {
                list.innerHTML = '<div style="padding: 40px; text-align: center; color: var(--success);">No errors! 🎉</div>';
                return;
            }
            list.innerHTML = '';
            data.errors.forEach(function(err) {
                var div = document.createElement('div');
                div.className = 'error-item';
                div.innerHTML = '<div class="error-path">' + escapeHtml(err.file_path) + '</div><div class="error-msg">' + escapeHtml(err.error) + '</div>';
                list.appendChild(div);
            });
        })
        .catch(function(err) {
            list.innerHTML = '<div style="color: var(--error);">Error: ' + escapeHtml(err.message) + '</div>';
        });
}

function closeErrorModal() {
    var modal = document.getElementById('error-modal');
    if (modal) modal.classList.add('hidden');
}

function addExcludePattern() {
    var modal = document.getElementById('pattern-modal');
    if (modal) modal.classList.remove('hidden');
    var input = document.getElementById('new-pattern');
    if (input) { input.value = ''; input.focus(); }
}

function closePatternModal() {
    var modal = document.getElementById('pattern-modal');
    if (modal) modal.classList.add('hidden');
}

function confirmAddPattern() {
    var input = document.getElementById('new-pattern');
    if (!input || !input.value.trim()) { showToast('Enter a pattern', 'warning'); return; }
    var pattern = input.value.trim();
    var container = document.getElementById('exclude-patterns');
    if (container) {
        var chip = document.createElement('span');
        chip.className = 'pattern-tag';
        chip.innerHTML = escapeHtml(pattern) + ' <button onclick="removePattern(this)">×</button>';
        container.appendChild(chip);
    }
    closePatternModal();
    showToast('Pattern added: ' + pattern, 'success');
}

function removePattern(btn) { if (btn.parentElement) btn.parentElement.remove(); }

// ============================================
// AI CONFIGURATION
// ============================================

var aiConfig = { 
    llmProvider: 'ollama', 
    ollamaModel: 'llama3.1:8b', 
    openaiModel: 'gpt-4o-mini',
    anthropicModel: 'claude-sonnet-4-20250514',
    embeddingProvider: 'ollama',
    openaiEmbeddingModel: 'text-embedding-3-small'
};

function loadAIConfigUI() {
    try { Object.assign(aiConfig, JSON.parse(localStorage.getItem('aiConfig') || '{}')); } catch (e) {}
    var provider = document.getElementById('llm-provider');
    var ollamaModel = document.getElementById('ollama-model');
    var openaiModel = document.getElementById('openai-model');
    var anthropicModel = document.getElementById('anthropic-model');
    var embedding = document.getElementById('embedding-provider');
    var openaiEmbeddingModel = document.getElementById('openai-embedding-model');
    
    if (provider) provider.value = aiConfig.llmProvider;
    if (ollamaModel) ollamaModel.value = aiConfig.ollamaModel;
    if (openaiModel) openaiModel.value = aiConfig.openaiModel || 'gpt-4o-mini';
    if (anthropicModel) anthropicModel.value = aiConfig.anthropicModel || 'claude-sonnet-4-20250514';
    if (embedding) embedding.value = aiConfig.embeddingProvider;
    if (openaiEmbeddingModel) openaiEmbeddingModel.value = aiConfig.openaiEmbeddingModel || 'text-embedding-3-small';
    
    updateAIConfigUI();
    updateEmbeddingConfigUI();
    updateAIProviderLabel();
    
    // Also sync to backend on load to ensure consistency
    fetch(API + '/rag/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            llm_provider: aiConfig.llmProvider,
            ollama_model: aiConfig.ollamaModel,
            openai_model: aiConfig.openaiModel,
            anthropic_model: aiConfig.anthropicModel,
            embedding_provider: aiConfig.embeddingProvider,
            openai_embedding_model: aiConfig.openaiEmbeddingModel
        })
    }).catch(function(err) {
        console.log('Failed to sync AI config to backend:', err);
    });
}

function updateAIConfigUI() {
    var provider = document.getElementById('llm-provider');
    var ollamaGroup = document.getElementById('ollama-model-group');
    var openaiGroup = document.getElementById('openai-model-group');
    var anthropicGroup = document.getElementById('anthropic-model-group');
    var apiKeyNote = document.getElementById('api-key-note');
    
    if (provider) {
        var selectedProvider = provider.value;
        if (ollamaGroup) ollamaGroup.classList.toggle('hidden', selectedProvider !== 'ollama');
        if (openaiGroup) openaiGroup.classList.toggle('hidden', selectedProvider !== 'openai');
        if (anthropicGroup) anthropicGroup.classList.toggle('hidden', selectedProvider !== 'anthropic');
        if (apiKeyNote) apiKeyNote.classList.toggle('hidden', selectedProvider === 'ollama');
    }
}

function updateEmbeddingConfigUI() {
    var embedding = document.getElementById('embedding-provider');
    var openaiEmbeddingGroup = document.getElementById('openai-embedding-model-group');
    
    if (embedding && openaiEmbeddingGroup) {
        openaiEmbeddingGroup.classList.toggle('hidden', embedding.value !== 'openai');
    }
}

function updateAIProviderLabel() {
    var label = document.getElementById('ai-provider');
    if (!label) return;
    var text = 'Powered by ';
    if (aiConfig.llmProvider === 'ollama') text += 'Ollama';
    else if (aiConfig.llmProvider === 'openai') text += 'OpenAI';
    else if (aiConfig.llmProvider === 'anthropic') text += 'Claude';
    label.textContent = text;
}

function saveAIConfig() {
    var provider = document.getElementById('llm-provider');
    var ollamaModel = document.getElementById('ollama-model');
    var openaiModel = document.getElementById('openai-model');
    var anthropicModel = document.getElementById('anthropic-model');
    var embedding = document.getElementById('embedding-provider');
    var openaiEmbeddingModel = document.getElementById('openai-embedding-model');
    
    aiConfig = {
        llmProvider: provider ? provider.value : 'ollama',
        ollamaModel: ollamaModel ? ollamaModel.value : 'llama3.1:8b',
        openaiModel: openaiModel ? openaiModel.value : 'gpt-4o-mini',
        anthropicModel: anthropicModel ? anthropicModel.value : 'claude-sonnet-4-20250514',
        embeddingProvider: embedding ? embedding.value : 'ollama',
        openaiEmbeddingModel: openaiEmbeddingModel ? openaiEmbeddingModel.value : 'text-embedding-3-small'
    };
    localStorage.setItem('aiConfig', JSON.stringify(aiConfig));
    updateAIProviderLabel();
    var badge = document.getElementById('ai-status-badge');
    if (badge) { badge.textContent = 'Saving...'; badge.className = 'connection-badge'; }
    
    // Send all model configs to backend
    fetch(API + '/rag/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            llm_provider: aiConfig.llmProvider,
            ollama_model: aiConfig.ollamaModel,
            openai_model: aiConfig.openaiModel,
            anthropic_model: aiConfig.anthropicModel,
            embedding_provider: aiConfig.embeddingProvider,
            openai_embedding_model: aiConfig.openaiEmbeddingModel
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (badge) { badge.textContent = 'Not Tested'; badge.className = 'connection-badge'; }
        showToast('Settings saved. Test connection to verify.', 'success');
    })
    .catch(function(err) {
        if (badge) { badge.textContent = 'Error'; badge.className = 'connection-badge error'; }
        showToast('Failed to save settings: ' + err.message, 'error');
    });
}

// RAG Configuration
var ragConfig = {
    rerankerEnabled: false,
    topK: 5,
    chunkSize: 500,
    hybridSearch: true
};

function loadRAGConfigUI() {
    try { Object.assign(ragConfig, JSON.parse(localStorage.getItem('ragConfig') || '{}')); } catch (e) {}
    var reranker = document.getElementById('reranker-enabled');
    var topK = document.getElementById('rag-top-k');
    var chunkSize = document.getElementById('rag-chunk-size');
    var hybrid = document.getElementById('hybrid-search');
    if (reranker) reranker.checked = ragConfig.rerankerEnabled;
    if (topK) topK.value = ragConfig.topK;
    if (chunkSize) chunkSize.value = ragConfig.chunkSize;
    if (hybrid) hybrid.checked = ragConfig.hybridSearch;
}

function saveRAGConfig() {
    var reranker = document.getElementById('reranker-enabled');
    var topK = document.getElementById('rag-top-k');
    var chunkSize = document.getElementById('rag-chunk-size');
    var hybrid = document.getElementById('hybrid-search');
    
    ragConfig = {
        rerankerEnabled: reranker ? reranker.checked : false,
        topK: topK ? parseInt(topK.value) : 5,
        chunkSize: chunkSize ? parseInt(chunkSize.value) : 500,
        hybridSearch: hybrid ? hybrid.checked : true
    };
    
    localStorage.setItem('ragConfig', JSON.stringify(ragConfig));
    
    // Also save to backend
    fetch(API + '/rag/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            reranker_enabled: ragConfig.rerankerEnabled,
            top_k: ragConfig.topK,
            chunk_size: ragConfig.chunkSize,
            hybrid_search: ragConfig.hybridSearch
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        showToast('RAG settings saved', 'success');
    })
    .catch(function(err) {
        showToast('RAG settings saved locally. Backend update failed: ' + err.message, 'warning');
    });
}

function testAIConnection() {
    var provider = document.getElementById('llm-provider');
    var selectedProvider = provider ? provider.value : 'ollama';
    var model = document.getElementById('ollama-model');
    var selectedModel = model ? model.value : 'llama3.1:8b';
    
    showToast('Testing connection to ' + selectedProvider + '...', 'info');
    var badge = document.getElementById('ai-status-badge');
    if (badge) { badge.textContent = 'Testing...'; badge.className = 'connection-badge'; }
    
    // First, save the config, then test with specific provider
    fetch(API + '/rag/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            provider: selectedProvider,
            model: selectedModel
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var llmOk = data.llm && data.llm.available;
        var embOk = data.embeddings && data.embeddings.available;
        var llmError = data.llm && data.llm.error;
        var embError = data.embeddings && data.embeddings.error;
        
        if (llmOk && embOk) {
            showToast('Connected! LLM and Embeddings OK', 'success');
            if (badge) { badge.textContent = 'Connected'; badge.className = 'connection-badge success'; }
        } else if (llmOk) {
            var errMsg = embError ? ': ' + embError : '';
            showToast('LLM OK but embeddings failed' + errMsg, 'warning');
            if (badge) { badge.textContent = 'Partial'; badge.className = 'connection-badge warning'; }
        } else if (embOk) {
            var errMsg = llmError ? ': ' + llmError : '';
            showToast('Embeddings OK but LLM failed' + errMsg, 'warning');
            if (badge) { badge.textContent = 'Partial'; badge.className = 'connection-badge warning'; }
        } else {
            var errMsg = llmError || embError || 'Unknown error';
            showToast('Connection failed: ' + errMsg, 'error');
            if (badge) { badge.textContent = 'Failed'; badge.className = 'connection-badge error'; }
        }
    })
    .catch(function(err) {
        showToast('Test failed: ' + err.message, 'error');
        if (badge) { badge.textContent = 'Error'; badge.className = 'connection-badge error'; }
    });
}

// ============================================
// COMMAND PALETTE
// ============================================

var commands = [
    { name: 'Search', action: function() { switchView('search'); }, shortcut: '/' },
    { name: 'Documents', action: function() { switchView('documents'); } },
    { name: 'Settings', action: function() { switchView('settings'); } },
    { name: 'History', action: function() { switchView('history'); } },
    { name: 'Toggle Theme', action: toggleTheme, shortcut: '⌘T' },
    { name: 'Start Indexing', action: startIndexing },
    { name: 'Test AI', action: testAIConnection }
];

function openCommandPalette() {
    var modal = document.getElementById('command-palette');
    var input = document.getElementById('command-input');
    if (modal) modal.classList.remove('hidden');
    if (input) { input.value = ''; input.focus(); }
    renderCommands(commands);
}

function closeCommandPalette() {
    var modal = document.getElementById('command-palette');
    if (modal) modal.classList.add('hidden');
}

function toggleCommandPalette() {
    var modal = document.getElementById('command-palette');
    if (modal && modal.classList.contains('hidden')) openCommandPalette();
    else closeCommandPalette();
}

function filterCommands(query) {
    var filtered = commands.filter(function(cmd) { return cmd.name.toLowerCase().includes(query.toLowerCase()); });
    renderCommands(filtered);
}

function renderCommands(cmds) {
    var list = document.getElementById('command-list');
    if (!list) return;
    list.innerHTML = '';
    cmds.forEach(function(cmd) {
        var item = document.createElement('div');
        item.className = 'command-item';
        item.onclick = function() { closeCommandPalette(); cmd.action(); };
        item.innerHTML = '<span>' + escapeHtml(cmd.name) + '</span>' + (cmd.shortcut ? '<kbd>' + cmd.shortcut + '</kbd>' : '');
        list.appendChild(item);
    });
}

// ============================================
// MODALS & FILE OPS
// ============================================

function closeAllModals() {
    document.querySelectorAll('.modal').forEach(function(modal) { modal.classList.add('hidden'); });
}

function openFile(path) {
    if (!path) return;
    fetch(API + '/documents/open-path?file_path=' + encodeURIComponent(path), { method: 'POST' })
        .then(function(r) { if (!r.ok) throw new Error('Failed'); return r.json(); })
        .then(function(data) { showToast('Opening: ' + path.split('/').pop(), 'info'); })
        .catch(function() { showToast('Could not open file', 'warning'); });
}

function copyResults() {
    var body = document.getElementById('ai-answer-body');
    if (body && body.textContent) { navigator.clipboard.writeText(body.textContent); showToast('Copied', 'success'); }
}

function downloadResults() {
    var body = document.getElementById('ai-answer-body');
    if (!body) return;
    var blob = new Blob([body.textContent || ''], { type: 'text/plain' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'ai-answer.txt'; a.click();
    URL.revokeObjectURL(url);
}

// ============================================
// UI HELPERS & UTILITIES
// ============================================

function showElement(id) { var el = document.getElementById(id); if (el) el.classList.remove('hidden'); }
function hideElement(id) { var el = document.getElementById(id); if (el) el.classList.add('hidden'); }
function setElement(id, value) { var el = document.getElementById(id); if (el) el.textContent = value; }

function showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toast-container');
    if (!container) return;
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML = '<span>' + escapeHtml(message) + '</span><button onclick="this.parentElement.remove()">×</button>';
    container.appendChild(toast);
    setTimeout(function() { if (toast.parentElement) toast.remove(); }, 4000);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escapeAttr(str) {
    if (!str) return '';
    return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function formatPath(path) {
    if (!path) return '';
    var parts = path.split('/');
    return parts.length <= 3 ? path : '.../' + parts.slice(-2).join('/');
}

function formatDate(timestamp) {
    if (!timestamp) return '-';
    var d = new Date(timestamp);
    return isNaN(d.getTime()) ? '-' : d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function getFileType(filename) {
    if (!filename) return '';
    return filename.split('.').pop().toLowerCase();
}

// ============================================================================
// Extra UI features
// ============================================================================

// Filter state
var filterState = {
    fileTypes: []
};

// Preview state
var previewState = {
    visible: false,
    document: null
};

// Document chat state
var documentChatState = {
    document: null,
    history: []
};

// Indexing progress state
var indexingState = {
    activeSessionId: null,
    eventSource: null
};

// ============================================================================
// QUICK FILTERS
// ============================================================================

function toggleTypeFilter(type) {
    var index = filterState.fileTypes.indexOf(type);
    if (index === -1) {
        filterState.fileTypes.push(type);
    } else {
        filterState.fileTypes.splice(index, 1);
    }
    
    // Update UI
    document.querySelectorAll('.filter-chip').forEach(function(chip) {
        chip.classList.toggle('active', filterState.fileTypes.includes(chip.dataset.type));
    });
    
    // Re-run search if there's a query
    if (state.query) {
        performSearch();
    }
}

function clearFilters() {
    filterState.fileTypes = [];
    document.querySelectorAll('.filter-chip').forEach(function(chip) {
        chip.classList.remove('active');
    });
    
    if (state.query) {
        performSearch();
    }
}

// ============================================================================
// DOCUMENT PREVIEW
// ============================================================================

function openPreview(docId) {
    Promise.all([
        fetch(API + '/documents/' + docId + '/content?highlight=' + encodeURIComponent(state.query || '')),
        fetch(API + '/documents/' + docId + '/metadata')
    ])
    .then(function(responses) {
        return Promise.all(responses.map(function(r) { return r.json(); }));
    })
    .then(function(data) {
        var content = data[0];
        var metadata = data[1];
        
        previewState.document = Object.assign({}, content, metadata);
        previewState.visible = true;
        
        renderPreviewPanel();
        document.getElementById('preview-panel').classList.remove('hidden');
        document.body.classList.add('preview-open');
    })
    .catch(function(error) {
        console.error('Error opening preview:', error);
        showToast('Failed to load document preview', 'error');
    });
}

function closePreview() {
    previewState.visible = false;
    previewState.document = null;
    
    document.getElementById('preview-panel').classList.add('hidden');
    document.body.classList.remove('preview-open');
}

function renderPreviewPanel() {
    var panel = document.getElementById('preview-panel');
    if (!panel || !previewState.document) return;
    
    var doc = previewState.document;
    var fileType = doc.file_type || doc.filename.split('.').pop();
    var icon = ICONS[fileType] || ICONS.default;
    
    panel.innerHTML = 
        '<div class="preview-header">' +
            '<div class="preview-title">' +
                '<span class="icon">' + icon + '</span>' +
                '<h3>' + (doc.filename || 'Document') + '</h3>' +
            '</div>' +
            '<div class="preview-actions">' +
                '<button class="btn btn-sm" onclick="summarizeDocument(' + doc.doc_id + ')" title="Summarize">📝 Summary</button>' +
                '<button class="btn btn-sm" onclick="findSimilarDocs(' + doc.doc_id + ')" title="Find Similar">🔍 Similar</button>' +
                '<button class="btn btn-sm" onclick="openDocumentChat(' + doc.doc_id + ')" title="Chat">💬 Chat</button>' +
                '<button class="btn btn-sm" onclick="openFileExternal(\'' + (doc.file_path || '').replace(/'/g, "\\'") + '\')" title="Open File">📂 Open</button>' +
                '<button class="icon-btn" onclick="closePreview()" title="Close">✕</button>' +
            '</div>' +
        '</div>' +
        '<div class="preview-meta">' +
            (doc.page_count ? '<span>' + doc.page_count + ' pages</span>' : '') +
            (doc.file_size_bytes ? '<span>' + formatFileSize(doc.file_size_bytes) + '</span>' : '') +
            '<span>' + (doc.extraction_method || 'direct') + '</span>' +
            '<span>' + (doc.chunk_count || 0) + ' chunks</span>' +
        '</div>' +
        '<div class="preview-content" id="preview-content">' +
            (doc.highlighted_content || doc.content || '<p class="empty">No content available</p>') +
        '</div>' +
        (doc.highlight_positions && doc.highlight_positions.length > 0 ? 
            '<div class="preview-navigation">' +
                '<span>' + doc.highlight_positions.length + ' matches</span>' +
                '<button class="btn btn-sm" onclick="navigateHighlight(-1)">◀ Prev</button>' +
                '<button class="btn btn-sm" onclick="navigateHighlight(1)">Next ▶</button>' +
            '</div>' : '');
}

function formatFileSize(bytes) {
    if (!bytes) return '';
    var units = ['B', 'KB', 'MB', 'GB'];
    var size = bytes;
    var unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
        size /= 1024;
        unit++;
    }
    return size.toFixed(1) + ' ' + units[unit];
}

function openFileExternal(filePath) {
    // Attempt to open file - this works in Electron/Tauri, otherwise show path
    showToast('File: ' + filePath, 'info');
}

// ============================================================================
// DOCUMENT SUMMARIES
// ============================================================================

function summarizeDocument(docId, summaryType) {
    summaryType = summaryType || 'executive';
    
    var modal = document.getElementById('summary-modal');
    var content = document.getElementById('summary-content');
    
    if (modal) modal.classList.remove('hidden');
    if (content) content.innerHTML = '<div class="loading">Generating summary...</div>';
    
    fetch(API + '/documents/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId, summary_type: summaryType })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (content) {
            var keyPointsHtml = '';
            if (summaryType === 'key_points' && data.key_points && data.key_points.length > 0) {
                keyPointsHtml = '<ul class="key-points">' + 
                    data.key_points.map(function(p) { return '<li>' + p + '</li>'; }).join('') + 
                    '</ul>';
            }
            
            content.innerHTML = 
                '<div class="summary-header">' +
                    '<h4>' + data.filename + '</h4>' +
                    '<div class="summary-type-tabs">' +
                        '<button class="' + (summaryType === 'executive' ? 'active' : '') + '" onclick="summarizeDocument(' + docId + ', \'executive\')">Executive</button>' +
                        '<button class="' + (summaryType === 'key_points' ? 'active' : '') + '" onclick="summarizeDocument(' + docId + ', \'key_points\')">Key Points</button>' +
                        '<button class="' + (summaryType === 'detailed' ? 'active' : '') + '" onclick="summarizeDocument(' + docId + ', \'detailed\')">Detailed</button>' +
                    '</div>' +
                '</div>' +
                '<div class="summary-body">' +
                    (keyPointsHtml || '<p>' + data.summary + '</p>') +
                '</div>' +
                '<div class="summary-footer">' +
                    'Generated: ' + new Date(data.generated_at).toLocaleString() +
                '</div>';
        }
    })
    .catch(function(error) {
        console.error('Summary error:', error);
        if (content) content.innerHTML = '<p class="error">Failed to generate summary. Check that AI is available.</p>';
    });
}

function closeSummaryModal() {
    var modal = document.getElementById('summary-modal');
    if (modal) modal.classList.add('hidden');
}

// ============================================================================
// SIMILAR DOCUMENTS
// ============================================================================

function findSimilarDocs(docId) {
    var modal = document.getElementById('similar-modal');
    var content = document.getElementById('similar-content');
    
    if (modal) modal.classList.remove('hidden');
    if (content) content.innerHTML = '<div class="loading">Finding similar documents...</div>';
    
    fetch(API + '/documents/' + docId + '/similar?top_k=10')
    .then(function(response) { return response.json(); })
    .then(function(similar) {
        if (content) {
            if (!similar || similar.length === 0) {
                content.innerHTML = '<p class="empty">No similar documents found.</p>';
            } else {
                content.innerHTML = '<div class="similar-list">' +
                    similar.map(function(doc) {
                        var icon = ICONS[doc.file_type] || ICONS.default;
                        return '<div class="similar-item" onclick="openPreview(' + doc.doc_id + '); closeSimilarModal();">' +
                            '<div class="similar-icon">' + icon + '</div>' +
                            '<div class="similar-info">' +
                                '<div class="similar-name">' + doc.filename + '</div>' +
                                '<div class="similar-snippet">' + (doc.snippet || '').substring(0, 100) + '...</div>' +
                            '</div>' +
                            '<div class="similar-score">' + Math.round(doc.similarity_score * 100) + '%</div>' +
                        '</div>';
                    }).join('') +
                '</div>';
            }
        }
    })
    .catch(function(error) {
        console.error('Similar docs error:', error);
        if (content) content.innerHTML = '<p class="error">Failed to find similar documents.</p>';
    });
}

function closeSimilarModal() {
    var modal = document.getElementById('similar-modal');
    if (modal) modal.classList.add('hidden');
}

// ============================================================================
// DOCUMENT CHAT
// ============================================================================

function openDocumentChat(docId) {
    fetch(API + '/documents/' + docId + '/metadata')
    .then(function(response) { return response.json(); })
    .then(function(doc) {
        documentChatState.document = doc;
        documentChatState.history = [];
        
        // Update UI
        var chatHeader = document.getElementById('document-chat-header');
        if (chatHeader) {
            var icon = ICONS[doc.file_type] || ICONS.default;
            chatHeader.innerHTML = 
                '<div class="chat-doc-info">' +
                    '<span class="icon">' + icon + '</span>' +
                    '<span class="name">Chatting with: ' + doc.filename + '</span>' +
                    '<button class="btn btn-sm" onclick="closeDocumentChat()">✕ Exit Chat</button>' +
                '</div>';
            chatHeader.classList.remove('hidden');
        }
        
        // Switch to AI mode with document context
        setSearchMode('ai');
        state.conversationHistory = [];
        
        var answerBody = document.getElementById('ai-answer-body');
        if (answerBody) {
            answerBody.innerHTML = '<p class="info">You are now chatting with <strong>' + doc.filename + '</strong>. All answers will be based only on this document.</p>';
        }
        
        showElement('ai-answer-section');
        hideElement('search-results-section');
        
        showToast('Now chatting with: ' + doc.filename, 'info');
        closePreview();
    })
    .catch(function(error) {
        console.error('Error opening document chat:', error);
        showToast('Failed to open document chat', 'error');
    });
}

function closeDocumentChat() {
    documentChatState.document = null;
    documentChatState.history = [];
    
    var chatHeader = document.getElementById('document-chat-header');
    if (chatHeader) chatHeader.classList.add('hidden');
    
    var answerBody = document.getElementById('ai-answer-body');
    if (answerBody) answerBody.innerHTML = '';
    
    showToast('Document chat closed', 'info');
}

// Override askAI to support document chat
var originalAskAI = typeof askAI === 'function' ? askAI : null;

function askAIWithDocContext(query) {
    if (documentChatState.document) {
        // Chat with specific document
        chatWithDocument(query);
    } else if (originalAskAI) {
        // Regular AI chat
        originalAskAI(query);
    }
}

function chatWithDocument(message) {
    if (!documentChatState.document) return;
    
    var answerBody = document.getElementById('ai-answer-body');
    var loading = document.getElementById('ai-loading');
    
    // Add user message
    appendChatMessage('user', message);
    if (loading) loading.classList.remove('hidden');
    
    fetch(API + '/documents/' + documentChatState.document.doc_id + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            doc_id: documentChatState.document.doc_id,
            message: message,
            conversation_history: documentChatState.history,
            stream: true
        })
    })
    .then(function(response) {
        if (loading) loading.classList.add('hidden');
        
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var fullAnswer = '';
        
        // Create message element for streaming
        var messageDiv = document.createElement('div');
        messageDiv.className = 'conversation-message assistant';
        messageDiv.innerHTML = '<div class="message-role">AI</div><div class="message-content"></div>';
        answerBody.appendChild(messageDiv);
        var contentDiv = messageDiv.querySelector('.message-content');
        
        function read() {
            return reader.read().then(function(result) {
                if (result.done) {
                    // Update history
                    documentChatState.history.push({ role: 'user', content: message });
                    documentChatState.history.push({ role: 'assistant', content: fullAnswer });
                    return;
                }
                
                var chunk = decoder.decode(result.value);
                var lines = chunk.split('\n').filter(function(line) {
                    return line.startsWith('data: ');
                });
                
                lines.forEach(function(line) {
                    var data = line.slice(6);
                    if (data === '[DONE]') return;
                    
                    try {
                        var parsed = JSON.parse(data);
                        if (parsed.token) {
                            fullAnswer += parsed.token;
                            contentDiv.innerHTML = formatMarkdown(fullAnswer);
                        }
                    } catch (e) {}
                });
                
                return read();
            });
        }
        
        return read();
    })
    .catch(function(error) {
        console.error('Document chat error:', error);
        if (loading) loading.classList.add('hidden');
        showToast('Failed to get response', 'error');
    });
}

function appendChatMessage(role, content) {
    var answerBody = document.getElementById('ai-answer-body');
    if (!answerBody) return;
    
    var messageDiv = document.createElement('div');
    messageDiv.className = 'conversation-message ' + role;
    messageDiv.innerHTML = 
        '<div class="message-role">' + (role === 'user' ? 'You' : 'AI') + '</div>' +
        '<div class="message-content">' + formatMarkdown(content) + '</div>';
    answerBody.appendChild(messageDiv);
    answerBody.scrollTop = answerBody.scrollHeight;
}

function formatMarkdown(text) {
    if (!text) return '';
    return text
        .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

// ============================================================================
// INDEXING PROGRESS
// ============================================================================

function checkIndexingSessions() {
    fetch(API + '/progress/sessions')
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.sessions && data.sessions.length > 0) {
            var active = data.sessions.find(function(s) {
                return s.status !== 'complete' && s.status !== 'failed' && s.status !== 'cancelled';
            });
            
            if (active) {
                indexingState.activeSessionId = active.session_id;
                showIndexingProgress(active);
                subscribeToProgress(active.session_id);
            }
        }
    })
    .catch(function(error) {
        console.error('Error checking sessions:', error);
    });
}

function showIndexingProgress(session) {
    var panel = document.getElementById('indexing-progress-panel');
    
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'indexing-progress-panel';
        panel.className = 'indexing-progress-panel';
        document.body.appendChild(panel);
    }
    
    var folderName = session.folder_path ? session.folder_path.split('/').pop() : 'folder';
    
    panel.innerHTML = 
        '<div class="progress-header">' +
            '<h4>📁 Indexing: ' + folderName + '</h4>' +
            '<div class="progress-controls">' +
                (session.is_paused ? 
                    '<button class="btn btn-sm" onclick="resumeIndexing(\'' + session.session_id + '\')">▶ Resume</button>' :
                    '<button class="btn btn-sm" onclick="pauseIndexing(\'' + session.session_id + '\')">⏸ Pause</button>') +
                '<button class="btn btn-sm btn-danger" onclick="cancelIndexing(\'' + session.session_id + '\')">✕ Cancel</button>' +
                '<button class="btn btn-sm" onclick="minimizeProgress()">_</button>' +
            '</div>' +
        '</div>' +
        '<div class="progress-bar-container">' +
            '<div class="progress-bar" style="width: ' + session.overall_percent + '%"></div>' +
            '<span class="progress-text">' + session.overall_percent + '%</span>' +
        '</div>' +
        '<div class="progress-stats">' +
            '<div class="stat"><span class="label">Files</span><span class="value">' + session.processed_files + ' / ' + session.total_files + '</span></div>' +
            '<div class="stat"><span class="label">Status</span><span class="value status-' + session.status + '">' + session.status + '</span></div>' +
            '<div class="stat"><span class="label">Speed</span><span class="value">' + (session.files_per_second || 0).toFixed(1) + '/s</span></div>' +
            '<div class="stat"><span class="label">ETA</span><span class="value">' + formatDuration(session.estimated_remaining_seconds) + '</span></div>' +
        '</div>' +
        '<div class="progress-current">' +
            (session.current_file ? 
                '<span class="current-label">Processing: </span><span class="current-file">' + session.current_file + '</span>' : '') +
        '</div>' +
        '<div class="progress-results">' +
            '<span class="success">✓ ' + (session.successful_files || 0) + '</span>' +
            '<span class="warning">⚠ ' + (session.warning_files || 0) + '</span>' +
            '<span class="failed">✕ ' + (session.failed_files || 0) + '</span>' +
        '</div>' +
        '<div class="progress-log" id="progress-log"></div>';
    
    panel.classList.remove('hidden', 'minimized');
}

function subscribeToProgress(sessionId) {
    if (indexingState.eventSource) {
        indexingState.eventSource.close();
    }
    
    indexingState.eventSource = new EventSource(API + '/progress/sessions/' + sessionId + '/stream');
    
    indexingState.eventSource.onmessage = function(event) {
        var data = JSON.parse(event.data);
        
        if (data.type === 'session') {
            showIndexingProgress(data.data);
        }
        
        if (data.type === 'file') {
            appendProgressLog(data.data);
        }
        
        if (data.type === 'complete') {
            indexingState.eventSource.close();
            showIndexingComplete(data.data);
        }
        
        if (data.error) {
            indexingState.eventSource.close();
            showToast('Indexing session ended', 'error');
        }
    };
    
    indexingState.eventSource.onerror = function() {
        indexingState.eventSource.close();
    };
}

function appendProgressLog(fileProgress) {
    var log = document.getElementById('progress-log');
    if (!log) return;
    
    var statusIcons = { success: '✓', warning: '⚠', failed: '✕', skipped: '○' };
    
    var entry = document.createElement('div');
    entry.className = 'log-entry status-' + fileProgress.status;
    entry.innerHTML = 
        '<span class="log-status">' + (statusIcons[fileProgress.status] || '•') + '</span>' +
        '<span class="log-file">' + fileProgress.filename + '</span>' +
        (fileProgress.chunks_created ? '<span class="log-chunks">' + fileProgress.chunks_created + ' chunks</span>' : '') +
        (fileProgress.error_message ? '<span class="log-error">' + fileProgress.error_message + '</span>' : '');
    
    log.insertBefore(entry, log.firstChild);
    
    while (log.children.length > 50) {
        log.removeChild(log.lastChild);
    }
}

function showIndexingComplete(session) {
    var panel = document.getElementById('indexing-progress-panel');
    if (!panel) return;
    
    panel.innerHTML = 
        '<div class="progress-complete">' +
            '<h4>✓ Indexing Complete</h4>' +
            '<div class="complete-stats">' +
                '<p>Processed ' + session.total_files + ' files</p>' +
                '<p>✓ ' + session.successful_files + ' success | ⚠ ' + session.warning_files + ' warnings | ✕ ' + session.failed_files + ' failed</p>' +
                '<p>Created ' + (session.total_chunks || 0) + ' chunks</p>' +
            '</div>' +
            '<button class="btn btn-primary" onclick="hideProgress()">Close</button>' +
            (session.failed_files > 0 ? '<button class="btn" onclick="viewQuarantine()">View Failed Files</button>' : '') +
        '</div>';
    
    showToast('Indexing complete!', 'success');
    loadStats();
}

function pauseIndexing(sessionId) {
    fetch(API + '/progress/sessions/' + sessionId + '/pause', { method: 'POST' })
    .then(function() { showToast('Indexing paused', 'info'); });
}

function resumeIndexing(sessionId) {
    fetch(API + '/progress/sessions/' + sessionId + '/resume', { method: 'POST' })
    .then(function() { showToast('Indexing resumed', 'info'); });
}

function cancelIndexing(sessionId) {
    if (confirm('Are you sure you want to cancel indexing?')) {
        fetch(API + '/progress/sessions/' + sessionId + '/cancel', { method: 'POST' })
        .then(function() {
            hideProgress();
            showToast('Indexing cancelled', 'info');
        });
    }
}

function minimizeProgress() {
    var panel = document.getElementById('indexing-progress-panel');
    if (panel) panel.classList.toggle('minimized');
}

function hideProgress() {
    var panel = document.getElementById('indexing-progress-panel');
    if (panel) panel.classList.add('hidden');
    indexingState.activeSessionId = null;
}

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '--';
    if (seconds < 60) return Math.round(seconds) + 's';
    if (seconds < 3600) return Math.round(seconds / 60) + 'm';
    return Math.round(seconds / 3600) + 'h ' + Math.round((seconds % 3600) / 60) + 'm';
}

function viewQuarantine() {
    switchView('settings');
    // TODO: Switch to quarantine tab
}

// Check for active indexing on page load
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(checkIndexingSessions, 1000);
});

// ============================================================================
// ENHANCED SEARCH RESULTS RENDERING
// ============================================================================

// Override renderResults to add action buttons
var originalRenderResults = typeof renderResults === 'function' ? renderResults : null;

function renderResultsWithActions(results) {
    var listEl = document.getElementById('results-list');
    if (!listEl) return;
    
    if (!results || results.length === 0) {
        listEl.innerHTML = '<div class="no-results">No results found</div>';
        return;
    }
    
    listEl.innerHTML = results.map(function(result, index) {
        var icon = ICONS[result.file_type] || ICONS.default;
        var snippets = (result.snippets || []).slice(0, 2).map(function(s) {
            return '<p class="snippet">' + s + '</p>';
        }).join('');
        
        return '<div class="result-item" tabindex="0" data-doc-id="' + result.id + '" onclick="openPreview(' + result.id + ')">' +
            '<div class="result-header">' +
                '<span class="result-icon">' + icon + '</span>' +
                '<span class="result-title">' + result.filename + '</span>' +
                '<span class="result-score">' + Math.round(result.score * 100) + '%</span>' +
            '</div>' +
            '<div class="result-snippets">' + snippets + '</div>' +
            '<div class="result-meta">' +
                '<span>' + result.file_type + '</span>' +
                (result.page_count ? '<span>' + result.page_count + ' pages</span>' : '') +
                (result.doc_author ? '<span>' + result.doc_author + '</span>' : '') +
            '</div>' +
            '<div class="result-actions">' +
                '<button class="btn-xs" onclick="event.stopPropagation(); summarizeDocument(' + result.id + ')" title="Summarize">📝</button>' +
                '<button class="btn-xs" onclick="event.stopPropagation(); findSimilarDocs(' + result.id + ')" title="Similar">🔍</button>' +
                '<button class="btn-xs" onclick="event.stopPropagation(); openDocumentChat(' + result.id + ')" title="Chat">💬</button>' +
            '</div>' +
        '</div>';
    }).join('');
}
