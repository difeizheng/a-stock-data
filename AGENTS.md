# a-stock-data — Agent 指南

本文件只写 `CLAUDE.md` 和 `README.md` **没覆盖**、但 agent 启动后必须知道的差分。
完整架构、数据源优先级、已知坑请先读 `CLAUDE.md`。

## 命令（非标准，CLAUDE.md 已有的不重复）

- **报告生成无 `--reset` 安全垫**：`batch_reports.py` 跑前会读写 `.generation_checkpoint.json`；想重跑必须先 `--reset`，否则会沿用旧进度导致"跑了没结果"。
- **本地快捷入口**：`run_claude.bat`（已 `chcp 65001` 设 UTF-8，绕开 GBK 控制台 emoji 报错）。
- **Docker 仅打包公开脚本**：Dockerfile 只 COPY `stock_screener/report_generator/batch_runner.py`，`small_goal/`、`SKILL.md`、`tests/` 不进镜像。

## 约定

- **三大子系统职责分离，不要混用入口**：
  - `SKILL.md`（144KB 单文件）= 对外交付物，内嵌 Python，**不要拆分或"重构"成多文件**。
  - 根目录 `*.py` = 批量研报流水线，入口 `batch_runner.py`。
  - `small_goal/` = 个人投资工作台，入口 `daily_check.py`，与根脚本数据/配置互不依赖。
- **checkpoint 文件一律只追加不手删**（见 CLAUDE.md "State/checkpoint files" 清单）；中断重跑用各脚本的 `--reset`/`--status` 参数，别手动删 JSON。
- **股票代码归一化在多个脚本里各有一份**：`get_prefix()` 规则见 CLAUDE.md，**别为"统一"新建第四份**——会引入不一致。

## 禁区（动了会破坏交付物或泄密）

- **`small_goal/` 整目录被 `.gitignore`**（含持仓/策略/钉钉密钥）。它在本地磁盘但**禁止 `git add -f`**，也不要把其中的真实持仓数字写进 `reports/` 或 commit。
- **`dingtalk_config.json`** = webhook + HMAC 密钥，绝对不提交、不打印、不粘进日志。
- **`SKILL.md` 是版本化交付物**：改它要走 changelog（`CHANGELOG.md`），且不能引入未在 `requirements.txt` 外的依赖——它的卖点是"零外部文件依赖"。
- **`reports_bak/`、根目录 `2026-*-local-command-caveat*.txt`** = 历史快照/本地日志，只读。
