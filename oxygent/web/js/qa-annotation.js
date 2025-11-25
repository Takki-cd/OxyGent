// Q&A 标注系统 JavaScript - 表格式布局

class QAAnnotationSystem {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 100;
        this.totalItems = 100;
        this.selectedItems = new Set();
        this.data = [];
        
        this.init();
    }
    
    init() {
        this.generateDemoData();
        this.bindEvents();
        this.renderTable();
        this.updateSelectedCount();
    }
    
    generateDemoData() {
        // 生成与目标图片一致的demo数据
        this.data = [
            {
                id: 1,
                query: "商品如何上线",
                domain: "商品",
                domainEditable: true,
                importDate: "2025-11-21",
                questionCount: 672,
                status: "待分配",
                evaluationResult: null,
                issue: null,
                executor: null,
                selected: true
            },
            {
                id: 2,
                query: "商品如何修改主图",
                domain: "商品",
                domainEditable: true,
                importDate: "2025-11-21",
                questionCount: 42,
                status: "待测评",
                evaluationResult: "满意",
                issue: "表达异常",
                executor: "评测人：",
                selected: true
            },
            {
                id: 3,
                query: "如何设置限购",
                domain: "价格",
                domainEditable: true,
                importDate: "2025-11-21",
                questionCount: 981,
                status: "待标注",
                evaluationResult: "非常满意",
                issue: null,
                executor: 981,
                selected: false
            },
            {
                id: 4,
                query: "如何开启预售",
                domain: "促销",
                domainEditable: true,
                importDate: "2025-11-18",
                questionCount: 555,
                status: "待解决",
                evaluationResult: "不满意",
                issue: "内容异常",
                executor: 555,
                selected: false
            },
            {
                id: 5,
                query: "怎么审批预售",
                domain: "推广",
                domainEditable: true,
                importDate: "2025-11-17",
                questionCount: 123,
                status: "已完成",
                evaluationResult: "非常满意",
                issue: null,
                executor: 123,
                selected: false
            },
            {
                id: 6,
                query: "预约预售有什么区别",
                domain: "数据",
                domainEditable: true,
                importDate: "2025-11-16",
                questionCount: 789,
                status: "已过期",
                evaluationResult: null,
                issue: null,
                executor: 789,
                selected: false
            },
            {
                id: 7,
                query: "没库存能开预售么",
                domain: "供应商",
                domainEditable: true,
                importDate: "2025-11-15",
                questionCount: 321,
                status: "已完成",
                evaluationResult: "不满意",
                issue: "内容异常",
                executor: 321,
                selected: false
            },
            {
                id: 8,
                query: "预售需要先充值部分费用...",
                domain: "采购",
                domainEditable: true,
                importDate: "2025-11-14",
                questionCount: 999,
                status: "已完成",
                evaluationResult: "不满意",
                issue: "表达异常",
                executor: 999,
                selected: false
            },
            {
                id: 9,
                query: "预售商品必须有库存货...",
                domain: "推广",
                domainEditable: true,
                importDate: "2025-11-13",
                questionCount: 100,
                status: "已完成",
                evaluationResult: "非常满意",
                issue: null,
                executor: 100,
                selected: false
            },
            {
                id: 10,
                query: "预售期间无法可以吗?",
                domain: "价格",
                domainEditable: true,
                importDate: "2025-11-12",
                questionCount: 234,
                status: "已完成",
                evaluationResult: "非常满意",
                issue: null,
                executor: 234,
                selected: false
            }
        ];
    }
    
    bindEvents() {
        // 全选复选框
        document.getElementById('selectAll').addEventListener('change', (e) => {
            this.toggleSelectAll(e.target.checked);
        });
        
        // Tab切换
        document.querySelectorAll('.tab-item').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchTab(e.target);
            });
        });
    }
    
    renderTable() {
        const tbody = document.getElementById('dataTableBody');
        tbody.innerHTML = '';
        
        this.data.forEach(item => {
            const row = this.createTableRow(item);
            tbody.appendChild(row);
        });
    }
    
    createTableRow(item) {
        const tr = document.createElement('tr');
        
        tr.innerHTML = `
            <td>
                <input type="checkbox" ${item.selected ? 'checked' : ''} 
                       onchange="qaSystem.toggleItemSelection(${item.id}, this.checked)">
            </td>
            <td>${item.query}</td>
            <td>
                <span class="domain-tag">${item.domain}</span>
                ${item.domainEditable ? '<span class="edit-icon">✏️</span>' : ''}
            </td>
            <td>${item.importDate}</td>
            <td>${item.questionCount}</td>
            <td>
                <span class="status-tag ${this.getStatusClass(item.status)}">${item.status}</span>
            </td>
            <td>
                ${item.evaluationResult ? this.renderEvaluationResult(item.evaluationResult) : '–'}
            </td>
            <td>
                ${item.issue ? item.issue : '–'}
            </td>
            <td>
                ${item.executor ? item.executor : '–'}
            </td>
            <td>
                <a href="#" class="action-link">分配</a>
                <a href="#" class="action-link">详测</a>
                <a href="#" class="action-link">删除</a>
            </td>
        `;
        
        return tr;
    }
    
    getStatusClass(status) {
        const statusMap = {
            '待分配': 'status-pending',
            '待测评': 'status-evaluating', 
            '待标注': 'status-annotating',
            '待解决': 'status-solving',
            '已完成': 'status-completed',
            '已过期': 'status-expired'
        };
        return statusMap[status] || 'status-pending';
    }
    
    renderEvaluationResult(result) {
        const resultMap = {
            '满意': { class: 'result-satisfied', icon: '😊' },
            '不满意': { class: 'result-unsatisfied', icon: '😞' },
            '非常满意': { class: 'result-very-satisfied', icon: '😊' }
        };
        
        const config = resultMap[result];
        if (!config) return result;
        
        return `
            <div class="result-tag ${config.class}">
                <span class="result-icon"></span>
                ${result}
            </div>
        `;
    }
    
    toggleSelectAll(checked) {
        this.data.forEach(item => {
            item.selected = checked;
            if (checked) {
                this.selectedItems.add(item.id);
            } else {
                this.selectedItems.delete(item.id);
            }
        });
        
        this.renderTable();
        this.updateSelectedCount();
    }
    
    toggleItemSelection(id, checked) {
        const item = this.data.find(d => d.id === id);
        if (item) {
            item.selected = checked;
            if (checked) {
                this.selectedItems.add(id);
            } else {
                this.selectedItems.delete(id);
            }
        }
        
        // 更新全选状态
        const allSelected = this.data.every(item => item.selected);
        const noneSelected = this.data.every(item => !item.selected);
        const selectAllCheckbox = document.getElementById('selectAll');
        
        if (allSelected) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else if (noneSelected) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        }
        
        this.updateSelectedCount();
    }
    
    updateSelectedCount() {
        const count = this.selectedItems.size;
        document.querySelector('.selected-count').textContent = `已选 ${count} 条`;
    }
    
    switchTab(tabElement) {
        // 移除所有active类
        document.querySelectorAll('.tab-item').forEach(tab => {
            tab.classList.remove('active');
        });
        
        // 添加active类到当前tab
        tabElement.classList.add('active');
        
        // 这里可以根据不同tab加载不同数据
        console.log('切换到:', tabElement.textContent);
    }
}

// 全局函数
function searchData() {
    console.log('执行查询');
    // 这里可以添加查询逻辑
}

function resetFilters() {
    console.log('重置过滤器');
    // 重置所有过滤器
    document.getElementById('businessDomain').value = '';
    document.getElementById('abnormalIssue').value = '';
    document.getElementById('executor').value = '';
    document.getElementById('evaluationResult').value = '';
}

function goToPage(direction) {
    if (direction === 'prev' && qaSystem.currentPage > 1) {
        qaSystem.currentPage--;
    } else if (direction === 'next') {
        qaSystem.currentPage++;
    }
    
    console.log('跳转到页面:', qaSystem.currentPage);
    // 这里可以添加分页逻辑
}

// 批量操作函数
function batchImport() {
    console.log('批量导入');
}

function batchAssign() {
    console.log('批量分配');
}

function batchSolve() {
    console.log('批量解决');
}

function batchEditDomain() {
    console.log('批量编辑业务域');
}

function batchDelete() {
    const selectedCount = qaSystem.selectedItems.size;
    if (selectedCount === 0) {
        alert('请先选择要删除的项目');
        return;
    }
    
    if (confirm(`确定要删除选中的 ${selectedCount} 个项目吗？`)) {
        console.log('批量删除', Array.from(qaSystem.selectedItems));
        // 这里添加删除逻辑
    }
}

function downloadTemplate() {
    console.log('下载模板');
}

function batchExport() {
    console.log('批量导出');
}

// 初始化系统
let qaSystem;
document.addEventListener('DOMContentLoaded', () => {
    qaSystem = new QAAnnotationSystem();
    
    // 绑定批量操作按钮
    const batchButtons = document.querySelectorAll('.btn-batch');
    batchButtons.forEach((btn, index) => {
        const actions = [batchImport, batchAssign, batchSolve, batchEditDomain, batchDelete];
        if (actions[index]) {
            btn.addEventListener('click', actions[index]);
        }
    });
    
    // 绑定导出按钮
    const exportButtons = document.querySelectorAll('.btn-export');
    exportButtons.forEach((btn, index) => {
        const actions = [downloadTemplate, batchExport];
        if (actions[index]) {
            btn.addEventListener('click', actions[index]);
        }
    });
});

console.log('Q&A标注系统已加载');