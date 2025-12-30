/**
 * QA标注平台前端逻辑
 */

const API_BASE = '/api/v1';

// 全局状态
let state = {
    tasks: [],
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
    selectedTask: null
};

// 工具函数
function formatTime(timeStr) {
    if (!timeStr) return '-';
    const date = new Date(timeStr);
    return date.toLocaleString('zh-CN');
}

function debounce(fn, delay) {
    let timer = null;
    return function(...args) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

function showToast(message, type = 'info') {
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

// API调用
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

// 获取统计信息
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

// 获取任务列表
async function loadTasks(page = 1) {
    const filters = getFilters();
    
    try {
        const data = await apiGet('/tasks', {
            ...filters,
            page: page,
            page_size: state.pageSize
        });
        
        state.tasks = data.items || [];
        state.total = data.total || 0;
        state.currentPage = data.page || 1;
        state.totalPages = data.total_pages || 1;
        
        renderTasks();
        renderPagination();
    } catch (error) {
        console.error('获取任务列表失败:', error);
        showToast('获取任务列表失败', 'error');
    }
}

// 获取过滤条件
function getFilters() {
    return {
        qa_type: document.getElementById('filterQAType')?.value || '',
        status: document.getElementById('filterStatus')?.value || '',
        priority: document.getElementById('filterPriority')?.value || '',
        start_time: document.getElementById('filterStartTime')?.value || '',
        end_time: document.getElementById('filterEndTime')?.value || '',
        search: document.getElementById('filterSearch')?.value || ''
    };
}

// 应用过滤
function applyFilters() {
    loadTasks(1);
}

// 重置过滤
function resetFilters() {
    document.getElementById('filterQAType').value = '';
    document.getElementById('filterStatus').value = '';
    document.getElementById('filterPriority').value = '';
    document.getElementById('filterStartTime').value = '';
    document.getElementById('filterEndTime').value = '';
    document.getElementById('filterSearch').value = '';
    loadTasks(1);
}

// 渲染统计信息
function renderStats() {
    const total = state.stats.pending + state.stats.annotated + 
                  state.stats.approved + state.stats.rejected;
    
    const pendingPercent = total > 0 ? (state.stats.pending / total * 100) : 0;
    const annotatedPercent = total > 0 ? (state.stats.annotated / total * 100) : 0;
    const approvedPercent = total > 0 ? (state.stats.approved / total * 100) : 0;
    
    document.getElementById('statPending').textContent = state.stats.pending;
    document.getElementById('statAnnotated').textContent = state.stats.annotated;
    document.getElementById('statApproved').textContent = state.stats.approved;
    document.getElementById('statRejected').textContent = state.stats.rejected;
    
    document.getElementById('progressPending').style.width = `${pendingPercent}%`;
    document.getElementById('progressAnnotated').style.width = `${annotatedPercent}%`;
    document.getElementById('progressApproved').style.width = `${approvedPercent}%`;
}

// 渲染任务列表
function renderTasks() {
    const tbody = document.getElementById('qaTableBody');
    const emptyState = document.getElementById('emptyState');
    
    if (state.tasks.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'flex';
        return;
    }
    
    emptyState.style.display = 'none';
    
    tbody.innerHTML = state.tasks.map(task => `
        <tr>
            <td title="${task.qa_id}">${task.qa_id.substring(0, 8)}...</td>
            <td>
                <span class="priority-tag" data-priority="${task.priority}">
                    P${task.priority}
                </span>
            </td>
            <td>
                <span class="status-tag ${task.status}">${getStatusText(task.status)}</span>
            </td>
            <td title="${task.source_type}">
                <span class="source-type-tag" data-type="${task.source_type}">${getSourceTypeText(task.source_type)}</span>
            </td>
            <td title="${formatQuestion(task)}">${formatQuestion(task)}</td>
            <td title="${formatAnswer(task)}">${formatAnswer(task)}</td>
            <td class="time-cell">${formatTime(task.created_at)}</td>
            <td>
                <button class="action-btn" onclick="viewTask('${task.qa_id}')">
                    查看
                </button>
            </td>
        </tr>
    `).join('');
    
    // 更新统计
    document.getElementById('mainStats').textContent = `共 ${state.total} 条`;
}

function formatQuestion(task) {
    if (task.question) {
        return String(task.question).substring(0, 50);
    }
    return '-';
}

function formatAnswer(task) {
    if (task.answer) {
        return String(task.answer).substring(0, 100);
    }
    return '-';
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

function getSourceTypeText(type) {
    const typeMap = {
        'e2e': '端到端',
        'user_agent': '用户Agent',
        'agent_agent': '子Agent',
        'agent_llm': 'LLM',
        'agent_tool': 'Tool',
        'agent_other': '其他'
    };
    return typeMap[type] || type;
}

// 渲染分页
function renderPagination() {
    document.getElementById('paginationInfo').textContent = 
        `第 ${state.currentPage}/${state.totalPages} 页，共 ${state.total} 条`;
    
    document.getElementById('pageNum').textContent = state.currentPage;
    
    // 更新按钮状态
    const prevBtn = document.querySelector('#paginationBtns button:nth-child(2)');
    const nextBtn = document.querySelector('#paginationBtns button:nth-child(4)');
    const firstBtn = document.querySelector('#paginationBtns button:nth-child(1)');
    const lastBtn = document.querySelector('#paginationBtns button:nth-child(5)');
    
    prevBtn.disabled = state.currentPage <= 1;
    nextBtn.disabled = state.currentPage >= state.totalPages;
    firstBtn.disabled = state.currentPage <= 1;
    lastBtn.disabled = state.currentPage >= state.totalPages;
}

// 翻页
function changePage(page) {
    if (page < 1 || page > state.totalPages) return;
    loadTasks(page);
}

// 查看任务详情
async function viewTask(qaId) {
    try {
        const task = await apiGet(`/tasks/${qaId}`);
        state.selectedTask = task;
        renderTaskDetail(task);
        openDrawer();
    } catch (error) {
        console.error('获取任务详情失败:', error);
        showToast('获取任务详情失败', 'error');
    }
}

// 渲染任务详情
function renderTaskDetail(task) {
    const drawerBody = document.getElementById('drawerBody');
    
    drawerBody.innerHTML = `
        <div class="detail-section">
            <div class="detail-section-title">基本信息</div>
            <div class="detail-data-card">
                <div class="detail-key">QA ID</div>
                <div class="detail-value">${task.qa_id}</div>
            </div>
            <div class="detail-data-card" style="margin-top: 8px;">
                <div class="detail-key">Trace ID</div>
                <div class="detail-value">${task.source_trace_id}</div>
            </div>
            <div class="detail-data-card" style="margin-top: 8px;">
                <div class="detail-key">来源类型</div>
                <div class="detail-value">
                    <span class="source-type-tag" data-type="${task.source_type}">${getSourceTypeText(task.source_type)}</span>
                </div>
            </div>
            <div class="detail-data-card" style="margin-top: 8px;">
                <div class="detail-key">优先级</div>
                <div class="detail-value">P${task.priority}</div>
            </div>
            <div class="detail-data-card" style="margin-top: 8px;">
                <div class="detail-key">状态</div>
                <div class="detail-value">
                    <span class="status-tag ${task.status}">${getStatusText(task.status)}</span>
                </div>
            </div>
            <div class="detail-data-card" style="margin-top: 8px;">
                <div class="detail-key">层级</div>
                <div class="detail-value">
                    ${task.is_root ? '根节点（端到端）' : `子节点 (depth=${task.depth})`}
                </div>
            </div>
            <div class="detail-data-card" style="margin-top: 8px;">
                <div class="detail-key">创建时间</div>
                <div class="detail-value">${formatTime(task.created_at)}</div>
            </div>
        </div>
        
        <div class="detail-section">
            <div class="detail-section-title">QA内容</div>
            <div class="detail-data-card">
                <div class="detail-key">Question / Input</div>
                <div class="detail-value" style="margin-bottom: 12px;">
                    <pre>${formatValue(task.question)}</pre>
                </div>
                <div class="detail-key">Answer / Output</div>
                <div class="detail-value">
                    <pre>${formatValue(task.answer)}</pre>
                </div>
            </div>
        </div>
        
        ${task.caller || task.callee ? `
        <div class="detail-section">
            <div class="detail-section-title">调用链信息</div>
            <div class="detail-data-card">
                ${task.caller ? `<div class="detail-key">Caller</div><div class="detail-value" style="margin-bottom: 8px;">${task.caller}</div>` : ''}
                ${task.callee ? `<div class="detail-key">Callee</div><div class="detail-value">${task.callee}</div>` : ''}
            </div>
        </div>
        ` : ''}
        
        ${task.annotation && Object.keys(task.annotation).length > 0 ? `
        <div class="detail-section">
            <div class="detail-section-title">标注结果</div>
            <div class="detail-data-card">
                ${renderAnnotation(task.annotation)}
            </div>
        </div>
        ` : ''}
        
        ${task.status !== 'pending' ? '' : renderAnnotationForm(task)}
    `;
}

function formatValue(value) {
    if (value === null || value === undefined) return '-';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
}

function renderAnnotation(annotation) {
    return Object.entries(annotation).map(([key, value]) => {
        return `
            <div class="detail-key">${key}</div>
            <div class="detail-value" style="margin-bottom: 8px;">${formatValue(value)}</div>
        `;
    }).join('');
}

// 渲染标注表单
function renderAnnotationForm(task) {
    return `
        <div class="detail-section">
            <div class="detail-section-title">标注</div>
            <div class="annotation-form">
                <div class="form-group">
                    <label class="form-label">标注结果</label>
                    <textarea class="form-textarea" id="annotationContent" 
                        placeholder="请输入标注结果..."></textarea>
                </div>
                <div class="form-group">
                    <label class="form-label">评分</label>
                    <select class="filter-select" id="annotationScore" style="width: 100%;">
                        <option value="">请选择</option>
                        <option value="1">优秀 (1分)</option>
                        <option value="0.8">良好 (0.8分)</option>
                        <option value="0.6">一般 (0.6分)</option>
                        <option value="0.4">较差 (0.4分)</option>
                        <option value="0.2">很差 (0.2分)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">备注</label>
                    <textarea class="form-textarea" id="annotationComment" 
                        placeholder="可选输入备注..." style="min-height: 60px;"></textarea>
                </div>
                <div class="form-actions">
                    <button class="btn btn-success" onclick="submitAnnotation('${task.qa_id}')">
                        提交标注
                    </button>
                    <button class="btn btn-secondary" onclick="approveTask('${task.qa_id}')">
                        通过
                    </button>
                    <button class="btn btn-danger" onclick="rejectTask('${task.qa_id}')">
                        拒绝
                    </button>
                </div>
            </div>
        </div>
    `;
}

// 提交标注
async function submitAnnotation(qaId) {
    const content = document.getElementById('annotationContent')?.value;
    const score = document.getElementById('annotationScore')?.value;
    const comment = document.getElementById('annotationComment')?.value;
    
    if (!content && !score) {
        showToast('请输入标注结果或评分', 'warning');
        return;
    }
    
    try {
        await apiPut(`/tasks/${qaId}/annotate`, {
            status: 'annotated',
            annotation: {
                content: content,
                score: score ? parseFloat(score) : null,
                comment: comment || ''
            },
            scores: score ? { overall_score: parseFloat(score) } : {}
        });
        
        showToast('标注成功', 'success');
        closeDrawer();
        loadTasks(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('标注失败:', error);
        showToast('标注失败', 'error');
    }
}

// 通过任务
async function approveTask(qaId) {
    try {
        await apiPost(`/tasks/${qaId}/approve`, {});
        showToast('已通过', 'success');
        closeDrawer();
        loadTasks(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('操作失败:', error);
        showToast('操作失败', 'error');
    }
}

// 拒绝任务
async function rejectTask(qaId) {
    try {
        await apiPost(`/tasks/${qaId}/reject`, {});
        showToast('已拒绝', 'success');
        closeDrawer();
        loadTasks(state.currentPage);
        loadStats();
    } catch (error) {
        console.error('操作失败:', error);
        showToast('操作失败', 'error');
    }
}

// 打开抽屉
function openDrawer() {
    document.getElementById('drawerOverlay').classList.add('active');
    document.getElementById('detailDrawer').classList.add('active');
}

// 关闭抽屉
function closeDrawer() {
    document.getElementById('drawerOverlay').classList.remove('active');
    document.getElementById('detailDrawer').classList.remove('active');
    state.selectedTask = null;
}

// 展开/收起侧边栏区域
function toggleSection(sectionId) {
    const header = document.querySelector(`.sidebar-section-header:has(+ #${sectionId}Content)`);
    const content = document.getElementById(`${sectionId}Content`);
    const icon = document.getElementById(`${sectionId}ToggleIcon`);
    
    if (header && content) {
        header.classList.toggle('section-collapsed');
        content.style.maxHeight = header.classList.contains('section-collapsed') 
            ? '0' 
            : content.scrollHeight + 'px';
    }
    
    if (icon) {
        icon.textContent = header?.classList.contains('section-collapsed') ? '▶' : '▼';
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadTasks();
    
    // 监听过滤条件变化
    const filterInputs = document.querySelectorAll('.filter-input, .filter-select');
    filterInputs.forEach(input => {
        input.addEventListener('change', () => loadTasks(1));
    });
});

// 导出函数供全局使用
window.changePage = changePage;
window.applyFilters = applyFilters;
window.resetFilters = resetFilters;
window.viewTask = viewTask;
window.submitAnnotation = submitAnnotation;
window.approveTask = approveTask;
window.rejectTask = rejectTask;
window.closeDrawer = closeDrawer;
window.toggleSection = toggleSection;
window.debounce = debounce;
