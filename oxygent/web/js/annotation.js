/**
 * QA标注平台 - 前端逻辑（简洁风格版 - 支持列宽拖拽）
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
    
    // 过滤条件
    filters: {
        status: '',
        priority: '',
        sourceType: '',
        batchId: '',
        search: ''
    },
    
    // 统计数据
    stats: {
        total: 0,
        pending: 0,
        annotated: 0,
        approved: 0
    },
    
    // 批次列表
    batches: [],
    
    // 当前查看的子任务
    currentChildTask: null
};

// API基础路径
const API_BASE = '/api/qa';

// ============================================================================
// 工具函数
// ============================================================================
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
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

function truncate(str, len = 50) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
}

function getPriorityLabel(priority) {
    const labels = { 0: 'P0', 1: 'P1', 2: 'P2', 3: 'P3' };
    return labels[priority] || `P${priority}`;
}

function getPriorityClass(priority) {
    return `p${priority}`;
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

function getSourceTypeLabel(sourceType) {
    const labels = {
        'e2e': '端到端',
        'user_agent': '用户→Agent',
        'agent_agent': 'Agent→Agent',
        'agent_tool': 'Agent→Tool'
    };
    return labels[sourceType] || sourceType;
}

function getTaskIdShort(taskId) {
    if (!taskId) return '-';
    return taskId.substring(0, 8);
}

// ============================================================================
// API调用
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

async function fetchTasks(page = 1, pageSize = 15) {
    const params = new URLSearchParams({
        page: page,
        page_size: pageSize
    });
    
    // 确保筛选条件被正确传递
    if (state.filters.status && state.filters.status !== '') {
        params.append('status', state.filters.status);
    }
    if (state.filters.priority !== '' && state.filters.priority !== undefined && state.filters.priority !== null) {
        params.append('priority', state.filters.priority);
    }
    if (state.filters.batchId && state.filters.batchId !== '') {
        params.append('batch_id', state.filters.batchId);
    }
    if (state.filters.search && state.filters.search.trim() !== '') {
        params.append('search', state.filters.search.trim());
    }
    
    console.log('Fetching tasks with params:', params.toString());
    return apiRequest(`/tasks?${params}`);
}

async function fetchTaskTree(taskId) {
    return apiRequest(`/tasks/${taskId}/tree`);
}

async function fetchStats() {
    return apiRequest('/stats');
}

async function fetchBatches() {
    return apiRequest('/batches');
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
    return apiRequest('/extract/preview', {
        method: 'POST',
        body: JSON.stringify({ 
            start_time: startTime, 
            end_time: endTime,
            include_sub_nodes: includeSubNodes,
            limit: limit
        })
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
// 渲染函数
// ============================================================================

// 渲染统计面板
function renderStats() {
    const panel = document.getElementById('statsPanel');
    if (!panel) return;
    
    const { stats } = state;
    panel.innerHTML = `
        <div class="stat-card total">
            <div class="stat-value">${stats.total || 0}</div>
            <div class="stat-label">总任务</div>
        </div>
        <div class="stat-card pending">
            <div class="stat-value">${stats.by_status?.pending || 0}</div>
            <div class="stat-label">待标注</div>
        </div>
        <div class="stat-card annotated">
            <div class="stat-value">${stats.by_status?.annotated || 0}</div>
            <div class="stat-label">已标注</div>
        </div>
        <div class="stat-card approved">
            <div class="stat-value">${stats.by_status?.approved || 0}</div>
            <div class="stat-label">已通过</div>
        </div>
    `;
}

// 渲染批次下拉
function renderBatchSelect() {
    const select = document.getElementById('filterBatch');
    if (!select) return;
    
    const currentValue = select.value;
    select.innerHTML = '<option value="">全部批次</option>' +
        state.batches.map(b => `<option value="${b.batch_id}">${b.batch_id.substring(0, 8)} (${b.count}条)</option>`).join('');
    select.value = currentValue;
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
            <td class="task-id">${getTaskIdShort(task.task_id)}</td>
            <td><span class="qa-priority ${getPriorityClass(task.priority)}">${getPriorityLabel(task.priority)}</span></td>
            <td><span class="qa-status ${getStatusClass(task.status)}">${getStatusLabel(task.status)}</span></td>
            <td><span class="qa-source">${getSourceTypeLabel(task.source_type)}</span></td>
            <td class="qa-question" title="${task.question || ''}">${task.question || ''}</td>
            <td class="qa-answer" title="${task.answer || ''}">${task.answer || ''}</td>
            <td class="qa-time">${formatDateShort(task.created_at)}</td>
            <td class="qa-action">
                <button class="btn btn-primary btn-small" onclick="event.stopPropagation(); openTaskDetail('${task.task_id}')">
                    标注
                </button>
            </td>
        </tr>
    `).join('');
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

// 渲染抽屉内容
function renderDrawerBody() {
    const container = document.getElementById('drawerBody');
    if (!container || !state.currentTask) return;
    
    const task = state.currentTask;
    const tree = state.currentTaskTree;
    const isReviewer = state.currentUser.role === 'reviewer' || state.currentUser.role === 'admin';
    
    container.innerHTML = `
        <!-- 任务信息 -->
        <div class="qa-section">
            <div class="qa-label">
                <span>任务信息</span>
                <span class="qa-status ${getStatusClass(task.status)}">${getStatusLabel(task.status)}</span>
            </div>
            <div style="display:flex; gap:16px; font-size:12px; color:#666; margin-top:8px;">
                <span>ID: ${task.task_id}</span>
                <span>来源: ${getSourceTypeLabel(task.source_type)}</span>
                <span>优先级: ${getPriorityLabel(task.priority)}</span>
                <span>创建: ${formatDate(task.created_at)}</span>
            </div>
        </div>
        
        <!-- 原始问题 -->
        <div class="qa-section">
            <div class="qa-label">原始问题</div>
            <div class="qa-content">${task.question || '(无)'}</div>
        </div>
        
        <!-- 原始答案 -->
        <div class="qa-section">
            <div class="qa-label">原始答案</div>
            <div class="qa-content">${task.answer || '(无)'}</div>
        </div>
        
        <!-- 标注表单 -->
        <div class="annotation-form">
            <div class="form-title">标注信息</div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>标注后问题</label>
                    <textarea id="annotatedQuestion" rows="3">${task.question || ''}</textarea>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>标注后答案</label>
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
                    <button class="btn btn-primary" onclick="handleSubmitAnnotation()">提交标注</button>
                ` : ''}
                ${isReviewer && task.status === 'annotated' ? `
                    <button class="btn btn-success" onclick="handleReview('approved')">审核通过</button>
                    <button class="btn btn-danger" onclick="handleReview('rejected')">审核拒绝</button>
                ` : ''}
            </div>
        </div>
        
        <!-- 子任务树 -->
        ${tree && tree.children && tree.children.length > 0 ? `
            <div class="children-tree">
                <div class="tree-title">关联子任务 (${tree.children.length})</div>
                ${tree.children.map(child => `
                    <div class="tree-item" onclick="viewChildTask('${child.task_id}')" title="点击查看详情">
                        <div class="tree-item-left">
                            <span class="tree-item-type ${child.source_type}">${getSourceTypeLabel(child.source_type)}</span>
                            <span class="tree-item-question">${truncate(child.question, 30)}</span>
                        </div>
                        <span class="qa-status ${getStatusClass(child.status)}">${getStatusLabel(child.status)}</span>
                    </div>
                `).join('')}
            </div>
        ` : ''}
        
        <!-- 子任务详情 -->
        ${state.currentChildTask ? `
            <div class="qa-section" style="background: #FFF9E6; margin-top: 16px;">
                <div class="qa-label">
                    <span>子任务详情</span>
                    <button class="btn btn-small btn-secondary" onclick="closeChildTaskDetail()">关闭</button>
                </div>
                <div style="margin-top: 8px; font-size: 12px; color: #666;">
                    <div><strong>问题:</strong> ${state.currentChildTask.question || '(无)'}</div>
                    <div style="margin-top: 8px;"><strong>答案:</strong> ${state.currentChildTask.answer || '(无)'}</div>
                </div>
            </div>
        ` : ''}
    `;
}

// ============================================================================
// 事件处理
// ============================================================================

// 打开任务详情抽屉
async function openTaskDetail(taskId) {
    try {
        const tree = await fetchTaskTree(taskId);
        state.currentTask = tree.root;
        state.currentTaskTree = tree;
        state.currentChildTask = null;
        
        // 加载已有标注
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

// 打开抽屉
function openDrawer() {
    document.getElementById('drawerOverlay').classList.add('show');
    document.getElementById('detailDrawer').classList.add('show');
}

// 关闭抽屉
function closeDrawer() {
    document.getElementById('drawerOverlay').classList.remove('show');
    document.getElementById('detailDrawer').classList.remove('show');
}

// 查看子任务详情
async function viewChildTask(taskId) {
    try {
        const tree = await fetchTaskTree(taskId);
        if (tree && tree.root) {
            state.currentChildTask = tree.root;
            renderDrawerBody();
        }
    } catch (error) {
        showToast('加载子任务失败: ' + error.message, 'error');
    }
}

// 关闭子任务详情
function closeChildTaskDetail() {
    state.currentChildTask = null;
    renderDrawerBody();
}

// 翻页
async function changePage(page) {
    if (page < 1 || page > state.totalPages) return;
    state.currentPage = page;
    await loadTasks();
}

// 加载任务列表
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

// 加载统计
async function loadStats() {
    try {
        state.stats = await fetchStats();
        renderStats();
    } catch (error) {
        console.error('加载统计失败:', error);
    }
}

// 加载批次
async function loadBatches() {
    try {
        const result = await fetchBatches();
        state.batches = result.batches || [];
        renderBatchSelect();
    } catch (error) {
        console.error('加载批次失败:', error);
    }
}

// 应用筛选
async function applyFilters() {
    state.filters.status = document.getElementById('filterStatus')?.value || '';
    state.filters.priority = document.getElementById('filterPriority')?.value || '';
    state.filters.batchId = document.getElementById('filterBatch')?.value || '';
    state.filters.search = document.getElementById('filterSearch')?.value || '';
    state.currentPage = 1;
    console.log('Applying filters:', state.filters);
    await loadTasks();
}

// 预览导入
async function handlePreviewImport() {
    const startTime = document.getElementById('importStartTime')?.value;
    const endTime = document.getElementById('importEndTime')?.value;
    
    if (!startTime || !endTime) {
        showToast('请选择时间范围', 'warning');
        return;
    }
    
    try {
        const btn = document.getElementById('btnPreview');
        btn.disabled = true;
        btn.innerHTML = '<span class="loading dark"></span> 预览中...';
        
        const result = await previewExtraction(
            startTime.replace('T', ' ') + ':00',
            endTime.replace('T', ' ') + ':59'
        );
        
        showToast(`可导入: Trace ${result.trace_count || 0} 条, Node ${result.node_count || 0} 条`, 'success');
        
        document.getElementById('previewResult').innerHTML = `
            <div style="padding:12px; background:#F0F7FF; border-radius:6px; margin-top:12px; font-size:12px;">
                <strong>预览结果:</strong><br>
                Trace记录: ${result.trace_count || 0} 条<br>
                Node记录: ${result.node_count || 0} 条<br>
                预估总量: ${result.estimated_total || 0} 条
            </div>
        `;
    } catch (error) {
        showToast('预览失败: ' + error.message, 'error');
    } finally {
        const btn = document.getElementById('btnPreview');
        btn.disabled = false;
        btn.textContent = '预览';
    }
}

// 执行导入
async function handleExecuteImport() {
    const startTime = document.getElementById('importStartTime')?.value;
    const endTime = document.getElementById('importEndTime')?.value;
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
        
        // 刷新数据
        state.currentPage = 1;
        await Promise.all([loadTasks(), loadStats(), loadBatches()]);
        
    } catch (error) {
        showToast('导入失败: ' + error.message, 'error');
    } finally {
        const btn = document.getElementById('btnImport');
        btn.disabled = false;
        btn.textContent = '导入';
    }
}

// 提交标注
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
        annotation_notes: document.getElementById('annotationNotes')?.value || ''
    };
    
    if (!data.annotated_question || !data.annotated_answer) {
        showToast('请填写标注后的问题和答案', 'warning');
        return;
    }
    
    try {
        await submitAnnotation(data);
        showToast('标注提交成功', 'success');
        
        // 刷新数据
        await openTaskDetail(state.currentTask.task_id);
        await loadTasks();
        await loadStats();
        
    } catch (error) {
        showToast('提交失败: ' + error.message, 'error');
    }
}

// 审核标注
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
        
        // 刷新数据
        await openTaskDetail(state.currentTask.task_id);
        await loadTasks();
        await loadStats();
        
    } catch (error) {
        showToast('审核失败: ' + error.message, 'error');
    }
}

// 切换导入面板
function toggleImportPanel() {
    const panel = document.getElementById('importPanel');
    const icon = document.getElementById('importToggleIcon');
    panel.classList.toggle('collapsed');
    icon.textContent = panel.classList.contains('collapsed') ? '▶' : '▼';
}

// 切换用户角色
function switchRole(role) {
    state.currentUser.role = role;
    const labels = { annotator: '标注员', reviewer: '审核员', admin: '管理员' };
    document.getElementById('userRole').textContent = labels[role];
    showToast(`已切换为${labels[role]}角色`, 'info');
    
    // 刷新详情（如果有）
    if (state.currentTask) {
        renderDrawerBody();
    }
}

// 初始化ES索引
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
    
    // 创建resize代理元素
    resizeProxy = document.createElement('div');
    resizeProxy.className = 'resizing-proxy';
    resizeProxy.style.display = 'none';
    document.body.appendChild(resizeProxy);
    
    ths.forEach(th => {
        // 创建拖拽把手
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
            
            // 显示代理线
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
        
        // 更新代理线位置
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
    console.log('QA Annotation Platform initialized (Simple Style with Column Resize)');
    
    // 初始化侧边栏拖拽
    initSidebarResize();
    
    // 初始化表格列宽拖拽
    initTableColumnResize();
    
    // 设置默认时间范围
    const now = new Date();
    const hoursBefore = 3;
    const hoursAgo = new Date(now.getTime() - hoursBefore * 60 * 60 * 1000);
    
    const formatForInput = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    };
    
    const startInput = document.getElementById('importStartTime');
    const endInput = document.getElementById('importEndTime');
    if (startInput) startInput.value = formatForInput(hoursAgo);
    if (endInput) endInput.value = formatForInput(now);
    
    // 加载数据
    try {
        await Promise.all([
            loadTasks(),
            loadStats(),
            loadBatches()
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
