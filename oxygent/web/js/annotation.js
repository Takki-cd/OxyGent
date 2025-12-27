/**
 * QA标注平台 - 前端逻辑
 */

// ============================================================================
// 全局状态
// ============================================================================
const state = {
    // 用户信息
    currentUser: {
        id: 'user_001',
        name: '标注员',
        role: 'annotator'  // annotator / reviewer / admin
    },
    
    // 任务列表
    tasks: [],
    totalTasks: 0,
    currentPage: 1,
    pageSize: 20,
    
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
        approved: 0,
        rejected: 0
    },
    
    // 批次列表
    batches: [],
    
    // 已导入的hash缓存（用于前端去重提示）
    importedHashes: new Set()
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

function truncate(str, len = 100) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
}

function getPriorityLabel(priority) {
    const labels = { 0: 'P0-E2E', 1: 'P1-User', 2: 'P2-Agent', 3: 'P3-Tool' };
    return labels[priority] || `P${priority}`;
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

function getSourceTypeLabel(sourceType) {
    const labels = {
        'e2e': '端到端',
        'user_agent': '用户→Agent',
        'agent_agent': 'Agent→Agent',
        'agent_tool': 'Agent→Tool'
    };
    return labels[sourceType] || sourceType;
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

// 预览导入
async function previewExtraction(startTime, endTime) {
    return apiRequest('/extract/preview', {
        method: 'POST',
        body: JSON.stringify({ start_time: startTime, end_time: endTime })
    });
}

// 执行导入
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

// 获取任务树形列表
async function fetchTasksTree(page = 1, pageSize = 20, filters = {}) {
    const params = new URLSearchParams({
        page,
        page_size: pageSize
    });
    if (filters.status) params.append('status', filters.status);
    if (filters.priority !== '' && filters.priority !== undefined) params.append('priority', filters.priority);
    if (filters.batchId) params.append('batch_id', filters.batchId);
    if (filters.search) params.append('search', filters.search);
    
    return apiRequest(`/tasks/tree?${params}`);
}

// 获取任务列表
async function fetchTasks(page = 1, pageSize = 20, filters = {}) {
    const params = new URLSearchParams({
        page,
        page_size: pageSize,
        only_root: 'true'
    });
    if (filters.status) params.append('status', filters.status);
    if (filters.priority !== '') params.append('priority', filters.priority);
    if (filters.sourceType) params.append('source_type', filters.sourceType);
    if (filters.batchId) params.append('batch_id', filters.batchId);
    if (filters.search) params.append('search', filters.search);
    
    return apiRequest(`/tasks?${params}`);
}

// 获取任务详情（含树形结构）
async function fetchTaskTree(taskId) {
    return apiRequest(`/tasks/${taskId}/tree`);
}

// 获取统计
async function fetchStats() {
    return apiRequest('/stats');
}

// 获取批次列表
async function fetchBatches() {
    return apiRequest('/batches');
}

// 分配任务
async function assignTask(taskId, assignedTo) {
    return apiRequest('/tasks/assign', {
        method: 'POST',
        body: JSON.stringify({ task_id: taskId, assigned_to: assignedTo })
    });
}

// 提交标注
async function submitAnnotation(data) {
    return apiRequest('/annotations/submit', {
        method: 'POST',
        body: JSON.stringify(data)
    });
}

// 获取任务的标注
async function fetchAnnotationByTask(taskId) {
    try {
        return await apiRequest(`/annotations/by-task/${taskId}`);
    } catch {
        return null;
    }
}

// 审核标注
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

// 初始化索引
async function initIndices() {
    return apiRequest('/admin/init-indices', { method: 'POST' });
}

// ============================================================================
// UI渲染
// ============================================================================

// 渲染统计面板
function renderStats() {
    const panel = document.getElementById('statsPanel');
    if (!panel) return;
    
    const { stats } = state;
    panel.innerHTML = `
        <div class="stat-item">
            <span class="stat-value">${stats.total || 0}</span>
            <span class="stat-label">总任务</span>
        </div>
        <div class="stat-item">
            <span class="stat-value">${stats.by_status?.pending || 0}</span>
            <span class="stat-label">待标注</span>
        </div>
        <div class="stat-item">
            <span class="stat-value">${stats.by_status?.annotated || 0}</span>
            <span class="stat-label">已标注</span>
        </div>
        <div class="stat-item">
            <span class="stat-value">${stats.by_status?.approved || 0}</span>
            <span class="stat-label">已通过</span>
        </div>
        <div class="stat-item">
            <span class="stat-value">${stats.root_count || 0}</span>
            <span class="stat-label">E2E任务</span>
        </div>
    `;
}

// 渲染批次下拉
function renderBatchSelect() {
    const select = document.getElementById('filterBatch');
    if (!select) return;
    
    select.innerHTML = '<option value="">全部批次</option>' +
        state.batches.map(b => `<option value="${b.batch_id}">${b.batch_id.substring(0, 8)}... (${b.count}条)</option>`).join('');
}

// 渲染任务列表
function renderTaskList() {
    const container = document.getElementById('taskList');
    if (!container) return;
    
    if (state.tasks.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <img src="./image/empty.svg" alt="">
                <p>暂无任务数据</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = state.tasks.map(task => `
        <div class="task-item ${task.source_type === 'e2e' ? 'e2e' : 'sub-task'} ${state.currentTask?.task_id === task.task_id ? 'active' : ''}"
             onclick="selectTask('${task.task_id}')">
            <div class="task-header">
                <span class="task-priority p${task.priority}">${getPriorityLabel(task.priority)}</span>
                <span class="task-status ${task.status}">${getStatusLabel(task.status)}</span>
            </div>
            <div class="task-question">${truncate(task.question, 80)}</div>
            <div class="task-meta">
                <span>${getSourceTypeLabel(task.source_type)}</span>
                <span>${formatDate(task.created_at)}</span>
                ${task.children_count > 0 ? `<span class="task-children-badge">${task.children_count}个子任务</span>` : ''}
            </div>
        </div>
    `).join('');
}

// 渲染分页
function renderPagination() {
    const info = document.getElementById('paginationInfo');
    const btns = document.getElementById('paginationBtns');
    if (!info || !btns) return;
    
    const totalPages = Math.ceil(state.totalTasks / state.pageSize);
    info.textContent = `第 ${state.currentPage}/${totalPages || 1} 页，共 ${state.totalTasks} 条`;
    
    btns.innerHTML = `
        <button class="pagination-btn" onclick="changePage(${state.currentPage - 1})" ${state.currentPage <= 1 ? 'disabled' : ''}>上一页</button>
        <button class="pagination-btn" onclick="changePage(${state.currentPage + 1})" ${state.currentPage >= totalPages ? 'disabled' : ''}>下一页</button>
    `;
}

// 渲染任务详情
function renderTaskDetail() {
    const container = document.getElementById('taskDetail');
    if (!container) return;
    
    if (!state.currentTask) {
        container.innerHTML = `
            <div class="task-detail-empty">
                <img src="./image/empty.svg" alt="">
                <p>请从左侧选择一个任务</p>
            </div>
        `;
        return;
    }
    
    const task = state.currentTask;
    const tree = state.currentTaskTree;
    const isReviewer = state.currentUser.role === 'reviewer' || state.currentUser.role === 'admin';
    
    container.innerHTML = `
        <!-- 任务信息 -->
        <div class="qa-section">
            <div class="qa-label">
                <span>📋 任务信息</span>
                <span class="task-status ${task.status}">${getStatusLabel(task.status)}</span>
            </div>
            <div style="display:flex; gap:16px; font-size:12px; color:#666; margin-top:8px;">
                <span>ID: ${task.task_id.substring(0, 8)}...</span>
                <span>来源: ${getSourceTypeLabel(task.source_type)}</span>
                <span>优先级: ${getPriorityLabel(task.priority)}</span>
                <span>创建: ${formatDate(task.created_at)}</span>
            </div>
        </div>
        
        <!-- 原始问题 -->
        <div class="qa-section">
            <div class="qa-label">❓ 原始问题</div>
            <div class="qa-content">${task.question || '(无)'}</div>
        </div>
        
        <!-- 原始答案 -->
        <div class="qa-section">
            <div class="qa-label">💬 原始答案</div>
            <div class="qa-content">${task.answer || '(无)'}</div>
        </div>
        
        <!-- 标注表单 -->
        <div class="annotation-form" id="annotationForm">
            <div class="form-title">✏️ 标注信息</div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>标注后问题</label>
                    <textarea id="annotatedQuestion" rows="3">${task.question || ''}</textarea>
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>标注后答案</label>
                    <textarea id="annotatedAnswer" rows="5">${task.answer || ''}</textarea>
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
            
            <div style="display:flex; gap:12px; margin-top:20px;">
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
                <div class="tree-title">🌳 关联子任务 (${tree.children.length})</div>
                ${tree.children.map(child => `
                    <div class="tree-item" onclick="selectTask('${child.task_id}')">
                        <div class="tree-item-left">
                            <span class="tree-item-type ${child.source_type}">${getSourceTypeLabel(child.source_type)}</span>
                            <span class="tree-item-question">${truncate(child.question, 50)}</span>
                        </div>
                        <span class="task-status ${child.status}">${getStatusLabel(child.status)}</span>
                    </div>
                `).join('')}
            </div>
        ` : ''}
    `;
}

// ============================================================================
// 事件处理
// ============================================================================

// 选择任务
async function selectTask(taskId) {
    try {
        const tree = await fetchTaskTree(taskId);
        state.currentTask = tree.root;
        state.currentTaskTree = tree;
        
        // 尝试加载已有标注
        const annotation = await fetchAnnotationByTask(taskId);
        if (annotation) {
            // 填充已有标注数据
            setTimeout(() => {
                const form = document.getElementById('annotationForm');
                if (form && annotation) {
                    const q = document.getElementById('annotatedQuestion');
                    const a = document.getElementById('annotatedAnswer');
                    if (q) q.value = annotation.annotated_question || '';
                    if (a) a.value = annotation.annotated_answer || '';
                    // ... 其他字段
                }
            }, 100);
        }
        
        renderTaskList();
        renderTaskDetail();
    } catch (error) {
        showToast('加载任务失败: ' + error.message, 'error');
    }
}

// 切换页码
async function changePage(page) {
    if (page < 1) return;
    state.currentPage = page;
    await loadTasks();
}

// 加载任务列表
async function loadTasks() {
    try {
        const result = await fetchTasksTree(state.currentPage, state.pageSize, state.filters);
        state.tasks = result.tasks || [];
        state.totalTasks = result.total || 0;
        renderTaskList();
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

// 应用过滤
function applyFilters() {
    state.filters.status = document.getElementById('filterStatus')?.value || '';
    state.filters.priority = document.getElementById('filterPriority')?.value || '';
    state.filters.batchId = document.getElementById('filterBatch')?.value || '';
    state.filters.search = document.getElementById('filterSearch')?.value || '';
    state.currentPage = 1;
    loadTasks();
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
        btn.innerHTML = '<span class="loading"></span> 预览中...';
        
        const result = await previewExtraction(
            startTime.replace('T', ' ') + ':00',
            endTime.replace('T', ' ') + ':59'
        );
        
        showToast(`可导入: Trace ${result.trace_count || 0} 条, Node ${result.node_count || 0} 条`, 'success');
        
        document.getElementById('previewResult').innerHTML = `
            <div style="padding:12px; background:#F0F7FF; border-radius:6px; margin-top:12px;">
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
        await Promise.all([loadTasks(), loadStats(), loadBatches()]);
        
    } catch (error) {
        showToast('导入失败: ' + error.message, 'error');
    } finally {
        const btn = document.getElementById('btnImport');
        btn.disabled = false;
        btn.textContent = '执行导入';
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
        
        // 刷新当前任务
        await selectTask(state.currentTask.task_id);
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
        // 先获取标注ID
        const annotation = await fetchAnnotationByTask(state.currentTask.task_id);
        if (!annotation) {
            showToast('未找到标注记录', 'error');
            return;
        }
        
        await reviewAnnotation(annotation.annotation_id, state.currentUser.id, status, comment || '');
        showToast(status === 'approved' ? '审核通过' : '已拒绝', 'success');
        
        await selectTask(state.currentTask.task_id);
        await loadStats();
        
    } catch (error) {
        showToast('审核失败: ' + error.message, 'error');
    }
}

// 切换导入面板
function toggleImportPanel() {
    const panel = document.getElementById('importPanel');
    panel.classList.toggle('collapsed');
}

// 切换用户角色（演示用）
function switchRole(role) {
    state.currentUser.role = role;
    const labels = { annotator: '标注员', reviewer: '审核员', admin: '管理员' };
    state.currentUser.name = labels[role];
    
    document.getElementById('userRole').textContent = labels[role];
    document.getElementById('userName').textContent = labels[role];
    
    renderTaskDetail();
    showToast(`已切换为${labels[role]}角色`, 'info');
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
// 初始化
// ============================================================================
document.addEventListener('DOMContentLoaded', async () => {
    console.log('QA Annotation Platform initialized');
    
    // 设置默认时间范围（最近7天）
    const now = new Date();
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    
    const startInput = document.getElementById('importStartTime');
    const endInput = document.getElementById('importEndTime');
    if (startInput) startInput.value = weekAgo.toISOString().slice(0, 16);
    if (endInput) endInput.value = now.toISOString().slice(0, 16);
    
    // 绑定过滤器事件
    document.getElementById('filterStatus')?.addEventListener('change', applyFilters);
    document.getElementById('filterPriority')?.addEventListener('change', applyFilters);
    document.getElementById('filterBatch')?.addEventListener('change', applyFilters);
    document.getElementById('filterSearch')?.addEventListener('input', debounce(applyFilters, 500));
    
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
    
    renderTaskDetail();
});

// 防抖函数
function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

