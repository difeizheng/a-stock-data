# 趋势雷达 - 决策日志

## [2026-07-13] 修复钉钉推送签名 bug

**决策**：修复 TrendRadar 开盘/收盘简报脚本的钉钉签名错误。

**理由**：
1. `base64.b64encode()` 在 Python3 返回 `bytes` 类型
2. `urllib.parse.quote_plus(bytes)` 会逐字节编码，产出的签名字符串和钉钉服务端用 `str` 计算的签名不一致
3. 导致所有钉钉投递的任务报"签名不匹配"错误

**影响**：
- morning_brief.py 第 321、340-343 行修复
- closing_brief.py 第 342、375-377 行修复
- 添加 `.decode("utf-8")` + errcode 检查逻辑
- 钉钉推送恢复正常，测试消息成功送达

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
