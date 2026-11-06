"""How Wildbook values map onto the rows of an EarthRanger event's list field.

Each animal is one row of a list field on the event. Which list, and which fields in each
row take the animal's ID, sex and age, come from the action's settings. The Wildbook
encounter's remarks point to the row as `er=<site>:<event number>:<row>`, a stamp added
when the sighting is uploaded to Wildbook.
"""
import re
from typing import Dict, Optional, Tuple

# Every spelling of a value, in Wildbook or in an EarthRanger option, after `_normalize`
SEX_WORDS = {
    "male": {"male", "m"},
    "female": {"female", "f"},
    "unknown": {"unknown", "u"},
}
AGE_WORDS = {
    "adult": {"adult", "ad"},
    "subadult": {"subadult", "sa"},
    "juvenile": {"juvenile", "ju", "juv"},
    "calf": {"calf", "ca"},
    "unknown": {"unknown", "u"},
}

# The tag may follow other remarks, separated by "|" or ";" (e.g. "UNIDENTIFIED; er=twiga:50325:3").
STAMP_RE = re.compile(r"(?:^|[|;])\s*er=([a-z0-9-]+):(\d+):(\d+)\s*(?:[|;]|$)")


def parse_stamp(remarks: Optional[str]) -> Optional[Tuple[str, int, int]]:
    """(site, event number, row) from an encounter's remarks, or None."""
    match = STAMP_RE.search(remarks or "")
    return (match.group(1), int(match.group(2)), int(match.group(3))) if match else None


def _normalize(value) -> str:
    return re.sub(r"[\s_-]", "", str(value)).lower()


def _pick_option(value, words: Dict[str, set], options: Optional[dict]):
    """The stored value of the option meaning the same as `value`, or None."""
    if value is None or not options:
        return None
    spellings = next((s for s in words.values() if _normalize(value) in s), {_normalize(value)})
    hits = [v for name, v in options.items() if _normalize(name) in spellings or _normalize(v) in spellings]
    return hits[0] if len(hits) == 1 else None


def individual_id_value(name: Optional[str], options: Optional[dict]):
    """Free text: the Wildbook name. Dropdown: the option with that name, or whose name
    is that name followed by a nickname (`HNBF093` -> `HNBF093_Aubrey`), when only one fits."""
    if not name:
        return None
    if options is None:
        return name
    if name in options:
        return options[name]
    hits = [v for label, v in options.items() if label and str(label).split("_", 1)[0] == name]
    return hits[0] if len(hits) == 1 else None


def age_value(life_stage: Optional[str], options: Optional[dict]):
    """The option for a Wildbook life stage. A form with no Juvenile choice takes Subadult:
    the upload to Wildbook turns Subadult into `juvenile` (Twiga's NW monitoring form)."""
    value = _pick_option(life_stage, AGE_WORDS, options)
    if value is None and life_stage and _normalize(life_stage) in AGE_WORDS["juvenile"]:
        value = _pick_option("subadult", AGE_WORDS, options)
    return value


# The location note added on upload when a sighting's position was moved by its bearing and distance,
# e.g. "reprojected from lon=31.906362, lat=-12.989308 (bearing=314° from EXIF, distance=186m)".
REPROJECTED_RE = re.compile(r"reprojected from lon=[^()|;]*\([^)]*\)", re.IGNORECASE)


def remarks_without_stamp(remarks: Optional[str]) -> str:
    """The encounter's remarks with the er= tag, the upload's location note and their
    separators taken out (`UNIDENTIFIED; er=twiga:50325:3` -> `UNIDENTIFIED`)."""
    text = REPROJECTED_RE.sub("", remarks or "")
    text = STAMP_RE.sub(lambda m: m.group(0)[0] if m.group(0)[0] in "|;" else "", text)
    text = re.sub(r"([|;])(?:\s*[|;])+", r"\1", text)  # separators left next to each other
    return re.sub(r"^[\s|;]+|[\s|;]+$", "", text)


def appended_notes(current: Optional[str], remarks: Optional[str], options: Optional[dict]):
    """The row's notes with the Wildbook remarks added after them, unless they are already
    there. None for a dropdown notes field, or when Wildbook has no remarks besides the tag."""
    remarks = remarks_without_stamp(remarks)
    if options is not None or not remarks:
        return None
    current = (current or "").strip()
    if not current:
        return remarks
    return current if remarks in current else f"{current}; {remarks}"


def row_values(encounter: dict, name: Optional[str], fields: Dict[str, Optional[dict]],
               id_field: Optional[str], sex_field: Optional[str], age_field: Optional[str],
               notes_field: Optional[str] = None, current_row: Optional[dict] = None) -> Dict[str, tuple]:
    """{field: (Wildbook value, EarthRanger value or None)} for the configured fields that
    the event type has."""
    values = {}
    if id_field:
        values[id_field] = (name, individual_id_value(name, fields.get(id_field)))
    if sex_field:
        values[sex_field] = (encounter.get("sex"), _pick_option(encounter.get("sex"), SEX_WORDS, fields.get(sex_field)))
    if age_field:
        values[age_field] = (encounter.get("lifeStage"), age_value(encounter.get("lifeStage"), fields.get(age_field)))
    if notes_field:
        remarks = encounter.get("occurrenceRemarks")
        values[notes_field] = (remarks_without_stamp(remarks),
                               appended_notes((current_row or {}).get(notes_field), remarks, fields.get(notes_field)))
    return {field: value for field, value in values.items() if field in fields}
