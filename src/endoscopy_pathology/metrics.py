"""Clinical metrics with participant-cluster percentile bootstrap intervals."""
from collections import defaultdict
import math
import random

METRICS = ["visual_correctness", "visual_correct_and_complete", "link_presence_sensitivity",
           "link_presence_specificity", "link_presence_ppv", "link_presence_npv", "link_presence_f1",
           "correct_specimen_sensitivity", "correct_specimen_ppv", "correct_specimen_f1",
           "exact_specimen_assignment_accuracy"]


def record_counts(record):
    model = record.get("model_specimens")
    ref = record.get("reference_specimens")
    if not isinstance(model, list) or any(not isinstance(x, str) for x in model) or len(set(model)) != len(model):
        raise ValueError("Model specimens must be a unique list of labels")
    if ref is not None and (not isinstance(ref, list) or any(not isinstance(x, str) for x in ref) or len(set(ref)) != len(ref)):
        raise ValueError("Reference specimens must be a unique list or null for pending review")
    incorrect, incomplete = record.get("visual_incorrect"), record.get("visual_incomplete")
    if any(x is not None and type(x) is not bool for x in [incorrect, incomplete]):
        raise ValueError("Visual flags must be boolean or null")
    va = incorrect is not None
    vc = incorrect is False
    vcomplete = va and incomplete is not None
    if ref is None:
        tp = fp = fn = tn = pair_tp = pair_fp = pair_fn = exact = assessable = 0
    else:
        mp, rp = bool(model), bool(ref)
        tp, fp, fn, tn = int(mp and rp), int(mp and not rp), int(not mp and rp), int(not mp and not rp)
        ms, rs = set(model), set(ref)
        pair_tp, pair_fp, pair_fn = len(ms & rs), len(ms - rs), len(rs - ms)
        exact, assessable = int(ms == rs), 1
    return [(int(vc), int(va)), (int(vc and incomplete is False), int(vcomplete)),
            (tp, tp + fn), (tn, tn + fp), (tp, tp + fp), (tn, tn + fn), (2 * tp, 2 * tp + fp + fn),
            (pair_tp, pair_tp + pair_fn), (pair_tp, pair_tp + pair_fp),
            (2 * pair_tp, 2 * pair_tp + pair_fp + pair_fn), (exact, assessable)]


def percentile(values, q):
    values = sorted(values)
    index = (len(values) - 1) * q
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def evaluate(records, replicates=5000, seed=20261028):
    if type(replicates) is not int or replicates < 1 or not records:
        raise ValueError("Supply records and a positive bootstrap replicate count")
    groups = defaultdict(lambda: [[0, 0] for _ in METRICS])
    seen = set()
    for record in records:
        key = record["case_id"], record["image_number"]
        if key in seen:
            raise ValueError("Duplicate evaluated image")
        seen.add(key)
        cluster = record.get("cluster_id")
        if not isinstance(cluster, str) or not cluster:
            raise ValueError("Every record needs an explicit local participant cluster_id")
        for totals, (n, d) in zip(groups[cluster], record_counts(record)):
            totals[0] += n; totals[1] += d
    grouped = list(groups.values())
    total = [[sum(g[i][j] for g in grouped) for j in [0, 1]] for i in range(len(METRICS))]
    boot = [[] for _ in METRICS]
    rng = random.Random(seed)
    for _ in range(replicates):
        selected = rng.choices(grouped, k=len(grouped))
        for i in range(len(METRICS)):
            n, d = sum(g[i][0] for g in selected), sum(g[i][1] for g in selected)
            if d:
                boot[i].append(n / d)
    return {"images": len(records), "participant_clusters": len(groups),
            "method": "participant-cluster percentile bootstrap; Python standard-library generator",
            "replicates": replicates, "seed": seed,
            "metrics": {name: {"numerator": n, "denominator": d, "estimate": n / d if d else None,
                               "ci95_lower": percentile(b, .025) if b else None,
                               "ci95_upper": percentile(b, .975) if b else None,
                               "valid_bootstrap_replicates": len(b)}
                        for name, (n, d), b in zip(METRICS, total, boot)}}
