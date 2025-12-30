/**
 * QA标注平台前端逻辑（新版 - 旧版风格）
 * 
 * 特性：
 * - 侧边栏拖拽功能
 * - 表格列宽拖拽功能
 * - 时间范围默认中国上海时间近三天
 * - 标注进度条仿照旧版
 * - 列表展示GroupID和TraceID
 * - 抽屉式标注页面（占50%空间）
 * - 简约精美的基础信息展示
 * - 修复debounce bug - 改用搜索按钮触发
 */

const API_BASE = '/api/v1';

// 全局状态
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
        rejected: 0
    },
    selectedData: null,
    sidebarWidth: 280,
    sidebarMinWidth: 200,
    sidebarMaxWidth: 400
};

// Agent颜色映射
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
// 工具函数
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
// 侧边栏拖拽功能
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
// 表格列宽拖拽功能
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
// API调用
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
        throw new Error(`API调用失败: ${response.status}`);
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
        throw new Error(`API调用失败: ${response.status}`);
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
        throw new Error(`API调用失败: ${response.status}`);
    }
    return response.json();
}

// ============================================================================
// 数据加载
// ============================================================================

async function loadStats() {
    try {
        const stats = await apiGet('/stats');
        state.stats = {
            pending: stats.pending || 0,
            annotated: stats.annotated || 0,
            approved: stats.approved || 0,
            rejected: stats.rejected || 0
        };
        renderStats();
    } catch (error) {
        console.error('获取统计信息失败:', error);
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
        console.error('获取数据列表失败:', error);
        showToast('获取数据列表失败', 'error');
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
    // datetime-local格式是 "2025-12-27T20:38"，需要转换为ISO格式 "2025-12-27T20:38:00"
    // 直接返回，FastAPI会自动解析
    return datetimeLocal + ':00';
}

// 防抖定时器
let filterDebounceTimer = null;

// 防抖加载数据（用于实时搜索场景）
function debounceLoadData() {
    if (filterDebounceTimer) {
        clearTimeout(filterDebounceTimer);
    }
    filterDebounceTimer = setTimeout(() => {
        loadData(1);
    }, 300);
}

// 处理过滤输入框的输入事件（实时防抖搜索）
function handleFilterInput(element) {
    debounceLoadData();
}

// 点击搜索图标触发搜索
function handleSearchClick(type) {
    loadData(1);
}

// 搜索函数 - 点击搜索按钮触发（保留兼容）
function doSearch(type) {
    loadData(1);
}

function applyFilters() {
    loadStats(); // 同步更新统计信息
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
    loadStats(); // 同步更新统计信息
    loadData(1);
}

function setDefaultTimeRange() {
    const now = new Date();
    const threeDaysAgo = new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000);

    const toLocalISO = (date) => {
        const offset = 8 * 60;
        const localTime = new Date(date.getTime() + offset * 60 * 1000);
        return localTime.toISOString().slice(0, 16);
    };

    const startInput = document.getElementById('filterStartTime');
    const endInput = document.getElementById('filterEndTime');

    if (startInput) startInput.value = toLocalISO(threeDaysAgo);
    if (endInput) endInput.value = toLocalISO(now);
}

// ============================================================================
// 渲染函数
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
                        标注
                    </button>
                </td>
            </tr>
        `;
    }).join('');
    
    document.getElementById('mainStats').textContent = `共 ${state.total} 条`;
}

// 格式化调用关系 - 类似QA关系的表述
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
    // 完整展示GroupID和TraceID
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
        pending: '待标注',
        annotated: '已标注',
        approved: '已通过',
        rejected: '已拒绝'
    };
    return statusMap[status] || status;
}

function getDataTypeText(type) {
    const typeMap = {
        'e2e': 'E2E',
        'agent': 'Agent',
        'llm': 'LLM',
        'tool': 'Tool',
        'custom': '自定义'
    };
    return typeMap[type] || type || '-';
}

function renderPagination() {
    document.getElementById('paginationInfo').textContent = 
        `第 ${state.currentPage}/${state.totalPages} 页，共 ${state.total} 条`;
    
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
// 数据详情与标注
// ============================================================================

async function viewData(dataId) {
    try {
        const data = await apiGet(`/data/${dataId}`);
        state.selectedData = data;
        renderDataDetail(data);
        openDrawer();
        renderDataList();
    } catch (error) {
        console.error('获取数据详情失败:', error);
        showToast('获取数据详情失败', 'error');
    }
}

function renderDataDetail(data) {
    const drawerBody = document.getElementById('drawerBody');
    const isPending = data.status === 'pending';
    const isAnnotated = data.status === 'annotated';
    
    // 构建基本信息三列表格 - 标签 | 值1 | 值2
    const metaRows = [];
    
    // 第一行：标签 + Group | Trace
    metaRows.push(`
        <tr class="meta-row-label">
            <td class="meta-cell-label">标签</td>
            <td class="meta-cell-value" colspan="2">
                <span class="qa-priority p${data.priority ?? 4}">P${data.priority ?? 4}</span>
                <span class="qa-status ${data.status}">${getStatusText(data.status)}</span>
                <span class="data-type-tag" data-type="${data.data_type}">${getDataTypeText(data.data_type)}</span>
            </td>
        </tr>
    `);
    
    // Group单独一行
    metaRows.push(`
        <tr class="meta-row-data">
            <td class="meta-cell-label">Group</td>
            <td class="meta-cell-value group-value" colspan="2" title="${data.source_group_id || ''}">${data.source_group_id || '-'}</td>
        </tr>
    `);
    
    // Trace单独一行
    metaRows.push(`
        <tr class="meta-row-data">
            <td class="meta-cell-label">Trace</td>
            <td class="meta-cell-value trace-value" colspan="2" title="${data.source_trace_id || ''}">${data.source_trace_id || '-'}</td>
        </tr>
    `);
    
    // 时间行
    metaRows.push(`
        <tr class="meta-row-data">
            <td class="meta-cell-label">时间</td>
            <td class="meta-cell-value" colspan="2">${formatDateTimeFull(data.created_at)}</td>
        </tr>
    `);
    
    // 调用关系行
    if (data.caller || data.callee) {
        metaRows.push(`
            <tr class="meta-row-data">
                <td class="meta-cell-label">调用关系</td>
                <td class="meta-cell-value" colspan="2">${formatCallerCallee(data)}</td>
            </tr>
        `);
    }
    
    drawerBody.innerHTML = `
        <!-- 基本信息区域 - 三列表格 -->
        <div class="detail-meta-section">
            <table class="meta-table">
                <tbody>
                    ${metaRows.join('')}
                </tbody>
            </table>
        </div>

        <!-- QA内容 - 重点区域 -->
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

        <!-- 标注结果展示 -->
        ${data.annotation && Object.keys(data.annotation).length > 0 ? `
        <div class="detail-annotation-section">
            <div class="section-header">
                <span class="section-icon">📋</span>
                <span class="section-title">已标注结果</span>
            </div>
            <div class="annotation-content">
                ${renderAnnotation(data.annotation)}
            </div>
        </div>
        ` : ''}

        <!-- 标注表单 - 仅待标注状态显示 -->
        ${isPending ? renderAnnotationForm(data) : ''}
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
    if (!content) return '<span class="empty-content">暂无内容</span>';
    if (typeof content === 'object') {
        return `<pre>${JSON.stringify(content, null, 2)}</pre>`;
    }
    if (isJSON(content)) {
        return `<pre>${JSON.stringify(JSON.parse(content), null, 2)}</pre>`;
    }
    return `<pre>${String(content)}</pre>`;
}

function renderAnnotation(annotation) {
    if (!annotation || Object.keys(annotation).length === 0) {
        return '<span class="empty-content">暂无标注结果</span>';
    }
    
    // 构建表格形式的KV展示
    // 特殊处理：将question排在前面，content排在后面
    const entries = Object.entries(annotation);
    
    // 排序：question优先，然后是content，然后按字母顺序，comment最后
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
    const isAnnotated = data.status === 'annotated';
    
    // 待标注状态只显示"提交标注"按钮
    // 已标注状态显示"标注审核通过"和"标注审核拒绝"按钮
    let buttonsHtml = '';
    
    if (isPending) {
        buttonsHtml = `
            <button class="btn btn-primary" onclick="submitAnnotation('${data.data_id}')">
                💾 提交标注
            </button>
        `;
    } else if (isAnnotated) {
        buttonsHtml = `
            <button class="btn btn-success" onclick="approveData('${data.data_id}')">
                ✅ 标注审核通过
            </button>
            <button class="btn btn-danger" onclick="rejectData('${data.data_id}')">
                ❌ 标注审核拒绝
            </button>
        `;
    }
    
    return `
        <div class="annotation-form">
            <div class="form-header">
                <span class="form-icon">✏️</span>
                <span class="form-title">标注</span>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">修正后Question</label>
                    <textarea class="form-textarea" id="annotationQuestion" rows="3" 
                        placeholder="可选，填写修正后的Question...">${data.question || ''}</textarea>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">修正后Answer</label>
                    <textarea class="form-textarea" id="annotationAnswer" rows="4" 
                        placeholder="可选，填写修正后的Answer...">${data.answer || ''}</textarea>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">质量评分</label>
                    <select class="form-select" id="qualityScore">
                        <option value="">请选择</option>
                        <option value="1">优秀 (1分)</option>
                        <option value="0.8">良好 (0.8分)</option>
                        <option value="0.6">一般 (0.6分)</option>
                        <option value="0.4">较差 (0.4分)</option>
                        <option value="0.2">很差 (0.2分)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">标注备注</label>
                    <textarea class="form-textarea" id="annotationComment" rows="3" 
                        placeholder="可选输入备注..." style="min-height: 70px;"></textarea>
                </div>
            </div>
            
            <div class="form-actions">
                ${buttonsHtml}
            </div>
        </div>
    `;
}

// ============================================================================
// 标注操作
// ============================================================================

async function submitAnnotation(dataId) {
    const question = document.getElementById('annotationQuestion')?.value;
    const answer = document.getElementById('annotationAnswer')?.value;
    const score = document.getElementById('qualityScore')?.value;
    const comment = document.getElementById('annotationComment')?.value;
    
    if (!question && !answer && !score) {
        showToast('请至少填写一个标注内容', 'warning');
        return;
    }
    
    try {
        await apiPut(`/data/${dataId}/annotate`, {
            status: 'annotated',
            annotation: {
                content: answer,
                question: question,
                score: score ? parseFloat(score) : null,
                comment: comment || ''
            },
            scores: score ? { overall_score: parseFloat(score) } : {}
        });
        
        showToast('标注成功', 'success');
        closeDrawer();
        loadData(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('标注失败:', error);
        showToast('标注失败: ' + error.message, 'error');
    }
}

async function approveData(dataId) {
    try {
        await apiPost(`/data/${dataId}/approve`, {});
        showToast('已通过', 'success');
        closeDrawer();
        loadData(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('操作失败:', error);
        showToast('操作失败', 'error');
    }
}

async function rejectData(dataId) {
    const comment = prompt('请输入拒绝原因:');
    if (comment === null) return;
    
    try {
        await apiPost(`/data/${dataId}/reject`, { comment: comment || '' });
        showToast('已拒绝', 'success');
        closeDrawer();
        loadData(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('操作失败:', error);
        showToast('操作失败', 'error');
    }
}

// ============================================================================
// 抽屉控制
// ============================================================================

function openDrawer() {
    document.getElementById('drawerOverlay').classList.add('show');
    document.getElementById('detailDrawer').classList.add('show');
}

function closeDrawer() {
    document.getElementById('drawerOverlay').classList.remove('show');
    document.getElementById('detailDrawer').classList.remove('show');
    state.selectedData = null;
    renderDataList();
}

// ============================================================================
// 侧边栏展开/收起
// ============================================================================

function toggleSection(sectionId) {
    const header = document.querySelector(`.sidebar-section-header:has(+ #${sectionId}Content)`);
    const content = document.getElementById(`${sectionId}Content`);
    const icon = document.getElementById(`${sectionId}ToggleIcon`);
    
    if (header && content) {
        header.classList.toggle('section-collapsed');
        content.classList.toggle('collapsed');
    }
    
    if (icon) {
        icon.textContent = header?.classList.contains('section-collapsed') ? '▶' : '▼';
    }
}

// ============================================================================
// 初始化
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('QA Annotation Platform initialized (新版-旧版风格)');

    initSidebarResize();
    initTableColumnResize();
    setDefaultTimeRange();

    // 监听时间变化 - 原生 datetime-local 控件在选择时间后会触发 change 事件
    // 我们阻止默认行为，只让值更新，不触发搜索
    const startInput = document.getElementById('filterStartTime');
    const endInput = document.getElementById('filterEndTime');

    const handleTimeChange = function(e) {
        e.preventDefault();
        e.stopPropagation();
    };

    if (startInput) startInput.addEventListener('change', handleTimeChange, { capture: true });
    if (endInput) endInput.addEventListener('change', handleTimeChange, { capture: true });

    // 加载数据和统计
    Promise.all([
        loadStats(),
        loadData()
    ]).catch(error => {
        console.error('初始化加载失败:', error);
    });
});

// 导出全局函数
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
