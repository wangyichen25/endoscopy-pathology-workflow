# Endoscopy–pathology workflow

A source-grounded multimodal workflow for assigning visual impressions to endoscopic images and linking sampled findings to pathology specimens. It combines images, existing image labels, complete endoscopy reports, and pathology reports. It does not predict histology from an image alone.

This public reference implementation preserves the clinical prompting principles and provides a portable inference, independent-review, adjudication, and evaluation interface. It replaces the original institution-specific extraction and authentication layers. It contains no patient records, clinical images, review exports, institutional infrastructure configuration, credentials, or private study results. Performance from a private validation cohort cannot be reproduced from the synthetic examples in this repository. Adapting the model or transport requires fresh validation.

## Workflow

1. Group images and reports by encounter; retain procedure provenance and original image labels.
2. Preserve source labels in the visual impression. Add report findings only when visible in that particular image. Keep histology separate from visual descriptions.
3. Require a coherent image → sampled finding/tissue → specimen → applicable diagnosis chain. Resolve anatomical and container provenance; abstain when ambiguous. Do not distribute mixed histology from a pooled container to individual lesions without explicit mapping.
4. Return ordered, structured image labels, specimen associations, sampling type, confidence, and rationale. Validate the response contract without automatically rewriting clinical labels.
5. Have two reviewers independently inspect images and source reports. Retain concordant component judgments; resolve discrepancies with a third reviewer.

The prompt is in [`instructions.txt`](src/endoscopy_pathology/prompts/instructions.txt). The public package uses only the Python standard library at runtime (Python 3.10 or later).

## Offline demonstration

```sh
python -m pip install .
endoscopy-pathology demo --output-dir /tmp/endoscopy-pathology-demo
endoscopy-pathology validate \
  --case /tmp/endoscopy-pathology-demo/case.json \
  --prediction /tmp/endoscopy-pathology-demo/canned_prediction.json
python -m unittest discover -s tests -v
```

Use a fresh output directory. The demonstration creates a checkerboard image, fictitious reports, a canned prediction, and two blank review CSVs. It makes no network requests and does not demonstrate diagnostic performance. Populate both review files before adjudication; blank cells remain pending.

```sh
endoscopy-pathology adjudicate \
  --case /tmp/endoscopy-pathology-demo/case.json \
  --prediction /tmp/endoscopy-pathology-demo/canned_prediction.json \
  --reviewer1 /tmp/endoscopy-pathology-demo/reviewer1.csv \
  --reviewer2 /tmp/endoscopy-pathology-demo/reviewer2.csv \
  --cluster-id synthetic-participant \
  --output /tmp/endoscopy-pathology-reference.json
endoscopy-pathology evaluate \
  --references /tmp/endoscopy-pathology-reference.json \
  --output /tmp/endoscopy-pathology-metrics.json
```

For disagreement, add `--adjudicator path/to/third-review.csv`. See [review and evaluation definitions](docs/review-and-evaluation.md) before interpreting metrics. The one-image demo cannot provide useful confidence intervals.

## Configured inference

Inference is opt-in. Before any transmission, use independently de-identified inputs and an endpoint approved for those inputs. This package does **not** de-identify reports, labels, identifiers, or image pixels and does not detect protected information.

Set `WORKFLOW_API_URL` to the full HTTPS chat-completions endpoint, `WORKFLOW_API_KEY` through your approved secret mechanism, and `WORKFLOW_MODEL` to an explicitly chosen multimodal model. There is no default endpoint or model. `.env.example` lists names only; this package does not automatically load `.env` files. Do not put secrets in command arguments or tracked files.

```sh
endoscopy-pathology infer \
  --case path/to/deidentified/case.json \
  --output-dir path/to/private/new-run \
  --allow-network
```

The adapter expects bearer authentication, inline image support, and strict JSON-schema chat completions. Other services need an approved adapter. Redirects are refused. Transient server/rate-limit errors may be retried; interrupted transport is not retried automatically. Provider-side retention and logging depend on the configured service.

Outputs contain clinical content and must remain in approved private storage. Model response bodies and credentials are not logged to the console. The unedited raw response is saved only with `--save-raw-response`; structured predictions always preserve the returned clinical text after contract validation. Outputs are created with restrictive permissions and are not overwritten.

See [input/output contract](docs/input-output.md) and [privacy boundaries](SECURITY.md). This is research software; structural validation is not clinical validation, and model confidence categories are not calibrated probabilities.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

No clinical data or access credentials are needed for the tests. Do not add private data, raw model outputs, local endpoint settings, or institution-specific adapters to this repository. Public access does not itself establish a software license; obtain appropriate permission before redistribution or reuse beyond applicable rights.
