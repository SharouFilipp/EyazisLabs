"""Графики результатов тестирования для отчёта (по results/benchmark.json)."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results"
b = json.loads((OUT / "benchmark.json").read_text(encoding="utf-8"))
G = b["groups"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False})
VAR = [("full", "SE: Score·Posd·Posp", "#2f5aa8"), ("ostis", "семантический OSTIS", "#3c9a5f"),
       ("score_posp", "Score·Posp", "#9bb7e8"), ("lead", "Lead-N", "#e0a03c"), ("random", "Random-N", "#b8b8b8")]

# 1. F1 по группам документов (N = 10)
groups = [("fr_cs", "франц., CS"), ("fr_lit", "франц., лит."), ("it_cs", "итал., CS"), ("it_lit", "итал., лит."),
          ("all", "все")]
fig, ax = plt.subplots(figsize=(8, 3.8))
w = 0.16
for k, (v, name, c) in enumerate(VAR):
    xs = [i + (k - 2) * w for i in range(len(groups))]
    ys = [100 * G[g]["by_n"]["10"][v]["f1"] for g, _ in groups]
    ax.bar(xs, ys, w, label=name, color=c)
ax.set_xticks(range(len(groups)), [n for _, n in groups])
ax.set_ylabel("F1, %"); ax.set_ylim(0, 70); ax.grid(axis="y", alpha=.3)
ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.13), frameon=False, fontsize=8.5)
fig.tight_layout(); fig.savefig(OUT / "f1_groups.png", dpi=200); plt.close(fig)

# 2. F1 в зависимости от длины реферата
fig, ax = plt.subplots(figsize=(6.5, 3.6))
ns = ["5", "10", "15"]
for v, name, c in VAR:
    ax.plot([5, 10, 15], [100 * G["all"]["by_n"][n][v]["f1"] for n in ns], marker="o", label=name, color=c)
ax.set_xticks([5, 10, 15]); ax.set_xlabel("число предложений в реферате N"); ax.set_ylabel("F1, %")
ax.set_ylim(15, 60); ax.grid(alpha=.3); ax.legend(frameon=False, fontsize=9)
fig.tight_layout(); fig.savefig(OUT / "f1_by_n.png", dpi=200); plt.close(fig)

# 3. Время этапов обработки одного документа
st = G["all"]["stages"]
labels = ["извлечение\nтекста PDF", "SE: разбиение\nна предлож.", "SE: термины\nи tf(t,D)", "SE: веса\nw(t,D)",
          "SE: веса предл.\nи отбор", "SE: ключевые\nслова", "OSTIS:\nвесь реферат"]
vals = [G["all"]["t_read"], st["split"], st["terms"], st["weights"], st["sentences"], st["keywords"], G["all"]["t_ostis"]]
fig, ax = plt.subplots(figsize=(8.2, 3.5))
bars = ax.bar(labels, vals, color=["#9aa4b5"] + ["#2f5aa8"] * 5 + ["#3c9a5f"])
for r, v in zip(bars, vals):
    ax.text(r.get_x() + r.get_width() / 2, v + 1.5, f"{v:.2f}".replace(".", ","), ha="center", fontsize=9)
ax.set_ylabel("мс (медиана из 5 замеров)"); ax.grid(axis="y", alpha=.3); ax.set_ylim(0, max(vals) * 1.18)
fig.tight_layout(); fig.savefig(OUT / "time_stages.png", dpi=200); plt.close(fig)
# 4. ключевые слова: SE и OSTIS
fig, ax = plt.subplots(figsize=(7, 3.2))
gk = [("fr_cs", "франц., CS"), ("fr_lit", "франц., лит."), ("it_cs", "итал., CS"), ("it_lit", "итал., лит."), ("all", "все")]
x = range(len(gk)); w4 = 0.2
for k, (key, name, c) in enumerate([("kw_precision", "SE: точность", "#2f5aa8"), ("kw_recall", "SE: покрытие", "#9bb7e8"),
                                    ("kw_ostis_precision", "OSTIS: точность", "#3c9a5f"),
                                    ("kw_ostis_recall", "OSTIS: покрытие", "#a7d7b5")]):
    ax.bar([i + (k - 1.5) * w4 for i in x], [100 * G[g][key] for g, _ in gk], w4, label=name, color=c)
ax.set_xticks(list(x), [n for _, n in gk]); ax.set_ylabel("%"); ax.set_ylim(0, 110); ax.grid(axis="y", alpha=.3)
ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.14), frameon=False, fontsize=8.5)
fig.tight_layout(); fig.savefig(OUT / "keywords.png", dpi=200); plt.close(fig)

# 5. вклад шагов семантического метода
ab = b["agent_ablations"]
fig, ax = plt.subplots(figsize=(7.5, 3.0))
names = list(ab)[::-1]
vals = [100 * ab[k]["f1"] for k in names]
bars = ax.barh(names, vals, color="#3c9a5f")
ax.axvline(100 * G["all"]["by_n"]["10"]["full"]["f1"], color="#2f5aa8", ls="--", lw=1.2, label="sentence extraction")
for r, v in zip(bars, vals):
    ax.text(v + 0.5, r.get_y() + r.get_height() / 2, f"{v:.1f}".replace(".", ","), va="center", fontsize=9)
ax.set_xlim(0, 60); ax.set_xlabel("F1, % (N = 10)"); ax.legend(frameon=False, fontsize=9, loc="lower right", bbox_to_anchor=(1, 1))
fig.tight_layout(); fig.savefig(OUT / "ostis_ablation.png", dpi=200); plt.close(fig)
print("ok")
