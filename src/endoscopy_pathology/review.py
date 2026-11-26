"""Independent component reviews, explicit adjudication and reference export."""
import csv
import json

FIELDS = ["case_id", "image_number", "visual_incorrect", "visual_incomplete",
          "pathology_accepted", "reference_specimens", "comment"]


def boolean(value):
    if value is None or value == "":
        return None
    if type(value) is bool:
        return value
    value = str(value).strip().lower()
    if value in ["1", "true", "yes"]:
        return True
    if value in ["0", "false", "no"]:
        return False
    raise ValueError("Review flags must be true, false or blank")


def write_template(case, prediction, destination):
    with open(destination, "w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for image in prediction["images"]:
            writer.writerow({"case_id": case["case_id"], "image_number": image["image_number"]})


def load_reviews(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if set(reader.fieldnames or []) != set(FIELDS):
            raise ValueError("Review columns do not match the public contract")
        result = {}
        for row in reader:
            try:
                number = int(row["image_number"])
            except (TypeError, ValueError):
                raise ValueError("Invalid reviewed image number") from None
            key = row["case_id"], number
            if key in result:
                raise ValueError("Duplicate reviewed image")
            for field in ["visual_incorrect", "visual_incomplete", "pathology_accepted"]:
                row[field] = boolean(row[field])
            if row["reference_specimens"].strip():
                try:
                    labels = json.loads(row["reference_specimens"])
                except json.JSONDecodeError:
                    raise ValueError("Reference specimen labels must be a JSON array") from None
                if not isinstance(labels, list) or any(not isinstance(x, str) or not x.strip() for x in labels) or len(set(labels)) != len(labels):
                    raise ValueError("Reference specimens must be unique nonempty labels")
                row["reference_specimens"] = sorted(labels)
            else:
                row["reference_specimens"] = None
            result[key] = row
        return result


def normalize_pathology(review, model_specimens):
    accepted = review["pathology_accepted"]
    reference = review["reference_specimens"]
    if accepted is None:
        return None
    if accepted:
        if reference is not None and reference != model_specimens:
            raise ValueError("An accepted assignment cannot change the proposed specimen set")
        return model_specimens
    if reference is None:
        raise ValueError("Rejected pathology needs explicit reference labels, including [] when none match")
    # A reviewer can reject the diagnosis text while retaining the specimen set.
    return reference


def resolve(case, prediction, reviewer1, reviewer2, adjudicator=None, cluster_id=None):
    adjudicator = adjudicator or {}
    expected = {(case["case_id"], im["image_number"]) for im in prediction["images"]}
    if set(reviewer1) != expected or set(reviewer2) != expected or not set(adjudicator) <= expected:
        raise ValueError("Review coverage does not match this case")
    resolved = []
    for image in prediction["images"]:
        key = case["case_id"], image["image_number"]
        a, b, third = reviewer1[key], reviewer2[key], adjudicator.get(key)
        model = sorted(x["specimen_label"] for x in image["pathology_associations"])
        va = a["visual_incorrect"], a["visual_incomplete"]
        vb = b["visual_incorrect"], b["visual_incomplete"]
        if va == vb and None not in va:
            visual, visual_source = va, "two_reviewer_agreement"
        else:
            if third is None:
                raise ValueError("Visual disagreement or pending review requires explicit adjudication")
            visual = third["visual_incorrect"], third["visual_incomplete"]
            if None in visual:
                raise ValueError("Visual adjudication must supply both error flags")
            visual_source = "third_reviewer"
        pa, pb = normalize_pathology(a, model), normalize_pathology(b, model)
        if pa is not None and pa == pb and a["pathology_accepted"] == b["pathology_accepted"]:
            reference, accepted, pathology_source = pa, a["pathology_accepted"], "two_reviewer_agreement"
        else:
            if third is None or normalize_pathology(third, model) is None:
                raise ValueError("Pathology disagreement or pending review requires explicit adjudication")
            reference = normalize_pathology(third, model)
            accepted = third["pathology_accepted"]
            pathology_source = "third_reviewer"
        resolved.append({"case_id": case["case_id"], "cluster_id": cluster_id or case["case_id"],
                         "image_number": image["image_number"], "model_specimens": model,
                         "reference_specimens": reference, "visual_incorrect": visual[0],
                         "visual_incomplete": visual[1], "visual_reference_source": visual_source,
                         "pathology_accepted": accepted,
                         "pathology_reference_source": pathology_source})
    return resolved
