"""Structured output contract and independent semantic validation."""
import json

ELIGIBILITY = ("eligible", "not_biopsy_site", "pathology_not_derivable", "uncertain")
IMAGE_KEYS = {"image_number", "eligibility", "visual_impression", "pathology_associations"}
ASSOCIATION_KEYS = {"specimen_label", "pathology", "biopsy_type", "confidence", "rationale"}


def response_schema(image_count):
    if type(image_count) is not int or image_count < 1:
        raise ValueError("image_count must be a positive integer")
    association = {
        "type": "object", "additionalProperties": False,
        "required": sorted(ASSOCIATION_KEYS),
        "properties": {
            "specimen_label": {"type": "string", "minLength": 1},
            "pathology": {"type": "string", "minLength": 1},
            "biopsy_type": {"type": "string", "enum": ["targeted", "non_targeted"]},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "rationale": {"type": "string", "minLength": 1},
        },
    }
    image = {
        "type": "object", "additionalProperties": False, "required": sorted(IMAGE_KEYS),
        "properties": {
            "image_number": {"type": "integer", "minimum": 1, "maximum": image_count},
            "eligibility": {"type": "string", "enum": list(ELIGIBILITY)},
            "visual_impression": {"type": "string"},
            "pathology_associations": {"type": "array", "items": association},
        },
    }
    return {"type": "object", "additionalProperties": False, "required": ["images"],
            "properties": {"images": {"type": "array", "minItems": image_count,
                                      "maxItems": image_count, "items": image}}}


def validate_prediction(prediction, image_count):
    """Validate syntax and consistency, never clinical truth or de-identification."""
    response_schema(image_count)
    if not isinstance(prediction, dict) or set(prediction) != {"images"}:
        raise ValueError("Prediction must contain only the images array")
    images = prediction["images"]
    if not isinstance(images, list) or len(images) != image_count:
        raise ValueError("Prediction must cover every supplied image exactly once")
    for expected_number, image in enumerate(images, 1):
        if not isinstance(image, dict) or set(image) != IMAGE_KEYS:
            raise ValueError("Image prediction has missing or unexpected fields")
        if type(image["image_number"]) is not int or image["image_number"] != expected_number:
            raise ValueError("Image predictions must retain the supplied order")
        if image["eligibility"] not in ELIGIBILITY:
            raise ValueError("Invalid eligibility")
        if not isinstance(image["visual_impression"], str):
            raise ValueError("Visual impression must be text")
        associations = image["pathology_associations"]
        if not isinstance(associations, list):
            raise ValueError("Associations must be an array")
        if image["eligibility"] != "eligible" and associations:
            raise ValueError("Abstained or unsampled images cannot carry an association")
        labels = set()
        for association in associations:
            if not isinstance(association, dict) or set(association) != ASSOCIATION_KEYS:
                raise ValueError("Association has missing or unexpected fields")
            for field in ["specimen_label", "pathology", "rationale"]:
                if not isinstance(association[field], str) or not association[field].strip():
                    raise ValueError("Specimen, pathology and rationale must be nonempty text")
            if association["specimen_label"] in labels:
                raise ValueError("Duplicate specimen association for one image")
            labels.add(association["specimen_label"])
            if association["biopsy_type"] not in ["targeted", "non_targeted"]:
                raise ValueError("Invalid biopsy type")
            if association["confidence"] not in ["low", "medium", "high"]:
                raise ValueError("Invalid confidence")
    return prediction


def parse_prediction(text, image_count):
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise ValueError("Provider returned invalid JSON") from None
    return validate_prediction(value, image_count)
