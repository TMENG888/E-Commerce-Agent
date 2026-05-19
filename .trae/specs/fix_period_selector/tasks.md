# 标准化日期选择器修复 - 实现计划

## [ ] Task 1: 修改 upload.html 添加 uploadInit 函数
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 将 upload.html 中的初始化逻辑封装到 `uploadInit` 函数中
  - 确保函数可在 AJAX 导航后被调用
  - 添加延迟确保 DOM 已更新
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `human-judgment` TR-1.1: upload 页面通过 AJAX 导航加载后，周期选择器可正常切换
  - `human-judgment` TR-1.2: 选择器点击后 UI 状态正确切换（selected 类、checked 属性）

## [ ] Task 2: 修改 upload.html 的 JavaScript 结构
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 
  - 修改脚本结构，确保即使通过 AJAX 加载也能正确初始化
  - 使用 `requestAnimationFrame` 确保 DOM 操作在正确时机执行
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `human-judgment` TR-2.1: 从首页刷新后导航到 upload 页面，选择器功能正常

## [ ] Task 3: 验证修复效果
- **Priority**: P1
- **Depends On**: Task 1, Task 2
- **Description**: 
  - 启动开发服务器测试
  - 验证 AJAX 导航后周期选择器功能正常
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `human-judgment` TR-3.1: 完整测试流程验证（首页刷新 → 导航 upload → 切换周期）