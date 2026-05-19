# 分布图与表格分类数量不一致问题修复方案

## 问题分析

### 1. 现象
- 分类分布柱状图显示：超级爆款 2 个
- 表格筛选"超级爆款"后只显示：1 个

### 2. 根本原因
系统存在两个独立的数据处理路径：

**路径1（图表）**：使用缓存数据
```python
# analyze_and_cache() 生成
analysis_cache['category_stats'] = {'超级爆款': 2, ...}
analysis_cache['product_list'] = [{category: '超级爆款'}, ...]
```

**路径2（API）**：每次请求重新计算
```python
# /api/products 每次调用都重新执行
df = load_data()
df = preprocess_data(df)
df, _, _ = classify_products(df)  # 重新分类
```

**问题**：虽然两者都使用 `CURRENT_PERIOD_DAYS`，但由于缓存的分类结果与实时计算可能存在差异，导致统计数量不一致。

### 3. 解决方案
修改 `/api/products` API，优先使用缓存中的 `product_list` 数据，确保分类结果一致。

## 文件修改计划

### 1. 修改 `app.py` 中的 `/api/products` API
- 优先从 `analysis_cache['product_list']` 获取数据
- 仅在缓存为空时才重新计算

### 2. 修改 `/api/products/ids` API（如果需要）
- 同样改为使用缓存数据

## 实施步骤

1. **第一步**：修改 `/api/products` API，使用缓存数据
2. **第二步**：修改 `/api/products/ids` API，保持一致性
3. **第三步**：测试验证分布图和表格显示数量一致

## 风险评估

- **低风险**：修改仅涉及数据读取逻辑，不影响核心分类算法
- **回滚方案**：恢复原始代码即可回退

## 验证标准

1. 分布图显示的超级爆款数量与表格筛选结果一致
2. 其他分类（待清理垃圾、转化陷阱等）数量也保持一致
3. 分页功能正常工作