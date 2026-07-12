#!/usr/bin/env python3
"""
A股投资报告 → 小白友好版 转换器
"""
import os
from datetime import datetime

REPORTS_DIR = r'D:\project_room\workspace2024\mytest\a-stock-data\reports'
OUTPUT_DIR = r'D:\project_room\workspace2024\mytest\a-stock-data\reports小白版'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate小白解读(stock_name, code):
    today = datetime.now().strftime('%Y-%m-%d')
    return """---

# 📚 小白解读板块

> 本章节专为投资新手（小白）编写，用最通俗的语言解释专业术语

---

## 一、财务指标小词典

### 什么是"每股收益(EPS)"？
假设公司只有你一个股东，公司今年赚了100万，你持有1万股。
每股收益 = 100万 ÷ 1万股 = 100元/股

**通俗理解**：持有一股，今年帮你赚了多少钱。这个数字越高，说明公司越能赚钱。

**对比技巧**：同行业对比，比如工行赚3元/股，建行赚2.8元/股，工行更赚钱。

---

### 什么是"ROE（净资产收益率）"？
ROE = 净利润 ÷ 净资产 × 100%

**通俗理解**：你存100万进银行，年利率12%，ROE就是12%。

**判断标准**：
- ROE > 20%：非常优秀，可能是行业龙头
- ROE 15-20%：优秀，继续保持
- ROE 10-15%：良好，稳健
- ROE 5-10%：一般，跑输通胀
- ROE < 5%：较差，考虑换股

**巴菲特法则**：长期年化ROE > 15% 的公司值得关注

---

### 什么是"净利润增长率"？
增长率 = (今年利润 - 去年利润) ÷ 去年利润 × 100%

**通俗理解**：今年比去年多赚了百分之多少

**判断标准**：
- > 20%：高速增长
- 10-20%：稳健增长
- 0-10%：低速增长
- < 0%：负增长，警惕

---

### 什么是"扣非净利润"？
扣掉"横财"（卖资产、政府补贴、炒股）后的真实利润，更可信

---

## 二、估值指标小词典

### 什么是"PE（市盈率）"？
PE = 股价 ÷ 每股收益。≈按今年赚钱速度，多少年回本

**举例**：PE=10，持有10年回本

| 行业 | 低PE | 中PE | 高PE |
|------|------|------|------|
| 银行 | <6 | 6-10 | >10 |
| 钢铁/煤炭 | <8 | 8-15 | >15 |
| 消费 | <15 | 15-25 | >25 |
| 科技/AI | <30 | 30-50 | >50 |

---

### 什么是"PB（市净率）"？
PB = 股价 ÷ 每股净资产

- PB < 1：可能低估（也可能是陷阱）
- PB = 1：合理
- PB > 3：偏高（成长股例外）

---

### 什么是"机构一致预期"？
13家券商分析师对明年EPS的预测取平均。预测≠事实，仅供参考

---

## 三、策略评价小词典

**为什么用这几个指标？**

1. **股息率**：存银行年利率。>4%算高股息
2. **PE**：贵不贵。银行<8便宜，>15贵
3. **ROE**：公司用股东钱的效率。>15%优秀
4. **市值**：<50亿小盘股波动大，>500亿大盘稳健

---

## 四、投资铁律

1. **分散持仓**：单只股票不超过总仓位20%
2. **止损不止盈**：亏20%必须卖
3. **持续学习**：每个报告学会一个指标

---

*小白解读生成于 """ + today + """
*由 A股投资报告小白化系统 自动生成*
"""

def convert_report(input_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    basename = os.path.basename(input_path)
    name_parts = basename.replace('_投资研究报告_', '_').replace('.md', '').split('_')
    stock_name = name_parts[0] if len(name_parts) > 0 else '未知'
    code = name_parts[1] if len(name_parts) > 1 else ''
    
    小白版内容 = content + generate小白解读(stock_name, code)
    
    output_name = basename.replace('.md', '_小白版.md')
    output_path = os.path.join(OUTPUT_DIR, output_name)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(小白版内容)
    
    return output_name, len(小白版内容)

def main():
    print("=" * 60)
    print("A股投资报告 → 小白友好版 转换器")
    print("=" * 60)
    
    reports = []
    for f in os.listdir(REPORTS_DIR):
        if '投资研究报告_2026-05-27' in f and '小白版' not in f:
            reports.append(f)
    
    print(f"找到 {len(reports)} 个报告待转换")
    
    success = 0
    errors = []
    
    for i, report in enumerate(reports):
        input_path = os.path.join(REPORTS_DIR, report)
        try:
            output_name, size = convert_report(input_path)
            success += 1
            print(f"  [{i+1}/{len(reports)}] 生成 {output_name}")
        except Exception as e:
            errors.append((report, str(e)))
            print(f"  [{i+1}/{len(reports)}] 失败 {report}: {e}")
    
    print(f"\n完成: 成功 {success} 个，失败 {len(errors)} 个")
    print(f"输出目录: {OUTPUT_DIR}")

if __name__ == '__main__':
    main()
