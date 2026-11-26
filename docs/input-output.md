# Input and output contract

One case JSON represents an encounter. Use local anonymous case and procedure identifiers; these are not a de-identification method. Include all relevant procedures, source image labels, complete endoscopy reports, and applicable pathology reports/addenda. Preserve local specimen labels within the encounter and make them unique when reports reuse container letters (for example, use report-qualified labels consistently).

```json
{
  "case_id": "synthetic-case",
  "procedures": [{"procedure_id": "synthetic-procedure", "family": "synthetic endoscopy", "report_text": "SYNTHETIC: focal finding sampled into A."}],
  "pathology_reports": [{"report_text": "SYNTHETIC: A, demonstration tissue diagnosis."}],
  "images": [{"image_number": 1, "procedure_id": "synthetic-procedure", "source_label": "Synthetic focal finding", "image_path": "checkerboard.png"}]
}
```

Image numbers are consecutive from 1 in attachment order. PNG/JPEG files must be local, at most 20 MB each, and resolve inside the case directory; absolute paths and escaping symlinks are rejected. Remote image URLs are not fetched. File signatures are checked for transport compatibility, not malicious content or identifying pixels. Export image files without identifying overlays and metadata before use.

One output record per image contains `image_number`, `eligibility`, `visual_impression`, and `pathology_associations`. The eligibility vocabulary is `eligible`, `not_biopsy_site`, `pathology_not_derivable`, or `uncertain`. An association includes `specimen_label`, `pathology`, `biopsy_type` (`targeted`/`non_targeted`), `confidence` (`low`/`medium`/`high`), and `rationale`. Noneligible records must have an empty association array. An eligible record may remain unlinked when no safe association can be made; no association means a negative prediction for link-presence evaluation regardless of eligibility.

The validator rejects missing/extra fields, incorrect image coverage/order, duplicate specimen links, and incompatible eligibility/association combinations. It cannot establish that the model preserved a label correctly, inspected an image accurately, or matched the true specimen. These are clinical review tasks. A receipt records the configured model, the SHA-256 digest of the case-specific prompt, image count, and the fact that no clinical response rewriting occurred. Treat receipts as private provenance.
