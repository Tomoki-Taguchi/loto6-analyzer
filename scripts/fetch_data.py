#!/usr/bin/env python3
"""LOTO6 データスクレイピング - m-shokai.jp から全抽選データを取得"""

import json
import re
import time
import sys
import os
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://m-shokai.jp/loto6-site/history?page={}"
OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "data" / "loto6_data.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LOTO6Analyzer/1.0)"
}
REQUEST_DELAY = 1.5  # seconds between requests


def load_existing_data():
    """既存データを読み込む。なければ空データを返す。"""
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": None, "total_draws": 0, "draws": []}


def parse_page(html: str) -> list[dict]:
    """1ページ分のHTMLから抽選データをパースする。"""
    soup = BeautifulSoup(html, "lxml")
    draws = []

    rows = soup.select("table tr")
    if not rows:
        # テーブル構造が異なる場合のフォールバック
        rows = soup.find_all("tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        # 回数と日付を取得
        first_cell_text = cells[0].get_text(separator=" ", strip=True)
        round_match = re.search(r"第(\d+)回", first_cell_text)
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", first_cell_text)

        if not round_match or not date_match:
            # 日付形式がYYYY/MM/DD の場合
            date_match = re.search(r"(\d{4}/\d{2}/\d{2})", first_cell_text)
            if not round_match:
                continue

        round_num = int(round_match.group(1))
        if date_match:
            date_str = date_match.group(1).replace("/", "-")
        else:
            date_str = "unknown"

        # 数字を取得 - spanタグから
        number_spans = cells[1].find_all("span")
        if number_spans:
            numbers = []
            for span in number_spans:
                text = span.get_text(strip=True)
                if text.isdigit():
                    numbers.append(int(text))
            if len(numbers) >= 7:
                main_numbers = sorted(numbers[:6])
                bonus = numbers[6]
            elif len(numbers) == 7:
                main_numbers = sorted(numbers[:6])
                bonus = numbers[6]
            else:
                # spanがうまく取れない場合、テキストから取得
                all_text = cells[1].get_text(separator=" ", strip=True)
                nums = [int(x) for x in re.findall(r"\d+", all_text)]
                if len(nums) >= 7:
                    main_numbers = sorted(nums[:6])
                    bonus = nums[6]
                else:
                    continue
        else:
            # spanがない場合、テキストから直接取得
            all_text = cells[1].get_text(separator=" ", strip=True)
            nums = [int(x) for x in re.findall(r"\d+", all_text)]
            if len(nums) >= 7:
                main_numbers = sorted(nums[:6])
                bonus = nums[6]
            else:
                continue

        # バリデーション
        if len(main_numbers) != 6:
            continue
        if not all(1 <= n <= 43 for n in main_numbers):
            continue
        if not (1 <= bonus <= 43):
            continue

        draws.append({
            "round": round_num,
            "date": date_str,
            "numbers": main_numbers,
            "bonus": bonus
        })

    return draws


def fetch_all_data(existing_last_round: int = 0):
    """全ページからデータを取得する。差分更新対応。"""
    all_draws = []
    page = 1
    max_pages = 30  # 安全上限

    while page <= max_pages:
        url = BASE_URL.format(page)
        print(f"Fetching page {page}: {url}")

        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"  Error fetching page {page}: {e}")
            # リトライ
            time.sleep(3)
            try:
                response = requests.get(url, headers=HEADERS, timeout=30)
                response.raise_for_status()
            except requests.RequestException as e2:
                print(f"  Retry failed for page {page}: {e2}")
                break

        draws = parse_page(response.text)
        if not draws:
            print(f"  No draws found on page {page}. Stopping.")
            break

        print(f"  Found {len(draws)} draws (rounds {draws[0]['round']}-{draws[-1]['round']})")
        all_draws.extend(draws)

        # 全部既存データより古いなら差分更新完了
        if existing_last_round > 0:
            newest_on_page = max(d["round"] for d in draws)
            if newest_on_page <= existing_last_round:
                print(f"  All draws on this page already exist. Stopping.")
                break

        page += 1
        time.sleep(REQUEST_DELAY)

    return all_draws


def main():
    print("=== LOTO6 Data Fetcher ===")
    existing = load_existing_data()
    existing_rounds = {d["round"] for d in existing["draws"]}
    last_round = max(existing_rounds) if existing_rounds else 0
    print(f"Existing data: {len(existing_rounds)} draws, last round: {last_round}")

    new_draws = fetch_all_data(last_round)
    print(f"\nFetched {len(new_draws)} draws total")

    # 既存データとマージ（重複排除）
    merged = {d["round"]: d for d in existing["draws"]}
    new_count = 0
    for d in new_draws:
        if d["round"] not in merged:
            new_count += 1
        merged[d["round"]] = d

    all_draws = sorted(merged.values(), key=lambda x: x["round"])

    output = {
        "last_updated": datetime.now().isoformat(),
        "total_draws": len(all_draws),
        "draws": all_draws
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(all_draws)} draws to {OUTPUT_PATH}")
    print(f"New draws added: {new_count}")


if __name__ == "__main__":
    main()
