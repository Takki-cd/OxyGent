/**
 * QA Annotation Platform Frontend Logic (New Version - Legacy Style)
 * 
 * Features:
 * - Sidebar drag functionality
 * - Table column width drag functionality
 * - Time range default to Shanghai timezone, last 3 days
 * - Annotation progress bar following legacy style
 * - Display GroupID and TraceID in list
 * - Drawer-style annotation page (50% width)
 * - Clean and elegant basic info display
 * - Fixed debounce bug - use search button to trigger
 */

const API_BASE = '/api/v1';

// Global State
let state = {
    dataList: [],
    total: 0,
    currentPage: 1,
    pageSize: 20,
    totalPages: 1,
    stats: {
        pending: 0,
        annotated: 0,
        approved: 0,
        rejected: 0,
        kb_ingested: 0,
        kb_failed: 0
    },
    kbEnabled: false,
    selectedData: null,
    sidebarWidth: 320,
    sidebarMinWidth: 200,
    sidebarMaxWidth: 400
};

// KB Status Constants
const KB_STATUS = {
    INGESTED: 'kb_ingested',
    FAILED: 'kb_failed'
};

// Agent Color Mapping
const agentColorMap = [
    {bgColor: '#FEEAD4', color: '#7d4303'},
    {bgColor: '#E4FBCC', color: '#417609'},
    {bgColor: '#D3F8DF', color: '#116e30'},
    {bgColor: '#E0F2FE', color: '#044c7c'},
    {bgColor: '#E0EAFF', color: '#002980'},
    {bgColor: '#EFF1F5', color: '#313b4e'},
    {bgColor: '#FBE8FF', color: '#690080'},
    {bgColor: '#FBE7F6', color: '#6d1257'},
    {bgColor: '#FEF7C4', color: '#7d6e02'},
    {bgColor: '#E6F4D7', color: '#41641b'},
    {bgColor: '#D5F5F6', color: '#166669'},
    {bgColor: '#D2E9FF', color: '#004180'},
    {bgColor: '#D1DFFF', color: '#002780'},
    {bgColor: '#D5D9EB', color: '#293156'},
    {bgColor: '#EBE9FE', color: '#11067a'},
    {bgColor: '#FFE4E8', color: '#800013'},
];

// ============================================================================
// Utility Functions
// ============================================================================

function formatDateTimeFull(timeStr) {
    if (!timeStr) return '-';
    try {
        const date = new Date(timeStr.replace(' ', 'T'));
        const year = date.getFullYear();
        const month = (date.getMonth() + 1).toString().padStart(2, '0');
        const day = date.getDate().toString().padStart(2, '0');
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        return `${year}-${month}-${day} ${hours}:${minutes}`;
    } catch {
        return timeStr;
    }
}

function formatDateShort(timeStr) {
    if (!timeStr) return '-';
    try {
        const date = new Date(timeStr.replace(' ', 'T'));
        const month = (date.getMonth() + 1).toString().padStart(2, '0');
        const day = date.getDate().toString().padStart(2, '0');
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        const seconds = date.getSeconds().toString().padStart(2, '0');
        return `${month}-${day} ${hours}:${minutes}:${seconds}`;
    } catch {
        return timeStr;
    }
}

function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return hash;
}

function getAgentAvatar(agentName, size = 18) {
    if (!agentName) return '';
    const idx = Math.abs(hashCode(agentName)) % 16;
    const cur = agentColorMap[idx];
    const initial = agentName.charAt(0).toUpperCase();
    return `<span style="display: inline-flex; align-items: center; justify-content: center; width: ${size}px; height: ${size}px; border-radius: 50%; background-color: ${cur?.bgColor || '#eee'}; color: ${cur?.color || '#666'}; font-size: ${size * 0.5}px; font-weight: 600;">${initial}</span>`;
}

function showToast(message, type = 'info') {
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================================================
// Sidebar Drag Functionality
// ============================================================================

function initSidebarResize() {
    const sidebar = document.getElementById('annotationSidebar');
    const handle = document.getElementById('sidebarResizeHandle');
    
    if (!sidebar || !handle) return;
    
    let isResizing = false;
    let startX, startWidth;
    
    sidebar.style.width = state.sidebarWidth + 'px';
    
    handle.addEventListener('mousedown', (e) => {
        isResizing = true;
        startX = e.clientX;
        startWidth = sidebar.offsetWidth;
        handle.classList.add('active');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        
        const diffX = e.clientX - startX;
        const newWidth = Math.max(state.sidebarMinWidth, Math.min(state.sidebarMaxWidth, startWidth + diffX));
        sidebar.style.width = newWidth + 'px';
        state.sidebarWidth = newWidth;
    });
    
    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            handle.classList.remove('active');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
    });
}

// ============================================================================
// Table Column Width Drag Functionality
// ============================================================================

function initTableColumnResize() {
    const table = document.getElementById('qaTable');
    if (!table) return;
    
    const ths = table.querySelectorAll('th[data-column]');
    let isResizing = false;
    let currentTh = null;
    let startX = 0;
    let startWidth = 0;
    let resizeProxy = null;
    
    resizeProxy = document.createElement('div');
    resizeProxy.className = 'resizing-proxy';
    resizeProxy.style.display = 'none';
    document.body.appendChild(resizeProxy);
    
    ths.forEach(th => {
        const handle = document.createElement('div');
        handle.className = 'resize-handle';
        th.appendChild(handle);
        
        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            
            isResizing = true;
            currentTh = th;
            startX = e.clientX;
            startWidth = th.offsetWidth;
            
            const thRect = th.getBoundingClientRect();
            resizeProxy.style.left = thRect.right + 'px';
            resizeProxy.style.top = thRect.top + 'px';
            resizeProxy.style.height = thRect.height + 'px';
            resizeProxy.style.display = 'block';
            
            th.classList.add('resizing');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isResizing || !currentTh) return;
        
        const diffX = e.clientX - startX;
        const newWidth = Math.max(40, startWidth + diffX);
        currentTh.style.width = newWidth + 'px';
        
        const thRect = currentTh.getBoundingClientRect();
        resizeProxy.style.left = thRect.right + 'px';
        resizeProxy.style.top = thRect.top + 'px';
        resizeProxy.style.height = thRect.height + 'px';
    });
    
    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            if (currentTh) {
                currentTh.classList.remove('resizing');
            }
            resizeProxy.style.display = 'none';
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            currentTh = null;
        }
    });
}

// ============================================================================
// API Calls
// ============================================================================

async function apiGet(endpoint, params = {}) {
    const url = new URL(`${API_BASE}${endpoint}`, window.location.origin);
    Object.entries(params).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== '') {
            url.searchParams.append(key, value);
        }
    });
    
    const response = await fetch(url.toString());
    if (!response.ok) {
        throw new Error(`API call failed: ${response.status}`);
    }
    return response.json();
}

async function apiPut(endpoint, data) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!response.ok) {
        throw new Error(`API call failed: ${response.status}`);
    }
    return response.json();
}

async function apiPost(endpoint, data) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!response.ok) {
        throw new Error(`API call failed: ${response.status}`);
    }
    return response.json();
}

// ============================================================================
// Data Loading
// ============================================================================

async function loadStats() {
    try {
        const filters = getFilters();
        const stats = await apiGet('/stats', {
            start_time: filters.start_time || '',
            end_time: filters.end_time || ''
        });
        state.stats = {
            pending: stats.pending || 0,
            annotated: stats.annotated || 0,
            approved: stats.approved || 0,
            rejected: stats.rejected || 0,
            kb_ingested: stats.kb_ingested || 0,
            kb_failed: stats.kb_failed || 0
        };
        
        // Load KB status
        try {
            const kbStatus = await apiGet('/data/kb/status');
            state.kbEnabled = kbStatus.enabled || false;
        } catch (e) {
            state.kbEnabled = false;
        }
        
        renderStats();
        renderKBStats();
    } catch (error) {
        console.error('Failed to fetch statistics:', error);
    }
}

async function loadData(page = 1) {
    const filters = getFilters();

    try {
        const data = await apiGet('/data', {
            ...filters,
            page: page,
            page_size: state.pageSize
        });

        state.dataList = data.items || [];
        state.total = data.total || 0;
        state.currentPage = data.page || 1;
        state.totalPages = data.total_pages || 1;

        renderDataList();
        renderPagination();
    } catch (error) {
        console.error('Failed to fetch data list:', error);
        showToast('Failed to fetch data list', 'error');
    }
}

function getFilters() {
    const startTime = document.getElementById('filterStartTime')?.value;
    const endTime = document.getElementById('filterEndTime')?.value;
    const filterCaller = document.getElementById('filterCaller')?.value;
    const filterCallee = document.getElementById('filterCallee')?.value;
    const filterGroupId = document.getElementById('filterGroupId')?.value;
    const filterTraceId = document.getElementById('filterTraceId')?.value;
    const filterSearch = document.getElementById('filterSearch')?.value;

    return {
        data_type: document.getElementById('filterDataType')?.value || '',
        status: document.getElementById('filterStatus')?.value || '',
        priority: document.getElementById('filterPriority')?.value || '',
        caller: filterCaller || '',
        callee: filterCallee || '',
        group_id: filterGroupId || '',
        trace_id: filterTraceId || '',
        search: filterSearch || '',
        start_time: startTime ? formatTimeForBackend(startTime) : '',
        end_time: endTime ? formatTimeForBackend(endTime) : ''
    };
}

function formatTimeForBackend(datetimeLocal) {
    if (!datetimeLocal) return '';
    // datetime-local format is "2025-12-27T20:38", need to convert to ISO format "2025-12-27T20:38:00"
    // Just return, FastAPI will parse it automatically
    return datetimeLocal + ':00';
}

// Debounce Timer
let filterDebounceTimer = null;

// Debounced Data Loading (for real-time search scenarios)
function debounceLoadData() {
    if (filterDebounceTimer) {
        clearTimeout(filterDebounceTimer);
    }
    filterDebounceTimer = setTimeout(() => {
        loadData(1);
    }, 300);
}

// Handle Filter Input Events (real-time debounced search)
function handleFilterInput(element) {
    debounceLoadData();
}

// Trigger Search on Search Icon Click
function handleSearchClick(type) {
    loadData(1);
}

// Search Function - Trigger on Search Button Click (legacy compatibility)
function doSearch(type) {
    loadData(1);
}

function applyFilters() {
    loadStats(); // Sync update statistics
    loadData(1);
}

function resetFilters() {
    document.getElementById('filterDataType').value = '';
    document.getElementById('filterStatus').value = '';
    document.getElementById('filterPriority').value = '';
    document.getElementById('filterCaller').value = '';
    document.getElementById('filterCallee').value = '';
    document.getElementById('filterGroupId').value = '';
    document.getElementById('filterTraceId').value = '';
    document.getElementById('filterSearch').value = '';

    setDefaultTimeRange();
    loadStats(); // Sync update statistics
    loadData(1);
}

function setDefaultTimeRange() {
    const now = new Date();
    // Round up minutes: set seconds and milliseconds to 0, then add 1 minute
    const roundedNow = new Date(now);
    roundedNow.setSeconds(0, 0);  // Reset seconds and milliseconds to 0
    roundedNow.setMinutes(roundedNow.getMinutes() + 1);  // Add 1 minute for rounding effect

    const threeDaysAgo = new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000);

    const toLocalISO = (date) => {
        const offset = 8 * 60;
        const localTime = new Date(date.getTime() + offset * 60 * 1000);
        return localTime.toISOString().slice(0, 16);
    };

    const startInput = document.getElementById('filterStartTime');
    const endInput = document.getElementById('filterEndTime');

    if (startInput) startInput.value = toLocalISO(threeDaysAgo);
    if (endInput) endInput.value = toLocalISO(roundedNow);
}

// ============================================================================
// Rendering Functions
// ============================================================================

function renderStats() {
    const total = state.stats.pending + state.stats.annotated + 
                  state.stats.approved + state.stats.rejected;
    
    const pendingPercent = total > 0 ? (state.stats.pending / total * 100) : 0;
    const annotatedPercent = total > 0 ? (state.stats.annotated / total * 100) : 0;
    const approvedPercent = total > 0 ? (state.stats.approved / total * 100) : 0;
    const rejectedPercent = total > 0 ? (state.stats.rejected / total * 100) : 0;
    
    document.getElementById('statPending').textContent = state.stats.pending;
    document.getElementById('statAnnotated').textContent = state.stats.annotated;
    document.getElementById('statApproved').textContent = state.stats.approved;
    document.getElementById('statRejected').textContent = state.stats.rejected;
    
    document.getElementById('progressPending').style.width = `${pendingPercent}%`;
    document.getElementById('progressAnnotated').style.width = `${annotatedPercent}%`;
    document.getElementById('progressApproved').style.width = `${approvedPercent}%`;
    document.getElementById('progressRejected').style.width = `${rejectedPercent}%`;
    
    // Render KB stats if enabled
    renderKBStats();
}

function renderKBStats() {
    // Check if KB stats elements exist, if not create them
    let kbStatsContainer = document.getElementById('kbStatsContainer');
    if (!kbStatsContainer) {
        // Create KB stats container
        const progressSection = document.querySelector('.progress-bar-container');
        if (progressSection) {
            kbStatsContainer = document.createElement('div');
            kbStatsContainer.id = 'kbStatsContainer';
            kbStatsContainer.className = 'kb-stats-container';
            kbStatsContainer.innerHTML = `
                <div class="progress-bar-label" style="margin-top: 12px;">
                    <span>📚 Knowledge Base</span>
                    ${state.kbEnabled ? '<span class="kb-enabled-badge">Enabled</span>' : '<span class="kb-disabled-badge">Not Configured</span>'}
                </div>
                <div class="kb-stats-grid" style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 8px;">
                    <div class="kb-stat-block ingested">
                        <div class="kb-stat-value" id="statKbIngested">0</div>
                        <div class="kb-stat-label">Ingested</div>
                    </div>
                    <div class="kb-stat-block failed">
                        <div class="kb-stat-value" id="statKbFailed">0</div>
                        <div class="kb-stat-label">Failed</div>
                    </div>
                </div>
            `;
            progressSection.parentNode.insertBefore(kbStatsContainer, progressSection.nextSibling);
        }
    }
    
    // Update KB stats values
    const kbIngestedEl = document.getElementById('statKbIngested');
    const kbFailedEl = document.getElementById('statKbFailed');
    
    if (kbIngestedEl) kbIngestedEl.textContent = state.stats.kb_ingested || 0;
    if (kbFailedEl) kbFailedEl.textContent = state.stats.kb_failed || 0;
}

function renderDataList() {
    const tbody = document.getElementById('qaTableBody');
    const emptyState = document.getElementById('emptyState');
    
    if (state.dataList.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'flex';
        return;
    }
    
    emptyState.style.display = 'none';
    
    tbody.innerHTML = state.dataList.map(data => {
        const isActive = state.selectedData?.data_id === data.data_id ? 'active' : '';
        
        return `
            <tr class="${isActive}" onclick="viewData('${data.data_id}')">
                <td class="task-id" title="${data.data_id}">${data.data_id}</td>
                <td>
                    <span class="qa-priority p${data.priority ?? 4}">P${data.priority ?? 4}</span>
                </td>
                <td>
                    <span class="qa-status ${data.status}">${getStatusText(data.status)}</span>
                </td>
                <td>
                    <span class="data-type-tag" data-type="${data.data_type}">${getDataTypeText(data.data_type)}</span>
                </td>
                <td class="qa-callee" title="${getCalleeDisplay(data)}">
                    ${formatCallerCallee(data)}
                </td>
                <td class="qa-question" title="${data.question || ''}">${data.question || '-'}</td>
                <td class="qa-group-trace" title="${formatGroupTraceTooltip(data)}">
                    ${formatGroupTrace(data)}
                </td>
                <td class="qa-time">${formatDateShort(data.created_at)}</td>
                <td class="qa-action">
                    <button class="btn btn-primary btn-small" onclick="event.stopPropagation(); viewData('${data.data_id}')">
                        Annotate
                    </button>
                </td>
            </tr>
        `;
    }).join('');
    
    document.getElementById('mainStats').textContent = `${state.total} items`;
}

// Format Call Relationship - Similar to QA relationship expression
function formatCallerCallee(data) {
    const caller = data.caller || 'User';
    const callee = data.callee || 'Unknown';
    const dataType = data.data_type || '';
    
    if (dataType === 'e2e') {
        return `<span class="qa-relation e2e" title="${caller} → ${callee}">User → ${getAgentAvatar(callee)}${callee}</span>`;
    } else if (dataType === 'agent') {
        return `<span class="qa-relation agent" title="${caller} → ${callee}">${getAgentAvatar(caller)}${caller} → ${getAgentAvatar(callee)}${callee}</span>`;
    } else if (dataType === 'llm') {
        return `<span class="qa-relation llm" title="${caller} → ${callee}">${getAgentAvatar(caller)}${caller} → ${getAgentAvatar(callee)}${callee}</span>`;
    } else if (dataType === 'tool') {
        return `<span class="qa-relation tool" title="${caller} → ${callee}">${getAgentAvatar(caller)}${caller} → 🔧 ${callee}</span>`;
    } else {
        return `<span class="qa-relation" title="${caller} → ${callee}">${getAgentAvatar(caller)}${caller} → ${getAgentAvatar(callee)}${callee}</span>`;
    }
}

function formatGroupTrace(data) {
    // Display GroupID and TraceID completely
    const groupId = data.source_group_id || '-';
    const traceId = data.source_trace_id || '-';
    
    return `
        <div class="group-trace-full">
            <div class="group-trace-item">
                <span class="group-trace-label">G:</span>
                <span class="group-trace-value" title="${data.source_group_id || ''}">${groupId}</span>
            </div>
            <div class="group-trace-item">
                <span class="group-trace-label">T:</span>
                <span class="group-trace-value trace" title="${data.source_trace_id || ''}">${traceId}</span>
            </div>
        </div>
    `;
}

function formatGroupTraceTooltip(data) {
    let tooltip = '';
    if (data.source_group_id) tooltip += `Group: ${data.source_group_id}\n`;
    if (data.source_trace_id) tooltip += `Trace: ${data.source_trace_id}`;
    return tooltip || '-';
}

function getCalleeDisplay(data) {
    const caller = data.caller || '';
    const callee = data.callee || '';
    if (caller && callee) {
        return `${caller} → ${callee}`;
    }
    return callee || caller || '-';
}

function getStatusText(status) {
    const statusMap = {
        pending: 'Pending',
        annotated: 'Annotated',
        approved: 'Approved',
        rejected: 'Rejected',
        kb_ingested: 'Ingested',
        kb_failed: 'Failed'
    };
    return statusMap[status] || status;
}

function getDataTypeText(type) {
    const typeMap = {
        'e2e': 'E2E',
        'agent': 'Agent',
        'llm': 'LLM',
        'tool': 'Tool',
        'custom': 'Custom'
    };
    return typeMap[type] || type || '-';
}

function renderPagination() {
    document.getElementById('paginationInfo').textContent = 
        `Page ${state.currentPage}/${state.totalPages}, ${state.total} items`;
    
    document.getElementById('pageNum').textContent = state.currentPage;
    
    const prevBtn = document.querySelector('#paginationBtns button:nth-child(2)');
    const nextBtn = document.querySelector('#paginationBtns button:nth-child(4)');
    const firstBtn = document.querySelector('#paginationBtns button:nth-child(1)');
    const lastBtn = document.querySelector('#paginationBtns button:nth-child(5)');
    
    if (prevBtn) prevBtn.disabled = state.currentPage <= 1;
    if (nextBtn) nextBtn.disabled = state.currentPage >= state.totalPages;
    if (firstBtn) firstBtn.disabled = state.currentPage <= 1;
    if (lastBtn) lastBtn.disabled = state.currentPage >= state.totalPages;
}

function changePage(page) {
    if (page < 1 || page > state.totalPages) return;
    loadData(page);
}

// ============================================================================
// Data Detail & Annotation
// ============================================================================

async function viewData(dataId) {
    try {
        const data = await apiGet(`/data/${dataId}`);
        state.selectedData = data;
        renderDataDetail(data);
        openDrawer();
        renderDataList();
    } catch (error) {
        console.error('Failed to fetch data details:', error);
        showToast('Failed to fetch data details', 'error');
    }
}

function renderDataDetail(data) {
    const drawerBody = document.getElementById('drawerBody');
    const isPending = data.status === 'pending';
    const isAnnotated = data.status === 'annotated';
    
    // Build basic info 3-column table - Label | Value1 | Value2
    const metaRows = [];
    
    // First row: Label + Group | Trace
    metaRows.push(`
        <tr class="meta-row-label">
            <td class="meta-cell-label">Label</td>
            <td class="meta-cell-value" colspan="2">
                <span class="qa-priority p${data.priority ?? 4}">P${data.priority ?? 4}</span>
                <span class="qa-status ${data.status}">${getStatusText(data.status)}</span>
                <span class="data-type-tag" data-type="${data.data_type}">${getDataTypeText(data.data_type)}</span>
            </td>
        </tr>
    `);
    
    // Group single row
    metaRows.push(`
        <tr class="meta-row-data">
            <td class="meta-cell-label">Group</td>
            <td class="meta-cell-value group-value" colspan="2" title="${data.source_group_id || ''}">${data.source_group_id || '-'}</td>
        </tr>
    `);
    
    // Trace single row
    metaRows.push(`
        <tr class="meta-row-data">
            <td class="meta-cell-label">Trace</td>
            <td class="meta-cell-value trace-value" colspan="2" title="${data.source_trace_id || ''}">${data.source_trace_id || '-'}</td>
        </tr>
    `);
    
    // Time row
    metaRows.push(`
        <tr class="meta-row-data">
            <td class="meta-cell-label">Time</td>
            <td class="meta-cell-value" colspan="2">${formatDateTimeFull(data.created_at)}</td>
        </tr>
    `);
    
    // Call relationship row
    if (data.caller || data.callee) {
        metaRows.push(`
            <tr class="meta-row-data">
                <td class="meta-cell-label">Call Relationship</td>
                <td class="meta-cell-value" colspan="2">${formatCallerCallee(data)}</td>
            </tr>
        `);
    }
    
    drawerBody.innerHTML = `
        <!-- Basic Info Area - 3-column Table -->
        <div class="detail-meta-section">
            <table class="meta-table">
                <tbody>
                    ${metaRows.join('')}
                </tbody>
            </table>
        </div>

        <!-- QA Content - Key Area -->
        <div class="detail-qa-section">
            <div class="qa-block">
                <div class="qa-block-header">
                    <span class="qa-block-icon">❓</span>
                    <span class="qa-block-title">Question / Input</span>
                </div>
                <div class="qa-block-content ${isJSON(data.question) ? 'json-content' : ''}">
                    ${formatContent(data.question)}
                </div>
            </div>
            
            <div class="qa-block">
                <div class="qa-block-header">
                    <span class="qa-block-icon">💡</span>
                    <span class="qa-block-title">Answer / Output</span>
                </div>
                <div class="qa-block-content ${isJSON(data.answer) ? 'json-content' : ''}">
                    ${formatContent(data.answer)}
                </div>
            </div>
        </div>

        <!-- Annotation Result Display -->
        ${data.annotation && Object.keys(data.annotation).length > 0 ? `
        <div class="detail-annotation-section">
            <div class="section-header">
                <span class="section-icon">📋</span>
                <span class="section-title">Annotated Result</span>
            </div>
            <div class="annotation-content">
                ${renderAnnotation(data.annotation)}
            </div>
        </div>
        ` : ''}

        <!-- Reject Reason Display - Only show for rejected status -->
        ${data.status === 'rejected' && data.reject_reason ? `
        <div class="reject-reason-section">
            <div class="section-header rejected">
                <span class="section-icon">🚫</span>
                <span class="section-title">Reject Reason</span>
            </div>
            <div class="reject-reason-content">
                ${escapeHtml(data.reject_reason)}
            </div>
        </div>
        ` : ''}

        <!-- Annotation Form - Only show for pending status -->
        ${isPending ? renderAnnotationForm(data) : ''}
        
        <!-- Review Action Area - Show review buttons for annotated status -->
        ${isAnnotated ? renderReviewSection(data) : ''}
        
        <!-- Knowledge Base Section - Show for approved status or KB-related status -->
        ${(data.status === 'approved' || data.status === 'kb_ingested' || data.status === 'kb_failed') ? renderKBSection(data) : ''}
    `;
}

function isJSON(str) {
    if (!str || typeof str !== 'string') return false;
    try {
        JSON.parse(str);
        return true;
    } catch {
        return false;
    }
}

function formatContent(content) {
    if (!content) return '<span class="empty-content">No content available</span>';
    if (typeof content === 'object') {
        return `<pre>${JSON.stringify(content, null, 2)}</pre>`;
    }
    if (isJSON(content)) {
        return `<pre>${JSON.stringify(JSON.parse(content), null, 2)}</pre>`;
    }
    return `<pre>${String(content)}</pre>`;
}

// XSS Escape Function
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderAnnotation(annotation) {
    if (!annotation || Object.keys(annotation).length === 0) {
        return '<span class="empty-content">No annotation result</span>';
    }
    
    // Build KV display in table format
    // Special handling: put question first, content last
    const entries = Object.entries(annotation);
    
    // Sort: question first, then content, then alphabetical order, comment last
    entries.sort((a, b) => {
        const keyA = a[0].toLowerCase();
        const keyB = b[0].toLowerCase();
        
        if (keyA === 'question') return -1;
        if (keyB === 'question') return 1;
        if (keyA === 'content') return -1;
        if (keyB === 'content') return 1;
        if (keyA === 'comment') return 1;
        if (keyB === 'comment') return -1;
        
        return keyA.localeCompare(keyB);
    });
    
    const rows = entries.map(([key, value]) => {
        let displayValue = value;
        if (typeof value === 'object') {
            displayValue = JSON.stringify(value, null, 2);
        }
        return `
            <tr>
                <td class="annotation-kv-key">${key}</td>
                <td class="annotation-kv-value">${displayValue}</td>
            </tr>
        `;
    }).join('');
    
    return `
        <table class="annotation-kv-table">
            <tbody>
                ${rows}
            </tbody>
        </table>
    `;
}

function renderAnnotationForm(data) {
    const isPending = data.status === 'pending';
    
    // Pending status only shows "Submit Annotation" button
    let buttonsHtml = '';
    
    if (isPending) {
        buttonsHtml = `
            <button class="btn btn-primary" onclick="submitAnnotation('${data.data_id}')">
                💾 Submit Annotation
            </button>
        `;
    }
    
    return `
        <div class="annotation-form">
            <div class="form-header">
                <span class="form-icon">✏️</span>
                <span class="form-title">Annotation</span>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Corrected Question</label>
                    <textarea class="form-textarea" id="annotationQuestion" rows="3" 
                        placeholder="Optional, enter corrected Question...">${data.question || ''}</textarea>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Corrected Answer</label>
                    <textarea class="form-textarea" id="annotationAnswer" rows="4" 
                        placeholder="Optional, enter corrected Answer...">${data.answer || ''}</textarea>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Quality Score <span class="required-mark">*</span></label>
                    <select class="form-select" id="qualityScore">
                        <option value="">Please select</option>
                        <option value="1">Excellent (1.0)</option>
                        <option value="0.8">Good (0.8)</option>
                        <option value="0.6">Fair (0.6)</option>
                        <option value="0.4">Poor (0.4)</option>
                        <option value="0.2">Very Poor (0.2)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Annotation Comment</label>
                    <textarea class="form-textarea" id="annotationComment" rows="3" 
                        placeholder="Optional, enter comments..." style="min-height: 70px;"></textarea>
                </div>
            </div>
            
            <div class="form-actions">
                ${buttonsHtml}
            </div>
        </div>
    `;
}

// Review Action Area - Show review buttons only, no annotation form
function renderReviewSection(data) {
    let actionsHtml = `
        <button class="btn btn-success" onclick="approveData('${data.data_id}')">
            ✅ Approve Annotation
        </button>
        <button class="btn btn-danger" onclick="rejectData('${data.data_id}')">
            ❌ Reject Annotation
        </button>
    `;
    
    // Add KB actions if enabled and data is approved
    if (state.kbEnabled && data.status === 'approved') {
        actionsHtml += `
            <button class="btn btn-primary" onclick="ingestToKB('${data.data_id}')" style="margin-left: 8px;">
                📤 Approve & Ingest to KB
            </button>
        `;
    }
    
    return `
        <div class="review-section">
            <div class="review-header">
                <span class="review-icon">👁️</span>
                <span class="review-title">Annotation Review</span>
            </div>
            <div class="review-actions">
                ${actionsHtml}
            </div>
        </div>
    `;
}

// ============================================================================
// Annotation Operations
// ============================================================================

async function submitAnnotation(dataId) {
    const question = document.getElementById('annotationQuestion')?.value;
    const answer = document.getElementById('annotationAnswer')?.value;
    const score = document.getElementById('qualityScore')?.value;
    const comment = document.getElementById('annotationComment')?.value;
    
    // Quality score required validation
    if (!score) {
        showToast('Please select quality score', 'warning');
        return;
    }
    
    if (!question && !answer && !comment) {
        showToast('Please fill in at least one correction or comment', 'warning');
        return;
    }
    
    try {
        await apiPut(`/data/${dataId}/annotate`, {
            status: 'annotated',
            annotation: {
                content: answer,
                question: question,
                score: parseFloat(score),
                comment: comment || ''
            },
            scores: { overall_score: parseFloat(score) }
        });
        
        showToast('Annotation submitted successfully', 'success');
        closeDrawer();
        loadData(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('Annotation failed:', error);
        showToast('Annotation failed: ' + error.message, 'error');
    }
}

async function approveData(dataId) {
    try {
        await apiPost(`/data/${dataId}/approve`, {});
        showToast('Approved', 'success');
        closeDrawer();
        loadData(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('Operation failed:', error);
        showToast('Operation failed', 'error');
    }
}

async function rejectData(dataId) {
    // Show custom reject reason input dialog
    showRejectDialog(dataId);
}

// Show Reject Reason Input Dialog
function showRejectDialog(dataId) {
    const drawerBody = document.getElementById('drawerBody');

    // Create custom dialog
    const dialog = document.createElement('div');
    dialog.className = 'reject-dialog-overlay';
    dialog.innerHTML = `
        <div class="reject-dialog">
            <div class="reject-dialog-header">
                <span>❌ Reject Annotation</span>
                <button class="reject-dialog-close" onclick="closeRejectDialog()">×</button>
            </div>
            <div class="reject-dialog-body">
                <label class="reject-dialog-label">Please enter reject reason:</label>
                <textarea id="rejectReason" class="reject-dialog-textarea" rows="4" placeholder="Please enter reject reason..."></textarea>
            </div>
            <div class="reject-dialog-actions">
                <button class="btn btn-secondary" onclick="closeRejectDialog()">Cancel</button>
                <button class="btn btn-danger" onclick="confirmReject('${dataId}')">Confirm Reject</button>
            </div>
        </div>
    `;

    document.body.appendChild(dialog);

    // Focus on input
    setTimeout(() => {
        document.getElementById('rejectReason').focus();
    }, 100);

    // Click overlay to close
    dialog.addEventListener('click', function(e) {
        if (e.target === dialog) {
            closeRejectDialog();
        }
    });
}

// Close Reject Dialog
function closeRejectDialog() {
    const dialog = document.querySelector('.reject-dialog-overlay');
    if (dialog) {
        dialog.remove();
    }
}

// Confirm Reject Operation
async function confirmReject(dataId) {
    const rejectReason = document.getElementById('rejectReason')?.value || '';
    closeRejectDialog();

    try {
        await apiPost(`/data/${dataId}/reject`, { reject_reason: rejectReason });
        showToast('Rejected', 'success');
        closeDrawer();
        loadData(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('Operation failed:', error);
        showToast('Operation failed', 'error');
    }
}

// ============================================================================
// Knowledge Base Ingestion Operations
// ============================================================================

async function ingestToKB(dataId) {
    if (!state.kbEnabled) {
        showToast('Knowledge Base is not configured. Please configure QA_KB_ENDPOINT and QA_KB_ID.', 'warning');
        return;
    }
    
    try {
        showToast('Ingesting to Knowledge Base...', 'info');
        const result = await apiPost(`/data/${dataId}/ingest-kb`, {});
        
        if (result.success) {
            showToast('Successfully ingested to Knowledge Base', 'success');
        } else {
            showToast('Failed to ingest: ' + result.message, 'error');
        }
        
        closeDrawer();
        loadData(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('KB ingestion failed:', error);
        showToast('KB ingestion failed: ' + error.message, 'error');
    }
}

// Export Global Functions
window.changePage = changePage;
window.applyFilters = applyFilters;
window.resetFilters = resetFilters;
window.viewData = viewData;
window.submitAnnotation = submitAnnotation;
window.approveData = approveData;
window.rejectData = rejectData;
window.closeDrawer = closeDrawer;
window.toggleSection = toggleSection;
window.doSearch = doSearch;
window.handleFilterInput = handleFilterInput;
window.handleSearchClick = handleSearchClick;
window.closeRejectDialog = closeRejectDialog;
window.confirmReject = confirmReject;
// Knowledge Base Functions
window.ingestToKB = ingestToKB;


// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('QA Annotation Platform initialized');

    initSidebarResize();
    initTableColumnResize();
    setDefaultTimeRange();

    // Listen for time changes - native datetime-local control triggers change event after selecting time
    // We prevent default behavior, only let value update, don't trigger search
    const startInput = document.getElementById('filterStartTime');
    const endInput = document.getElementById('filterEndTime');

    const handleTimeChange = function(e) {
        e.preventDefault();
        e.stopPropagation();
    };

    if (startInput) startInput.addEventListener('change', handleTimeChange, { capture: true });
    if (endInput) endInput.addEventListener('change', handleTimeChange, { capture: true });

    // Load data and statistics
    Promise.all([
        loadStats(),
        loadData()
    ]).catch(error => {
        console.error('Initialization load failed:', error);
    });
});
