"""
Builds the two test sheets for Deliverable 5 sections 2.2 (penetration testing).

Usage: copy run_baseline.py and compare.py into a NEW empty folder first, so
these runs don't overwrite your real results/en files. Then, in that folder:
    python3 make_attack_set.py Afrikaans_email_batch.xlsx attack.xlsx

It reads the English "Emails" sheet and writes attack.xlsx with three sheets:
  Emails   the English emails, unchanged (the baseline)
  Evasion  the same emails with an invisible zero-width space put inside
           every word longer than four letters (PT-01)
  Robust   five broken or hostile records that the harness must survive
           without crashing or running anything (PT-02 to PT-06)

Then run:
    python3 run_baseline.py attack.xlsx Emails en
    python3 run_baseline.py attack.xlsx Evasion ev
    python3 compare.py ev                      # PT-01: did scores drop?
    python3 run_baseline.py attack.xlsx Robust rb
    # PT-02..06: open results/rb/scores_rb.csv and check every row has a score
    # or a clean error, and that no cell starting with = was run as a formula.

No new phishing text is written. The evasion sheet only adds invisible
characters to emails that are already in the public corpora.
"""
import re
import sys

import pandas as pd

if len(sys.argv) != 3:
    sys.exit("Usage: python3 make_attack_set.py <source.xlsx> <attack.xlsx>")
src, out = sys.argv[1], sys.argv[2]

en = pd.read_excel(src, sheet_name="Emails", dtype=str)
en = en.copy()   # keep legitimate mail too, so compare.py can work out ROC-AUC
ZWSP = "​"


def hide(text):
    """Put a zero-width space in the middle of every word longer than 4 letters."""
    def split(m):
        w = m.group(0)
        return w[: len(w) // 2] + ZWSP + w[len(w) // 2:]
    # leave links and email addresses alone, so only the wording changes
    parts = re.split(r"(\S+@\S+|https?://\S+|www\.\S+)", str(text))
    return "".join(p if i % 2 else re.sub(r"[A-Za-z]{5,}", split, p)
                   for i, p in enumerate(parts))


ev = en.copy()
ev["subject_ev"] = ev["subject"].map(hide)
ev["body_ev"] = ev["body"].map(hide)
ev = ev.drop(columns=["subject", "body"])

base = en.iloc[0].to_dict()
robust_rows = [
    ("PT-02", "Oversized body", "A" * 32000),                                   # Excel cell limit
    ("PT-03", "Header injection\r\nBcc: victim@example.com", "Test body"),     # new line in subject
    ("PT-04", "Formula injection", '=HYPERLINK("http://example.com","click")'),  # spreadsheet formula
    ("PT-05", "Empty record", ""),                                              # nothing to score
    ("PT-06", "One very long word", "x" * 20000),                               # regex and timeout stress
]
rb = []
for rid, subj, body in robust_rows:
    r = dict(base)
    r.update({"email_id": rid, "subject_rb": subj, "body_rb": body})
    r.pop("subject", None)
    r.pop("body", None)
    rb.append(r)
rb = pd.DataFrame(rb)

with pd.ExcelWriter(out, engine="openpyxl") as xw:
    en.to_excel(xw, sheet_name="Emails", index=False)
    ev.to_excel(xw, sheet_name="Evasion", index=False)
    rb.to_excel(xw, sheet_name="Robust", index=False)
print(f"Wrote {out}: {len(en)} emails, {len(ev)} evasion copies, {len(rb)} robustness records")
