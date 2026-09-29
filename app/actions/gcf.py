"""GCF's giraffe event types and how Wildbook values map onto their rows.

This first version works with GCF's event types only. Each giraffe is one row of the
event's `Herd` list; Wildbook stamps the row in the encounter's remarks as
`er=<site>:<event number>:<row>`, written by GCF's ER2WB tool.
"""
import re
from typing import Dict, Optional, Tuple

GIRAFFE_EVENT_TYPES = (
    "giraffe_survey_encounter_ken",
    "giraffe_survey_encounter_tza",
    "giraffe_survey_encounter_zmb",
    "giraffe_survey_encounter_bwa",
    "giraffe_survey_encounter_nam",
    "giraffe_survey_kaza",
    "giraffe_random_encounter_zmb",
    "giraffe_random_encounter_nam",
    "giraffe_random_kaza",
    "giraffe_nw_monitoring",
)

LIST_FIELD = "Herd"
ID_FIELD = "giraffe_id"
SEX_FIELD = "giraffe_sex"
AGE_FIELD = "giraffe_age"
PHOTO_FIELD = "giraffe_photo"
WRITTEN_FIELDS = (ID_FIELD, SEX_FIELD, AGE_FIELD)

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
    spellings = next((s for s in words.values() if _normalize(value) in s), None)
    if not spellings:
        return None
    hits = [v for name, v in options.items() if _normalize(name) in spellings or _normalize(v) in spellings]
    return hits[0] if len(hits) == 1 else None


def giraffe_id_value(name: Optional[str], options: Optional[dict]):
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


def row_values(encounter: dict, name: Optional[str], fields: Dict[str, Optional[dict]]) -> Dict[str, tuple]:
    """{field: (Wildbook value, EarthRanger value or None)} for the fields this connector writes
    that the event type has (survey KAZA, for one, has no Giraffe ID)."""
    values = {
        ID_FIELD: (name, giraffe_id_value(name, fields.get(ID_FIELD))),
        SEX_FIELD: (encounter.get("sex"), _pick_option(encounter.get("sex"), SEX_WORDS, fields.get(SEX_FIELD))),
        AGE_FIELD: (encounter.get("lifeStage"),
                    _pick_option(encounter.get("lifeStage"), AGE_WORDS, fields.get(AGE_FIELD))),
    }
    return {field: value for field, value in values.items() if field in fields}
