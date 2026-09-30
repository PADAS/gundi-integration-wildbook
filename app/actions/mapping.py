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

STAMP_RE = re.compile(r"(?:^|\|)er=([a-z0-9-]+):(\d+):(\d+)(?:\||$)")


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


def row_values(encounter: dict, name: Optional[str], fields: Dict[str, Optional[dict]],
               id_field: Optional[str], sex_field: Optional[str], age_field: Optional[str]) -> Dict[str, tuple]:
    """{field: (Wildbook value, EarthRanger value or None)} for the configured fields that
    the event type has."""
    values = {}
    if id_field:
        values[id_field] = (name, individual_id_value(name, fields.get(id_field)))
    if sex_field:
        values[sex_field] = (encounter.get("sex"), _pick_option(encounter.get("sex"), SEX_WORDS, fields.get(sex_field)))
    if age_field:
        values[age_field] = (encounter.get("lifeStage"),
                             _pick_option(encounter.get("lifeStage"), AGE_WORDS, fields.get(age_field)))
    return {field: value for field, value in values.items() if field in fields}
