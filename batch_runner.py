#!/usr/bin/env python3
"""
A股投资报告批量生成系统 - 主控脚本

执行流程：
1. 运行股票筛选 → filtered_stocks.json
2. 运行报告生成 → reports/*.md
3. 输出进度和完成通知

用法：
  python batch_runner.py              # 完整流程
  python batch_runner.py --skip-scan  # 跳过筛选，直接生成报告
  python batch_runner.py --scan-only  # 只运行筛选
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PROGRESS_FILE = os.path.join(PROJECT_DIR, "progress_checkpoint.json")
FILTERED_FILE = os.path.join(PROJECT_DIR, "filtered_stocks.json")
REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")


def run_script(script_name, label):
    script_path = os.path.join(PROJECT_DIR, script_name)
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"  脚本: {script_name}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    start = time.time()
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_DIR,
        capture_output=False,
    )
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n[ERROR] {script_name} 执行失败 (退出码 {result.returncode})")
        return False

    print(f"\n[DONE] {label} 完成，耗时 {elapsed:.0f} 秒")
    return True


def count_reports():
    if not os.path.exists(REPORTS_DIR):
        return 0
    return len([f for f in os.listdir(REPORTS_DIR)
                if f.endswith(".md") and "投资研究报告" in f])


def write_progress(phase, message):
    data = {
        "phase": phase,
        "timestamp": datetime.now().isoformat(),
        "message": message,
        "reports_count": count_reports(),
    }
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    args = set(sys.argv[1:])
    skip_scan = "--skip-scan" in args
    scan_only = "--scan-only" in args

    print("=" * 60)
    print("A股投资报告批量生成系统 v2.0")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目录: {PROJECT_DIR}")
    print(f"已有报告: {count_reports()} 份")
    print("=" * 60)

    # Phase 1: 股票筛选
    if not skip_scan:
        write_progress("screening", "开始股票筛选")
        ok = run_script("stock_screener.py", "Phase 1: 股票筛选")
        if not ok:
            write_progress("error", "股票筛选失败")
            print("\n[STOP] 股票筛选失败，终止流程")
            sys.exit(1)

        if not os.path.exists(FILTERED_FILE):
            write_progress("error", "筛选结果文件未生成")
            print("\n[STOP] 筛选结果文件未生成")
            sys.exit(1)

        with open(FILTERED_FILE, "r", encoding="utf-8") as f:
            filtered = json.load(f)
        total = filtered.get("总计", 0)
        print(f"\n[INFO] 筛选完成: {total} 只候选股")

        if scan_only:
            write_progress("complete", f"筛选完成: {total} 只")
            sys.exit(0)
    else:
        print("\n[SKIP] 跳过股票筛选 (--skip-scan)")

    # Phase 2: 报告生成
    if not os.path.exists(FILTERED_FILE):
        print("\n[ERROR] filtered_stocks.json 不存在，请先运行筛选")
        sys.exit(1)

    write_progress("generation", "开始批量生成报告")
    ok = run_script("report_generator.py", "Phase 2: 批量生成报告")
    if not ok:
        write_progress("error", "报告生成失败")
        sys.exit(1)

    # 完成
    final_count = count_reports()
    write_progress("complete", f"全部完成: {final_count} 份报告")

    print(f"\n{'=' * 60}")
    print(f"全部流程完成！")
    print(f"  报告数量: {final_count} 份")
    print(f"  报告目录: {REPORTS_DIR}")
    print(f"  完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
