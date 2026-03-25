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
    });
  });
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

  document.getElementById("periodSection").style.display = "block";
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
function renderPrediction() {
  const container = document.getElementById("predictionResult");
  const modeInputs = document.querySelectorAll('input[name="mode"]');
  const data = getPeriodData();

  function render() {
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const pred = data.predictions[mode];
    const isFeatured = mode === "balanced";
    const sumRange = pred.metrics.sum_range || "";
    const periodLabel = currentPeriod === "all" ? "全期間" : `直近${currentPeriod}回`;

    container.innerHTML = `
      <div class="glossary-box">
        <h4>📖 用語説明</h4>
        <dl class="glossary">
          <dt>出現頻度</dt><dd>選択期間でその数字が何回出たかの割合。高いほど「よく出る数字」。</dd>
          <dt>直近頻度</dt><dd>直近100回・300回に限定した出現率。全期間より高ければ「最近調子が良い」数字。</dd>
          <dt>干ばつ度</dt><dd>その数字の平均出現間隔に対して、今どれだけ出ていないかの倍率。1.0なら平均通り、2.0なら平均の2倍出ていない。</dd>
          <dt>引っ張り</dt><dd>直近5回の抽選で何回出たかを加重評価。最新回ほど重く計算し、連続出現の勢いを測る。</dd>
          <dt>ペア相性</dt><dd>選出済みの他の数字と過去に同時に出た回数。全期間60%＋直近200回40%の混合評価。</dd>
          <dt>連番傾向</dt><dd>隣り合う数字（例: 14と15）が一緒に出やすい傾向があるかの指標。</dd>
          <dt>奇偶比率</dt><dd>6個中の奇数と偶数の内訳。過去データでは3:3〜4:2が多い。</dd>
          <dt>数字帯</dt><dd>低帯(1-14)・中帯(15-29)・高帯(30-43)の3グループの内訳。各帯から最低1個、最大3個選出。</dd>
          <dt>合計値</dt><dd>6個の合計。${periodLabel}の平均±1標準偏差の範囲（${sumRange}）に収まるよう制約。</dd>
          <dt>分析期間</dt><dd>上のスライダーで変更可能。直近100〜400回に絞ると「最近の傾向」を重視した予想になる。全期間は長期的な安定傾向を反映。</dd>
        </dl>
      </div>

      <div class="prediction-card ${isFeatured ? "featured" : ""}">
        <h3>${pred.mode_name}  <span class="period-badge">${periodLabel}</span></h3>
        <div class="balls-row">
          ${pred.numbers.map((n) => createBall(n)).join("")}
          <span style="color: var(--text-muted); align-self: center; margin: 0 4px;">+</span>
          ${pred.bonus ? createBall(pred.bonus, "ball-bonus") : ""}
        </div>
        <p class="ball-legend">● 本数字 ○ ボーナス数字</p>
        <div class="prediction-metrics">
          <div>奇偶 <span class="value">${pred.metrics.odd_even}</span></div>
          <div>帯 <span class="value">${pred.metrics.zones}</span></div>
          <div>合計 <span class="value">${pred.metrics.sum}</span></div>
          <div>許容範囲 <span class="value">${sumRange}</span></div>
        </div>
        <button class="reasons-toggle" onclick="toggleReasons(this)">選出根拠を表示</button>
        <div class="reasons-detail">
          ${pred.numbers
            .map((n) => {
              const r = pred.reasons[String(n)];
              return `<div class="reason-item">
                <span class="ball ball-small ball-gold">${n}</span>
                <span class="reason-text">${r.reason_text}</span>
              </div>`;
            })
            .join("")}
          ${pred.bonus ? `<div class="reason-item bonus-reason">
            <span class="ball ball-small ball-bonus">${pred.bonus}</span>
            <span class="reason-text">${pred.bonus_reason || "本数字に次ぐスコアで選出。"}</span>
          </div>` : ""}
        </div>
      </div>
    `;
  }

  modeInputs.forEach((input) => input.addEventListener("change", render));
  render();
}

function toggleReasons(btn) {
  const detail = btn.nextElementSibling;
  detail.classList.toggle("open");
  btn.textContent = detail.classList.contains("open") ? "選出根拠を閉じる" : "選出根拠を表示";
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
            freq.hot.includes(n) ? "#ff6b6b" : freq.cold.includes(n) ? "#4ecdc4" : "#FFD700"
          ),
          borderRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        title: { display: true, text: "数字別 出現回数", color: "#e0e0e0" },
      },
      scales: {
        x: { ticks: { color: "#888" }, grid: { display: false } },
        y: { ticks: { color: "#888" }, grid: { color: "rgba(255,255,255,0.05)" } },
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
        <div class="val" style="color: ${intensity > 0.5 ? "#4ecdc4" : "#ff6b6b"}">${d.val}回前</div>
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
          backgroundColor: "#FFD700",
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        title: { display: true, text: "引っ張り数の分布", color: "#e0e0e0" },
      },
      scales: {
        x: { ticks: { color: "#888" }, grid: { display: false } },
        y: { ticks: { color: "#888" }, grid: { color: "rgba(255,255,255,0.05)" } },
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
          backgroundColor: ["#ff6b6b", "#FFD700", "#4ecdc4"],
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: "#e0e0e0" } },
        title: { display: true, text: "数字帯の出現比率", color: "#e0e0e0" },
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
