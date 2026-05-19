// 全局变量
let currentData = [];
const API_BASE_URL = 'http://localhost:8000'; // FastAPI服务地址
const ITEMS_PER_PAGE = 20; // 每页显示的商品数量
let currentPage = 1; // 当前页码
let datePickerInstance;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeDatePicker();
    loadCategories();
    bindEvents();
    setDefaultDate();
});

async function loadCategories() {
    const categorySelect = document.getElementById('category-select');

    try {
        const response = await fetch(`${API_BASE_URL}/api/categories`);
        if (!response.ok) throw new Error('无法获取品类列表');

        const categories = await response.json();

        // 清空并填充下拉框
        categorySelect.innerHTML = '<option value="">-- 请选择品类 --</option>';

        categories.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat;
            option.textContent = cat;
            categorySelect.appendChild(option);
        });
    } catch (error) {
        console.error('加载品类失败:', error);
        categorySelect.innerHTML = '<option value="">加载失败，请重试</option>';
        showMessage('品类列表加载失败', 'error');
    }
}

// 初始化日期选择器
function initializeDatePicker() {
    datePickerInstance = flatpickr("#date-picker", {
        dateFormat: "Y-m-d",
        locale: "zh", // 需要引入中文语言包或手动配置
        disable: [function() { return true; }], // 初始状态禁用所有日期
        onChange: function(selectedDates, dateStr) {
            // 选择日期后可自动触发查询
            searchData();
        }
    });
    const datePicker = document.getElementById('date-picker');
    // 设置默认日期为今天
    const today = new Date();
    const formattedDate = today.toISOString().split('T')[0];
    datePicker.value = formattedDate;
    datePicker.max = formattedDate;
}

// 设置默认日期为昨天（如果有历史数据的话）
function setDefaultDate() {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const formattedYesterday = yesterday.toISOString().split('T')[0];
    document.getElementById('date-picker').value = formattedYesterday;
}

// 绑定事件监听器
function bindEvents() {
    const categorySelect = document.getElementById('category-select');

    categorySelect.addEventListener('change', async function() {
        const category = this.value;
        if (!category) {
            datePickerInstance.set('disable', [function() { return true; }]); // 清空品类则禁用日期
            return;
        }

        // 1. 从后端获取该品类可选的日期
        try {
            const response = await fetch(`${API_BASE_URL}/api/available-dates?category=${encodeURIComponent(category)}`);
            const availableDates = await response.json();

            if (availableDates.length > 0) {
                // 2. 更新日期插件：只允许点击存在数据的日期
                datePickerInstance.set('disable', [
                function(date) {
                    // 【修改点】：使用本地年-月-日格式，避免时区导致的日期减一
                    const year = date.getFullYear();
                    const month = String(date.getMonth() + 1).padStart(2, '0');
                    const day = String(date.getDate()).padStart(2, '0');
                    const dateStr = `${year}-${month}-${day}`;

                    return !availableDates.includes(dateStr);
                }
            ]);
                showMessage(`品类【${category}】共有 ${availableDates.length} 天的数据记录`, 'success');
            } else {
                datePickerInstance.set('disable', [function() { return true; }]);
                showMessage('该品类暂无采集记录', 'warning');
            }
        } catch (error) {
            console.error('获取日期失败:', error);
        }
    });

    document.getElementById('search-btn').addEventListener('click', searchData);
    document.getElementById('export-btn').addEventListener('click', exportData);
}

// 查询数据函数
async function searchData() {
    const date = document.getElementById('date-picker').value;
    // 修改：改为从 select 元素获取值
    const category = document.getElementById('category-select').value;

    if (!date) {
        showMessage('请选择采集日期', 'error');
        return;
    }

    if (!category) {
        showMessage('请从下拉框选择品类', 'warning');
        return;
    }

    // 显示加载状态
    showLoading(true);
    hideNoData();

    try {
        const url = `${API_BASE_URL}/api/analysis/top-goods?date=${encodeURIComponent(date)}&keyword=${encodeURIComponent(category)}`;

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        if (result.data && result.data.length > 0) {
            currentData = result.data;
            displayResults(result);
            enableExportButton();
            showMessage(`成功获取 ${result.count} 条数据`, 'success');
        } else {
            showNoData();
            disableExportButton();
            showMessage('未查询到相关数据', 'warning');
        }

    } catch (error) {
        console.error('查询数据失败:', error);
        showNoData();
        disableExportButton();
        showMessage('数据查询失败，请检查服务是否正常运行', 'error');
    } finally {
        showLoading(false);
    }
}

// 显示查询结果
function displayResults(result) {
    // 重置页码
    currentPage = 1;

    // 显示数据表格（第一页）
    displayDataTable(result.data);

    // 显示分页控件
    displayPagination(result.data.length);

    // 显示结果区域
    document.getElementById('results-section').style.display = 'block';
}

// 显示数据表格
function displayDataTable(data) {
    const tableBody = document.getElementById('table-body');
    tableBody.innerHTML = '';

    // 计算当前页的起始和结束索引
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = Math.min(startIndex + ITEMS_PER_PAGE, data.length);

    // 获取当前页的数据
    const pageData = data.slice(startIndex, endIndex);

    pageData.forEach((item, index) => {
        const globalIndex = startIndex + index; // 全局索引（用于显示正确的排名）
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${globalIndex + 1}</td>
            <td>${item.item_id || '-'}</td>
            <td class="description-cell">${item.description || '-'}</td>
            <td>¥${parseFloat(item.price || 0).toFixed(2)}</td>
            <td>${parseInt(item.want_count || 0).toLocaleString()}</td>
            <td>${parseInt(item.view_count || 0).toLocaleString()}</td>
            <td>${(parseFloat(item.cr || 0) * 100).toFixed(2)}%</td>
            <td class="hotness-score">${parseFloat(item.hotness_score || 0).toFixed(2)}</td>
            <td>
                <a href="${item.item_url}" target="_blank" class="link-btn">🔗 查看</a>
                <button onclick="addToFavorite('${item.item_id}')" class="link-btn" style="background:#e67e22; margin-left:5px">⭐ 收藏</button>
            </td>
    `;
        tableBody.appendChild(row);
    });

    // 更新分页信息显示
    updatePaginationInfo(data.length);
}

// 导出数据功能
function exportData() {
    if (!currentData || currentData.length === 0) {
        showMessage('没有可导出的数据', 'warning');
        return;
    }

    // 创建CSV内容
    const headers = ['排名', '商品ID', '商品描述', '价格', '想要人数', '浏览量', '转化率', '热度评分'];
    const csvContent = [
        headers.join(','),
        ...currentData.map((item, index) => [
            index + 1,
            item.item_id || '',
            `"${item.description || ''}"`,
            item.price || 0,
            item.want_count || 0,
            item.view_count || 0,
            `${(parseFloat(item.cr || 0) * 100).toFixed(2)}%`,
            parseFloat(item.hotness_score || 0).toFixed(2)
        ].join(','))
    ].join('\n');

    // 创建下载链接
    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `商品热度分析_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showMessage('数据导出成功', 'success');
}

// 显示/隐藏加载状态
function showLoading(show) {
    const loadingElement = document.getElementById('loading');
    loadingElement.style.display = show ? 'flex' : 'none';
}

// 显示无数据提示
function showNoData() {
    document.getElementById('results-section').style.display = 'none';
    document.getElementById('no-data').style.display = 'block';
}

// 隐藏无数据提示
function hideNoData() {
    document.getElementById('no-data').style.display = 'none';
}

// 启用导出按钮
function enableExportButton() {
    const exportBtn = document.getElementById('export-btn');
    exportBtn.disabled = false;
    exportBtn.classList.remove('disabled');
}

// 禁用导出按钮
function disableExportButton() {
    const exportBtn = document.getElementById('export-btn');
    exportBtn.disabled = true;
    exportBtn.classList.add('disabled');
}

// 显示消息提示
function showMessage(message, type = 'info') {
    // 创建消息元素
    const messageEl = document.createElement('div');
    messageEl.className = `message message-${type}`;
    messageEl.textContent = message;

    // 添加到页面
    document.body.appendChild(messageEl);

    // 3秒后自动移除
    setTimeout(() => {
        if (messageEl.parentNode) {
            messageEl.parentNode.removeChild(messageEl);
        }
    }, 3000);
}


// 显示分页控件
function displayPagination(totalItems) {
    const paginationContainer = document.getElementById('pagination-container');
    if (!paginationContainer) {
        createPaginationContainer();
    }

    updatePaginationControls(totalItems);
}

// 创建分页容器
function createPaginationContainer() {
    const resultsSection = document.getElementById('results-section');
    const paginationDiv = document.createElement('div');
    paginationDiv.id = 'pagination-container';
    paginationDiv.className = 'pagination-controls';
    paginationDiv.innerHTML = `
        <div class="pagination-info">
            <span id="page-info">显示第 1-30 条，共 0 条记录</span>
        </div>
        <div class="pagination-buttons">
            <button id="first-page" class="page-btn" onclick="goToPage(1)">首页</button>
            <button id="prev-page" class="page-btn" onclick="goToPage(currentPage - 1)">上一页</button>
            <span id="page-numbers"></span>
            <button id="next-page" class="page-btn" onclick="goToPage(currentPage + 1)">下一页</button>
            <button id="last-page" class="page-btn" onclick="goToPage(getTotalPages())">末页</button>
        </div>
        <div class="pagination-jump">
            <span>跳转到：</span>
            <input type="number" id="page-input" min="1" max="1" value="1">
            <button onclick="jumpToPage()">确定</button>
        </div>
    `;
    resultsSection.appendChild(paginationDiv);
}

// 更新分页控件
function updatePaginationControls(totalItems) {
    const totalPages = getTotalPages(totalItems);

    // 更新页码输入框的最大值
    const pageInput = document.getElementById('page-input');
    if (pageInput) {
        pageInput.max = totalPages;
    }

    // 更新按钮状态
    updateButtonStates(totalPages);

    // 更新页码数字显示
    updatePageNumbers(totalPages);
}

// 获取总页数
function getTotalPages(totalItems = currentData.length) {
    return Math.ceil(totalItems / ITEMS_PER_PAGE);
}

// 更新按钮状态
function updateButtonStates(totalPages) {
    const firstBtn = document.getElementById('first-page');
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');
    const lastBtn = document.getElementById('last-page');

    // 首页和上一页按钮
    if (currentPage <= 1) {
        firstBtn.disabled = true;
        prevBtn.disabled = true;
        firstBtn.classList.add('disabled');
        prevBtn.classList.add('disabled');
    } else {
        firstBtn.disabled = false;
        prevBtn.disabled = false;
        firstBtn.classList.remove('disabled');
        prevBtn.classList.remove('disabled');
    }

    // 下一页和末页按钮
    if (currentPage >= totalPages) {
        nextBtn.disabled = true;
        lastBtn.disabled = true;
        nextBtn.classList.add('disabled');
        lastBtn.classList.add('disabled');
    } else {
        nextBtn.disabled = false;
        lastBtn.disabled = false;
        nextBtn.classList.remove('disabled');
        lastBtn.classList.remove('disabled');
    }
}

// 更新页码数字显示
function updatePageNumbers(totalPages) {
    const pageNumbersContainer = document.getElementById('page-numbers');
    if (!pageNumbersContainer) return;

    pageNumbersContainer.innerHTML = '';

    // 计算要显示的页码范围
    let startPage, endPage;
    if (totalPages <= 7) {
        // 总页数较少时显示所有页码
        startPage = 1;
        endPage = totalPages;
    } else {
        // 总页数较多时显示部分页码
        if (currentPage <= 4) {
            startPage = 1;
            endPage = 7;
        } else if (currentPage >= totalPages - 3) {
            startPage = totalPages - 6;
            endPage = totalPages;
        } else {
            startPage = currentPage - 3;
            endPage = currentPage + 3;
        }
    }

    // 生成页码按钮
    for (let i = startPage; i <= endPage; i++) {
        const pageBtn = document.createElement('button');
        pageBtn.className = `page-number-btn ${i === currentPage ? 'active' : ''}`;
        pageBtn.textContent = i;
        pageBtn.onclick = () => goToPage(i);
        pageNumbersContainer.appendChild(pageBtn);
    }
}

// 跳转到指定页
function goToPage(page) {
    const totalPages = getTotalPages();

    // 验证页码
    if (page < 1 || page > totalPages || page === currentPage) {
        return;
    }

    currentPage = page;
    displayDataTable(currentData);
    updatePaginationControls(currentData.length);

    // --- 修改此处：滚动到表格容器 ---
    const tableContainer = document.querySelector('.table-container');
    if (tableContainer) {
        tableContainer.scrollIntoView({
            behavior: 'smooth',
            block: 'start' // 将元素的顶部与可视区域的顶部对齐
        });
    }
}

// 跳转到指定页码（通过输入框）
function jumpToPage() {
    const pageInput = document.getElementById('page-input');
    const page = parseInt(pageInput.value);

    if (page && page >= 1) {
        goToPage(page);
    } else {
        showMessage('请输入有效的页码', 'warning');
    }
}

// 更新分页信息显示
function updatePaginationInfo(totalItems) {
    const pageInfo = document.getElementById('page-info');
    if (!pageInfo) return;

    const totalPages = getTotalPages(totalItems);
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE + 1;
    const endIndex = Math.min(currentPage * ITEMS_PER_PAGE, totalItems);

    pageInfo.textContent = `显示第 ${startIndex}-${endIndex} 条，共 ${totalItems} 条记录`;
}

// 2. 添加收藏
async function addToFavorite(itemId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/favorites/add?item_id=${itemId}`, { method: 'POST' });
        if (response.ok) {
            showMessage('已加入收藏夹', 'success');
        }
    } catch (error) {
        showMessage('收藏失败', 'error');
    }
}

// 3. 加载收藏页列表
async function loadFavorites() {
    const tbody = document.getElementById('favorites-body');
    if (!tbody) return;

    try {
        const response = await fetch(`${API_BASE_URL}/api/favorites`);
        const data = await response.json();

        tbody.innerHTML = '';
        data.forEach(item => {
            const row = document.createElement('tr');

            // 检查货源链接是否存在且有效
            const hasSourceUrl = item.source_url && item.source_url.startsWith('http');
            const sourceLinkHtml = hasSourceUrl
                ? `<a href="${item.source_url}" target="_blank" class="link-btn" style="background: #27ae60; margin-bottom: 5px; display: block; text-align: center;">🛒 货源链接</a>`
                :'';
        // 优先显示 AI 生成的标题，如果没有则显示原描述
        const displayTitle = item.ai_generated_title && item.ai_generated_title !== '-'
            ? item.ai_generated_title
            : (item.description || '-');

        row.innerHTML = `
            <td>
                <div title="双击上架商品" 
                     ondblclick="runShelvingTask('${item.item_id}')" 
                     style="font-weight: bold; margin-bottom: 5px; cursor: pointer; color: #2980b9;">
                     ${item.item_id}
                </div>
                <div style="font-size: 13px; color: #666; max-height: 60px; overflow-y: auto;">${displayTitle}</div>
            </td>
            <td>¥${parseFloat(item.price || 0).toFixed(2)}</td>
            <td>${item.want_count || 0}</td>
            <td>
                <input type="text" id="url-${item.item_id}" value="${item.source_url || ''}" placeholder="粘贴 1688/PDD 链接" 
                       style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px;">
            </td>
            <td>
                <select id="status-${item.item_id}" style="padding: 5px; border-radius: 4px;">
                    <option value="0" ${item.status === 0 ? 'selected' : ''}>未上架</option>
                    <option value="1" ${item.status === 1 ? 'selected' : ''}>已上架</option>
                </select>
            </td>
            <td>
                <textarea id="remark-${item.item_id}" style="width: 100%; height: 60px; padding: 5px;">${item.remark || ''}</textarea>
            </td>
            <td style="min-width: 120px;">
                <a href="${item.item_url}" target="_blank" class="link-btn" style="margin-bottom: 5px; display: block; text-align: center;">🔗 闲鱼链接</a>
                
                ${sourceLinkHtml}
                
                <hr style="margin: 5px 0; border: 0; border-top: 1px solid #eee;">
                <div style="display: flex; gap: 5px;">
                    <button onclick="saveFavorite('${item.item_id}')" class="link-btn" style="flex: 1;">💾 保存</button>
                    <button onclick="deleteFavorite('${item.item_id}')" class="link-btn" style="background:#c0392b; flex: 0.5;">🗑️</button>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
} catch (error) {
    console.error('加载收藏失败', error);
}
}

// 4. 保存修改（状态、货源链接）
async function saveFavorite(itemId) {
    const status = document.getElementById(`status-${itemId}`).value;
    const sourceUrl = document.getElementById(`url-${itemId}`).value;
    const remark = document.getElementById(`remark-${itemId}`).value;

    try {
        const response = await fetch(`${API_BASE_URL}/api/favorites/update`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                item_id: itemId,
                status: parseInt(status),
                source_url: sourceUrl,
                remark: remark
            })
        });
        if (response.ok) {
            showMessage('保存成功', 'success');
            loadFavorites(); // 刷新列表以更新跳转链接
        }
    } catch (error) {
        showMessage('保存失败', 'error');
    }
}

// 5. 删除收藏
async function deleteFavorite(itemId) {
    if (!confirm('确定取消收藏吗？')) return;
    try {
        await fetch(`${API_BASE_URL}/api/favorites/${itemId}`, { method: 'DELETE' });
        loadFavorites();
    } catch (error) {
        showMessage('删除失败', 'error');
    }
}

// 自动化上架触发函数
async function runShelvingTask(itemId) {
    // 1. 弹出确认框（可选，防止误触）
    if (!confirm(`确定要启动商品 ${itemId} 的自动化上架任务吗？\n请确保本地 Chrome 已开启调试模式。`)) return;

    // 2. 显示提示
    showMessage(`正在启动上架程序: ${itemId}...`, 'info');

    try {
        const response = await fetch(`${API_BASE_URL}/api/favorites/shelve/${itemId}`, {
            method: 'POST'
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(`✅ 任务已提交：后台正在操作上架`, 'success');
        } else {
            showMessage(`❌ 启动失败: ${result.detail}`, 'error');
        }
    } catch (error) {
        console.error('上架请求失败:', error);
        showMessage('无法连接到后台服务', 'error');
    }
}