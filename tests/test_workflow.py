import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError

from endoscopy_pathology.cli import demo, main, write_private
from endoscopy_pathology.client import HTTPSClient, NoRedirect, ProviderError
from endoscopy_pathology.pipeline import build_prompt, build_payload, image_attachment, infer, load_case
from endoscopy_pathology.schema import validate_prediction, parse_prediction
from endoscopy_pathology.review import FIELDS, load_reviews, resolve
from endoscopy_pathology.metrics import evaluate, record_counts


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "demo"
        with patch("sys.stdout", io.StringIO()):
            demo(self.root)
        self.case = load_case(self.root / "case.json")
        self.pred = json.loads((self.root / "canned_prediction.json").read_text())

    def review(self, incorrect=False, incomplete=False, accepted=True, reference=None):
        return {("synthetic-case", 1): {"visual_incorrect": incorrect, "visual_incomplete": incomplete,
                "pathology_accepted": accepted, "reference_specimens": reference}}

    def test_offline_demo_creates_valid_fixture(self):
        self.assertEqual(validate_prediction(self.pred, 1), self.pred)
        self.assertEqual(load_reviews(self.root / "reviewer1.csv")[("synthetic-case", 1)]["pathology_accepted"], None)

    def test_prompt_has_source_labels_reports_and_pooling_rule(self):
        prompt = build_prompt(self.case)
        self.assertIn(self.case["images"][0]["source_label"], prompt)
        self.assertIn(self.case["procedures"][0]["report_text"], prompt)
        self.assertIn("pool", prompt.lower())
        self.assertNotIn("checkerboard.png", prompt)

    def test_ordered_image_payload(self):
        case = copy.deepcopy(self.case)
        case["images"].append({**case["images"][0], "image_number": 2})
        payload = build_payload(case, self.root, "synthetic-model")
        self.assertEqual(len(payload["messages"][1]["content"]), 3)
        self.assertEqual(payload["response_format"]["json_schema"]["schema"]["properties"]["images"]["minItems"], 2)

    def test_case_rejects_unknown_procedure(self):
        self.case["images"][0]["procedure_id"] = "unknown"
        with self.assertRaises(ValueError): build_prompt(self.case)

    def test_boolean_image_ordinal_rejected(self):
        self.pred["images"][0]["image_number"] = True
        with self.assertRaises(ValueError): validate_prediction(self.pred, 1)

    def test_missing_image_rejected(self):
        with self.assertRaises(ValueError): validate_prediction(self.pred, 2)

    def test_unknown_output_field_rejected(self):
        self.pred["extra"] = "invalid"
        with self.assertRaises(ValueError): validate_prediction(self.pred, 1)

    def test_noneligible_link_rejected(self):
        self.pred["images"][0]["eligibility"] = "uncertain"
        with self.assertRaises(ValueError): validate_prediction(self.pred, 1)

    def test_duplicate_specimen_rejected(self):
        self.pred["images"][0]["pathology_associations"] *= 2
        with self.assertRaises(ValueError): validate_prediction(self.pred, 1)

    def test_invalid_json_not_repaired(self):
        with self.assertRaises(ValueError): parse_prediction("```json\n{}\n```", 1)

    def test_local_path_boundary(self):
        for value in ["../outside.png", str(self.root / "checkerboard.png"), "https://example.invalid/image.png"]:
            with self.subTest(value=value), self.assertRaises(ValueError): image_attachment(self.root, value)

    def test_escaping_symlink_rejected(self):
        outside = self.root.parent / "outside.png"
        outside.write_bytes((self.root / "checkerboard.png").read_bytes())
        (self.root / "link.png").symlink_to(outside)
        with self.assertRaises(ValueError): image_attachment(self.root, "link.png")

    def test_unknown_image_format_rejected(self):
        (self.root / "unknown.bin").write_bytes(b"not an image")
        with self.assertRaises(ValueError): image_attachment(self.root, "unknown.bin")

    def test_explicit_https_configuration(self):
        for url in ["", "http://example.invalid", "https://name:secret@example.invalid"]:
            with self.subTest(url=url), self.assertRaises(ValueError): HTTPSClient(url, "dummy")

    def test_redirects_are_refused(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid/other"))

    def test_provider_error_omits_body(self):
        client = HTTPSClient("https://example.invalid/completions", "dummy", retries=0)
        client.opener = Mock()
        client.opener.open.side_effect = HTTPError(client.url, 401, "private-body", {}, io.BytesIO(b"private-body"))
        with self.assertRaises(ProviderError) as caught: client.complete({})
        self.assertNotIn("private-body", str(caught.exception))

    def test_raw_inference_is_not_rewritten(self):
        client = Mock()
        raw = {"choices": [{"message": {"content": json.dumps(self.pred)}}]}
        client.complete.return_value = raw
        pred, returned, receipt = infer(self.case, self.root, client, "synthetic-model")
        self.assertEqual(pred, self.pred)
        self.assertIs(returned, raw)
        self.assertFalse(receipt["response_edited"])

    def test_no_completion_fails(self):
        client = Mock(); client.complete.return_value = {"choices": []}
        with self.assertRaises(ValueError): infer(self.case, self.root, client, "synthetic-model")

    def test_inference_requires_network_flag_before_client(self):
        with patch("endoscopy_pathology.cli.HTTPSClient.from_environment") as client, patch("sys.stderr", io.StringIO()):
            status = main(["infer", "--case", str(self.root / "case.json"), "--output-dir", str(self.root / "out")])
        self.assertEqual(status, 2); client.assert_not_called()

    def test_existing_output_prevents_network(self):
        out = self.root / "out"; out.mkdir(); (out / "prediction.json").write_text("{}")
        with patch("endoscopy_pathology.cli.HTTPSClient.from_environment") as client, patch("sys.stderr", io.StringIO()):
            status = main(["infer", "--case", str(self.root / "case.json"), "--output-dir", str(out), "--allow-network"])
        self.assertEqual(status, 2); client.assert_not_called()

    def test_output_never_overwritten(self):
        path = self.root / "result.json"; write_private(path, {"first": True})
        with self.assertRaises(ValueError): write_private(path, {"first": False})
        self.assertEqual(json.loads(path.read_text()), {"first": True})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_correct_but_incomplete_is_correct(self):
        row = resolve(self.case, self.pred, self.review(incomplete=True), self.review(incomplete=True))[0]
        counts = record_counts(row)
        self.assertEqual(counts[0], (1, 1)); self.assertEqual(counts[1], (0, 1))

    def test_disagreement_requires_third(self):
        with self.assertRaises(ValueError): resolve(self.case, self.pred, self.review(), self.review(incomplete=True))

    def test_pending_does_not_become_negative(self):
        with self.assertRaises(ValueError): resolve(self.case, self.pred, self.review(incorrect=None), self.review(incorrect=None))
        row = {"model_specimens": [], "reference_specimens": None, "visual_incorrect": None, "visual_incomplete": None}
        self.assertTrue(all(pair == (0, 0) for pair in record_counts(row)))

    def test_third_adjudication_resolves_component_only(self):
        row = resolve(self.case, self.pred, self.review(), self.review(incomplete=True), self.review(incomplete=True))[0]
        self.assertEqual(row["visual_reference_source"], "third_reviewer")
        self.assertEqual(row["pathology_reference_source"], "two_reviewer_agreement")

    def test_pathology_text_disagreement_requires_third_even_same_specimen(self):
        with self.assertRaises(ValueError): resolve(self.case, self.pred, self.review(), self.review(accepted=False, reference=["A"]))
        row = resolve(self.case, self.pred, self.review(), self.review(accepted=False, reference=["A"]), self.review(accepted=False, reference=["A"]))[0]
        self.assertFalse(row["pathology_accepted"])
        self.assertEqual(row["reference_specimens"], ["A"])

    def test_rejection_needs_explicit_reference(self):
        with self.assertRaises(ValueError): resolve(self.case, self.pred, self.review(accepted=False), self.review(accepted=False))

    def test_shared_rejection_is_retained(self):
        row = resolve(self.case, self.pred, self.review(accepted=False, reference=[]), self.review(accepted=False, reference=[]))[0]
        self.assertEqual(row["reference_specimens"], [])
        self.assertEqual(row["pathology_reference_source"], "two_reviewer_agreement")

    def test_wrong_specimen_presence_and_pair_metrics_differ(self):
        row = {"case_id": "synthetic", "image_number": 1, "cluster_id": "participant", "model_specimens": ["A"],
               "reference_specimens": ["B"], "visual_incorrect": False, "visual_incomplete": False}
        metrics = evaluate([row], 20)["metrics"]
        self.assertEqual(metrics["link_presence_ppv"]["estimate"], 1)
        self.assertEqual(metrics["correct_specimen_ppv"]["estimate"], 0)
        self.assertEqual(metrics["exact_specimen_assignment_accuracy"]["estimate"], 0)
        self.assertIsNone(metrics["link_presence_specificity"]["estimate"])

    def test_clustering_and_determinism(self):
        row = resolve(self.case, self.pred, self.review(), self.review(), cluster_id="participant")[0]
        other = {**row, "case_id": "second-encounter"}
        result = evaluate([row, other], 20, 7)
        self.assertEqual(result["participant_clusters"], 1)
        self.assertEqual(result, evaluate([row, other], 20, 7))
        with self.assertRaises(ValueError): evaluate([row, row], 20)

    def test_review_csv_and_cli_end_to_end(self):
        for name in ["reviewer1.csv", "reviewer2.csv"]:
            with (self.root / name).open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS); writer.writeheader()
                writer.writerow({"case_id": "synthetic-case", "image_number": 1, "visual_incorrect": "false",
                                 "visual_incomplete": "true", "pathology_accepted": "true"})
        reference = self.root / "reference.json"; output = self.root / "metrics.json"
        self.assertEqual(main(["adjudicate", "--case", str(self.root / "case.json"), "--prediction", str(self.root / "canned_prediction.json"),
                              "--reviewer1", str(self.root / "reviewer1.csv"), "--reviewer2", str(self.root / "reviewer2.csv"), "--output", str(reference)]), 0)
        self.assertEqual(main(["evaluate", "--references", str(reference), "--output", str(output), "--replicates", "25"]), 0)
        self.assertEqual(json.loads(output.read_text())["metrics"]["visual_correctness"]["estimate"], 1)


if __name__ == "__main__":
    unittest.main()
