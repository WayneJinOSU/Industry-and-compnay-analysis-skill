#!/usr/bin/env python3
"""Run the index study and finish with a Gann circle plus written summary."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an evidence-aware Gann space-resonance study")
    parser.add_argument("--db", type=Path, help="已知的 KhQuant security DuckDB 文件（兼容旧调用）")
    parser.add_argument("--kh-code", help="KH 标的代码，如 000001.SH；优先检查本地库，缺失时经 KH CLI 补数")
    parser.add_argument("--force-supplement", action="store_true", help="忽略补数缓存并强制通过 KH CLI 补数")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--symbol", default="上证指数")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--projection-end", help="Optional YYYY-MM-DD end for future time-window projection")
    parser.add_argument("--future-sessions", type=Path, help="Optional exchange-calendar CSV with date/trade_date")
    parser.add_argument("--breadth", type=Path, help="Optional daily market-breadth CSV")
    parser.add_argument("--peer-indices", type=Path, help="Optional long CSV with date,symbol,close for broad-index confirmation")
    parser.add_argument("--wave-segments", type=Path, help="Optional declared wave-segment CSV for duration projections")
    parser.add_argument(
        "--wave-report",
        type=Path,
        default=None,
        help="Optional reviewed wave-scenario Markdown to integrate into the circle report",
    )
    args = parser.parse_args()
    if not args.db and not args.kh_code:
        parser.error("必须提供 --kh-code 或 --db")
    if args.db and args.kh_code:
        parser.error("--kh-code 与 --db 二选一")

    if args.kh_code:
        candidates = []
        if os.getenv("KHQUANT_ROOT"):
            candidates.append(Path(os.environ["KHQUANT_ROOT"]) / "tools")
        candidates.extend([Path.cwd() / "tools", Path("/Users/a/PycharmProjects/khquant/tools")])
        loader_dir = next((directory for directory in candidates if (directory / "kh_local_data.py").is_file()), None)
        if loader_dir is None:
            raise SystemExit("未找到 tools/kh_local_data.py；请在 khquant 工作区运行，或设置 KHQUANT_ROOT。")
        sys.path.insert(0, str(loader_dir))
        from kh_local_data import ensure_data  # type: ignore
        ensured = ensure_data(args.kh_code, args.start, args.end, "1d", force_supplement=args.force_supplement)
        if not ensured.db_path:
            raise SystemExit(f"KH 未返回 {args.kh_code} 的本地数据库路径")
        args.db = Path(ensured.db_path)

    here = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=True)
    if args.kh_code:
        (args.output / "kh_data_metadata.json").write_text(
            json.dumps(ensured.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    subprocess.run(
        [
            sys.executable,
            str(here / "run_index_study.py"),
            "--db",
            str(args.db),
            "--start",
            args.start,
            "--end",
            args.end,
            "--output",
            str(args.output),
        ],
        check=True,
    )
    multiclock_command = [
        sys.executable,
        str(here / "build_multiclock_time_ledger.py"),
        "--db",
        str(args.db),
        "--start",
        args.start,
        "--end",
        args.end,
        "--output",
        str(args.output),
    ]
    if args.projection_end:
        multiclock_command.extend(["--projection-end", args.projection_end])
    if args.future_sessions:
        multiclock_command.extend(["--future-sessions", str(args.future_sessions)])
    if args.breadth:
        multiclock_command.extend(["--breadth", str(args.breadth)])
    if args.peer_indices:
        multiclock_command.extend(["--peer-indices", str(args.peer_indices)])
    if args.wave_segments:
        multiclock_command.extend(["--wave-segments", str(args.wave_segments)])
    subprocess.run(multiclock_command, check=True)
    render_command = [
            sys.executable,
            str(here / "render_circle_report.py"),
            "--results",
            str(args.output),
            "--symbol",
            args.symbol,
            "--output",
            str(args.output),
        ]
    if args.wave_report:
        render_command.extend(["--wave-report", str(args.wave_report)])
    subprocess.run(render_command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
