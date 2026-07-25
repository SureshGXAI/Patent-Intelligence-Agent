"""Reviewer sign-off / annotation workflow on top of the audit trail.

An attorney (or reviewer) records a decision against a completed run. Each entry
is hash-chained: it commits to the previous entry's hash, and the first entry
commits to the run's analysis fingerprint. Any later edit to a note, decision,
or ordering breaks the chain, so `verify_reviews` can detect tampering.

    python -m patent_intel.review run.manifest.json \
        --reviewer "A. Attorney" --decision approved --notes "FTO cleared"
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
from typing import Optional

DECISIONS = {"approved", "rejected", "needs-work", "noted"}


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical(entry: dict) -> str:
    # hash everything except the entry_hash field itself
    return json.dumps({k: v for k, v in entry.items() if k != "entry_hash"},
                      sort_keys=True, separators=(",", ":"), default=str)


def add_signoff(manifest_path: str, reviewer: str, decision: str,
                notes: str = "") -> dict:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    with open(manifest_path) as fh:
        manifest = json.load(fh)
    reviews = manifest.get("reviews", [])
    anchor = manifest.get("analysis_fingerprint_sha256", "")
    prev_hash = reviews[-1]["entry_hash"] if reviews else anchor

    entry = {
        "index": len(reviews),
        "reviewer": reviewer,
        "decision": decision,
        "notes": notes,
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "prev_hash": prev_hash,
    }
    entry["entry_hash"] = _sha256(_canonical(entry))
    reviews.append(entry)
    manifest["reviews"] = reviews

    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    # mirror to an append-only reviews log next to the manifest
    log = manifest_path.replace(".manifest.json", ".reviews.jsonl")
    with open(log, "a") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
    return entry


def verify_reviews(manifest: dict) -> dict:
    """Recompute the hash chain; report whether it is intact."""
    reviews = manifest.get("reviews", [])
    anchor = manifest.get("analysis_fingerprint_sha256", "")
    expected_prev = anchor
    for i, entry in enumerate(reviews):
        if entry.get("prev_hash") != expected_prev:
            return {"ok": False, "broken_at": i, "reason": "prev_hash mismatch"}
        if _sha256(_canonical(entry)) != entry.get("entry_hash"):
            return {"ok": False, "broken_at": i, "reason": "entry_hash mismatch"}
        expected_prev = entry["entry_hash"]
    return {"ok": True, "entries": len(reviews), "anchored_to": anchor[:16]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="patent-intel-review", description=__doc__)
    ap.add_argument("manifest", help="path to a run's .manifest.json")
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--decision", required=True, choices=sorted(DECISIONS))
    ap.add_argument("--notes", default="")
    ap.add_argument("--verify", action="store_true",
                    help="verify the review chain and exit")
    args = ap.parse_args(argv)

    with open(args.manifest) as fh:
        manifest = json.load(fh)
    if args.verify:
        print(json.dumps(verify_reviews(manifest), indent=2))
        return 0
    entry = add_signoff(args.manifest, args.reviewer, args.decision, args.notes)
    print(f"Sign-off recorded: #{entry['index']} {entry['decision']} "
          f"by {entry['reviewer']} (hash {entry['entry_hash'][:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
