"""Compare English against one language.

Usage: python3 compare.py CODE      e.g. python3 compare.py af
Reads  results/en/scores_en.csv and results/CODE/scores_CODE.csv
Writes results/CODE/metrics_en_vs_CODE.csv, flips_en_vs_CODE.csv, rules_en_vs_CODE.csv,
       phishing_score_change_en_vs_CODE.csv
"""
import sys
from collections import Counter
import pandas as pd
from scipy.stats import binomtest, wilcoxon
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, confusion_matrix, roc_auc_score,
                             average_precision_score)

code = sys.argv[1]
en = pd.read_csv("results/en/scores_en.csv")
xx = pd.read_csv(f"results/{code}/scores_{code}.csv")

bad = pd.concat([en, xx])
bad = bad[bad.sa_score.isna()]
if len(bad):
    print("WARNING: emails with no score (fix or note them):")
    print(bad[["language", "email_id", "rules_hit"]].to_string(index=False))

ids = set(en.email_id) ^ set(xx.email_id)
if ids:
    sys.exit(f"Email IDs differ between English and {code}: {sorted(ids)}")

def metrics(d):
    d = d.dropna(subset=["sa_score"])
    y, p, s = d.label, d.predicted.astype(int), d.sa_score
    tn, fp, fn, tp = confusion_matrix(y, p, labels=[0, 1]).ravel()
    return {"emails": len(d), "TP": tp, "FN": fn, "FP": fp, "TN": tn,
            "accuracy": accuracy_score(y, p),
            "precision": precision_score(y, p, zero_division=0),
            "recall": recall_score(y, p, zero_division=0),
            "f1": f1_score(y, p, zero_division=0),
            "fpr": fp / (fp + tn) if (fp + tn) else 0.0,
            "roc_auc": roc_auc_score(y, s),
            "pr_auc": average_precision_score(y, s),
            "mean_score_phishing": s[y == 1].mean(),
            "mean_score_legit": s[y == 0].mean()}

m = pd.DataFrame([{"language": "en", **metrics(en)},
                  {"language": code, **metrics(xx)}]).round(3)
m.to_csv(f"results/{code}/metrics_en_vs_{code}.csv", index=False)
print("\n", m.T.to_string(header=False))

# Matched pairs: same email, English vs translated
j = en.merge(xx, on=["email_id", "label"], suffixes=("_en", f"_{code}"))
j = j.dropna(subset=["sa_score_en", f"sa_score_{code}"])
j["score_change"] = j[f"sa_score_{code}"] - j["sa_score_en"]
right_en = j.predicted_en == j.label
right_xx = j[f"predicted_{code}"] == j.label
lost, gained = j[right_en & ~right_xx], j[~right_en & right_xx]
pd.concat([lost.assign(change="correct in EN, wrong in " + code),
           gained.assign(change="wrong in EN, correct in " + code)]).to_csv(
    f"results/{code}/flips_en_vs_{code}.csv", index=False)
b, c = len(lost), len(gained)
p = binomtest(b, b + c, 0.5).pvalue if b + c else 1.0
print(f"\nSame email, different outcome: {b} became wrong, {c} became right "
      f"(exact McNemar p = {p:.4f})")
print(f"Mean score change per email (phishing): "
      f"{j[j.label == 1].score_change.mean():.2f}")

# Score shift for phishing emails, independent of the 5.0 cut-off
ph = j[j.label == 1]
down, same, up = (ph.score_change < 0).sum(), (ph.score_change == 0).sum(), (ph.score_change > 0).sum()
nz = ph[ph.score_change != 0]
w_p = wilcoxon(nz[f"sa_score_{code}"], nz["sa_score_en"]).pvalue if len(nz) else 1.0
print(f"Phishing scores after translation: {down} fell, {same} unchanged, {up} rose "
      f"(Wilcoxon signed-rank p = {w_p:.4f})")
ph.sort_values("score_change")[["email_id", "sa_score_en", f"sa_score_{code}",
                                "score_change", "rules_hit_en", f"rules_hit_{code}"]].to_csv(
    f"results/{code}/phishing_score_change_en_vs_{code}.csv", index=False)

# Which rules stopped (or started) firing after translation
def rule_counts(series):
    c = Counter()
    for t in series.fillna(""):
        c.update(r for r in str(t).split(",") if r and r != "none")
    return c
re_, rx = rule_counts(j.rules_hit_en), rule_counts(j[f"rules_hit_{code}"])
r = pd.DataFrame([{"rule": k, "hits_en": re_[k], f"hits_{code}": rx[k],
                   "difference": rx[k] - re_[k]} for k in set(re_) | set(rx)])
r = r.sort_values("difference")
r.to_csv(f"results/{code}/rules_en_vs_{code}.csv", index=False)
print("\nRules that lost the most hits after translation:")
print(r.head(10).to_string(index=False))
