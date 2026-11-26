"""CLI: offline synthetic demo, validation, inference, review and evaluation."""
import argparse
import binascii
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import zlib

from .client import HTTPSClient, ProviderError
from .pipeline import load_case, infer
from .schema import validate_prediction
from .review import write_template, load_reviews, resolve
from .metrics import evaluate


def write_private(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        raise ValueError("Output already exists; use a new destination")
    fd, temp = tempfile.mkstemp(prefix=".workflow-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.link(temp, path)
    finally:
        os.unlink(temp)


def synthetic_png():
    """A checkerboard transport fixture, not an endoscopic image."""
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", binascii.crc32(name + data) & 0xffffffff)
    pixels = b"".join(b"\0" + b"".join(bytes([255 if (x // 8 + y // 8) % 2 else 80] * 3) for x in range(32)) for y in range(32))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


def demo(destination):
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    case = {"case_id": "synthetic-case", "procedures": [{"procedure_id": "synthetic-procedure",
            "family": "synthetic endoscopy", "report_text": "SYNTHETIC DEMONSTRATION. A focal finding in segment Alpha was sampled into specimen A."}],
            "pathology_reports": [{"report_text": "SYNTHETIC DEMONSTRATION. A, segment Alpha: demonstration tissue diagnosis."}],
            "images": [{"image_number": 1, "procedure_id": "synthetic-procedure", "source_label": "Segment Alpha focal finding",
                        "image_path": "checkerboard.png"}]}
    prediction = {"images": [{"image_number": 1, "eligibility": "eligible", "visual_impression": "Segment Alpha focal finding.",
                   "pathology_associations": [{"specimen_label": "A", "pathology": "Demonstration tissue diagnosis.",
                   "biopsy_type": "targeted", "confidence": "high", "rationale": "Synthetic reports explicitly connect the demonstration finding to A."}]}]}
    (destination / "checkerboard.png").write_bytes(synthetic_png())
    write_private(destination / "case.json", case)
    write_private(destination / "canned_prediction.json", prediction)
    write_template(case, prediction, destination / "reviewer1.csv")
    write_template(case, prediction, destination / "reviewer2.csv")
    print("Synthetic transport/review fixtures created. No model was called; this is not a performance benchmark.")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    d = commands.add_parser("demo"); d.add_argument("--output-dir", required=True)
    for name in ["validate", "infer", "review-template", "adjudicate"]:
        command = commands.add_parser(name)
        command.add_argument("--case", type=Path, required=True)
        if name != "infer":
            command.add_argument("--prediction", type=Path, required=True)
        if name == "infer":
            command.add_argument("--output-dir", type=Path, required=True)
            command.add_argument("--allow-network", action="store_true")
            command.add_argument("--save-raw-response", action="store_true")
        if name == "review-template":
            command.add_argument("--output", type=Path, required=True)
        if name == "adjudicate":
            command.add_argument("--reviewer1", type=Path, required=True)
            command.add_argument("--reviewer2", type=Path, required=True)
            command.add_argument("--adjudicator", type=Path)
            command.add_argument("--cluster-id", help="Local anonymous participant cluster, shared across that participant's encounters")
            command.add_argument("--output", type=Path, required=True)
    e = commands.add_parser("evaluate")
    e.add_argument("--references", type=Path, nargs="+", required=True)
    e.add_argument("--output", type=Path, required=True)
    e.add_argument("--replicates", type=int, default=5000)
    e.add_argument("--seed", type=int, default=20261028)
    return p


def main(argv=None):
    os.umask(0o077)
    args = parser().parse_args(argv)
    try:
        if args.command == "demo":
            demo(args.output_dir); return 0
        if args.command == "evaluate":
            records = [row for path in args.references for row in json.loads(path.read_text())]
            write_private(args.output, evaluate(records, args.replicates, args.seed))
        else:
            case = load_case(args.case)
            if args.command == "infer":
                if not args.allow_network:
                    raise ValueError("Network inference requires --allow-network and an approved explicitly configured endpoint")
                destinations = ["prediction.json", "receipt.json"]
                if args.save_raw_response:
                    destinations.append("raw_response.json")
                if any((args.output_dir / name).exists() for name in destinations):
                    raise ValueError("Inference outputs already exist; use a new destination")
                prediction, raw, receipt = infer(case, args.case.parent, HTTPSClient.from_environment(),
                        os.getenv("WORKFLOW_MODEL", ""), os.getenv("WORKFLOW_REASONING_EFFORT") or None)
                write_private(args.output_dir / "prediction.json", prediction)
                write_private(args.output_dir / "receipt.json", receipt)
                if args.save_raw_response:
                    write_private(args.output_dir / "raw_response.json", raw)
            else:
                prediction = validate_prediction(json.loads(args.prediction.read_text()), len(case["images"]))
                if args.command == "validate":
                    print("Prediction contract passed. Clinical truth and de-identification are not validated.")
                elif args.command == "review-template":
                    if args.output.exists():
                        raise ValueError("Review destination already exists")
                    write_template(case, prediction, args.output)
                elif args.command == "adjudicate":
                    reference = resolve(case, prediction, load_reviews(args.reviewer1), load_reviews(args.reviewer2),
                            load_reviews(args.adjudicator) if args.adjudicator else None, args.cluster_id)
                    write_private(args.output, reference)
        return 0
    except (ValueError, OSError, ProviderError, KeyError, TypeError):
        # Do not print exception text: it can contain local paths, reports or credentials.
        print("Workflow failed. Check the documented input contract, review completeness and endpoint configuration. No input or response content is logged.", file=sys.stderr)
        return 2
