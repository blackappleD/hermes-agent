#!/usr/bin/env python3
"""
linz_event_summary.py
统计 Linz/Hermes JSONL 事件日志，支持 --input 和可选 --output。
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Linz JSONL 事件统计脚本")
    parser.add_argument("--input", required=True, help="输入 JSONL 文件路径")
    parser.add_argument("--output", help="输出 JSON 文件路径（可选）")
    args = parser.parse_args()

    total_lines = 0
    valid_events = 0
    invalid_lines = 0
    by_event_type = defaultdict(int)
    by_subject = defaultdict(int)

    path = Path(args.input)
    if not path.is_file():
        print(f"错误: 文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    with path.open(encoding="utf-8") as f:
        for line in f:
            total_lines += 1
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
                valid_events += 1
                event_type = event.get("event_type") or event.get("event") or "unknown"
                subject = event.get("subject") or event.get("type") or "unknown"
                by_event_type[event_type] += 1
                by_subject[subject] += 1
            except (json.JSONDecodeError, ValueError):
                invalid_lines += 1

    result = {
        "total_lines": total_lines,
        "valid_events": valid_events,
        "invalid_lines": invalid_lines,
        "by_event_type": dict(by_event_type),
        "by_subject": dict(by_subject),
    }

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output, encoding="utf-8")
        print(f"结果已写入: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
