/* ============================================================
   LOTO6 ANALYZER - Frontend Application (マルチ期間対応)
   ============================================================ */

let analysisData = null;
let rawData = null;
let currentPeriod = "all"; // 現在選択中の期間

/** 現在の期間のデータを返す */
function getPeriodData() {
  return analysisData.periods[currentPeriod];
}

// ============================================================
// Init
// ============================================================
document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  await loadData();
});

async function loadData() {
  const t = Date.now();
  try {
    const [analysisRes, rawRes] = await Promise.all([
      fetch(`data/analysis.json?t=${t}`),
      fetch(`data/loto6_data.json?t=${t}`),
    ]);
    analysisData = await analysisRes.json();
    rawData = await rawRes.json();
    setupPeriodSlider();
    renderAll();
  } catch (e) {
    document.querySelector("main").innerHTML =
      '<div class="loading">データの読み込みに失敗しました。データが生成されていない可能性があります。</div>';
    console.error(e);
  }
}

function renderAll() {
  renderStatsBar();
  renderPrediction();
  renderFrequency();
  renderPull();
  renderZone();
  renderPair();
  renderRecent();
  renderArchive();
  renderMonteCarlo();
}

// ============================================================
// Tabs
// ============================================================
function setupTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      updatePeriodVisibility();
      // 非表示タブ内で生成されたグラフは幅0で潰れるため、表示された時にリサイズし直す
      [freqChart, pullChart, zoneChart].forEach((c) => { if (c) c.resize(); });
    });
  });
}

/** 期間スライダーの表示制御：AI予想タブは全期間を並べて表示するのでスライダーを隠す */
function updatePeriodVisibility() {
  const section = document.getElementById("periodSection");
  if (!section || section.dataset.ready !== "1") return;
  const activeTab = document.querySelector(".tab.active");
  const isPrediction = activeTab && activeTab.dataset.tab === "prediction";
  section.style.display = isPrediction ? "none" : "block";
}

// ============================================================
// Period Slider
// ============================================================
function setupPeriodSlider() {
  const labels = analysisData.period_labels;
  if (!labels || labels.length <= 1) return;

  const slider = document.getElementById("periodSlider");
  const display = document.getElementById("periodDisplay");
  if (!slider || !display) return;

  slider.min = 0;
  slider.max = labels.length - 1;
  slider.value = labels.length - 1; // デフォルトは全期間（最後）
  slider.step = 1;

  function update() {
    const idx = parseInt(slider.value);
    const info = labels[idx];
    currentPeriod = info.key;
    display.innerHTML = `<span class="period-name">${info.label}</span><span class="period-range">${info.range}（${info.draws}回分）</span>`;
    renderAll();
  }

  slider.addEventListener("input", update);
  update();

  const section = document.getElementById("periodSection");
  section.dataset.ready = "1";
  updatePeriodVisibility();
}

// ============================================================
// Stats Bar
// ============================================================
function renderStatsBar() {
  const s = getPeriodData().summary_stats;
  document.getElementById("statsBar").innerHTML = `
    分析対象 <span>${s.total_draws}</span> 回分 ｜
    期間 <span>${s.date_range[0]}</span> 〜 <span>${s.date_range[1]}</span> ｜
    最終更新 <span>${analysisData.last_updated.split("T")[0]}</span>
  `;
}

// ============================================================
// Helpers
// ============================================================
function createBall(num, cls = "ball-gold") {
  return `<span class="ball ${cls}">${num}</span>`;
}

function createSmallBall(num, cls = "ball-gold") {
  return `<span class="ball ball-small ${cls}">${num}</span>`;
}

// ============================================================
// AI Prediction
// ============================================================
// 予想モードの表示順（データの mode_name をそのまま見出しに使う）
const MODE_ORDER = ["balanced", "frequency_heavy", "pull_heavy", "zone_balanced", "pair_heavy", "ml_heavy"];

function renderPrediction() {
  const container = document.getElementById("predictionResult");
  const periods = analysisData.period_labels; // [直近100, 200, 300, 400, 全期間]

  const glossary = `
    <div class="glossary-box">
      <h4>📖 用語説明</h4>
      <dl class="glossary">
        <dt>出現頻度</dt><dd>その期間で数字が何回出たかの割合。高いほど「よく出る数字」。</dd>
        <dt>直近頻度</dt><dd>直近100回・300回に限定した出現率。全期間より高ければ「最近調子が良い」数字。</dd>
        <dt>干ばつ度</dt><dd>その数字の平均出現間隔に対して、今どれだけ出ていないかの倍率。1.0なら平均通り、2.0なら平均の2倍出ていない。</dd>
        <dt>引っ張り</dt><dd>直近5回の抽選で何回出たかを加重評価。最新回ほど重く計算し、連続出現の勢いを測る。</dd>
        <dt>ペア相性</dt><dd>選出済みの他の数字と過去に同時に出た回数。全期間60%＋直近200回40%の混合評価。</dd>
        <dt>連番傾向</dt><dd>隣り合う数字（例: 14と15）が一緒に出やすい傾向があるかの指標。</dd>
        <dt>N回周期</dt><dd>各数字が「だいたいN回おきに出る」という周期パターンを検出。次の出現タイミングに近いほどスコアが高い。</dd>
        <dt>ランダムフォレスト</dt><dd>機械学習モデル。過去の出現パターン（直近20回の出現履歴、出現率、間隔等）から次回の出現確率を予測。100本の決定木の多数決で判断。</dd>
        <dt>LSTM</dt><dd>時系列ディープラーニングモデル。各数字の出現/未出現の時系列データを学習し、パターンの「流れ」から次回の出現確率を予測。</dd>
        <dt>🎲 モンテカルロ信頼度</dt><dd>各数字の統計スコアを重みとした抽選を1万回シミュレーションし、その数字が選ばれた割合。詳しくは「モンテカルロ信頼度」タブを参照。</dd>
        <dt>奇偶比率</dt><dd>6個中の奇数と偶数の内訳。過去データでは3:3〜4:2が多い。</dd>
        <dt>数字帯</dt><dd>低帯(1-14)・中帯(15-29)・高帯(30-43)の3グループの内訳。各帯から最低1個、最大3個選出。</dd>
        <dt>合計値</dt><dd>6個の合計。各期間の平均±1標準偏差の範囲に収まるよう制約。</dd>
        <dt>分析期間</dt><dd>各カードに直近100〜400回・全期間の予想を並べて表示。直近に絞るほど「最近の傾向」を、全期間は長期的な安定傾向を反映。</dd>
      </dl>
    </div>`;

  const cards = MODE_ORDER.map((mode) => {
    const base = analysisData.periods.all.predictions[mode];
    if (!base) return "";
    const isFeatured = mode === "balanced";
    const modeName = base.mode_name;

    const rows = periods
      .map((pInfo) => {
        const pdata = analysisData.periods[pInfo.key];
        const pred = pdata && pdata.predictions[mode];
        if (!pred) return "";

        // 予想が空（制約を満たす組が見つからなかった期間）はメッセージ表示
        if (!pred.numbers || pred.numbers.length === 0) {
          return `
            <div class="period-row">
              <div class="period-row-main">
                <span class="period-tag">${pInfo.label}</span>
                <span class="period-empty">この期間はデータ条件により予想を生成できませんでした</span>
              </div>
            </div>`;
        }

        const balls =
          pred.numbers.map((n) => createSmallBall(n)).join("") +
          `<span class="plus">+</span>` +
          (pred.bonus ? createSmallBall(pred.bonus, "ball-bonus") : "");

        const reasonsHtml =
          pred.numbers
            .map((n) => {
              const r = pred.reasons[String(n)];
              const mc = r.monte_carlo_pct != null ? `<span class="mc-badge" title="重み付き非復元抽出を1万回シミュレーションした際にこの数字が選ばれた割合">🎲 ${r.monte_carlo_pct}%</span>` : "";
              return `<div class="reason-item">
                <span class="ball ball-small ball-gold">${n}</span>
                <span class="reason-text">${r.reason_text}${mc}</span>
              </div>`;
            })
            .join("") +
          (pred.bonus
            ? `<div class="reason-item bonus-reason">
                <span class="ball ball-small ball-bonus">${pred.bonus}</span>
                <span class="reason-text">${pred.bonus_reason || "本数字に次ぐスコアで選出。"}</span>
              </div>`
            : "");

        return `
          <div class="period-row">
            <div class="period-row-main">
              <span class="period-tag">${pInfo.label}</span>
              <div class="balls-row compact">${balls}</div>
              <span class="period-metrics">奇偶 ${pred.metrics.odd_even} ｜ 合計 ${pred.metrics.sum}</span>
            </div>
            <button class="reasons-toggle sm" onclick="toggleReasons(this)">選出根拠 ▾</button>
            <div class="reasons-detail">${reasonsHtml}</div>
          </div>`;
      })
      .join("");

    return `
      <div class="prediction-card ${isFeatured ? "featured" : ""}">
        <h3>${modeName}</h3>
        <div class="period-rows">${rows}</div>
      </div>`;
  }).join("");

  container.innerHTML = glossary + `<p class="ball-legend">● 本数字 ○ ボーナス数字</p>` + cards;
}

function toggleReasons(btn) {
  const detail = btn.nextElementSibling;
  const open = detail.classList.toggle("open");
  btn.textContent = open ? "選出根拠を閉じる ▴" : "選出根拠 ▾";
}

// ============================================================
// Frequency
// ============================================================
let freqChart = null;
function renderFrequency() {
  const freq = getPeriodData().frequency;
  const labels = Array.from({ length: 43 }, (_, i) => i + 1);
  const counts = labels.map((n) => freq.counts[String(n)] || 0);

  const ctx = document.getElementById("freqChart").getContext("2d");
  if (freqChart) freqChart.destroy();
  freqChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "出現回数",
          data: counts,
          backgroundColor: labels.map((n) =>
            freq.hot.includes(n) ? "#e08a7a" : freq.cold.includes(n) ? "#57b0a5" : "#d6b24e"
          ),
          borderRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        title: { display: true, text: "数字別 出現回数", color: "#3a3843" },
      },
      scales: {
        x: { ticks: { color: "#888" }, grid: { display: false } },
        y: { ticks: { color: "#888" }, grid: { color: "rgba(0,0,0,0.06)" } },
      },
    },
  });

  document.getElementById("hotList").innerHTML = `<ul class="rank-list">${freq.hot
    .map(
      (n, i) =>
        `<li><span class="rank">${i + 1}</span> <span>${n}</span> <span>${freq.counts[String(n)]}回 (${freq.percentages[String(n)]}%)</span></li>`
    )
    .join("")}</ul>`;

  document.getElementById("coldList").innerHTML = `<ul class="rank-list">${freq.cold
    .map(
      (n, i) =>
        `<li><span class="rank">${i + 1}</span> <span>${n}</span> <span>${freq.counts[String(n)]}回 (${freq.percentages[String(n)]}%)</span></li>`
    )
    .join("")}</ul>`;

  const droughtNums = labels.map((n) => ({
    num: n,
    val: freq.drought[String(n)] || 0,
  }));
  const maxDrought = Math.max(...droughtNums.map((d) => d.val));

  document.getElementById("droughtGrid").innerHTML = droughtNums
    .map((d) => {
      const intensity = maxDrought > 0 ? d.val / maxDrought : 0;
      const cls = intensity > 0.7 ? "cold" : intensity < 0.2 ? "hot" : "";
      return `<div class="grid-cell ${cls}">
        <div class="num">${d.num}</div>
        <div class="val" style="color: ${intensity > 0.5 ? "#57b0a5" : "#e08a7a"}">${d.val}回前</div>
      </div>`;
    })
    .join("");
}

// ============================================================
// Pull
// ============================================================
let pullChart = null;
function renderPull() {
  const pull = getPeriodData().pull;

  document.getElementById("pullAvg").innerHTML = `
    <div class="number">${pull.average}</div>
    <div class="label">平均引っ張り数（前回からの重複数字数）</div>
  `;

  const labels = Object.keys(pull.distribution);
  const values = Object.values(pull.distribution);
  const ctx = document.getElementById("pullChart").getContext("2d");
  if (pullChart) pullChart.destroy();
  pullChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels.map((l) => `${l}個`),
      datasets: [
        {
          label: "回数",
          data: values,
          backgroundColor: "#d6b24e",
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        title: { display: true, text: "引っ張り数の分布", color: "#3a3843" },
      },
      scales: {
        x: { ticks: { color: "#888" }, grid: { display: false } },
        y: { ticks: { color: "#888" }, grid: { color: "rgba(0,0,0,0.06)" } },
      },
    },
  });

  const rows = pull.recent_pulls
    .slice()
    .reverse()
    .map(
      (p) => `<tr>
      <td>${p.round}</td>
      <td>${p.date}</td>
      <td>${p.numbers.map((n) => createSmallBall(n, p.pulled.includes(n) ? "ball-gold" : "ball-bonus")).join("")}</td>
      <td>${p.pull_count}個</td>
    </tr>`
    )
    .join("");

  document.getElementById("pullTable").innerHTML = `
    <table class="data-table">
      <thead><tr><th>回</th><th>日付</th><th>数字（金=引っ張り）</th><th>重複数</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ============================================================
// Zone
// ============================================================
let zoneChart = null;
function renderZone() {
  const zone = getPeriodData().zone;

  const ctx = document.getElementById("zoneChart").getContext("2d");
  if (zoneChart) zoneChart.destroy();
  zoneChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["低帯 (1-14)", "中帯 (15-29)", "高帯 (30-43)"],
      datasets: [
        {
          data: [zone.zone_averages.low, zone.zone_averages.mid, zone.zone_averages.high],
          backgroundColor: ["#e08a7a", "#d6b24e", "#57b0a5"],
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: "#3a3843" } },
        title: { display: true, text: "数字帯の出現比率", color: "#3a3843" },
      },
    },
  });

  const rows = zone.top_patterns
    .map(
      (p, i) => `<tr>
      <td style="color: var(--gold); font-weight: bold">${i + 1}</td>
      <td>${p.pattern}</td>
      <td>${p.count}回</td>
      <td>${p.percentage}%</td>
    </tr>`
    )
    .join("");

  document.getElementById("zonePatterns").innerHTML = `
    <table class="data-table">
      <thead><tr><th>#</th><th>パターン（低-中-高）</th><th>回数</th><th>割合</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ============================================================
// Pair
// ============================================================
function renderPair() {
  const pairs = getPeriodData().pairs;

  const rows = pairs.top_pairs
    .map(
      (p, i) => `<tr>
      <td style="color: var(--gold)">${i + 1}</td>
      <td>${createSmallBall(p.pair[0])} ${createSmallBall(p.pair[1])}</td>
      <td>${p.count}回</td>
    </tr>`
    )
    .join("");

  document.getElementById("pairTable").innerHTML = `
    <table class="data-table">
      <thead><tr><th>#</th><th>ペア</th><th>同時出現</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  const selector = document.getElementById("numberSelector");
  selector.innerHTML = Array.from({ length: 43 }, (_, i) => i + 1)
    .map((n) => `<button class="num-btn" data-num="${n}">${n}</button>`)
    .join("");

  // イベントリスナーの重複を防ぐためcloneで置換
  const newSelector = selector.cloneNode(true);
  selector.parentNode.replaceChild(newSelector, selector);

  newSelector.addEventListener("click", (e) => {
    if (!e.target.classList.contains("num-btn")) return;
    newSelector.querySelectorAll(".num-btn").forEach((b) => b.classList.remove("selected"));
    e.target.classList.add("selected");
    showAffinity(e.target.dataset.num);
  });
}

function showAffinity(num) {
  const affinity = getPeriodData().pairs.affinity[String(num)];
  if (!affinity) return;

  document.getElementById("affinityResult").innerHTML = `
    <div style="margin-top: 1rem">
      <p style="color: var(--text-muted); margin-bottom: 0.5rem">${num} と相性の良い数字 TOP5:</p>
      <div class="balls-row">
        ${affinity.map((a) => `<div style="text-align:center">${createSmallBall(a.number)}<br><small style="color:var(--text-muted)">${a.count}回</small></div>`).join("")}
      </div>
    </div>
  `;
}

// ============================================================
// Recent Results
// ============================================================
function renderRecent() {
  const recent = getPeriodData().recent_draws;
  const rows = recent
    .slice()
    .reverse()
    .map(
      (d) => `<tr>
      <td>${d.round}</td>
      <td>${d.date}</td>
      <td>${d.numbers.map((n) => createSmallBall(n)).join("")} ${createSmallBall(d.bonus, "ball-bonus")}</td>
      <td>${d.odd_even}</td>
      <td>${d.zones}</td>
      <td>${d.sum}</td>
    </tr>`
    )
    .join("");

  document.getElementById("recentTable").innerHTML = `
    <table class="data-table">
      <thead><tr><th>回</th><th>日付</th><th>数字 (+ bonus)</th><th>奇偶</th><th>帯</th><th>合計</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ============================================================
// Archive
// ============================================================
function renderArchive() {
  const archive = analysisData.archive || [];
  const modeStats = analysisData.mode_stats || {};
  const statsSection = document.getElementById("modeStatsSection");
  const listSection = document.getElementById("archiveList");

  // モード別成績サマリー
  if (Object.keys(modeStats).length > 0 && modeStats["all"]) {
    const allStats = modeStats["all"];
    let statsHtml = `<div class="card"><h3>📈 モード別 累計成績（全期間ベース）</h3>`;
    statsHtml += `<table class="data-table"><thead><tr>
      <th>モード</th><th>予想回数</th><th>平均一致数</th><th>最高一致</th>
      <th>5等(3個)</th><th>4等(4個)</th><th>3等(5個)</th><th>2等(5+B)</th><th>1等(6個)</th>
    </tr></thead><tbody>`;

    for (const [modeKey, s] of Object.entries(allStats.modes)) {
      const avg = s.total_rounds > 0 ? (s.total_matched / s.total_rounds).toFixed(2) : "-";
      statsHtml += `<tr>
        <td>${s.mode_name}</td>
        <td>${s.total_rounds}</td>
        <td><span class="value">${avg}</span></td>
        <td><span class="value">${s.best_match}</span></td>
        <td>${s.prize_counts["5th"]}</td>
        <td>${s.prize_counts["4th"]}</td>
        <td>${s.prize_counts["3rd"]}</td>
        <td>${s.prize_counts["2nd"]}</td>
        <td>${s.prize_counts["1st"]}</td>
      </tr>`;
    }
    statsHtml += `</tbody></table></div>`;
    statsSection.innerHTML = statsHtml;

    // ランダム基準（モンテカルロ・シミュレーション）との比較
    const baseline = allStats.random_baseline;
    const rbSection = document.getElementById("randomBaselineSection");
    if (baseline && rbSection) {
      rbSection.innerHTML = `
        <div class="card">
          <h3>🎲 ランダム基準との比較（モンテカルロ・シミュレーション）</h3>
          <p style="color:var(--text-muted); font-size:0.85rem; margin-bottom:0.8rem;">
            「完全にランダムな6個」を${baseline.n_simulations.toLocaleString()}回シミュレーションし、実際に予想した${baseline.total_rounds}回分に換算した場合の期待値です。AIモードの実績が上の表と比べて優れているかの参考値としてご覧ください。
          </p>
          <div class="prediction-metrics">
            <div>平均一致数(ランダム) <span class="value">${baseline.avg_matched}</span></div>
            <div>4等 期待値 <span class="value">${baseline.prize_expected["4th"]}</span></div>
            <div>3等 期待値 <span class="value">${baseline.prize_expected["3rd"]}</span></div>
            <div>2等 期待値 <span class="value">${baseline.prize_expected["2nd"]}</span></div>
            <div>1等 期待値 <span class="value">${baseline.prize_expected["1st"]}</span></div>
          </div>
        </div>
      `;
    } else if (rbSection) {
      rbSection.innerHTML = "";
    }
  } else {
    statsSection.innerHTML = `<div class="card"><p style="color:var(--text-muted)">まだ答え合わせ済みのデータがありません。次回の抽選結果が反映されると、ここに成績が表示されます。</p></div>`;
    const rbSection = document.getElementById("randomBaselineSection");
    if (rbSection) rbSection.innerHTML = "";
  }

  // アーカイブ一覧（新しい順）
  if (archive.length === 0) {
    listSection.innerHTML = `<div class="card"><p style="color:var(--text-muted)">アーカイブはまだありません。</p></div>`;
    return;
  }

  let listHtml = "";
  const sorted = [...archive].reverse();

  for (const entry of sorted) {
    const verified = entry.verified;
    const statusBadge = verified
      ? '<span class="badge badge-verified">答え合わせ済</span>'
      : '<span class="badge badge-pending">結果待ち</span>';

    listHtml += `<div class="card archive-entry">`;
    listHtml += `<h3>第${entry.predicted_round}回予想 ${statusBadge}</h3>`;
    listHtml += `<p style="color:var(--text-muted);font-size:0.8rem;">生成日: ${entry.generated_at.split("T")[0]} ｜ データ: 第${entry.data_up_to_round}回まで</p>`;

    // 実際の結果
    if (verified && entry.actual) {
      listHtml += `<div class="actual-result">`;
      listHtml += `<span style="color:var(--text-muted);font-size:0.85rem;">実際の結果:</span> `;
      listHtml += entry.actual.numbers.map(n => createSmallBall(n)).join("");
      listHtml += ` + ${createSmallBall(entry.actual.bonus, "ball-bonus")}`;
      listHtml += `<span style="color:var(--text-muted);font-size:0.8rem;margin-left:8px;">(${entry.actual.date})</span>`;
      listHtml += `</div>`;
    }

    // 各期間の予想（全期間のみ表示、他は折りたたみ）
    for (const [pkey, pdata] of Object.entries(entry.predictions_by_period)) {
      const isAll = pkey === "all";
      if (!isAll) continue; // メインは全期間のみ表示

      for (const [modeKey, pred] of Object.entries(pdata.modes)) {
        const matchCount = pred.match_count;
        const matched = new Set(pred.matched_numbers || []);
        const bonusHit = pred.bonus_matched;

        let matchLabel = "";
        if (verified) {
          const cls = matchCount >= 4 ? "match-high" : matchCount >= 3 ? "match-mid" : "match-low";
          matchLabel = `<span class="match-badge ${cls}">${matchCount}個一致${bonusHit ? " +B" : ""}</span>`;
          // 等級
          let prize = "";
          if (matchCount === 6) prize = "🥇 1等";
          else if (matchCount === 5 && bonusHit) prize = "🥈 2等";
          else if (matchCount === 5) prize = "🥉 3等";
          else if (matchCount === 4) prize = "4等";
          else if (matchCount === 3) prize = "5等";
          if (prize) matchLabel += ` <span class="prize-label">${prize}</span>`;
        }

        listHtml += `<div class="archive-pred-row">`;
        listHtml += `<span class="archive-mode-name">${pred.mode_name}</span> ${matchLabel}<br>`;

        // 数字表示（一致した数字はハイライト）
        listHtml += `<div class="archive-balls">`;
        for (const n of pred.numbers) {
          if (verified && matched.has(n)) {
            listHtml += `<span class="ball ball-small ball-matched">${n}</span>`;
          } else {
            listHtml += createSmallBall(n, verified ? "ball-miss" : "ball-gold");
          }
        }
        if (pred.bonus != null) {
          const bonusCls = verified ? (bonusHit ? "ball-matched" : "ball-miss") : "ball-bonus";
          listHtml += ` <span style="color:var(--text-muted);font-size:0.8rem;">+</span> `;
          listHtml += `<span class="ball ball-small ${bonusCls}">${pred.bonus}</span>`;
        }
        listHtml += `</div>`;

        // 選出根拠（折りたたみ）
        const reasonId = `reason-${entry.predicted_round}-${pkey}-${modeKey}`;
        listHtml += `<button class="reasons-toggle" onclick="toggleArchiveReason('${reasonId}')">選出根拠</button>`;
        listHtml += `<div id="${reasonId}" class="reasons-detail">`;
        for (const n of pred.numbers) {
          const r = pred.reasons[String(n)];
          if (r) {
            const isMatch = verified && matched.has(n);
            listHtml += `<div class="reason-item">
              <span class="ball ball-small ${isMatch ? 'ball-matched' : 'ball-gold'}">${n}</span>
              <span class="reason-text">${r.reason_text}</span>
            </div>`;
          }
        }
        if (pred.bonus != null && pred.bonus_reason) {
          listHtml += `<div class="reason-item bonus-reason">
            <span class="ball ball-small ball-bonus">${pred.bonus}</span>
            <span class="reason-text">${pred.bonus_reason}</span>
          </div>`;
        }
        listHtml += `</div>`;

        listHtml += `</div>`;
      }
    }

    // 他期間は折りたたみ
    const otherPeriodsId = `other-${entry.predicted_round}`;
    const otherPeriods = Object.entries(entry.predictions_by_period).filter(([k]) => k !== "all");
    if (otherPeriods.length > 0) {
      listHtml += `<button class="reasons-toggle" onclick="toggleArchiveReason('${otherPeriodsId}')">他の期間の予想を表示</button>`;
      listHtml += `<div id="${otherPeriodsId}" class="reasons-detail">`;

      for (const [pkey, pdata] of otherPeriods) {
        listHtml += `<div style="margin-top:0.8rem;"><strong style="color:var(--gold-dim)">${pdata.label}（${pdata.range}）</strong></div>`;
        for (const [modeKey, pred] of Object.entries(pdata.modes)) {
          const matched = new Set(pred.matched_numbers || []);
          const mc = pred.match_count;
          let mcLabel = verified && mc != null ? ` [${mc}個一致${pred.bonus_matched ? "+B" : ""}]` : "";

          listHtml += `<div class="archive-pred-row-compact">`;
          listHtml += `<span class="archive-mode-name">${pred.mode_name}${mcLabel}</span> `;
          for (const n of pred.numbers) {
            if (verified && matched.has(n)) {
              listHtml += `<span class="ball ball-small ball-matched">${n}</span>`;
            } else {
              listHtml += createSmallBall(n, verified ? "ball-miss" : "ball-gold");
            }
          }
          if (pred.bonus != null) {
            const bonusCls = verified ? (pred.bonus_matched ? "ball-matched" : "ball-miss") : "ball-bonus";
            listHtml += ` <span style="font-size:0.7rem;color:var(--text-muted);">+</span> <span class="ball ball-small ${bonusCls}">${pred.bonus}</span>`;
          }
          listHtml += `</div>`;
        }
      }
      listHtml += `</div>`;
    }

    listHtml += `</div>`;
  }

  listSection.innerHTML = listHtml;
}

function toggleArchiveReason(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle("open");
}

// ============================================================
// Monte Carlo (モンテカルロ信頼度)
// ============================================================
function renderMonteCarlo() {
  renderMcConfidenceGrid();
}

function renderMcConfidenceGrid() {
  const container = document.getElementById("mcConfidenceGrid");
  if (!container) return;

  const modeInput = document.querySelector('input[name="mode"]:checked');
  const mode = modeInput ? modeInput.value : "balanced";
  const pred = getPeriodData().predictions[mode];
  const mc = pred && pred.monte_carlo;
  if (!mc) {
    container.innerHTML = `<p style="color:var(--text-muted)">データがありません。</p>`;
    return;
  }

  const labels = Array.from({ length: 43 }, (_, i) => i + 1);
  const maxPct = Math.max(...labels.map((n) => mc[String(n)] || 0));

  container.innerHTML = labels
    .map((n) => {
      const pct = mc[String(n)] || 0;
      const isSelected = pred.numbers.includes(n);
      const intensity = maxPct > 0 ? pct / maxPct : 0;
      const color = intensity > 0.6 ? "#e08a7a" : intensity > 0.3 ? "#d6b24e" : "#57b0a5";
      return `<div class="grid-cell ${isSelected ? "hot" : ""}">
        <div class="num">${n}</div>
        <div class="val" style="color:${color}">${pct.toFixed(1)}%</div>
      </div>`;
    })
    .join("");
}

// ============================================================
// PDF Export
// ============================================================
function exportPDF() {
  const periods = analysisData.periods;
  const periodLabels = analysisData.period_labels;
  const latestRound = analysisData.latest_round;
  const nextRound = latestRound + 1;
  const updatedDate = analysisData.last_updated.split("T")[0];

  let html = `<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>LOTO6 ANALYZER - 予想レポート</title>
<style>
  @page { size: A4; margin: 15mm; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", sans-serif; color: #222; font-size: 11px; line-height: 1.5; }
  h1 { text-align: center; font-size: 20px; margin-bottom: 4px; }
  .subtitle { text-align: center; color: #666; font-size: 11px; margin-bottom: 12px; }
  .meta { text-align: center; color: #888; font-size: 10px; margin-bottom: 16px; border-bottom: 2px solid #FFD700; padding-bottom: 8px; }
  .period-section { margin-bottom: 16px; page-break-inside: avoid; }
  .period-title { background: #1a1a2e; color: #FFD700; padding: 5px 10px; font-size: 13px; font-weight: bold; border-radius: 4px; margin-bottom: 8px; }
  .mode-block { margin-bottom: 10px; padding: 8px; border: 1px solid #ddd; border-radius: 6px; page-break-inside: avoid; }
  .mode-name { font-weight: bold; font-size: 12px; color: #1a1a2e; margin-bottom: 4px; }
  .numbers { display: flex; gap: 6px; align-items: center; margin-bottom: 4px; flex-wrap: wrap; }
  .ball { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 50%; font-size: 13px; font-weight: bold; }
  .ball-main { background: #FFD700; color: #1a1a2e; }
  .ball-bonus { background: #fff; color: #FFD700; border: 2px solid #FFD700; }
  .plus { color: #999; font-size: 14px; }
  .metrics { color: #666; font-size: 10px; margin-bottom: 4px; }
  .reason { color: #444; font-size: 9.5px; line-height: 1.4; }
  .reason b { color: #1a1a2e; }
  .disclaimer { text-align: center; color: #999; font-size: 9px; margin-top: 16px; padding-top: 8px; border-top: 1px solid #ddd; }
  @media print { .no-print { display: none; } }
</style></head><body>`;

  html += `<h1>LOTO6 ANALYZER</h1>`;
  html += `<p class="subtitle">統計分析 × AI予想レポート</p>`;
  html += `<p class="meta">第${nextRound}回予想 ｜ データ最終更新: ${updatedDate} ｜ 分析対象: 第1回〜第${latestRound}回</p>`;

  // 各期間
  for (const pInfo of periodLabels) {
    const pKey = pInfo.key;
    const pData = periods[pKey];
    if (!pData) continue;

    html += `<div class="period-section">`;
    html += `<div class="period-title">${pInfo.label}（${pInfo.range} / ${pInfo.draws}回分）</div>`;

    const modes = ["balanced", "frequency_heavy", "pull_heavy", "zone_balanced", "pair_heavy", "ml_heavy"];
    for (const mode of modes) {
      const pred = pData.predictions[mode];
      if (!pred) continue;

      const balls = pred.numbers.map(n => `<span class="ball ball-main">${n}</span>`).join("");
      const bonus = pred.bonus ? `<span class="plus">+</span><span class="ball ball-bonus">${pred.bonus}</span>` : "";
      const m = pred.metrics;

      let reasonLines = pred.numbers.map(n => {
        const r = pred.reasons[String(n)];
        return r ? `<b>${n}</b>: ${r.reason_text}` : "";
      }).filter(x => x).join(" / ");

      if (pred.bonus && pred.bonus_reason) {
        reasonLines += ` / <b>B${pred.bonus}</b>: ${pred.bonus_reason}`;
      }

      html += `<div class="mode-block">`;
      html += `<div class="mode-name">${pred.mode_name}</div>`;
      html += `<div class="numbers">${balls} ${bonus}</div>`;
      html += `<div class="metrics">奇偶: ${m.odd_even} ｜ 帯: ${m.zones} ｜ 合計: ${m.sum} ｜ 範囲: ${m.sum_range || ""}</div>`;
      html += `<div class="reason">${reasonLines}</div>`;
      html += `</div>`;
    }

    html += `</div>`;
  }

  html += `<p class="disclaimer">本ツールは過去の抽選データに基づく統計分析であり、将来の当選を予測・保証するものではありません。宝くじの購入は自己責任でお願いします。</p>`;
  html += `</body></html>`;

  // HTMLファイルとしてダウンロード（ブラウザで開いてPDF保存可能）
  const blob = new Blob([html], { type: "text/html; charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `LOTO6_予想レポート_第${nextRound}回_${updatedDate}.html`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  alert("HTMLファイルがダウンロードされました。\\nブラウザで開いて「ファイル → PDFとして書き出す」でPDFに変換できます。");
}
