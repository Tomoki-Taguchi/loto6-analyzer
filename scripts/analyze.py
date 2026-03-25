#!/usr/bin/env python3
"""LOTO6 分析エンジン - 統計分析 + 予想生成（v3: 周期分析・RF・LSTM搭載）"""

import json
import math
import random
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
import torch
import torch.nn as nn

DATA_PATH = Path(__file__).parent.parent / "docs" / "data" / "loto6_data.json"
OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "data" / "analysis.json"

# 毎日同じ予想を出すためにシードを日付で固定
random.seed(date.today().isoformat())


def load_data():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 1. 出現頻度分析（改善: 直近重み付き頻度を追加）
# ============================================================
def analyze_frequency(draws):
    counter = Counter()
    last_seen = {}
    current_round = draws[-1]["round"]

    # 全期間
    for d in draws:
        for n in d["numbers"]:
            counter[n] += 1
            last_seen[n] = d["round"]

    total = len(draws)
    counts = {str(n): counter.get(n, 0) for n in range(1, 44)}
    percentages = {str(n): round(counter.get(n, 0) / total * 100, 2) for n in range(1, 44)}
    drought = {str(n): current_round - last_seen.get(n, 0) for n in range(1, 44)}

    # 直近100回・300回の出現頻度（改善②）
    recent_100 = Counter()
    recent_300 = Counter()
    for d in draws[-100:]:
        for n in d["numbers"]:
            recent_100[n] += 1
    for d in draws[-300:]:
        for n in d["numbers"]:
            recent_300[n] += 1

    recent_100_pct = {str(n): round(recent_100.get(n, 0) / min(100, total) * 100, 2) for n in range(1, 44)}
    recent_300_pct = {str(n): round(recent_300.get(n, 0) / min(300, total) * 100, 2) for n in range(1, 44)}

    # 各数字の平均出現間隔を計算（改善③で使用）
    appearances = defaultdict(list)
    for d in draws:
        for n in d["numbers"]:
            appearances[n].append(d["round"])
    avg_intervals = {}
    for n in range(1, 44):
        rounds = sorted(appearances.get(n, []))
        if len(rounds) >= 2:
            intervals = [rounds[i+1] - rounds[i] for i in range(len(rounds)-1)]
            avg_intervals[str(n)] = round(sum(intervals) / len(intervals), 2)
        else:
            avg_intervals[str(n)] = total  # 出現が少ない場合

    sorted_by_freq = sorted(range(1, 44), key=lambda n: counter.get(n, 0), reverse=True)
    hot = sorted_by_freq[:10]
    cold = sorted_by_freq[-10:]

    return {
        "counts": counts,
        "percentages": percentages,
        "drought": drought,
        "hot": hot,
        "cold": cold,
        "recent_100": recent_100_pct,
        "recent_300": recent_300_pct,
        "avg_intervals": avg_intervals,
    }


# ============================================================
# 2. 引っ張り分析
# ============================================================
def analyze_pull(draws):
    distribution = Counter()
    pull_details = []

    for i in range(1, len(draws)):
        prev = set(draws[i - 1]["numbers"])
        curr = set(draws[i]["numbers"])
        overlap = prev & curr
        distribution[len(overlap)] += 1
        if i >= len(draws) - 20:
            pull_details.append({
                "round": draws[i]["round"],
                "date": draws[i]["date"],
                "numbers": draws[i]["numbers"],
                "pulled": sorted(list(overlap)),
                "pull_count": len(overlap),
            })

    total_transitions = len(draws) - 1
    avg = sum(k * v for k, v in distribution.items()) / total_transitions if total_transitions else 0

    return {
        "distribution": {str(k): v for k, v in sorted(distribution.items())},
        "average": round(avg, 2),
        "last_draw_numbers": draws[-1]["numbers"],
        "recent_pulls": pull_details[-10:],
    }


# ============================================================
# 3. 数字帯分析
# ============================================================
def get_zone(n):
    if n <= 14:
        return "low"
    elif n <= 29:
        return "mid"
    else:
        return "high"


def analyze_zone(draws):
    pattern_counter = Counter()
    zone_totals = {"low": 0, "mid": 0, "high": 0}

    for d in draws:
        zones = [get_zone(n) for n in d["numbers"]]
        low_c = zones.count("low")
        mid_c = zones.count("mid")
        high_c = zones.count("high")
        pattern = f"{low_c}-{mid_c}-{high_c}"
        pattern_counter[pattern] += 1
        zone_totals["low"] += low_c
        zone_totals["mid"] += mid_c
        zone_totals["high"] += high_c

    total = len(draws) * 6
    zone_averages = {k: round(v / total * 100, 2) for k, v in zone_totals.items()}
    top_patterns = [
        {"pattern": p, "count": c, "percentage": round(c / len(draws) * 100, 1)}
        for p, c in pattern_counter.most_common(10)
    ]

    return {
        "zone_averages": zone_averages,
        "top_patterns": top_patterns,
    }


# ============================================================
# 4. ペア分析（改善④: 直近ペアも分析）
# ============================================================
def analyze_pairs(draws):
    pair_counter = Counter()
    recent_pair_counter = Counter()  # 直近200回

    for d in draws:
        for pair in combinations(d["numbers"], 2):
            pair_counter[pair] += 1

    for d in draws[-200:]:
        for pair in combinations(d["numbers"], 2):
            recent_pair_counter[pair] += 1

    top_pairs = [
        {"pair": list(pair), "count": count}
        for pair, count in pair_counter.most_common(30)
    ]

    # 各数字の相性マップ（上位5つ）
    affinity = {}
    for n in range(1, 44):
        partners = [(p, c) for p, c in pair_counter.items() if n in p]
        partners.sort(key=lambda x: x[1], reverse=True)
        top5 = []
        for pair, count in partners[:5]:
            other = pair[1] if pair[0] == n else pair[0]
            top5.append({"number": other, "count": count})
        affinity[str(n)] = top5

    return {
        "top_pairs": top_pairs,
        "affinity": affinity,
        "pair_counts": {f"{a}-{b}": c for (a, b), c in pair_counter.items()},
        "recent_pair_counts": {f"{a}-{b}": c for (a, b), c in recent_pair_counter.items()},
    }


# ============================================================
# 5. 連番分析（改善⑤: 新規追加）
# ============================================================
def analyze_consecutive(draws):
    """隣接数字（連番）の出現傾向を分析"""
    consec_count = 0
    total_draws = len(draws)

    for d in draws:
        nums = sorted(d["numbers"])
        for i in range(len(nums) - 1):
            if nums[i + 1] - nums[i] == 1:
                consec_count += 1
                break  # 1回の抽選で1カウント

    consec_rate = round(consec_count / total_draws * 100, 1)

    # 各数字が連番で出現した回数
    consec_partner_counts = Counter()
    for d in draws:
        nums = sorted(d["numbers"])
        for i in range(len(nums) - 1):
            if nums[i + 1] - nums[i] == 1:
                consec_partner_counts[nums[i]] += 1
                consec_partner_counts[nums[i + 1]] += 1

    return {
        "has_consecutive_rate": consec_rate,
        "partner_counts": {str(n): consec_partner_counts.get(n, 0) for n in range(1, 44)},
    }


# ============================================================
# 6. N回周期分析
# ============================================================
def analyze_cycle(draws):
    """各数字の出現周期を検出し、次回出現の期待度を算出"""
    total_draws = len(draws)
    current_round = draws[-1]["round"]

    cycle_data = {}
    for n in range(1, 44):
        # 出現した回のリスト
        appearances = [d["round"] for d in draws if n in d["numbers"]]
        if len(appearances) < 3:
            cycle_data[str(n)] = {
                "dominant_cycle": None,
                "cycle_score": 0.0,
                "intervals": [],
                "next_expected": None,
            }
            continue

        # 出現間隔を計算
        intervals = [appearances[i + 1] - appearances[i] for i in range(len(appearances) - 1)]
        avg_interval = sum(intervals) / len(intervals)

        # 最頻出の間隔（周期候補）を検出
        interval_counter = Counter(intervals)
        # 近い間隔をグルーピング（±1の範囲）
        grouped = defaultdict(int)
        for iv, cnt in interval_counter.items():
            grouped[iv] += cnt
        # 上位3つの周期候補
        top_cycles = sorted(grouped.items(), key=lambda x: x[1], reverse=True)[:3]
        dominant_cycle = top_cycles[0][0] if top_cycles else int(avg_interval)

        # 最後の出現からの経過
        since_last = current_round - appearances[-1]

        # 周期スコア: 支配的周期に対してどれだけ「次に来そう」か
        # 周期の倍数に近いほどスコアが高い
        if dominant_cycle > 0:
            remainder = since_last % dominant_cycle
            closeness = 1.0 - (min(remainder, dominant_cycle - remainder) / (dominant_cycle / 2))
            # 1周期以上経過でボーナス
            cycle_multiplier = min(since_last / dominant_cycle, 2.0)
            score = closeness * cycle_multiplier
        else:
            score = 0.0

        next_expected = appearances[-1] + dominant_cycle

        cycle_data[str(n)] = {
            "dominant_cycle": dominant_cycle,
            "cycle_score": round(score, 4),
            "avg_interval": round(avg_interval, 1),
            "since_last": since_last,
            "next_expected": next_expected,
            "top_cycles": [{"cycle": c, "count": cnt} for c, cnt in top_cycles[:3]],
        }

    return cycle_data


# ============================================================
# 7. ランダムフォレスト予測
# ============================================================
def build_rf_features(draws, target_idx, n):
    """各数字について、特徴量と教師ラベルを構築"""
    window = 20
    if target_idx < window:
        return None, None

    features = []
    # 直近window回の出現 (0/1)
    for i in range(window):
        features.append(1.0 if n in draws[target_idx - 1 - i]["numbers"] else 0.0)
    # 直近5/10/20回の出現率
    for w in [5, 10, 20]:
        count = sum(1 for i in range(w) if n in draws[target_idx - 1 - i]["numbers"])
        features.append(count / w)
    # 最後に出てからの経過回数
    since_last = 0
    for i in range(target_idx - 1, -1, -1):
        if n in draws[i]["numbers"]:
            since_last = target_idx - 1 - i
            break
    features.append(since_last / 20.0)  # 正規化
    # 前回出たか
    features.append(1.0 if n in draws[target_idx - 1]["numbers"] else 0.0)

    label = 1 if n in draws[target_idx]["numbers"] else 0
    return features, label


def predict_rf(draws):
    """ランダムフォレストで各数字の次回出現確率を予測"""
    print("  Training Random Forest...")
    rf_scores = {}
    window = 20

    for n in range(1, 44):
        X, y = [], []
        for idx in range(window, len(draws)):
            feat, label = build_rf_features(draws, idx, n)
            if feat is not None:
                X.append(feat)
                y.append(label)

        X = np.array(X)
        y = np.array(y)

        if len(set(y)) < 2:
            rf_scores[n] = 0.5
            continue

        clf = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X, y)

        # 次回の特徴量を作成して予測
        next_feat, _ = build_rf_features(draws, len(draws) - 1, n)
        if next_feat is None:
            rf_scores[n] = 0.5
            continue

        # 最後のデータで次回を予測するために特徴量を再構築
        feat = []
        for i in range(window):
            feat.append(1.0 if n in draws[len(draws) - 1 - i]["numbers"] else 0.0)
        for w in [5, 10, 20]:
            count = sum(1 for i in range(w) if n in draws[len(draws) - 1 - i]["numbers"])
            feat.append(count / w)
        since_last = 0
        for i in range(len(draws) - 1, -1, -1):
            if n in draws[i]["numbers"]:
                since_last = len(draws) - 1 - i
                break
        feat.append(since_last / 20.0)
        feat.append(1.0 if n in draws[-1]["numbers"] else 0.0)

        prob = clf.predict_proba(np.array([feat]))[0]
        rf_scores[n] = float(prob[1]) if len(prob) > 1 else 0.5

    return rf_scores


# ============================================================
# 8. LSTM予測
# ============================================================
class LottoLSTM(nn.Module):
    def __init__(self, input_size=1, hidden_size=32, num_layers=1):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.fc(out[:, -1, :])
        return self.sigmoid(out)


def predict_lstm(draws, seq_len=30, epochs=50):
    """LSTMで各数字の次回出現確率を予測"""
    print("  Training LSTM...")
    torch.manual_seed(42)
    lstm_scores = {}

    for n in range(1, 44):
        # 時系列データ作成: 各回で出現=1, 未出現=0
        series = np.array([1.0 if n in d["numbers"] else 0.0 for d in draws], dtype=np.float32)

        if len(series) < seq_len + 1:
            lstm_scores[n] = 0.5
            continue

        # スライディングウィンドウでデータセット作成
        X, y = [], []
        for i in range(len(series) - seq_len):
            X.append(series[i:i + seq_len])
            y.append(series[i + seq_len])

        X = torch.tensor(np.array(X)).unsqueeze(-1)  # (samples, seq_len, 1)
        y = torch.tensor(np.array(y)).unsqueeze(-1)  # (samples, 1)

        model = LottoLSTM(input_size=1, hidden_size=32)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.005)
        criterion = nn.BCELoss()

        # 学習
        model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            output = model(X)
            loss = criterion(output, y)
            loss.backward()
            optimizer.step()

        # 次回の予測
        model.eval()
        with torch.no_grad():
            last_seq = torch.tensor(series[-seq_len:]).unsqueeze(0).unsqueeze(-1)
            prob = model(last_seq).item()

        lstm_scores[n] = prob

    return lstm_scores


# ============================================================
# 9. AI予想エンジン（v3: 10要素統合）
# ============================================================
MODES = {
    "balanced":        {"freq": 0.15, "drought": 0.12, "pull": 0.10, "pair": 0.10, "consec": 0.05, "recent": 0.08, "cycle": 0.12, "rf": 0.12, "lstm": 0.12, "random": 0.04},
    "frequency_heavy": {"freq": 0.30, "drought": 0.08, "pull": 0.07, "pair": 0.07, "consec": 0.03, "recent": 0.12, "cycle": 0.08, "rf": 0.08, "lstm": 0.08, "random": 0.09},
    "pull_heavy":      {"freq": 0.10, "drought": 0.08, "pull": 0.28, "pair": 0.10, "consec": 0.05, "recent": 0.04, "cycle": 0.08, "rf": 0.09, "lstm": 0.09, "random": 0.09},
    "zone_balanced":   {"freq": 0.12, "drought": 0.12, "pull": 0.07, "pair": 0.10, "consec": 0.05, "recent": 0.07, "cycle": 0.12, "rf": 0.10, "lstm": 0.10, "random": 0.15},
    "pair_heavy":      {"freq": 0.10, "drought": 0.08, "pull": 0.07, "pair": 0.22, "consec": 0.05, "recent": 0.07, "cycle": 0.08, "rf": 0.10, "lstm": 0.10, "random": 0.13},
    "ml_heavy":        {"freq": 0.08, "drought": 0.05, "pull": 0.05, "pair": 0.05, "consec": 0.02, "recent": 0.05, "cycle": 0.10, "rf": 0.25, "lstm": 0.25, "random": 0.10},
}

MODE_NAMES = {
    "balanced": "総合予想",
    "frequency_heavy": "出現頻度重視",
    "pull_heavy": "引っ張り重視",
    "zone_balanced": "数字帯バランス重視",
    "pair_heavy": "ペア重視",
    "ml_heavy": "AI(RF+LSTM)重視",
}


def normalize(values: dict) -> dict:
    """0-1に正規化"""
    vals = list(values.values())
    min_v, max_v = min(vals), max(vals)
    rng = max_v - min_v if max_v != min_v else 1
    return {k: (v - min_v) / rng for k, v in values.items()}


def generate_prediction(freq_data, pull_data, zone_data, pair_data, consec_data, cycle_data, rf_scores_raw, lstm_scores_raw, draws, weights):
    """1つの予想を生成（v3: 10要素統合）"""
    total_draws = len(draws)

    # --- スコア計算 ---

    # ① 出現頻度スコア（全期間）
    freq_scores = normalize({n: freq_data["counts"].get(str(n), 0) for n in range(1, 44)})

    # ② 直近重み付き頻度スコア（改善: 直近100回+300回の加重平均）
    recent_scores = {}
    for n in range(1, 44):
        r100 = float(freq_data["recent_100"].get(str(n), 0))
        r300 = float(freq_data["recent_300"].get(str(n), 0))
        # 直近100回を重視（0.6:0.4）
        recent_scores[n] = r100 * 0.6 + r300 * 0.4
    recent_scores = normalize(recent_scores)

    # ③ 干ばつスコア（改善: 平均間隔と比較した相対的な遅延度）
    drought_raw = {}
    for n in range(1, 44):
        current_drought = freq_data["drought"].get(str(n), 0)
        avg_interval = freq_data["avg_intervals"].get(str(n), 7)
        # 平均間隔に対してどれだけ遅延しているか（1.0 = 平均通り、2.0 = 平均の2倍遅い）
        if avg_interval > 0:
            drought_raw[n] = current_drought / avg_interval
        else:
            drought_raw[n] = 0
    drought_scores = normalize(drought_raw)

    # ④ 引っ張りスコア（改善: 直近N回の出現頻度でグラデーション化）
    pull_scores = {}
    recent_5 = [set(d["numbers"]) for d in draws[-5:]]
    for n in range(1, 44):
        # 直近5回での出現回数を加重（直近ほど重い）
        weighted_pull = 0.0
        weights_pull = [0.40, 0.25, 0.15, 0.12, 0.08]  # 最新→古い
        for i, nums in enumerate(reversed(recent_5)):
            if n in nums:
                weighted_pull += weights_pull[i]
        pull_scores[n] = weighted_pull
    pull_scores = normalize(pull_scores)

    # ⑤ 連番スコア
    consec_scores_raw = {n: consec_data["partner_counts"].get(str(n), 0) for n in range(1, 44)}
    consec_base_scores = normalize(consec_scores_raw)

    # ⑥ 周期スコア
    cycle_scores = normalize({n: cycle_data.get(str(n), {}).get("cycle_score", 0) for n in range(1, 44)})

    # ⑦ ランダムフォレストスコア
    rf_scores = normalize({n: rf_scores_raw.get(n, 0.5) for n in range(1, 44)})

    # ⑧ LSTMスコア
    lstm_scores = normalize({n: lstm_scores_raw.get(n, 0.5) for n in range(1, 44)})

    # ペアカウント辞書（全期間+直近を混合）
    pair_counts_all = pair_data.get("pair_counts", {})
    pair_counts_recent = pair_data.get("recent_pair_counts", {})

    # 合計値の制約（改善⑥: 標準偏差ベース ±1σ）
    sums = [sum(d["numbers"]) for d in draws]
    avg_sum = sum(sums) / len(sums)
    std_sum = math.sqrt(sum((s - avg_sum) ** 2 for s in sums) / len(sums))
    sum_range = (avg_sum - std_sum, avg_sum + std_sum)

    last_numbers = set(pull_data["last_draw_numbers"])

    # --- 改善⑦: 複数候補から最良を選ぶ（貪欲法のバイアス軽減） ---
    NUM_TRIALS = 20
    best_result = None
    best_score = -1

    for trial in range(NUM_TRIALS):
        selected = []
        sel_reasons = {}

        for step in range(6):
            candidates = []
            for n in range(1, 44):
                if n in selected:
                    continue

                # ペアスコア: 全期間60% + 直近200回40%
                pair_score = 0.0
                if selected:
                    for s in selected:
                        key = f"{min(n,s)}-{max(n,s)}"
                        all_c = pair_counts_all.get(key, 0)
                        rec_c = pair_counts_recent.get(key, 0) * (total_draws / min(200, total_draws))
                        pair_score += all_c * 0.6 + rec_c * 0.4
                    pair_score /= len(selected)

                # 連番ボーナス: 選出済みの数字の隣にある場合スコアアップ
                consec_bonus = consec_base_scores.get(n, 0)
                if selected:
                    for s in selected:
                        if abs(n - s) == 1:
                            consec_bonus = 1.0
                            break

                candidates.append((n, {
                    "freq": freq_scores.get(n, 0),
                    "recent": recent_scores.get(n, 0),
                    "drought": drought_scores.get(n, 0),
                    "pull": pull_scores.get(n, 0),
                    "pair_raw": pair_score,
                    "consec": consec_bonus,
                    "cycle": cycle_scores.get(n, 0),
                    "rf": rf_scores.get(n, 0),
                    "lstm": lstm_scores.get(n, 0),
                    "random": random.random(),
                }))

            # ペアスコアを正規化
            pair_raws = [c[1]["pair_raw"] for c in candidates]
            pr_min, pr_max = min(pair_raws), max(pair_raws)
            pr_range = pr_max - pr_min if pr_max != pr_min else 1
            for _, scores in candidates:
                scores["pair"] = (scores["pair_raw"] - pr_min) / pr_range

            # 総合スコア計算
            scored = []
            for n, scores in candidates:
                total = (
                    weights["freq"] * scores["freq"]
                    + weights["recent"] * scores["recent"]
                    + weights["drought"] * scores["drought"]
                    + weights["pull"] * scores["pull"]
                    + weights["pair"] * scores["pair"]
                    + weights["consec"] * scores["consec"]
                    + weights["cycle"] * scores["cycle"]
                    + weights["rf"] * scores["rf"]
                    + weights["lstm"] * scores["lstm"]
                    + weights["random"] * scores["random"]
                )
                scored.append((n, total, scores))

            scored.sort(key=lambda x: x[1], reverse=True)

            # トライアルごとにトップNからランダムに揺らす（改善⑦）
            if trial > 0 and len(scored) > 5:
                top_k = min(5 + trial // 3, len(scored))
                random.shuffle(scored[:top_k])

            # 制約チェックしながら選出
            found = False
            for n, total_score, scores in scored:
                test_selected = selected + [n]

                # 帯バランスチェック
                zones = [get_zone(x) for x in test_selected]
                zone_counts = Counter(zones)
                remaining = 6 - len(test_selected)

                if any(c > 3 for c in zone_counts.values()):
                    continue
                missing_zones = [z for z in ["low", "mid", "high"] if zone_counts.get(z, 0) == 0]
                if len(missing_zones) > remaining:
                    continue

                # 奇偶バランス（最大4まで）
                odds = sum(1 for x in test_selected if x % 2 == 1)
                evens = len(test_selected) - odds
                if odds > 4 or evens > 4:
                    continue

                # 最後の数字: 合計値チェック（改善⑥: ±1σ）
                if len(test_selected) == 6:
                    s = sum(test_selected)
                    if not (sum_range[0] <= s <= sum_range[1]):
                        continue

                selected.append(n)

                # 理由生成用にスコアを記録
                factor_scores = {
                    "freq": scores["freq"] * weights["freq"],
                    "recent": scores["recent"] * weights["recent"],
                    "drought": scores["drought"] * weights["drought"],
                    "pull": scores["pull"] * weights["pull"],
                    "pair": scores["pair"] * weights["pair"],
                    "consec": scores["consec"] * weights["consec"],
                    "cycle": scores["cycle"] * weights["cycle"],
                    "rf": scores["rf"] * weights["rf"],
                    "lstm": scores["lstm"] * weights["lstm"],
                }
                sel_reasons[str(n)] = {
                    "total_score": total_score,
                    "factor_scores": factor_scores,
                    "raw_scores": {k: v for k, v in scores.items() if k != "pair_raw"},
                }
                found = True
                break

            if not found:
                break

        if len(selected) != 6:
            continue

        # この候補セットの品質を評価
        trial_sum = sum(selected)
        sum_deviation = abs(trial_sum - avg_sum) / std_sum
        zones = Counter(get_zone(x) for x in selected)
        zone_balance = 1.0 / (1.0 + max(zones.values()) - min(zones.values()))
        odds = sum(1 for x in selected if x % 2 == 1)
        odd_balance = 1.0 - abs(odds - 3) / 3.0
        total_quality = sum(sel_reasons[str(n)]["total_score"] for n in selected)
        quality = total_quality * 0.4 + zone_balance * 0.2 + odd_balance * 0.2 + (1.0 - min(sum_deviation, 2.0) / 2.0) * 0.2

        if quality > best_score:
            best_score = quality
            best_result = (selected[:], dict(sel_reasons))

    if best_result is None:
        return {"numbers": [], "bonus": None, "bonus_reason": "", "reasons": {}, "metrics": {}}

    selected, sel_reasons = best_result
    selected.sort()

    # --- 選出理由の文章生成 ---
    reasons = {}
    for n in selected:
        info = sel_reasons[str(n)]
        factor_scores = info["factor_scores"]
        sorted_factors = sorted(factor_scores.items(), key=lambda x: x[1], reverse=True)
        top_factor = sorted_factors[0][0]
        second_factor = sorted_factors[1][0] if len(sorted_factors) > 1 else None

        freq_count = freq_data["counts"].get(str(n), 0)
        freq_pct = freq_data["percentages"].get(str(n), 0)
        r100_pct = freq_data["recent_100"].get(str(n), 0)
        r300_pct = freq_data["recent_300"].get(str(n), 0)
        drought_val = freq_data["drought"].get(str(n), 0)
        avg_interval = freq_data["avg_intervals"].get(str(n), 7)

        reason_parts = []

        # メイン理由
        if top_factor == "freq":
            reason_parts.append(f"全{total_draws}回中{freq_count}回出現（{freq_pct}%）と高い出現頻度を記録")
        elif top_factor == "recent":
            reason_parts.append(f"直近100回で{r100_pct}%と最近の出現率が高い（全期間{freq_pct}%）")
        elif top_factor == "drought":
            ratio = round(drought_val / avg_interval, 1) if avg_interval > 0 else 0
            reason_parts.append(f"平均{avg_interval:.0f}回間隔に対し{drought_val}回未出現（{ratio}倍の遅延）で出現期待が高い")
        elif top_factor == "pull":
            recent_count = sum(1 for d in draws[-5:] if n in d["numbers"])
            reason_parts.append(f"直近5回中{recent_count}回出現しており、連続出現の勢いあり")
        elif top_factor == "pair":
            reason_parts.append("選出済みの他の数字との同時出現回数が多く、相性が良い")
        elif top_factor == "consec":
            neighbors = [s for s in selected if abs(n - s) == 1 and s != n]
            if neighbors:
                reason_parts.append(f"{neighbors[0]}との連番ペアで出現しやすい傾向")
            else:
                reason_parts.append("連番を含む抽選で出やすい傾向がある")
        elif top_factor == "cycle":
            cd = cycle_data.get(str(n), {})
            dc = cd.get("dominant_cycle", "?")
            reason_parts.append(f"約{dc}回周期で出現するパターンを検出、次の出現タイミングに該当")
        elif top_factor == "rf":
            rf_prob = rf_scores_raw.get(n, 0.5)
            reason_parts.append(f"ランダムフォレストが出現確率{rf_prob:.1%}と高く予測")
        elif top_factor == "lstm":
            lstm_prob = lstm_scores_raw.get(n, 0.5)
            reason_parts.append(f"LSTMが時系列パターンから出現確率{lstm_prob:.1%}と予測")

        # サブ理由（2番目に効いた要素）
        if second_factor and second_factor != top_factor:
            if second_factor == "recent" and r100_pct > float(freq_pct):
                reason_parts.append(f"直近100回の出現率{r100_pct}%で上昇傾向")
            elif second_factor == "drought" and drought_val >= 8:
                ratio = round(drought_val / avg_interval, 1) if avg_interval > 0 else 0
                reason_parts.append(f"平均間隔の{ratio}倍となる{drought_val}回未出現")
            elif second_factor == "pull" and n in last_numbers:
                reason_parts.append("前回の抽選でも出現")
            elif second_factor == "freq" and float(freq_pct) > 14.0:
                reason_parts.append(f"全期間出現率{freq_pct}%と安定して高い")
            elif second_factor == "pair":
                reason_parts.append("他の選出数字との相性も良好")
            elif second_factor == "consec":
                neighbors = [s for s in selected if abs(n - s) == 1 and s != n]
                if neighbors:
                    reason_parts.append(f"{neighbors[0]}と連番")
            elif second_factor == "cycle":
                cd = cycle_data.get(str(n), {})
                reason_parts.append(f"約{cd.get('dominant_cycle', '?')}回周期のタイミング")
            elif second_factor == "rf":
                reason_parts.append(f"RF予測でも高評価")
            elif second_factor == "lstm":
                reason_parts.append(f"LSTM予測でも高評価")

        zone_name = {"low": "低帯(1-14)", "mid": "中帯(15-29)", "high": "高帯(30-43)"}[get_zone(n)]
        reason_parts.append(zone_name)

        reason_text = "。".join(reason_parts) + "。"

        reasons[str(n)] = {
            "score": round(info["total_score"], 4),
            "top_factor": top_factor,
            "reason_text": reason_text,
            "details": {k: round(v, 4) for k, v in info["raw_scores"].items()},
        }

    # --- ボーナス数字選出 ---
    bonus_candidates = []
    for n in range(1, 44):
        if n in selected:
            continue
        pair_score = 0.0
        for s in selected:
            key = f"{min(n,s)}-{max(n,s)}"
            all_c = pair_counts_all.get(key, 0)
            rec_c = pair_counts_recent.get(key, 0) * (total_draws / min(200, total_draws))
            pair_score += all_c * 0.6 + rec_c * 0.4
        pair_score /= len(selected)

        total = (
            weights["freq"] * freq_scores.get(n, 0)
            + weights["recent"] * recent_scores.get(n, 0)
            + weights["drought"] * drought_scores.get(n, 0)
            + weights["pull"] * pull_scores.get(n, 0)
            + weights["consec"] * consec_base_scores.get(n, 0)
            + weights["cycle"] * cycle_scores.get(n, 0)
            + weights["rf"] * rf_scores.get(n, 0)
            + weights["lstm"] * lstm_scores.get(n, 0)
            + weights["random"] * random.random()
        )
        bonus_candidates.append((n, total))
    bonus_candidates.sort(key=lambda x: x[1], reverse=True)
    bonus_number = bonus_candidates[0][0] if bonus_candidates else None

    # ボーナス数字の理由文
    bonus_reason = ""
    if bonus_number:
        bn = bonus_number
        b_freq_pct = freq_data["percentages"].get(str(bn), 0)
        b_drought = freq_data["drought"].get(str(bn), 0)
        b_avg_int = freq_data["avg_intervals"].get(str(bn), 7)
        b_r100 = freq_data["recent_100"].get(str(bn), 0)
        b_parts = ["本数字6個に次ぐ総合スコアで選出"]
        if float(b_r100) > float(b_freq_pct):
            b_parts.append(f"直近100回の出現率{b_r100}%で上昇傾向")
        elif float(b_freq_pct) > 14:
            b_parts.append(f"出現率{b_freq_pct}%と高頻度")
        if b_drought >= 8:
            ratio = round(b_drought / b_avg_int, 1) if b_avg_int > 0 else 0
            b_parts.append(f"平均間隔の{ratio}倍（{b_drought}回）未出現")
        if bn in last_numbers:
            b_parts.append("前回も出現")
        bonus_reason = "。".join(b_parts) + "。"

    # メトリクス
    odds = sum(1 for x in selected if x % 2 == 1)
    evens = 6 - odds
    zones = Counter(get_zone(x) for x in selected)
    total_sum = sum(selected)

    return {
        "numbers": selected,
        "bonus": bonus_number,
        "bonus_reason": bonus_reason,
        "reasons": reasons,
        "metrics": {
            "odd_even": f"{odds}:{evens}",
            "zones": f"{zones.get('low',0)}-{zones.get('mid',0)}-{zones.get('high',0)}",
            "sum": total_sum,
            "avg_sum": round(avg_sum, 1),
            "sum_std": round(std_sum, 1),
            "sum_range": f"{sum_range[0]:.0f}〜{sum_range[1]:.0f}",
        },
    }


def run_predictions(freq_data, pull_data, zone_data, pair_data, consec_data, cycle_data, rf_scores, lstm_scores, draws, period_label="all"):
    predictions = {}
    for mode_key, weights in MODES.items():
        random.seed(f"{date.today().isoformat()}_{mode_key}_{period_label}")
        predictions[mode_key] = generate_prediction(
            freq_data, pull_data, zone_data, pair_data, consec_data, cycle_data, rf_scores, lstm_scores, draws, weights
        )
        predictions[mode_key]["mode_name"] = MODE_NAMES[mode_key]
    return predictions


def analyze_period(draws, period_label="all"):
    """指定された抽選データに対して全分析 + 予想を実行"""
    print(f"  Frequency/Pull/Zone/Pair/Consecutive...")
    freq = analyze_frequency(draws)
    pull = analyze_pull(draws)
    zone = analyze_zone(draws)
    pairs = analyze_pairs(draws)
    consec = analyze_consecutive(draws)

    print(f"  Cycle analysis...")
    cycle = analyze_cycle(draws)

    print(f"  Random Forest...")
    rf_scores = predict_rf(draws)

    print(f"  LSTM...")
    lstm_scores = predict_lstm(draws)

    print(f"  Generating predictions...")
    predictions = run_predictions(freq, pull, zone, pairs, consec, cycle, rf_scores, lstm_scores, draws, period_label)

    sums = [sum(d["numbers"]) for d in draws]
    odds_counts = [sum(1 for n in d["numbers"] if n % 2 == 1) for d in draws]

    return {
        "frequency": freq,
        "pull": pull,
        "zone": zone,
        "consecutive": consec,
        "pairs": {
            "top_pairs": pairs["top_pairs"],
            "affinity": pairs["affinity"],
        },
        "cycle": cycle,
        "rf_scores": {str(k): round(v, 4) for k, v in rf_scores.items()},
        "lstm_scores": {str(k): round(v, 4) for k, v in lstm_scores.items()},
        "predictions": predictions,
        "summary_stats": {
            "total_draws": len(draws),
            "avg_sum": round(sum(sums) / len(sums), 1),
            "sum_std": round(math.sqrt(sum((s - sum(sums) / len(sums)) ** 2 for s in sums) / len(sums)), 1),
            "avg_odd_count": round(sum(odds_counts) / len(odds_counts), 1),
            "date_range": [draws[0]["date"], draws[-1]["date"]],
        },
        "recent_draws": [
            {
                "round": d["round"],
                "date": d["date"],
                "numbers": d["numbers"],
                "bonus": d["bonus"],
                "sum": sum(d["numbers"]),
                "odd_even": f"{sum(1 for n in d['numbers'] if n % 2 == 1)}:{sum(1 for n in d['numbers'] if n % 2 == 0)}",
                "zones": f"{sum(1 for n in d['numbers'] if n <= 14)}-{sum(1 for n in d['numbers'] if 15 <= n <= 29)}-{sum(1 for n in d['numbers'] if n >= 30)}",
            }
            for d in draws[-20:]
        ],
    }


# ============================================================
# メイン
# ============================================================
PERIOD_SIZES = [100, 200, 300, 400]  # 直近N回

def main():
    print("=== LOTO6 Analyzer v2 (マルチ期間対応) ===")
    data = load_data()
    all_draws = data["draws"]
    print(f"Loaded {len(all_draws)} draws")

    # 全期間の分析
    print(f"\n--- 全期間 ({len(all_draws)}回) ---")
    result_all = analyze_period(all_draws, "all")

    # 各期間の分析
    periods = {"all": result_all}
    for size in PERIOD_SIZES:
        if len(all_draws) < size:
            print(f"\n--- 直近{size}回: データ不足のためスキップ ---")
            continue
        period_draws = all_draws[-size:]
        label = str(size)
        print(f"\n--- 直近{size}回 (第{period_draws[0]['round']}回〜第{period_draws[-1]['round']}回) ---")
        periods[label] = analyze_period(period_draws, label)

    # 期間ラベル一覧（フロントエンドのスライダー用）
    period_labels = []
    for size in PERIOD_SIZES:
        if str(size) in periods:
            pd = all_draws[-size:]
            period_labels.append({
                "key": str(size),
                "label": f"直近{size}回",
                "range": f"第{pd[0]['round']}回〜第{pd[-1]['round']}回",
                "draws": size,
            })
    period_labels.append({
        "key": "all",
        "label": f"全期間",
        "range": f"第{all_draws[0]['round']}回〜第{all_draws[-1]['round']}回",
        "draws": len(all_draws),
    })

    output = {
        "last_updated": data["last_updated"],
        "latest_round": all_draws[-1]["round"],
        "period_labels": period_labels,
        "periods": periods,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nAnalysis saved to {OUTPUT_PATH}")

    # 結果表示
    for period_key, result in periods.items():
        label = f"直近{period_key}回" if period_key != "all" else "全期間"
        print(f"\n=== {label} ===")
        for mode_key, pred in result["predictions"].items():
            print(f"  {pred['mode_name']}: {pred['numbers']} + bonus:{pred['bonus']}")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
