# 缓存清理问题修复方案

## 问题根源分析

### 1. 缓存机制概述
系统存在两级缓存：
- **后端缓存**：`app.py` 中的 `analysis_cache` 全局变量
- **前端缓存**：浏览器 `localStorage` 中的 `analysisData`

### 2. 问题流程
```
1. 用户上传新数据文件
2. 后端：清空 analysis_cache → 重新计算分析结果
3. 前端：表单提交时清理 localStorage
4. 用户通过侧边栏导航到其他页面（AJAX）
5. 问题：loadAnalysisData() 优先读取 localStorage（如果未过期）
6. 结果：显示旧数据，商品数量不一致
```

### 3. 关键代码问题
在 `base.html` 的 `loadAnalysisData()` 函数中：
```javascript
const cachedData = localStorage.getItem('analysisData');
if (cachedData) {
    window.analysisData = JSON.parse(cachedData);
    return;  // ← 问题：直接使用缓存，不验证是否最新
}
```

## 修复方案

### 方案一：数据上传成功后强制刷新（推荐）
修改 `upload.html`，在表单提交成功后强制刷新所有数据：
- 清空 localStorage
- 重新从服务器获取数据
- 更新全局变量

### 方案二：添加时间戳验证
在缓存数据中添加时间戳，每次请求时验证是否过期

### 方案三：AJAX 导航后强制刷新
修改 `loadPageContent()`，在页面加载后强制刷新分析数据

## 文件修改计划

### 1. 修改 upload.html
- 在表单提交事件中，确保 localStorage 被清理
- 添加成功回调，强制刷新页面数据

### 2. 修改 base.html
- 修改 `loadAnalysisData()`，添加缓存验证机制
- 修改 `loadPageContent()`，页面切换后强制刷新数据

## 实施步骤

1. **第一步**：修改 `upload.html` 的表单提交事件，确保 localStorage 和全局变量被正确清理
2. **第二步**：修改 `base.html` 的 `loadPageContent()`，在页面加载后调用数据刷新
3. **第三步**：测试验证上传新数据后各页面商品数量一致

## 风险评估

- **低风险**：修改仅涉及缓存清理逻辑，不影响核心业务逻辑
- **回滚方案**：恢复原始代码即可回退

## 验证标准

1. 上传新数据文件后，所有页面显示相同的商品数量
2. 通过侧边栏导航时，数据能正确更新
3. 刷新页面后数据保持一致