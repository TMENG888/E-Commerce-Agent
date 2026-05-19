# 标准化日期选择器修复 - 产品需求文档

## Overview
- **Summary**: 修复 AJAX 导航后上传页面周期选择器无法正常切换的问题
- **Purpose**: 解决从首页刷新后导航到 upload 页面时，周期选择器 UI 状态与实际值不一致的问题
- **Target Users**: 所有使用数据分析平台上传数据的用户

## Goals
- 修复 upload 页面通过 AJAX 导航加载时周期选择器无法正常切换的问题
- 确保页面初始化逻辑在 AJAX 导航后正确执行

## Non-Goals (Out of Scope)
- 修改页面整体布局或样式
- 修改其他页面的功能

## Background & Context
- 系统使用 AJAX 导航实现页面切换，通过 `history.pushState` 和 `fetch` 获取内容
- `base.html` 中的 `loadPageContent` 函数负责加载新页面内容
- 期望每个页面定义一个 `xxxInit` 初始化函数，在内容加载后调用

## Functional Requirements
- **FR-1**: upload 页面通过 AJAX 导航加载时，周期选择器应能正常切换
- **FR-2**: 周期选择器的 UI 状态（selected 类、checked 属性）应与当前配置一致

## Constraints
- **Technical**: 保持现有代码结构，最小化改动
- **Dependencies**: 需要修改 `upload.html` 和 `base.html`

## Acceptance Criteria

### AC-1: AJAX 导航后周期选择器可正常切换
- **Given**: 用户在首页刷新后通过侧边栏导航到 upload 页面
- **When**: 用户点击周期选择器（1天、7天、30天）
- **Then**: 选择器应正确切换选中状态，隐藏字段值应更新
- **Verification**: `human-judgment`

### AC-2: 初始化函数正确调用
- **Given**: upload 页面通过 AJAX 导航加载
- **When**: 页面内容插入 DOM 后
- **Then**: `uploadInit` 函数应被自动调用
- **Verification**: `programmatic`

## Open Questions
- [ ] 已确认：`loadPageContent` 中已预留调用 `uploadInit` 的逻辑