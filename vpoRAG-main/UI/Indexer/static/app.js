const socket = io();
let configSections = [];

// Tab switching
function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    
    document.getElementById(`${tabName}-tab`).classList.add('active');
    event.target.classList.add('active');
    
    if (tabName === 'settings') loadConfig();
    if (tabName === 'logs') loadLogs();
}

// Load stats on page load
window.addEventListener('DOMContentLoaded', () => {
    refreshStats();
});

// Refresh stats
function refreshStats() {
    fetch('/api/stats')
        .then(r => r.json())
        .then(data => {
            document.getElementById('file-count').textContent = `Files: ${data.file_count}`;
            document.getElementById('chunk-count').textContent = `Chunks: ${data.total_chunks}`;
            document.getElementById('last-build').textContent = `Last Build: ${data.last_build}`;
            document.getElementById('src-dir').value = data.src_dir;
            document.getElementById('out-dir').value = data.out_dir;
            
            // Display category breakdown
            const statsDiv = document.getElementById('category-stats');
            if (data.chunk_counts && Object.keys(data.chunk_counts).length > 0) {
                let html = '<h3>Category Breakdown</h3>';
                for (const [category, count] of Object.entries(data.chunk_counts)) {
                    html += `<div class="category-item"><span>${category}</span><span>${count} chunks</span></div>`;
                }
                statsDiv.innerHTML = html;
            } else {
                statsDiv.innerHTML = '<p class="info">No chunks indexed yet. Click "Build Index" to start.</p>';
            }
        })
        .catch(err => console.error('Failed to load stats:', err));
}

// Build index
function buildIndex() {
    const logsDiv = document.getElementById('build-logs');
    logsDiv.innerHTML = '=== Starting incremental build ===\n';
    
    fetch('/api/build', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'started') {
                logsDiv.innerHTML += 'Build process started...\n';
            }
        })
        .catch(err => {
            logsDiv.innerHTML += `ERROR: ${err}\n`;
        });
}

// Rebuild all
function rebuildAll() {
    if (!confirm('This will delete the processing state and rebuild all documents. Continue?')) {
        return;
    }
    
    const logsDiv = document.getElementById('build-logs');
    logsDiv.innerHTML = '=== Starting full rebuild ===\n';
    
    fetch('/api/rebuild', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'started') {
                logsDiv.innerHTML += 'Rebuild process started...\n';
            }
        })
        .catch(err => {
            logsDiv.innerHTML += `ERROR: ${err}\n`;
        });
}

// Build incremental (index only, no cross-refs)
function buildIncremental() {
    const logsDiv = document.getElementById('build-logs');
    logsDiv.innerHTML = '=== Starting incremental indexing (no cross-references) ===\n';
    
    fetch('/api/build-incremental', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'started') {
                logsDiv.innerHTML += 'Incremental indexing started...\n';
            }
        })
        .catch(err => {
            logsDiv.innerHTML += `ERROR: ${err}\n`;
        });
}

// Build cross-references incrementally
function buildCrossRefsIncremental() {
    if (!confirm('WARNING: This only creates backward references (existing→new chunks).\nNot bidirectional. Continue?')) {
        return;
    }
    
    const logsDiv = document.getElementById('build-logs');
    logsDiv.innerHTML = '=== Starting incremental cross-reference build ===\n';
    
    fetch('/api/build-crossrefs-incremental', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'started') {
                logsDiv.innerHTML += 'Incremental cross-reference build started...\n';
            }
        })
        .catch(err => {
            logsDiv.innerHTML += `ERROR: ${err}\n`;
        });
}

// Socket.IO log streaming
socket.on('log', (data) => {
    const logsDiv = document.getElementById('build-logs');
    logsDiv.innerHTML += data.data + '\n';
    logsDiv.scrollTop = logsDiv.scrollHeight;
});

socket.on('build_complete', (data) => {
    const logsDiv = document.getElementById('build-logs');
    logsDiv.innerHTML += `\n=== Build completed (exit code: ${data.code}) ===\n`;
    refreshStats();
});

// Load configuration
function loadConfig() {
    fetch('/api/config')
        .then(r => r.json())
        .then(data => {
            configSections = data.sections;
            renderConfigEditor();
        })
        .catch(err => console.error('Failed to load config:', err));
}

// Render structured config editor
function renderConfigEditor() {
    const container = document.getElementById('config-editor');
    container.innerHTML = '';
    
    configSections.forEach((section, sectionIdx) => {
        const sectionDiv = document.createElement('div');
        sectionDiv.className = 'config-section';
        
        const sectionHeader = document.createElement('h3');
        sectionHeader.className = 'config-section-header';
        sectionHeader.textContent = section.name;
        sectionDiv.appendChild(sectionHeader);
        
        section.fields.forEach((field, fieldIdx) => {
            const fieldDiv = document.createElement('div');
            fieldDiv.className = 'config-field';
            
            const fieldLabel = document.createElement('label');
            fieldLabel.className = 'config-field-label';
            fieldLabel.textContent = field.name;
            fieldDiv.appendChild(fieldLabel);
            
            if (field.comment) {
                const fieldComment = document.createElement('div');
                fieldComment.className = 'config-field-comment';
                fieldComment.textContent = field.comment;
                fieldDiv.appendChild(fieldComment);
            }
            
            const fieldInput = document.createElement('input');
            fieldInput.type = 'text';
            fieldInput.className = 'config-field-input';
            fieldInput.value = field.value;
            fieldInput.dataset.section = sectionIdx;
            fieldInput.dataset.field = fieldIdx;
            fieldInput.addEventListener('input', (e) => {
                configSections[sectionIdx].fields[fieldIdx].value = e.target.value;
            });
            fieldDiv.appendChild(fieldInput);
            
            sectionDiv.appendChild(fieldDiv);
        });
        
        container.appendChild(sectionDiv);
    });
}

// Save configuration
function saveConfig() {
    fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sections: configSections })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'saved') {
            alert('Configuration saved successfully! Changes will take effect on next build.');
        }
    })
    .catch(err => alert('Failed to save config: ' + err));
}

// Load full logs
function loadLogs() {
    fetch('/api/logs')
        .then(r => r.json())
        .then(data => {
            document.getElementById('full-logs').textContent = data.logs;
        })
        .catch(err => console.error('Failed to load logs:', err));
}
