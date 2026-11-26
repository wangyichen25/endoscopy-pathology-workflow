# Review and evaluation

Two physicians should review every image independently with the original labels, images, endoscopy reports, pathology reports, and workflow output available. Blind each reviewer to the other's decisions. The CSV is a transport format, not a blinded review application.

The columns are `case_id`, `image_number`, `visual_incorrect`, `visual_incomplete`, `pathology_accepted`, `reference_specimens`, and `comment`. Boolean cells accept true/false, yes/no, or 1/0. Empty cells are pending, never assumed negative. Comments must remain within approved private storage.

* Set `visual_incorrect` for any incorrect statement and `visual_incomplete` for any material omission. Both may be true. Correctness includes correct-and-complete and correct-but-incomplete descriptions; complete correctness requires both flags false.
* Accept pathology only when the proposed specimen associations and associated pathology text are acceptable. On acceptance, a blank `reference_specimens` retains the model's specimen set. On rejection, explicitly enter the reference specimen set as a JSON array, such as `["A"]` or `[]`. Rejecting diagnosis text can retain the same specimen labels. Linkage metrics assess specimen assignment, not independent correctness of every pathology phrase.
* Compare both visual flags and both pathology acceptance/reference judgments. A third reviewer must explicitly resolve any disagreement or pending component. Concordant component judgments are retained. The adjudication export records each component's reference source. The third reviewer is not forced to choose one earlier opinion.

## Performance measures

For binary link presence, a positive reference means at least one pathology specimen should be linked to the image. A positive prediction means at least one association was returned. A wrong specimen can count as a binary true positive while failing exact linkage.

| Measure | Definition |
| --- | --- |
| Sensitivity (recall) | TP / (TP + FN) |
| Specificity | TN / (TN + FP) |
| Positive predictive value (precision) | TP / (TP + FP) |
| Negative predictive value | TN / (TN + FN) |
| F1 | 2TP / (2TP + FP + FN) |
| Correct-specimen sensitivity | Correct image–specimen pairs / reference pairs |
| Correct-specimen positive predictive value | Correct image–specimen pairs / proposed pairs |
| Correct-specimen F1 | 2 × correct pairs / (2 × correct pairs + extra pairs + missed pairs) |
| Exact specimen-assignment accuracy | Images with identical proposed and reference specimen sets / evaluated images; includes correctly unlinked images |
| Visual correctness | Images without an incorrect-statement flag / images assessed for correctness |
| Correct and complete visual impressions | Images with both error flags false / images assessed for both flags |

Pairs are micro-aggregated across images; a wrong specimen creates both an extra and a missed pair. Multiple links are allowed. No AUROC is calculated because the workflow returns decisions and categorical, uncalibrated confidence rather than a continuous link score. An undefined denominator yields JSON `null`, not zero. Pending pathology references are excluded from pathology denominators.

The evaluator uses 5,000 percentile bootstrap resamples of participant clusters by default. Reuse the same local `cluster_id` across all encounters for the same participant. The default is the case identifier, so explicitly override it when participants have repeated encounters. The code reports the number of valid resamples for each measure; small or single-cluster samples can give uninformative intervals. Its Python standard-library generator is portable; it does not reproduce a private study's random-number stream or results exactly.

For inter-reviewer agreement, calculate percent agreement and Cohen's kappa on the original independent judgments before adjudication, separately for visual correctness, visual completeness, and pathology acceptance. State the binary definition used; agreement on inclusive correctness differs from agreement on complete acceptance. A third-reviewer reference is a consensus reference standard and does not eliminate shared reviewer error. This package's performance evaluator does not infer pre-adjudication agreement from adjudicated rows; retain the independent CSVs for that separate analysis.
