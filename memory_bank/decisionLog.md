# 趋势雷达 - 决策日志

## [2026-07-05] 初始化 Memory Bank

**决策**：采用 RooFlow 的 5 文件 Memory Bank 结构，扩展为 6 文件（增加 portfolioState.md 和 marketNotes.md）。

**理由**：
1. 投资系统需要追踪持仓状态和市场观察，这是 RooFlow 没有的
2. 风控铁律需要结构化记录，便于回溯
3. 报告质量红线需要明确记录，避免重复犯错

**影响**：
- 每次买卖操作后更新 portfolioState.md + decisionLog.md
- 每次生成报告后更新 marketNotes.md
- 风控触发时自动预警
