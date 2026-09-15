const API_BASE_URL = 'http://localhost:8001';

// DOM Elements
const topbarLogo = document.getElementById('topbar-logo');
const topbarTitle = document.getElementById('topbar-title');
const topbarDivider = document.getElementById('topbar-divider');
const hero = document.getElementById('hero');
const selectedImageView = document.getElementById('selected-image-view');
const processingState = document.getElementById('processing-state');
const resultsView = document.getElementById('results-view');
const heroDropzone = document.getElementById('hero-dropzone');
const heroUploadBtn = document.getElementById('hero-upload-btn') || heroDropzone;
const sidebarUploadBtn = document.getElementById('sidebar-upload-btn');
const fileInput = document.createElement('input');
fileInput.type = 'file';
fileInput.accept = '.png,.jpg,.jpeg,image/*';
fileInput.multiple = true;
fileInput.hidden = true;
document.body.appendChild(fileInput);

const imageStack = document.getElementById('image-stack');
const stackEmpty = document.getElementById('stack-empty');
const selectedImage = document.getElementById('selected-image');
const extractBtn = document.getElementById('extract-btn');
const statusText = document.getElementById('status-text');
const resultImage = document.getElementById('result-image');
const resultsDataPanel = document.getElementById('results-data-panel');
const themeToggle = document.getElementById('theme-toggle-checkbox');
const zoomInBtn = document.getElementById('zoom-in-btn');
const zoomOutBtn = document.getElementById('zoom-out-btn');
const zoomResetBtn = document.getElementById('zoom-reset-btn');
const zoomLevelBadge = document.getElementById('zoom-level-badge');
const viewerDocTitle = document.getElementById('viewer-doc-title');
const uploadCountBadge = document.getElementById('upload-count-badge');
const documentSearch = document.getElementById('document-search');
const searchClearBtn = document.getElementById('search-clear-btn');
const saveChangesBtn = document.getElementById('save-changes-btn');
const saveBtnIcon = document.getElementById('save-btn-icon');
const saveBtnText = document.getElementById('save-btn-text');
const extractionStatusPill = document.getElementById('extraction-status-pill');
let searchQuery = '';

// State
let selectedFile = null;
let uploads = []; // from server manifest
let selectedUploadId = null;
let currentStructuredData = null;
let progressInterval = null;
let extractionStates = {};   // { uploadId: 'processing' | 'completed' | 'failed' }
let activeExtractionId = null;  // which upload is currently being polled

// Theme Initialization & Persistence
function applyTheme(isLight) {
    document.documentElement.classList.toggle('light-mode', isLight);
    document.body.classList.toggle('light-mode', isLight);
    if (themeToggle) {
        themeToggle.checked = isLight;
    }
}

try {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        applyTheme(true);
    } else if (savedTheme === 'dark') {
        applyTheme(false);
    }
} catch (e) {
    console.warn('LocalStorage error while reading theme:', e);
}

if (themeToggle) {
    themeToggle.addEventListener('change', () => {
        const isLight = themeToggle.checked;
        applyTheme(isLight);
        try {
            localStorage.setItem('theme', isLight ? 'light' : 'dark');
        } catch (e) {
            console.warn('LocalStorage error while saving theme:', e);
        }
    });
}

// Upload dropzone interactions
if (heroDropzone) {
    heroDropzone.addEventListener('click', () => fileInput.click());

    heroDropzone.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInput.click();
        }
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        heroDropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            heroDropzone.classList.add('dragover');
        });
    });

    ['dragleave', 'dragend', 'drop'].forEach(eventName => {
        heroDropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            heroDropzone.classList.remove('dragover');
        });
    });

    heroDropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        if (dt && dt.files && dt.files.length > 0) {
            Array.from(dt.files).forEach(file => uploadFile(file));
        }
    });
} else if (heroUploadBtn) {
    heroUploadBtn.addEventListener('click', () => fileInput.click());
}

if (sidebarUploadBtn) {
    sidebarUploadBtn.addEventListener('click', () => fileInput.click());
}

// Clipboard paste handling
window.addEventListener('paste', (e) => {
    if (hero && hero.style.display === 'none') return;
    const clipboardData = e.clipboardData;
    if (!clipboardData) return;

    const items = clipboardData.items;
    if (!items || items.length === 0) return;

    let filesFound = [];
    for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') {
            const file = items[i].getAsFile();
            if (file) filesFound.push(file);
        }
    }

    if (filesFound.length > 0) {
        e.preventDefault();
        filesFound.forEach(file => uploadFile(file));
    }
});

// Search / Filter logs
if (documentSearch) {
    documentSearch.addEventListener('input', (e) => {
        searchQuery = e.target.value.trim().toLowerCase();
        if (searchClearBtn) {
            searchClearBtn.style.display = searchQuery ? 'block' : 'none';
        }
        renderSidebar();
    });
}

if (searchClearBtn) {
    searchClearBtn.addEventListener('click', () => {
        if (documentSearch) {
            documentSearch.value = '';
            searchQuery = '';
            searchClearBtn.style.display = 'none';
            renderSidebar();
            documentSearch.focus();
        }
    });
}

fileInput.addEventListener('change', () => {
    const files = Array.from(fileInput.files);
    files.forEach(file => uploadFile(file));
    fileInput.value = '';
});

async function uploadFile(file) {
    if (!file) return;
    selectedFile = file;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch(`${API_BASE_URL}/api/upload`, {
            method: 'POST',
            body: formData,
        });
        if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
        const data = await resp.json();

        // Refresh sidebar so the new image shows up immediately
        await fetchUploads();

        // Select the newly uploaded image (shows preview + Extract button)
        selectUpload(data.upload_id);
    } catch (err) {
        console.error(err);
        showToast('Upload failed.', true);
    }
}

if (extractBtn) {
    extractBtn.addEventListener('click', (e) => {
        e.preventDefault();
        console.log('Extract clicked, uploadId =', selectedUploadId);
        if (selectedFile) {
            processExtraction(selectedUploadId);
        } else {
            showToast('Please select an uploaded image first.', true);
        }
    });
}

async function processExtraction(uploadId) {
    if (!uploadId) return;

    // Remember we're processing this upload
    extractionStates[uploadId] = 'processing';
    activeExtractionId = uploadId;
    selectedUploadId = uploadId;

    // Show processing state
    selectedImageView.style.display = 'none';
    processingState.style.display = 'flex';
    resultsView.style.display = 'none';
    const processingTitle = document.querySelector('.processing-title');
    if (processingTitle) processingTitle.textContent = 'AI-powered OCR Extraction';
    startProgressPolling(uploadId);

    try {
        const response = await fetch(`${API_BASE_URL}/api/extract/${uploadId}`, {
            method: 'POST',
        });
        if (!response.ok) throw new Error(`Server responded ${response.status}`);
        // Backend runs in background; UI updates via polling.
    } catch (err) {
        console.error(err);
        extractionStates[uploadId] = 'failed';
        if (activeExtractionId === uploadId && progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
        }
        if (selectedUploadId === uploadId) {
            processingState.style.display = 'none';
            resultsView.style.display = 'flex';
            resultsDataPanel.innerHTML = '<div class="error-message">Extraction failed.</div>';
        }
    }
}

function startProgressPolling(uploadId) {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    if (statusText) statusText.textContent = 'Uploading...';

    progressInterval = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE_URL}/api/progress/${uploadId}`);
            if (!resp.ok) return;
            const data = await resp.json();
            updateStatusText(data.stage);
        } catch (err) {
            console.error('Progress check failed', err);
        }
    }, 1000);
}

async function updateStatusText(stage) {
    if (!statusText) return;
    switch (stage) {
        case 'uploading': statusText.textContent = 'Uploading image...'; break;
        case 'queued': statusText.textContent = 'Queued...'; break;
        case 'validating': statusText.textContent = 'Validating image...'; break;
        case 'preprocessing': statusText.textContent = 'Preprocessing image...'; break;
        case 'ocr': statusText.textContent = 'Extracting text (GLM-OCR)...'; break;
        case 'postprocessing': statusText.textContent = 'Post-processing...'; break;
        case 'extracting': statusText.textContent = 'Parsing fields...'; break;
        case 'saving': statusText.textContent = 'Saving...'; break;
        case 'finalizing': statusText.textContent = 'Finalizing results...'; break;
        case 'completed':
            statusText.textContent = 'Completed!';
            if (progressInterval) { clearInterval(progressInterval); progressInterval = null; }
            if (activeExtractionId) {
                extractionStates[activeExtractionId] = 'completed';
            }
            const completedId = activeExtractionId;
            activeExtractionId = null;
            await fetchUploads();
            // If the user is still on this upload, load the result
            if (selectedUploadId && extractionStates[selectedUploadId] === 'completed') {
                selectUpload(selectedUploadId);
            }
            break;
        case 'failed':
            statusText.textContent = 'Error occurred';
            if (progressInterval) { clearInterval(progressInterval); progressInterval = null; }
            break;
        default: statusText.textContent = 'Processing...';
    }
}

async function fetchUploads() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/uploads`);
        if (!response.ok) throw new Error('Failed to load uploads');
        const data = await response.json();
        uploads = data.uploads || [];
        renderSidebar();
    } catch (err) {
        console.error(err);
    }
}

function renderSidebar() {
    if (uploadCountBadge) {
        uploadCountBadge.textContent = uploads.length;
    }
    imageStack.innerHTML = '';
    if (uploads.length === 0) {
        stackEmpty.textContent = 'No documents uploaded';
        stackEmpty.style.display = 'block';
        return;
    }

    const filtered = searchQuery
        ? uploads.filter(u => {
            const name = (u.original_filename || u.id || '').toLowerCase();
            return name.includes(searchQuery);
        })
        : uploads;

    if (filtered.length === 0) {
        stackEmpty.textContent = 'No matching logs found';
        stackEmpty.style.display = 'block';
        return;
    }

    stackEmpty.style.display = 'none';
    filtered.forEach(upload => {
        const row = document.createElement('div');
        row.className = 'image-stack-item';
        if (upload.id === selectedUploadId) row.classList.add('active');

        // Name (clickable to select)
        const nameSpan = document.createElement('span');
        nameSpan.className = 'item-name';
        nameSpan.textContent = upload.original_filename || upload.id;
        nameSpan.addEventListener('click', () => selectUpload(upload.id));
        row.appendChild(nameSpan);

        // Delete button
        const delBtn = document.createElement('button');
        delBtn.className = 'item-delete';
        delBtn.textContent = '×';
        delBtn.title = 'Delete this upload';
        delBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // prevent selecting when deleting
            deleteUpload(upload.id);
        });
        row.appendChild(delBtn);

        imageStack.appendChild(row);
    });
}

async function selectUpload(uploadId) {
    selectedUploadId = uploadId;
    const currentUpload = uploads.find(u => u.id === uploadId);
    if (currentUpload && viewerDocTitle) {
        viewerDocTitle.textContent = currentUpload.original_filename || 'PDF View';
    }
    renderSidebar();
    selectedImageView.style.display = 'none';
    processingState.style.display = 'none';
    resultsView.style.display = 'none';
    transitionToWorkspace();

    // Fetch and set the image immediately for all cases
    let imageUrl = null;
    try {
        const imageResp = await fetch(`${API_BASE_URL}/api/uploads/${uploadId}/image`);
        const imageBlob = await imageResp.blob();
        imageUrl = URL.createObjectURL(imageBlob);
    } catch (err) {
        console.error('Failed to load image:', err);
    }

    // Case 1: extraction is currently running for this upload
    if (extractionStates[uploadId] === 'processing') {
        activeExtractionId = uploadId;
        processingState.style.display = 'flex';
        if (statusText) statusText.textContent = 'Processing...';
        startProgressPolling(uploadId);
        return;
    }

    // Case 2: extraction was completed → show results
    if (extractionStates[uploadId] === 'completed' || (currentUpload && currentUpload.status === 'completed')) {
        try {
            const resultResp = await fetch(`${API_BASE_URL}/api/uploads/${uploadId}/result`);
            if (!resultResp.ok) throw new Error('Failed to load result');
            const resultData = await resultResp.json();
            resultsView.style.display = 'flex';
            if (imageUrl) resultImage.src = imageUrl;
            resetViewer();
            renderExtractedData(resultData.structured_data);
            if (extractionStatusPill) {
                extractionStatusPill.textContent = '● Extracted';
                extractionStatusPill.className = 'status-pill status-success';
            }
        } catch (err) {
            console.error(err);
            resultsView.style.display = 'flex';
            resultsDataPanel.innerHTML = '<div class="error-message">Failed to load this upload.</div>';
        }
        return;
    }

    // Case 3: not yet extracted → show preview + Extract button
    if (imageUrl) selectedImage.src = imageUrl;
    selectedImageView.style.display = 'flex';
    extractBtn.onclick = () => processExtraction(uploadId);
}

async function deleteUpload(uploadId) {
    if (!confirm('Delete this upload and all its extracted data?')) return;

    try {
        const resp = await fetch(`${API_BASE_URL}/api/uploads/${uploadId}`, {
            method: 'DELETE'
        });
        if (!resp.ok) throw new Error(`Server responded ${resp.status}`);

        // If the deleted upload was selected, clear the results panel
        if (selectedUploadId === uploadId) {
            selectedUploadId = null;
            resultsDataPanel.innerHTML = '';
            resultImage.src = '';
            resultsView.style.display = 'none';
            selectedImageView.style.display = 'none';
            hero.style.display = 'flex';
            topbarLogo.style.display = 'none';
            topbarTitle.style.display = 'none';
        }

        // Refresh sidebar
        await fetchUploads();
    } catch (err) {
        console.error('Delete failed:', err);
        showToast('Failed to delete upload.', true);
    }
}

function transitionToWorkspace() {
    hero.style.display = 'none';
    topbarLogo.style.display = 'flex';
    if (topbarDivider) topbarDivider.style.display = 'block';
    topbarTitle.style.display = 'inline-block';
}

// Zoom/Pan
let scale = 1, translateX = 0, translateY = 0;
let isDragging = false, startX, startY;
let rafPending = false;

const resultsImagePanel = document.querySelector('.results-image-panel');

function scheduleViewerUpdate() {
    if (!rafPending) {
        rafPending = true;
        requestAnimationFrame(() => {
            resultImage.style.transform = `translate3d(${translateX}px, ${translateY}px, 0) scale(${scale})`;
            if (zoomLevelBadge) {
                zoomLevelBadge.textContent = `${Math.round(scale * 100)}%`;
            }
            rafPending = false;
        });
    }
}

function updateViewerTransform() {
    scheduleViewerUpdate();
}

function resetViewer() {
    scale = 1;
    translateX = 0;
    translateY = 0;
    scheduleViewerUpdate();
}

if (resultsImagePanel) {
    resultsImagePanel.addEventListener('wheel', (e) => {
        e.preventDefault();
        const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
        scale = Math.min(Math.max(scale * zoomFactor, 0.4), 4.5);
        scheduleViewerUpdate();
    }, { passive: false });

    resultsImagePanel.addEventListener('mousedown', (e) => {
        isDragging = true;
        startX = e.clientX - translateX;
        startY = e.clientY - translateY;
    });

    resultsImagePanel.addEventListener('touchstart', (e) => {
        if (e.touches.length === 1) {
            isDragging = true;
            startX = e.touches[0].clientX - translateX;
            startY = e.touches[0].clientY - translateY;
        }
    }, { passive: true });

    resultsImagePanel.addEventListener('touchmove', (e) => {
        if (isDragging && e.touches.length === 1) {
            translateX = e.touches[0].clientX - startX;
            translateY = e.touches[0].clientY - startY;
            scheduleViewerUpdate();
            e.preventDefault();
        }
    }, { passive: false });

    resultsImagePanel.addEventListener('touchend', () => {
        isDragging = false;
    });
}

window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    translateX = e.clientX - startX;
    translateY = e.clientY - startY;
    scheduleViewerUpdate();
});

window.addEventListener('mouseup', () => {
    isDragging = false;
});

if (zoomInBtn) {
    zoomInBtn.addEventListener('click', () => {
        scale = Math.min(scale * 1.25, 4.5);
        scheduleViewerUpdate();
    });
}

if (zoomOutBtn) {
    zoomOutBtn.addEventListener('click', () => {
        scale = Math.max(scale * 0.8, 0.4);
        scheduleViewerUpdate();
    });
}

if (zoomResetBtn) {
    zoomResetBtn.addEventListener('click', () => {
        resetViewer();
    });
}

// ================== GENERIC RENDERING ==================

function renderExtractedData(data) {
    console.log('Rendering extracted data:', data);
    resultsDataPanel.innerHTML = '';
    if (!data) {
        currentStructuredData = null;
        return;
    }

    // Ensure we have a Document object with sections
    if (!data.sections && (data.header || data.sample_data_table)) {
        // Legacy BoringLog conversion
        data = convertLegacyToDocument(data);
    }

    if (data.sections && Array.isArray(data.sections)) {
        currentStructuredData = JSON.parse(JSON.stringify(data));
        data.sections.forEach((section, idx) => {
            renderSection(section, idx);
        });
    } else {
        // Fallback: treat as raw text
        resultsDataPanel.innerHTML = `<div class="error-message">No recognizable sections found.</div>`;
        currentStructuredData = data;
    }
}

function convertLegacyToDocument(legacy) {
    const sections = [];
    if (legacy.header) {
        const fields = {};
        Object.keys(legacy.header).forEach(key => {
            if (legacy.header[key] !== null && legacy.header[key] !== undefined) {
                fields[key] = String(legacy.header[key]);
            }
        });
        sections.push({ name: 'Header', type: 'key_value', fields });
    }
    if (legacy.boring_advancement) {
        const fields = {};
        const adv = legacy.boring_advancement;
        ['Start_Date', 'Start_Time', 'Finish_Date', 'Finish_Time'].forEach(k => {
            if (adv[k] !== null && adv[k] !== undefined) fields[k] = String(adv[k]);
        });
        if (adv.advancement_rows && Array.isArray(adv.advancement_rows) && adv.advancement_rows.length > 0) {
            const columns = ['Depth', 'Method'];
            const rows = adv.advancement_rows.map(r => ({ Depth: r.Depth || '', Method: r.Method || '' }));
            sections.push({ name: 'Boring Advancement', type: 'table', columns, rows });
        } else if (Object.keys(fields).length > 0) {
            sections.push({ name: 'Boring Advancement', type: 'key_value', fields });
        }
    }
    if (legacy.sample_data_table && Array.isArray(legacy.sample_data_table)) {
        const columns = ['No.', 'From', 'To', 'Type', 'Blow 1', 'Blow 2', 'Blow 3', 'Blow 4', 'Recovery'];
        const rows = legacy.sample_data_table.map(row => ({
            'No.': row.sample_no || '',
            'From': row.from_depth || '',
            'To': row.to_depth || '',
            'Type': row.type || '',
            'Blow 1': row.blow_1 || '',
            'Blow 2': row.blow_2 || '',
            'Blow 3': row.blow_3 || '',
            'Blow 4': row.blow_4 || '',
            'Recovery': row.recovery || ''
        }));
        sections.push({ name: 'Sample Data Table', type: 'table', columns, rows });
    }
    if (legacy.lithology_data_table && Array.isArray(legacy.lithology_data_table)) {
        const columns = ['Depth From', 'Depth To', 'Description'];
        const rows = legacy.lithology_data_table.map(row => ({
            'Depth From': row.depth_from || '',
            'Depth To': row.depth_to || '',
            'Description': row.description || ''
        }));
        sections.push({ name: 'Lithology / Sample Description Table', type: 'table', columns, rows });
    }
    if (legacy.surface_cover_thickness) {
        const fields = {};
        Object.keys(legacy.surface_cover_thickness).forEach(k => {
            if (legacy.surface_cover_thickness[k] !== null && legacy.surface_cover_thickness[k] !== undefined) fields[k] = String(legacy.surface_cover_thickness[k]);
        });
        sections.push({ name: 'Surface Cover & Thickness', type: 'key_value', fields });
    }
    if (legacy.water_level_observations) {
        const fields = {};
        Object.keys(legacy.water_level_observations).forEach(k => {
            if (legacy.water_level_observations[k] !== null && legacy.water_level_observations[k] !== undefined) fields[k] = String(legacy.water_level_observations[k]);
        });
        sections.push({ name: 'Water Level Observations', type: 'key_value', fields });
    }
    if (legacy.boring_abandonment) {
        const fields = {};
        Object.keys(legacy.boring_abandonment).forEach(k => {
            if (legacy.boring_abandonment[k] !== null && legacy.boring_abandonment[k] !== undefined) fields[k] = String(legacy.boring_abandonment[k]);
        });
        sections.push({ name: 'Boring Abandonment', type: 'key_value', fields });
    }
    if (legacy.additional_remarks) {
        sections.push({ name: 'Additional Remarks', type: 'raw_text', text: String(legacy.additional_remarks) });
    }
    return { sections };
}

function renderSection(section, sectionIdx) {
    if (!section || !section.type) return;

    if (section.type === 'key_value') {
        let rowsHtml = '';
        if (section.fields && typeof section.fields === 'object') {
            for (const [key, value] of Object.entries(section.fields)) {
                const label = key.replace(/_/g, ' ');
                const rawVal = (value === null || value === undefined || value === '') ? '' : String(value);
                const displayValue = rawVal === '' ? '<span class="blank">—</span>' : escapeHtml(rawVal);
                rowsHtml += `
                    <div class="field-row">
                        <span class="field-label editable-field" contenteditable="true" spellcheck="false"
                              data-section-index="${sectionIdx}" data-field="${escapeHtml(key)}" data-label="true">${escapeHtml(label)}</span>
                        <span class="field-value editable-field" contenteditable="true" spellcheck="false"
                              data-section-index="${sectionIdx}" data-field="${escapeHtml(key)}">${displayValue}</span>
                    </div>`;
            }
        }
        if (!rowsHtml) return;
        const card = document.createElement('div');
        card.className = 'section-card';
        card.innerHTML = `<div class="section-title">${escapeHtml(section.name)}</div>${rowsHtml}`;
        resultsDataPanel.appendChild(card);
        if (section.raw_text) {
            const details = document.createElement('details');
            details.className = 'raw-text-details';
            details.innerHTML = `<summary>Show Raw OCR Text</summary><pre>${escapeHtml(section.raw_text)}</pre>`;
            resultsDataPanel.appendChild(details);
        }

    } else if (section.type === 'table') {
        let tableHtml = `<div class="section-card"><div class="section-title">${escapeHtml(section.name)}</div><div class="table-container"><table>`;
        const columns = section.columns || [];
        if (columns.length > 0) {
            tableHtml += '<thead><tr>';
            columns.forEach(col => {
                tableHtml += `<th contenteditable="true" spellcheck="false"
                                 data-section-index="${sectionIdx}" data-column="${escapeHtml(col)}" data-header="true">${escapeHtml(col)}</th>`;
            });
            tableHtml += '</tr></thead><tbody>';
            const rows = section.rows || [];
            rows.forEach((row, rowIdx) => {
                tableHtml += '<tr>';
                columns.forEach(col => {
                    const val = row[col] !== undefined ? row[col] : '';
                    const rawVal = (val === null || val === undefined) ? '' : String(val);
                    const displayVal = rawVal === '' ? '<span class="blank">—</span>' : escapeHtml(rawVal);
                    tableHtml += `<td contenteditable="true" spellcheck="false"
                                     data-section-index="${sectionIdx}" data-row-index="${rowIdx}" data-column="${escapeHtml(col)}">${displayVal}</td>`;
                });
                tableHtml += '</tr>';
            });
            tableHtml += '</tbody>';
        } else {
            tableHtml += '<tbody><tr><td>No columns available</td></tr></tbody>';
        }
        tableHtml += '</table></div></div>';
        resultsDataPanel.insertAdjacentHTML('beforeend', tableHtml);
        if (section.raw_text) {
            const details = document.createElement('details');
            details.className = 'raw-text-details';
            details.innerHTML = `<summary>Show Raw OCR Text</summary><pre>${escapeHtml(section.raw_text)}</pre>`;
            resultsDataPanel.appendChild(details);

        }

    } else if (section.type === 'raw_text') {
        const text = section.text || '';
        const card = document.createElement('div');
        card.className = 'section-card';
        card.innerHTML = `<div class="section-title">${escapeHtml(section.name)}</div>
                          <pre class="raw-section-text" contenteditable="true" spellcheck="false"
                               data-section-index="${sectionIdx}" data-field="text">${escapeHtml(text)}</pre>`;
        resultsDataPanel.appendChild(card);
        if (section.raw_text) {
            const details = document.createElement('details');
            details.className = 'raw-text-details';
            details.innerHTML = `<summary>Show Raw OCR Text</summary><pre>${escapeHtml(section.raw_text)}</pre>`;
            resultsDataPanel.appendChild(details);
        }
    }
}

// ================== EDITING LOGIC ==================

function markUnsaved() {
    if (extractionStatusPill && extractionStatusPill.textContent !== '● Unsaved Changes') {
        extractionStatusPill.textContent = '● Unsaved Changes';
        extractionStatusPill.className = 'status-pill status-unsaved';
    }
}

function syncElementToData(target, value) {
    if (!currentStructuredData || !currentStructuredData.sections) return;

    const sectionIdx = parseInt(target.dataset.sectionIndex, 10);
    if (isNaN(sectionIdx)) return;

    const section = currentStructuredData.sections[sectionIdx];
    if (!section) return;

    // Handle table header edit
    if (target.dataset.header === 'true') {
        const oldCol = target.dataset.column;
        const newCol = value.trim() || oldCol;
        if (newCol !== oldCol && section.columns) {
            const colIdx = section.columns.indexOf(oldCol);
            if (colIdx !== -1) {
                // Rename column
                section.columns[colIdx] = newCol;
                // Update all rows' keys
                section.rows.forEach(row => {
                    if (row.hasOwnProperty(oldCol)) {
                        row[newCol] = row[oldCol];
                        delete row[oldCol];
                    }
                });
            }
        }
        return;
    }

    // Handle key_value label edit
    if (target.dataset.label === 'true') {
        const oldKey = target.dataset.field;
        const newKey = value.trim() || oldKey;
        if (newKey !== oldKey && section.type === 'key_value' && section.fields) {
            if (section.fields.hasOwnProperty(oldKey)) {
                section.fields[newKey] = section.fields[oldKey];
                delete section.fields[oldKey];
                // Update data-field attribute on the corresponding value span
                // (we'll handle focusout to sync; the DOM will update next render)
            }
        }
        return;
    }

    // Handle table cell edit
    if (target.dataset.column && target.dataset.rowIndex) {
        const rowIdx = parseInt(target.dataset.rowIndex, 10);
        const column = target.dataset.column;
        if (isNaN(rowIdx)) return;
        if (!section.rows) section.rows = [];
        if (!section.rows[rowIdx]) section.rows[rowIdx] = {};
        section.rows[rowIdx][column] = value;
        return;
    }

    // Handle key_value value edit or raw_text edit
    if (target.dataset.field) {
        const field = target.dataset.field;
        if (section.type === 'key_value') {
            if (!section.fields) section.fields = {};
            section.fields[field] = value;
        } else if (section.type === 'raw_text') {
            if (field === 'text') section.text = value;
        }
    }
}

function collectAllEdits() {
    if (!currentStructuredData || !resultsDataPanel) return;
    const editableElements = resultsDataPanel.querySelectorAll('[contenteditable="true"]');
    editableElements.forEach(el => {
        const text = el.innerText.trim();
        const value = (text === '' || text === '—') ? null : text;
        syncElementToData(el, value);
    });
}

// Event Delegation for Editable Fields
if (resultsDataPanel) {
    resultsDataPanel.addEventListener('focusin', (e) => {
        const target = e.target.closest('[contenteditable="true"]');
        if (!target) return;
        const text = target.innerText.trim();
        if (text === '—') {
            target.innerHTML = '';
        }
    });

    resultsDataPanel.addEventListener('focusout', (e) => {
        const target = e.target.closest('[contenteditable="true"]');
        if (!target) return;
        const text = target.innerText.trim();
        if (text === '' || text === '—') {
            target.innerHTML = '<span class="blank">—</span>';
            syncElementToData(target, null);
        } else {
            syncElementToData(target, text);
        }
    });

    resultsDataPanel.addEventListener('input', (e) => {
        const target = e.target.closest('[contenteditable="true"]');
        if (!target) return;
        markUnsaved();
        const text = target.innerText.trim();
        const value = (text === '' || text === '—') ? null : text;
        syncElementToData(target, value);
    });

    resultsDataPanel.addEventListener('keydown', (e) => {
        const target = e.target.closest('[contenteditable="true"]');
        if (!target) return;
        if (e.key === 'Enter') {
            if (e.shiftKey && (target.dataset.field === 'description' || target.dataset.column === 'Description')) {
                return;
            }
            e.preventDefault();
            target.blur();
        }
    });
}

// Toast Notification
function showToast(message, isError = false) {
    let toast = document.getElementById('toast-notification');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast-notification';
        toast.className = 'toast-notification';
        document.body.appendChild(toast);
    }
    toast.className = `toast-notification ${isError ? 'toast-error' : 'toast-success'}`;
    toast.innerHTML = `<span class="toast-icon">${isError ? '⚠️' : '✅'}</span><span class="toast-text">${escapeHtml(message)}</span>`;
    toast.classList.add('show');
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
        toast.classList.remove('show');
    }, 3500);
}

// Save Changes
if (saveChangesBtn) {
    saveChangesBtn.addEventListener('click', async () => {
        if (!selectedUploadId) {
            showToast('No document selected to save.', true);
            return;
        }
        if (!currentStructuredData) {
            showToast('No structured data available to save.', true);
            return;
        }

        collectAllEdits();

        saveChangesBtn.disabled = true;
        saveChangesBtn.classList.add('saving');
        if (saveBtnIcon) saveBtnIcon.textContent = '⏳';
        if (saveBtnText) saveBtnText.textContent = 'Saving...';

        try {
            const resp = await fetch(`${API_BASE_URL}/api/uploads/${selectedUploadId}/result`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(currentStructuredData)
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || `Server returned ${resp.status}`);
            }

            saveChangesBtn.classList.remove('saving');
            saveChangesBtn.classList.add('success');
            if (saveBtnIcon) saveBtnIcon.textContent = '✓';
            if (saveBtnText) saveBtnText.textContent = 'Saved!';

            if (extractionStatusPill) {
                extractionStatusPill.textContent = '● Verified & Saved';
                extractionStatusPill.className = 'status-pill status-verified';
            }

            showToast('Saved successfully!');

            setTimeout(() => {
                saveChangesBtn.disabled = false;
                saveChangesBtn.classList.remove('success');
                if (saveBtnIcon) saveBtnIcon.textContent = '💾';
                if (saveBtnText) saveBtnText.textContent = 'Save Changes';
            }, 2500);

        } catch (err) {
            console.error('Failed to save structured data:', err);
            saveChangesBtn.classList.remove('saving');
            saveChangesBtn.disabled = false;
            if (saveBtnIcon) saveBtnIcon.textContent = '💾';
            if (saveBtnText) saveBtnText.textContent = 'Save Changes';
            showToast(`Failed to save: ${err.message}`, true);
        }
    });
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize on page load
(async () => {
    await fetchUploads();
})();
// Refresh sidebar when the browser tab regains focus
// (useful when uploads happen outside the frontend, e.g. via Swagger)
window.addEventListener('focus', () => {
    fetchUploads();
});