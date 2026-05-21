#!/usr/bin/env python3
"""
Linz/Hermes JSONL 事件日志统计脚本
用法: python linz_event_summary.py --input <path> [--output <path>]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="统计 Linz/Hermes JSONL 事件日志")
    parser.add_argument("--input", required=True, help="输入 JSONL 文件路径")
    parser.add_argument("--output", help="输出 JSON 文件路径（可选）")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    total_lines = 0
    valid_events = 0
    invalid_lines = 0
    event_type_counter = Counter()
    subject_counter = Counter()

    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            total_lines += 1
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                valid_events += 1
                event_type = obj.get("event_type", "unknown")
                subject = obj.get("subject", "unknown")
                event_type_counter[event_type] += 1
                subject_counter[subject] += 1
            except json.JSONDecodeError:
                invalid_lines += 1

    result = {
        "total_lines": total_lines,
        "valid_events": valid_events,
        "invalid_lines": invalid_lines,
        "by_event_type": dict(event_type_counter),
        "by_subject": dict(subject_counter),
    }

    output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"结果已写入: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
