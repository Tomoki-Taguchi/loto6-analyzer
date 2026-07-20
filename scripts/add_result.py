#!/usr/bin/env python3
"""LOTO6 抽選結果を手入力でデータに追記するスクリプト（依存: 標準ライブラリのみ）。

自動スクレイピング（fetch_data.py）を待たずに、確定した抽選結果を手で1件追加し、
続けて analyze.py を実行すれば次回予想が更新される。

使い方:
  # 最新回の「次の回」として追加（回号・日付を自動補完）
  python scripts/add_result.py --numbers "3 8 13 14 16 43" --bonus 26

  # 回号・日付を明示（過去回のバックフィルにも使える）
  python scripts/add_result.py --numbers "3,8,13,14,16,43" --bonus 26 --round 2121 --date 2026-07-20

  # 引数なしで対話入力
  python scripts/add_result.py

追記後、GitHub Actions の "Add LOTO6 Result (manual)" ワークフローは自動で
analyze.py まで実行して push する。ローカルで使う場合は続けて
`python scripts/analyze.py` を実行すること。
"""

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "docs" / "data" / "loto6_data.json"

MAIN_COUNT = 6
NUM_MIN, NUM_MAX = 1, 43


def load_data():
    if DATA_PATH.exists():
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": None, "total_draws": 0, "draws": []}


def parse_numbers(raw: str) -> list[int]:
    """スペース/カンマ区切りの文字列を整数リストに変換する。"""
    tokens = [t for t in re.split(r"[,\s]+", (raw or "").strip()) if t]
    nums = []
    for t in tokens:
        if not re.fullmatch(r"\d+", t):
            raise ValueError(f"数字として解釈できないトークンがあります: '{t}'")
        nums.append(int(t))
    return nums


def validate_draw(numbers: list[int], bonus: int):
    """本数字6個とボーナス1個の妥当性を検証する（不正なら ValueError）。"""
    if len(numbers) != MAIN_COUNT:
        raise ValueError(f"本数字は{MAIN_COUNT}個必要です（入力: {len(numbers)}個 {numbers}）")
    if len(set(numbers)) != MAIN_COUNT:
        raise ValueError(f"本数字に重複があります: {numbers}")
    for n in numbers:
        if not (NUM_MIN <= n <= NUM_MAX):
            raise ValueError(f"本数字は{NUM_MIN}〜{NUM_MAX}の範囲です（不正: {n}）")
    if not (NUM_MIN <= bonus <= NUM_MAX):
        raise ValueError(f"ボーナス数字は{NUM_MIN}〜{NUM_MAX}の範囲です（不正: {bonus}）")
    if bonus in numbers:
        raise ValueError(f"ボーナス数字({bonus})は本数字と重複できません: {numbers}")


def parse_date(raw: str) -> str:
    """YYYY-MM-DD / YYYY/MM/DD を検証して YYYY-MM-DD に正規化する。"""
    s = (raw or "").strip().replace("/", "-")
    datetime.strptime(s, "%Y-%m-%d")  # 不正な日付なら ValueError
    return s


def prompt(msg: str) -> str:
    try:
        return input(msg)
    except EOFError:
        return ""


def resolve_inputs(args):
    """CLI引数または対話入力から (numbers, bonus, round, date) を確定する。"""
    numbers_raw = args.numbers
    bonus_raw = args.bonus

    # 引数が無ければ対話モード
    if not numbers_raw:
        numbers_raw = prompt(f"本数字{MAIN_COUNT}個（スペース区切り 例: 3 8 13 14 16 43）: ")
    if bonus_raw in (None, ""):
        bonus_raw = prompt("ボーナス数字（例: 26）: ")

    numbers = sorted(parse_numbers(numbers_raw))
    bonus_list = parse_numbers(bonus_raw)
    if len(bonus_list) != 1:
        raise ValueError(f"ボーナス数字は1個だけ指定してください（入力: {bonus_list}）")
    bonus = bonus_list[0]
    validate_draw(numbers, bonus)

    round_num = int(args.round) if (args.round not in (None, "")) else None
    date_str = parse_date(args.date) if (args.date not in (None, "")) else None
    return numbers, bonus, round_num, date_str


def main():
    ap = argparse.ArgumentParser(description="LOTO6 抽選結果を手入力でデータに追記する")
    ap.add_argument("--numbers", help="本数字6個（スペース/カンマ区切り 例: '3 8 13 14 16 43'）")
    ap.add_argument("--bonus", help="ボーナス数字（例: 26）")
    ap.add_argument("--round", help="回号（省略時は最新+1）")
    ap.add_argument("--date", help="抽選日 YYYY-MM-DD（省略時は本日）")
    args = ap.parse_args()

    try:
        numbers, bonus, round_num, date_str = resolve_inputs(args)
    except ValueError as e:
        print(f"❌ 入力エラー: {e}", file=sys.stderr)
        return 1

    data = load_data()
    draws = data.get("draws", [])
    by_round = {d["round"]: d for d in draws}
    latest_round = max(by_round) if by_round else 0

    # 回号: 省略時は最新+1
    if round_num is None:
        round_num = latest_round + 1
    # 日付: 省略時は本日
    if date_str is None:
        date_str = date.today().isoformat()

    new_draw = {
        "round": round_num,
        "date": date_str,
        "numbers": numbers,
        "bonus": bonus,
    }

    if round_num in by_round:
        old = by_round[round_num]
        if old.get("numbers") == numbers and old.get("bonus") == bonus:
            print(f"ℹ️  第{round_num}回は同じ内容で既に存在します。変更なし。")
            return 0
        print(f"⚠️  第{round_num}回は既存です。上書きします: {old.get('numbers')}+{old.get('bonus')} → {numbers}+{bonus}")
    else:
        print(f"＋ 第{round_num}回を追加: {numbers} + ボーナス {bonus}（{date_str}）")
        if round_num != latest_round + 1:
            print(f"   ※ 最新は第{latest_round}回です。通常の次回は第{latest_round + 1}回。回号を確認してください。")

    by_round[round_num] = new_draw
    all_draws = sorted(by_round.values(), key=lambda x: x["round"])

    # 回号の連続性チェック（掲載漏れ・入力ミスの早期検知）
    present = {d["round"] for d in all_draws}
    gaps = [r for r in range(min(present), max(present) + 1) if r not in present]
    if gaps:
        print(f"⚠️  欠番があります: {gaps}（別途バックフィルを検討してください）")

    data["draws"] = all_draws
    data["total_draws"] = len(all_draws)
    data["last_updated"] = datetime.now().isoformat()

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✓ 保存しました: {DATA_PATH}（全{len(all_draws)}回）")
    print("  → 続けて `python scripts/analyze.py` を実行すると第"
          f"{max(present) + 1}回の予想が生成されます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
