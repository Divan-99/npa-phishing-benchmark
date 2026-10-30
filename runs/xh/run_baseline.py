"""Score one language sheet with SpamAssassin (local tests only).

Usage:
  python3 run_baseline.py MASTER.xlsx SHEET CODE
  e.g. python3 run_baseline.py master.xlsx Emails en
       python3 run_baseline.py master.xlsx Afrikaans af
Writes results/<code>/scores_<code>.csv
"""
import glob, os, re, subprocess, sys, time
import pandas as pd

THRESHOLD = 5.0  # SpamAssassin default required_score

def clean(v):
    return "" if pd.isna(v) else str(v)

def one_line(v):
    return re.sub(r"[\r\n]+", " ", clean(v)).strip()

def build_email(row, subject, body):
    head = (
        f"From: {one_line(row['sender'])}\n"
        f"To: {one_line(row['receiver'])}\n"
        f"Date: {one_line(row['date'])}\n"
        f"Subject: {one_line(subject)}\n"
        f"Message-ID: <{one_line(row['email_id'])}@npa-benchmark.local>\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: 8bit\n\n"
    )
    return (head + clean(body).replace("\r\n", "\n") + "\n").encode("utf-8")

def score(raw):
    try:
        out = subprocess.run(["spamassassin", "-L"], input=raw,
                             capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    head = out.split("\n\n", 1)[0]
    head = re.sub(r"\n[ \t]+", " ", head)  # unfold wrapped header lines
    m = re.search(r"^X-Spam-Status:.*?score=(-?[\d.]+).*?tests=(.*?)(?:\s+autolearn=|\s+version=|$)",
                  head, re.M)
    if not m:
        return None, "NO_SCORE"
    tests = re.sub(r"\s+", "", m.group(2))  # long rule lists wrap over several lines
    return float(m.group(1)), tests

def check_rules():
    """Stop early if sa-update never ran: without the full rule set every score is ~0."""
    if not glob.glob("/var/lib/spamassassin/*/updates_spamassassin_org/72_active.cf"):
        sys.exit("SpamAssassin rules are missing or incomplete. Run: sudo sa-update -v")
    gtube = b"Subject: test\n\nXJS*C4JDBQADN1.NSBN3*2IDNEN*GTUBE-STANDARD-ANTI-UBE-TEST-EMAIL*C.34X\n"
    s, _ = score(gtube)
    if s is None or s < 5:
        sys.exit("SpamAssassin self-test (GTUBE) failed. Check the install and sa-update.")

def main():
    check_rules()
    path, sheet, code = sys.argv[1], sys.argv[2], sys.argv[3]
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    subj = "subject" if code == "en" else f"subject_{code}"
    body = "body" if code == "en" else f"body_{code}"
    for col in ["email_id", "label", "sender", "receiver", "date", subj, body]:
        if col not in df.columns:
            sys.exit(f"Missing column '{col}' in sheet '{sheet}'")
    rows, start = [], time.time()
    for i, r in df.iterrows():
        s, tests = score(build_email(r, r[subj], r[body]))
        rows.append({"email_id": r["email_id"], "language": code,
                     "label": int(r["label"]), "sa_score": s,
                     "predicted": None if s is None else int(s >= THRESHOLD),
                     "rules_hit": tests})
        print(f"{i + 1}/{len(df)} {r['email_id']} score={s}", flush=True)
    os.makedirs(f"results/{code}", exist_ok=True)
    out = f"results/{code}/scores_{code}.csv"
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8")
    print(f"Saved {out} ({len(rows)} emails, {time.time() - start:.0f}s)")

if __name__ == "__main__":
    main()
