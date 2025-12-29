/**
 * QA标注平台 - 前端逻辑（全新侧边栏布局版）
 */

// ============================================================================
// 全局状态
// ============================================================================
const state = {
    // 用户信息
    currentUser: {
        id: 'user_001',
        name: '标注员',
        role: 'annotator'
    },
    
    // 任务列表
    tasks: [],
    totalTasks: 0,
    totalPages: 1,
    currentPage: 1,
    pageSize: 15,
    
    // 当前选中的任务
    currentTask: null,
    currentTaskTree: null,
    
    // 过滤条件（改造：新增时间范围和Agent筛选）
    filters: {
        start_time: '',
        end_time: '',
        status: '',
        priority: '',
        search: '',
        batchId: ''
    },
    
    // 统计数据
    stats: {
        total: 0,
        pending: 0,
        annotated: 0,
        approved: 0
    },
    
    // 待导入预览数据
    preview: {
        trace_pending: 0,
        node_pending: 0,
        total_pending: 0
    },
    
    // 批次列表
    batches: [],
    
    // 当前查看的子任务
    currentChildTask: null,
    
    // Node Map视图状态
    nodeMapView: 'flowchart',
    currentFlowchartNode: null,
    
    // 侧边栏展开状态
    sidebarState: {
        pendingImport: true,
        imported: true
    }
};

// Agent头像映射（复用index.html的配色）
const agentImgMap = [
    {bgColor: '#FEEAD4', imgUrl: './image/agents/agent_0.png'},
    {bgColor: '#E4FBCC', imgUrl: './image/agents/agent_1.png'},
    {bgColor: '#D3F8DF', imgUrl: './image/agents/agent_2.png'},
    {bgColor: '#E0F2FE', imgUrl: './image/agents/agent_3.png'},
    {bgColor: '#E0EAFF', imgUrl: './image/agents/agent_4.png'},
    {bgColor: '#EFF1F5', imgUrl: './image/agents/agent_5.png'},
    {bgColor: '#FBE8FF', imgUrl: './image/agents/agent_6.png'},
    {bgColor: '#FBE7F6', imgUrl: './image/agents/agent_7.png'},
    {bgColor: '#FEF7C4', imgUrl: './image/agents/agent_8.png'},
    {bgColor: '#E6F4D7', imgUrl: './image/agents/agent_9.png'},
    {bgColor: '#D5F5F6', imgUrl: './image/agents/agent_10.png'},
    {bgColor: '#D2E9FF', imgUrl: './image/agents/agent_11.png'},
    {bgColor: '#D1DFFF', imgUrl: './image/agents/agent_12.png'},
    {bgColor: '#D5D9EB', imgUrl: './image/agents/agent_13.png'},
    {bgColor: '#EBE9FE', imgUrl: './image/agents/agent_14.png'},
    {bgColor: '#FFE4E8', imgUrl: './image/agents/agent_15.png'},
];

// API基础路径
const API_BASE = '/api/qa';

// ============================================================================
// 工具函数
// ============================================================================
function showToast(message, type = 'info') {
    // 移除现有的toast
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    // 2.5秒后开始淡出
    setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    try {
        const d = new Date(dateStr.replace(' ', 'T'));
        return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
    } catch {
        return dateStr;
    }
}

function formatDateShort(dateStr) {
    if (!dateStr) return '-';
    try {
        const d = new Date(dateStr.replace(' ', 'T'));
        return `${d.getMonth()+1}/${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
    } catch {
        return dateStr;
    }
}

// JSON格式化（用于llm/tool类型的question展示）
function formatJSON(str) {
    if (!str) return '(无)';
    try {
        const obj = JSON.parse(str);
        return JSON.stringify(obj, null, 2);
    } catch {
        return str;
    }
}

// 判断是否为llm或tool类型
function isLLMorTool(task) {
    return task.callee_type === 'llm' || task.callee_type === 'tool';
}

function formatTime(dateStr) {
    if (!dateStr) return '--:--';
    try {
        const d = new Date(dateStr.replace(' ', 'T'));
        return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}:${d.getSeconds().toString().padStart(2,'0')}`;
    } catch {
        return dateStr;
    }
}

function getAgentAvatar(agentName, size = 24) {
    if (!agentName) return '';
    const idx = Math.abs(hashCode(agentName)) % 16;
    const cur = agentImgMap[idx];
    return `<img src="${cur.imgUrl}" style="background-color: ${cur.bgColor}; width: ${size}px; height: ${size}px; border-radius: 50%;" class="agent-avatar" alt="${agentName}">`;
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

function truncate(str, len = 50) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
}

function getPriorityLabel(priority) {
    // 改造：新的优先级定义
    // P0: 端到端, P1: Agent, P2: LLM, P3: Tool, P4: 其他
    const labels = {
        0: 'P0',
        1: 'P1',
        2: 'P2',
        3: 'P3',
        4: 'P4'
    };
    return labels[priority] || `P${priority}`;
}

function getPriorityClass(priority) {
    return `p${priority}`;
}

// 获取Agent/Tool显示名称（改造：直接显示被调用者名称）
function getCalleeDisplay(task) {
    // 简化：只返回名称，不加图标
    const callee = task.callee || '';
    return callee || '-';
}

function getStatusLabel(status) {
    const labels = {
        'pending': '待标注',
        'assigned': '已分配',
        'in_progress': '进行中',
        'annotated': '已标注',
        'reviewing': '审核中',
        'approved': '已通过',
        'rejected': '已拒绝',
        'expired': '已过期',
        'cancelled': '已取消'
    };
    return labels[status] || status;
}

function getStatusClass(status) {
    return status;
}

// 获取Agent名称
function getAgentName(task) {
    if (task.callee && task.callee.trim() !== '') {
        return task.callee;
    }
    
    const sourceType = task.source_type;
    if (sourceType === 'e2e' || sourceType === 'user_agent') {
        return 'User → Agent';
    } else if (sourceType === 'agent_agent') {
        return task.caller || 'Agent → Agent';
    } else if (sourceType === 'agent_tool') {
        return task.caller ? `${task.caller} → Tool` : 'Agent → Tool';
    } else if (sourceType === 'agent_llm') {
        return task.caller ? `${task.caller} → LLM` : 'Agent → LLM';
    }
    
    return task.callee || task.caller || 'Unknown';
}

// 获取显示的来源文本
function getSourceDisplay(task) {
    const caller = task.caller || '';
    const callee = task.callee || '';
    const sourceType = task.source_type;
    
    if (caller && callee) {
        return `${caller} → ${callee}`;
    }
    
    if (callee) {
        if (sourceType === 'e2e' || sourceType === 'user_agent') {
            return `User → ${callee}`;
        } else if (sourceType === 'agent_agent') {
            return `Agent → ${callee}`;
        } else if (sourceType === 'agent_tool') {
            return `Tool: ${callee}`;
        } else if (sourceType === 'agent_llm') {
            return `LLM: ${callee}`;
        }
        return callee;
    }
    
    if (caller) {
        return `${caller} → ?`;
    }
    
    if (sourceType === 'e2e' || sourceType === 'user_agent') {
        return 'User → Agent';
    } else if (sourceType === 'agent_agent') {
        return 'Agent → Agent';
    } else if (sourceType === 'agent_tool') {
        return 'Tool';
    } else if (sourceType === 'agent_llm') {
        return 'LLM';
    }
    
    return 'Unknown';
}

function getNodeTypeClass(sourceType) {
    if (sourceType === 'e2e' || sourceType === 'user_agent') return 'agent';
    if (sourceType === 'agent_agent') return 'agent';
    if (sourceType === 'agent_tool') return 'tool';
    if (sourceType === 'agent_llm') return 'llm';
    return 'agent';
}

function getTaskIdShort(taskId) {
    if (!taskId) return '-';
    return taskId;
}

// 截断文本（用于答案列）
function truncateText(str, maxLen = 30) {
    if (!str) return '';
    return str.length > maxLen ? str.substring(0, maxLen) + '...' : str;
}

// 格式化数字
function formatNumber(num) {
    if (num >= 10000) {
        return (num / 10000).toFixed(1) + 'w';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'k';
    }
    return num.toString();
}

// ============================================================================
// API调用（改造：支持新的过滤参数）
// ============================================================================
async function apiRequest(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        const data = await response.json();
        if (data.code !== 200 && data.code !== 0) {
            throw new Error(data.message || '请求失败');
        }
        return data.data;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// 获取待导入预览（改造：支持过滤条件）
async function fetchPendingPreview() {
    const startTime = document.getElementById('filterStartTime')?.value;
    const endTime = document.getElementById('filterEndTime')?.value;
    const search = document.getElementById('filterSearch')?.value || '';
    
    if (!startTime || !endTime) {
        showToast('请先选择时间范围', 'warning');
        return null;
    }
    
    const params = new URLSearchParams({
        start_time: startTime.replace('T', ' ') + ':00',
        end_time: endTime.replace('T', ' ') + ':59',
        include_sub_nodes: document.getElementById('importIncludeSubNodes')?.checked !== false,
        search: search
    });
    
    return apiRequest(`/extract/preview?${params}`);
}

// 获取已导入统计（改造：支持时间范围过滤）
async function fetchImportedStats() {
    const startTime = document.getElementById('filterStartTime')?.value;
    const endTime = document.getElementById('filterEndTime')?.value;
    
    const params = new URLSearchParams();
    if (startTime) {
        params.append('start_time', startTime.replace('T', ' ') + ':00');
    }
    if (endTime) {
        params.append('end_time', endTime.replace('T', ' ') + ':59');
    }
    
    const queryString = params.toString();
    const url = queryString ? `?${queryString}` : '';
    
    return apiRequest(`/overview${url}`);
}

// 获取任务列表（改造：使用新的过滤参数）
async function fetchTasks(page = 1, pageSize = 15) {
    const params = new URLSearchParams({
        page: page,
        page_size: pageSize
    });
    
    // 过滤条件
    const status = document.getElementById('filterStatus')?.value;
    const priority = document.getElementById('filterPriority')?.value;
    const search = document.getElementById('filterSearch')?.value;
    
    if (status && status !== '') {
        params.append('status', status);
    }
    if (priority && priority !== '') {
        params.append('priority', priority);
    }
    if (search && search.trim() !== '') {
        params.append('search', search.trim());
    }
    
    // 时间范围（用于过滤创建时间）
    const startTime = document.getElementById('filterStartTime')?.value;
    const endTime = document.getElementById('filterEndTime')?.value;
    
    if (startTime) {
        params.append('start_time', startTime.replace('T', ' ') + ':00');
    }
    if (endTime) {
        params.append('end_time', endTime.replace('T', ' ') + ':59');
    }
    
    return apiRequest(`/tasks?${params}`);
}

async function fetchTaskTree(taskId) {
    return apiRequest(`/tasks/${taskId}/tree`);
}

async function fetchStats() {
    return apiRequest('/stats');
}

// 批次列表接口（暂时不使用）
async function fetchBatches() {
    try {
        return await apiRequest('/batches');
    } catch (error) {
        console.log('批次列表接口不可用');
        return { batches: [] };
    }
}

async function submitAnnotation(data) {
    return apiRequest('/annotations/submit', {
        method: 'POST',
        body: JSON.stringify(data)
    });
}

async function fetchAnnotationByTask(taskId) {
    try {
        return await apiRequest(`/annotations/by-task/${taskId}`);
    } catch {
        return null;
    }
}

async function reviewAnnotation(annotationId, reviewerId, reviewStatus, reviewComment = '') {
    return apiRequest('/annotations/review', {
        method: 'POST',
        body: JSON.stringify({
            annotation_id: annotationId,
            reviewer_id: reviewerId,
            review_status: reviewStatus,
            review_comment: reviewComment
        })
    });
}

async function previewExtraction(startTime, endTime, includeSubNodes = true, limit = 1000) {
    // 使用 GET 请求构建查询参数
    const params = new URLSearchParams({
        start_time: startTime,
        end_time: endTime,
        include_sub_nodes: includeSubNodes.toString(),
        limit: limit.toString()
    });
    return apiRequest(`/extract/preview?${params}`, {
        method: 'GET'
    });
}

async function executeExtraction(startTime, endTime, includeSubNodes = true, limit = 1000) {
    return apiRequest('/extract/execute', {
        method: 'POST',
        body: JSON.stringify({
            start_time: startTime,
            end_time: endTime,
            include_sub_nodes: includeSubNodes,
            limit: limit
        })
    });
}

async function initIndices() {
    return apiRequest('/admin/init-indices', { method: 'POST' });
}

// ============================================================================
// 渲染函数（改造：适配新布局）
// ============================================================================

// 渲染待导入预览区域
function renderPendingPreview(data) {
    if (!data) return;
    
    state.preview = {
        trace_pending: data.trace_pending || 0,
        node_pending: data.node_pending || 0,
        total_pending: data.estimated_total || 0
    };
    
    // 更新数量显示
    document.getElementById('previewTracePending').textContent = formatNumber(state.preview.trace_pending);
    document.getElementById('previewNodePending').textContent = formatNumber(state.preview.node_pending);
    document.getElementById('previewTotalPending').textContent = formatNumber(state.preview.total_pending);
    document.getElementById('pendingCount').textContent = formatNumber(state.preview.total_pending);
}

// 渲染已导入统计区域（恢复上一版本风格）
function renderImportedStats(data) {
    if (!data) return;
    
    const importedCount = data.imported_count || 0;
    const pendingCount = data.pending_count || 0;
    const annotatedCount = data.annotated_count || 0;
    const approvedCount = data.approved_count || 0;
    const rejectedCount = data.rejected_count || 0;
    const total = importedCount;
    
    // 更新已导入总数
    document.getElementById('importedCount').textContent = formatNumber(importedCount);
    
    // 更新各状态数量
    document.getElementById('statPending').textContent = formatNumber(pendingCount);
    document.getElementById('statAnnotated').textContent = formatNumber(annotatedCount);
    document.getElementById('statApproved').textContent = formatNumber(approvedCount);
    document.getElementById('statRejected').textContent = formatNumber(rejectedCount);
    
    // 更新进度条（恢复上一版本逻辑）
    const totalAnnotated = annotatedCount + approvedCount + rejectedCount;
    const annotatedPercent = total > 0 ? Math.round(totalAnnotated / total * 100) : 0;
    const approvedPercent = total > 0 ? Math.round(approvedCount / total * 100) : 0;
    
    document.getElementById('progressApproved').style.width = `${approvedPercent}%`;
    document.getElementById('progressAnnotated').style.width = `${annotatedPercent - approvedPercent}%`;
    document.getElementById('progressPending').style.width = `${Math.max(0, 100 - annotatedPercent)}%`;
}

// 渲染QA表格
function renderQATable() {
    const tbody = document.getElementById('qaTableBody');
    const emptyState = document.getElementById('emptyState');
    
    if (!tbody) return;
    
    if (state.tasks.length === 0) {
        tbody.innerHTML = '';
        emptyState.classList.add('show');
        return;
    }
    
    emptyState.classList.remove('show');
    
    tbody.innerHTML = state.tasks.map(task => `
        <tr class="${state.currentTask?.task_id === task.task_id ? 'active' : ''}" 
            onclick="openTaskDetail('${task.task_id}')">
            <td class="task-id" title="${task.task_id}">${getTaskIdShort(task.task_id)}</td>
            <td><span class="qa-priority ${getPriorityClass(task.priority)}">${getPriorityLabel(task.priority)}</span></td>
            <td><span class="qa-status ${getStatusClass(task.status)}">${getStatusLabel(task.status)}</span></td>
            <td class="qa-callee" title="${getCalleeDisplay(task)}">${getCalleeDisplay(task)}</td>
            <td class="qa-question" title="${task.question || ''}">${task.question || ''}</td>
            <td class="qa-answer" title="${task.answer || ''}">${truncateText(task.answer, 30)}</td>
            <td class="qa-time">${formatDateShort(task.created_at)}</td>
            <td class="qa-action">
                <button class="btn btn-primary btn-small" onclick="event.stopPropagation(); openTaskDetail('${task.task_id}')">
                    标注
                </button>
            </td>
        </tr>
    `).join('');
    
    // 更新主内容区统计
    document.getElementById('mainStats').textContent = `共 ${state.totalTasks} 条`;
}

// 渲染分页
function renderPagination() {
    const info = document.getElementById('paginationInfo');
    const pageNum = document.getElementById('pageNum');
    const btns = document.getElementById('paginationBtns');
    
    if (!info || !pageNum || !btns) return;
    
    state.totalPages = Math.ceil(state.totalTasks / state.pageSize) || 1;
    info.textContent = `第 ${state.currentPage}/${state.totalPages} 页，共 ${state.totalTasks} 条`;
    pageNum.textContent = state.currentPage;
    
    btns.innerHTML = `
        <button class="pagination-btn" onclick="changePage(1)" ${state.currentPage === 1 ? 'disabled' : ''}>首页</button>
        <button class="pagination-btn" onclick="changePage(${state.currentPage - 1})" ${state.currentPage === 1 ? 'disabled' : ''}>上一页</button>
        <span class="page-num">${state.currentPage}</span>
        <button class="pagination-btn" onclick="changePage(${state.currentPage + 1})" ${state.currentPage >= state.totalPages ? 'disabled' : ''}>下一页</button>
        <button class="pagination-btn" onclick="changePage(${state.totalPages})" ${state.currentPage >= state.totalPages ? 'disabled' : ''}>末页</button>
    `;
}

// ============================================================================
// Node Map 渲染
// ============================================================================

function renderTaskTree() {
    const tree = state.currentTaskTree;
    if (!tree || !tree.root) return '';
    
    const children = tree.children || [];
    
    return `
        <div class="task-tree-container">
            <div class="task-tree-header">
                <div class="task-tree-title">
                    📊 调用链路视图 (${children.length} 个子任务)
                </div>
                <div class="task-tree-tabs">
                    <div class="task-tree-tab ${state.nodeMapView === 'flowchart' ? 'active' : ''}" 
                         onclick="switchNodeMapView('flowchart')">
                        流程图
                    </div>
                    <div class="task-tree-tab ${state.nodeMapView === 'timeline' ? 'active' : ''}" 
                         onclick="switchNodeMapView('timeline')">
                        时间线
                    </div>
                </div>
            </div>
            
            ${state.nodeMapView === 'flowchart' ? renderFlowchartView(tree) : renderTimelineView(tree)}
        </div>
    `;
}

function renderFlowchartView(tree) {
    const root = tree.root;
    const children = tree.children || [];
    
    const nodes = [
        { ...root, isRoot: true },
        ...children
    ];
    
    return `
        <div class="flowchart-view">
            <div class="flowchart-container">
                ${nodes.map((node, index) => `
                    <div class="flowchart-node">
                        <div class="flowchart-node-card ${node.isRoot ? 'root' : getNodeTypeClass(node.source_type)} ${state.currentFlowchartNode === node.task_id ? 'active' : ''}"
                             onclick="selectFlowchartNode('${node.task_id}')"
                             title="点击查看详情：${getSourceDisplay(node)}">
                            ${getAgentAvatar(getAgentName(node), 24)}
                            <div class="flowchart-node-name">${getAgentName(node)}</div>
                            <div class="flowchart-node-type">${getSourceDisplay(node)}</div>
                        </div>
                        ${index < nodes.length - 1 ? `
                            <div class="flowchart-arrow">
                                <svg viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"/>
                                </svg>
                            </div>
                        ` : ''}
                    </div>
                `).join('')}
            </div>
            
            ${state.currentFlowchartNode ? renderFlowchartTaskDetail() : ''}
        </div>
    `;
}

function renderTimelineView(tree) {
    const root = tree.root;
    const children = tree.children || [];
    
    const allNodes = [root, ...children];
    
    const times = allNodes.map(n => new Date(n.created_at.replace(' ', 'T')).getTime());
    const minTime = Math.min(...times);
    const maxTime = Math.max(...times);
    const timeRange = maxTime - minTime || 1;
    
    return `
        <div class="flowchart-view timeline-view">
            ${allNodes.map(node => {
                const nodeTime = new Date(node.created_at.replace(' ', 'T')).getTime();
                const leftPercent = ((nodeTime - minTime) / timeRange) * 100;
                const width = Math.max(15, Math.min(40, 100 / allNodes.length));
                
                return `
                    <div class="timeline-row">
                        <div class="timeline-time">${formatTime(node.created_at)}</div>
                        <div class="timeline-bar">
                            <div class="timeline-bar-item ${node.isRoot ? 'root' : getNodeTypeClass(node.source_type)} ${state.currentFlowchartNode === node.task_id ? 'active' : ''}"
                                 style="left: ${leftPercent}%; width: ${width}%;"
                                 onclick="selectFlowchartNode('${node.task_id}')"
                                 title="${getAgentName(node)} - ${getSourceDisplay(node)}">
                                ${getAgentName(node)}
                            </div>
                        </div>
                    </div>
                `;
            }).join('')}
            
            ${state.currentFlowchartNode ? renderFlowchartTaskDetail() : ''}
        </div>
    `;
}

function selectFlowchartNode(taskId) {
    state.currentFlowchartNode = taskId;
    
    if (state.currentTask && state.currentTask.task_id === taskId) {
        renderDrawerBody();
        return;
    }
    
    viewChildTask(taskId);
}

function renderFlowchartTaskDetail() {
    const taskId = state.currentFlowchartNode;
    if (!taskId) return '';
    
    let task = null;
    if (state.currentTask && state.currentTask.task_id === taskId) {
        task = state.currentTask;
    } else {
        task = state.currentChildTask;
    }
    
    if (!task) return '';
    
    return `
        <div class="task-detail-card ${state.currentTask?.task_id === task.task_id ? 'active' : ''}">
            <div class="task-detail-header">
                <span class="qa-priority ${getPriorityClass(task.priority)}">${getPriorityLabel(task.priority)}</span>
                <span class="task-detail-title">${getAgentName(task)}</span>
                <span class="qa-status ${getStatusClass(task.status)}">${getStatusLabel(task.status)}</span>
            </div>
            <div class="task-detail-content">
                <strong>问题：</strong>${task.question || '(无)'}
            </div>
            <div class="task-detail-content" style="margin-top: 8px;">
                <strong>答案：</strong>${task.answer || '(无)'}
            </div>
        </div>
    `;
}

function switchNodeMapView(view) {
    state.nodeMapView = view;
    state.currentFlowchartNode = null;
    renderDrawerBody();
}

// 渲染抽屉内容（改造：适配新的平铺数据结构）
function renderDrawerBody() {
    const container = document.getElementById('drawerBody');
    if (!container || !state.currentTask) return;
    
    const task = state.currentTask;
    const tree = state.currentTaskTree;
    const isReviewer = state.currentUser.role === 'reviewer' || state.currentUser.role === 'admin';
    
    // 改造：子任务不再通过parent_task_id关联，改为通过source_trace_id查找同trace的E2E任务
    const children = tree && tree.children ? tree.children : [];
    
    container.innerHTML = `
        <div class="qa-section task-info-section">
            <div class="qa-label">
                <span>任务信息</span>
                <span class="qa-status ${getStatusClass(task.status)}">${getStatusLabel(task.status)}</span>
            </div>
            <div class="task-info-row">
                <span class="task-info-label">Agent:</span>
                <span class="task-info-value">${getCalleeDisplay(task)}</span>
            </div>
            <div class="task-info-row">
                <span class="task-info-label">类型:</span>
                <span class="task-info-value">${getPriorityLabel(task.priority)} (${task.callee_type || '-'})</span>
            </div>
            <div class="task-info-row">
                <span class="task-info-label">创建:</span>
                <span class="task-info-value">${formatDate(task.created_at)}</span>
            </div>
            <div class="task-info-row">
                <span class="task-info-label">trace_id:</span>
                <span class="task-info-value">${task.source_trace_id || '-'}</span>
            </div>
            <div class="task-info-row">
                <span class="task-info-label">node_id:</span>
                <span class="task-info-value">${task.source_node_id || '-'}</span>
            </div>
            <div class="task-info-row">
                <span class="task-info-label">task_id:</span>
                <span class="task-info-value">${task.task_id}</span>
            </div>
        </div>
        
        <div class="qa-section">
            <div class="qa-label">📥 Input</div>
            <div class="qa-content ${isLLMorTool(task) ? 'json-content' : ''}">${isLLMorTool(task) ? formatJSON(task.question) : (task.question || '(无)')}</div>
        </div>
        
        <div class="qa-section">
            <div class="qa-label">📤 Output</div>
            <div class="qa-content ${isLLMorTool(task) ? 'json-content' : ''}">${isLLMorTool(task) ? formatJSON(task.answer) : (task.answer || '(无)')}</div>
        </div>
        
        <div class="annotation-form">
            <div class="form-title">✏️ 标注信息</div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>修正后Input</label>
                    <textarea id="annotatedQuestion" rows="3">${task.question || ''}</textarea>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>修正后Output</label>
                    <textarea id="annotatedAnswer" rows="4">${task.answer || ''}</textarea>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>质量评分</label>
                    <select id="qualityLabel">
                        <option value="excellent">优秀</option>
                        <option value="good">良好</option>
                        <option value="acceptable" selected>可接受</option>
                        <option value="poor">较差</option>
                        <option value="invalid">无效</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>修正类型</label>
                    <select id="correctionType">
                        <option value="none" selected>无修正</option>
                        <option value="minor">小幅修正</option>
                        <option value="major">大幅修正</option>
                        <option value="rewrite">完全重写</option>
                    </select>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>领域</label>
                    <input type="text" id="domain" placeholder="如：金融、医疗、技术...">
                </div>
                <div class="form-group">
                    <label>意图</label>
                    <input type="text" id="intent" placeholder="如：咨询、投诉、查询...">
                </div>
                <div class="form-group">
                    <label>复杂度</label>
                    <select id="complexity">
                        <option value="">请选择</option>
                        <option value="simple">简单</option>
                        <option value="medium">中等</option>
                        <option value="complex">复杂</option>
                    </select>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label class="form-checkbox">
                        <input type="checkbox" id="isUseful" checked>
                        该QA对可用
                    </label>
                </div>
                <div class="form-group">
                    <label class="form-checkbox">
                        <input type="checkbox" id="shouldAddToKb">
                        加入知识库
                    </label>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>备注</label>
                    <textarea id="annotationNotes" rows="2" placeholder="可选的标注备注..."></textarea>
                </div>
            </div>
            
            <div class="form-actions">
                ${task.status === 'pending' || task.status === 'assigned' ? `
                    <button class="btn btn-primary" onclick="handleSubmitAnnotation()">💾 提交标注</button>
                ` : ''}
                ${isReviewer && task.status === 'annotated' ? `
                    <button class="btn btn-success" onclick="handleReview('approved')">✅ 审核通过</button>
                    <button class="btn btn-danger" onclick="handleReview('rejected')">❌ 审核拒绝</button>
                ` : ''}
            </div>
        </div>
        
        ${children.length > 0 ? renderTaskTree() : ''}
        
        ${children.length > 0 ? `
            <div class="child-task-section">
                <div class="child-task-title">📋 同trace关联任务 (${children.length}个)</div>
                <div class="child-task-list">
                    ${children.map(child => `
                        <div class="child-task-item ${state.currentChildTask?.task_id === child.task_id ? 'active' : ''}" 
                             onclick="viewChildTask('${child.task_id}')">
                            <div class="child-task-item-header">
                                <span class="child-task-item-type ${getPriorityClass(child.priority)}">${getPriorityLabel(child.priority)}</span>
                                <span class="child-task-item-callee">${getCalleeDisplay(child)}</span>
                                <span class="child-task-item-status">
                                    <span class="qa-status ${getStatusClass(child.status)}">${getStatusLabel(child.status)}</span>
                                </span>
                            </div>
                            <div class="child-task-item-question">${child.question || '(无)'}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        ` : ''}
        
        ${state.currentChildTask && state.currentChildTask.task_id !== task.task_id ? `
            <div class="qa-section" style="background: #FFF9E6; margin-top: 16px;">
                <div class="qa-label">
                    <span>📋 关联任务详情</span>
                    <button class="btn btn-small btn-secondary" onclick="closeChildTaskDetail()">关闭</button>
                </div>
                <div style="margin-top: 8px; font-size: 12px; color: #666;">
                    <div style="margin-bottom: 8px;">
                        <strong>类型：</strong>${getPriorityLabel(state.currentChildTask.priority)} | 
                        <strong>Agent：</strong>${getCalleeDisplay(state.currentChildTask)}
                    </div>
                    <div style="margin-bottom: 8px;">
                        <strong>Input：</strong>${state.currentChildTask.question || '(无)'}
                    </div>
                    <div><strong>Output：</strong>${state.currentChildTask.answer || '(无)'}</div>
                </div>
            </div>
        ` : ''}
    `;
}

// ============================================================================
// 事件处理
// ============================================================================

async function openTaskDetail(taskId) {
    try {
        const tree = await fetchTaskTree(taskId);
        state.currentTask = tree.root;
        state.currentTaskTree = tree;
        state.currentChildTask = null;
        state.currentFlowchartNode = taskId;
        state.nodeMapView = 'flowchart';
        
        const annotation = await fetchAnnotationByTask(taskId);
        if (annotation) {
            setTimeout(() => {
                const q = document.getElementById('annotatedQuestion');
                const a = document.getElementById('annotatedAnswer');
                if (q) q.value = annotation.annotated_question || '';
                if (a) a.value = annotation.annotated_answer || '';
            }, 100);
        }
        
        renderDrawerBody();
        openDrawer();
        renderQATable();
    } catch (error) {
        showToast('加载任务失败: ' + error.message, 'error');
    }
}

function openDrawer() {
    document.getElementById('drawerOverlay').classList.add('show');
    document.getElementById('detailDrawer').classList.add('show');
}

function closeDrawer() {
    document.getElementById('drawerOverlay').classList.remove('show');
    document.getElementById('detailDrawer').classList.remove('show');
    state.currentChildTask = null;
    state.currentFlowchartNode = null;
}

async function viewChildTask(taskId) {
    try {
        const tree = await fetchTaskTree(taskId);
        if (tree && tree.root) {
            state.currentChildTask = tree.root;
            state.currentFlowchartNode = taskId;
            renderDrawerBody();
        }
    } catch (error) {
        showToast('加载子任务失败: ' + error.message, 'error');
    }
}

function closeChildTaskDetail() {
    state.currentChildTask = null;
    if (state.currentTask) {
        state.currentFlowchartNode = state.currentTask.task_id;
    }
    renderDrawerBody();
}

async function changePage(page) {
    if (page < 1 || page > state.totalPages) return;
    state.currentPage = page;
    await loadTasks();
}

async function loadTasks() {
    try {
        const result = await fetchTasks(state.currentPage, state.pageSize);
        state.tasks = result.tasks || [];
        state.totalTasks = result.total || 0;
        renderQATable();
        renderPagination();
    } catch (error) {
        showToast('加载任务失败: ' + error.message, 'error');
    }
}

async function loadOverview() {
    try {
        const result = await fetchImportedStats();
        console.log('Overview result:', result);
        state.overview = result;
        renderPendingPreview(result);
        renderImportedStats(result);
    } catch (error) {
        console.error('加载概览失败:', error);
    }
}

async function loadImportedStats() {
    try {
        const result = await fetchImportedStats();
        renderImportedStats(result);
    } catch (error) {
        console.error('加载已导入统计失败:', error);
    }
}

async function applyFilters() {
    state.currentPage = 1;
    await loadTasks();
}

// 改造：新的预览导入函数（不显示toast，由调用方决定）
async function handlePreviewImport() {
    const startTime = document.getElementById('filterStartTime')?.value;
    const endTime = document.getElementById('filterEndTime')?.value;
    
    if (!startTime || !endTime) {
        return null;
    }
    
    try {
        const previewData = await fetchPendingPreview();
        if (previewData) {
            renderPendingPreview(previewData);
        }
        return previewData;
    } catch (error) {
        console.error('预览失败:', error);
        return null;
    }
}

// 改造：新的执行导入函数
async function handleExecuteImport() {
    const startTime = document.getElementById('filterStartTime')?.value;
    const endTime = document.getElementById('filterEndTime')?.value;
    const includeSubNodes = document.getElementById('importIncludeSubNodes')?.checked !== false;
    const limit = parseInt(document.getElementById('importLimit')?.value) || 1000;
    
    if (!startTime || !endTime) {
        showToast('请选择时间范围', 'warning');
        return;
    }
    
    if (!confirm('确定要执行导入吗？系统会自动去重，已存在的数据不会重复导入。')) {
        return;
    }
    
    try {
        const btn = document.getElementById('btnImport');
        btn.disabled = true;
        btn.innerHTML = '<span class="loading"></span> 导入中...';
        
        const result = await executeExtraction(
            startTime.replace('T', ' ') + ':00',
            endTime.replace('T', ' ') + ':59',
            includeSubNodes,
            limit
        );
        
        showToast(`导入完成: E2E ${result.e2e_count || 0} 条, 子任务 ${result.sub_task_count || 0} 条`, 'success');
        
        // 刷新数据（不显示toast）
        state.currentPage = 1;
        await Promise.all([
            loadTasks(),
            loadImportedStats(),
            handlePreviewImport()  // 只刷新数据，不显示toast
        ]);
        
    } catch (error) {
        showToast('导入失败: ' + error.message, 'error');
    } finally {
        const btn = document.getElementById('btnImport');
        if (btn) {
        btn.disabled = false;
            btn.innerHTML = '🚀 开始导入';
        }
    }
}

async function handleSubmitAnnotation() {
    if (!state.currentTask) {
        showToast('请先选择任务', 'warning');
        return;
    }
    
    const data = {
        task_id: state.currentTask.task_id,
        annotator_id: state.currentUser.id,
        annotated_question: document.getElementById('annotatedQuestion')?.value || '',
        annotated_answer: document.getElementById('annotatedAnswer')?.value || '',
        quality_label: document.getElementById('qualityLabel')?.value || 'acceptable',
        is_useful: document.getElementById('isUseful')?.checked !== false,
        correction_type: document.getElementById('correctionType')?.value || 'none',
        domain: document.getElementById('domain')?.value || '',
        intent: document.getElementById('intent')?.value || '',
        complexity: document.getElementById('complexity')?.value || '',
        should_add_to_kb: document.getElementById('shouldAddToKb')?.checked || false,
        annotation_notes: document.getElementById('annotationNotes')?.value || '',
    };
    
    if (!data.annotated_question || !data.annotated_answer) {
        showToast('请填写修正后的Input和Output', 'warning');
        return;
    }
    
    try {
        await submitAnnotation(data);
        showToast('标注提交成功', 'success');
        
        // 刷新相关数据
        await openTaskDetail(state.currentTask.task_id);
        await loadTasks();
        await loadImportedStats();
        
    } catch (error) {
        showToast('提交失败: ' + error.message, 'error');
    }
}

async function handleReview(status) {
    if (!state.currentTask) return;
    
    const comment = status === 'rejected' ? prompt('请输入拒绝原因:') : '';
    if (status === 'rejected' && !comment) {
        showToast('请输入拒绝原因', 'warning');
        return;
    }
    
    try {
        const annotation = await fetchAnnotationByTask(state.currentTask.task_id);
        if (!annotation) {
            showToast('未找到标注记录', 'error');
            return;
        }
        
        await reviewAnnotation(annotation.annotation_id, state.currentUser.id, status, comment || '');
        showToast(status === 'approved' ? '审核通过' : '已拒绝', 'success');
        
        await openTaskDetail(state.currentTask.task_id);
        await loadTasks();
        await loadImportedStats();
        
    } catch (error) {
        showToast('审核失败: ' + error.message, 'error');
    }
}

// 切换区域展开/收起
function toggleSection(sectionName) {
    const content = document.getElementById(`${sectionName}Content`);
    const icon = document.getElementById(`${sectionName}ToggleIcon`);
    
    if (!content || !icon) return;
    
    content.classList.toggle('collapsed');
    icon.textContent = content.classList.contains('collapsed') ? '▶' : '▼';
    state.sidebarState[sectionName] = !content.classList.contains('collapsed');
}

// 全局刷新
async function handleGlobalRefresh() {
    const startTime = document.getElementById('filterStartTime')?.value;
    const endTime = document.getElementById('filterEndTime')?.value;
    
    if (!startTime || !endTime) {
        showToast('请先选择时间范围', 'warning');
        return;
    }
    
    try {
        // 并行加载所有数据
        await Promise.all([
            handlePreviewImport(),
            loadTasks(),
            loadImportedStats()
        ]);
        showToast('数据刷新完成', 'success');
    } catch (error) {
        showToast('刷新失败: ' + error.message, 'error');
    }
}

function switchRole(role) {
    state.currentUser.role = role;
    const labels = { annotator: '标注员', reviewer: '审核员', admin: '管理员' };
    document.getElementById('userRole').textContent = labels[role];
    showToast(`已切换为${labels[role]}角色`, 'info');
    
    if (state.currentTask) {
        renderDrawerBody();
    }
}

async function handleInitIndices() {
    if (!confirm('确定要初始化ES索引吗？')) return;
    
    try {
        const result = await initIndices();
        showToast('索引初始化完成', 'success');
        console.log('Index init result:', result);
    } catch (error) {
        showToast('初始化失败: ' + error.message, 'error');
    }
}

// ============================================================================
// 左侧栏拖拽功能
// ============================================================================
function initSidebarResize() {
    const sidebar = document.getElementById('annotationSidebar');
    const handle = document.getElementById('sidebarResizeHandle');
    
    if (!sidebar || !handle) return;
    
    let isResizing = false;
    let startX, startWidth;
    
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
        const newWidth = Math.max(200, Math.min(500, startWidth + diffX));
        sidebar.style.width = newWidth + 'px';
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
        const newWidth = Math.max(60, startWidth + diffX);
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
// 初始化
// ============================================================================
document.addEventListener('DOMContentLoaded', async () => {
    console.log('QA Annotation Platform initialized (New Layout Edition)');
    
    // 初始化侧边栏拖拽
    initSidebarResize();
    
    // 初始化表格列宽拖拽
    initTableColumnResize();
    
    // 设置全局过滤的默认时间（今日0点到当前时间）
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
    
    const formatForInput = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    };
    
    const startInput = document.getElementById('filterStartTime');
    const endInput = document.getElementById('filterEndTime');
    if (startInput) startInput.value = formatForInput(todayStart);
    if (endInput) endInput.value = formatForInput(now);
    
    // 添加时间变化监听器（自动触发预览）
    if (startInput) {
        startInput.addEventListener('change', debounce(handlePreviewImport, 500));
    }
    if (endInput) {
        endInput.addEventListener('change', debounce(handlePreviewImport, 500));
    }
    
    // 进入页面自动加载数据
    try {
        await Promise.all([
            handlePreviewImport(),
            loadTasks(),
            loadImportedStats()
        ]);
    } catch (error) {
        console.error('初始化加载失败:', error);
    }
});

// 防抖函数
function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}
