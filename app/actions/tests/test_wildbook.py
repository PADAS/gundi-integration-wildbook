import copy

import pytest

from app.actions import gcf, handlers
from app.services.earthranger import site_name
from app.services.wildbook import WildbookClient

SEX = {"male": "m", "female": "f", "unknown": "u"}
AGE = {"adult": "ad", "subadult": "sa", "juvenile": "ju", "calf": "ca"}
FIELDS = {"giraffe_id": None, "giraffe_sex": SEX, "giraffe_age": AGE, "giraffe_notes": None}


# --- stamps and values -------------------------------------------------------------------

@pytest.mark.parametrize("remarks, expected", [
    ("er=twiga:2040:2", ("twiga", 2040, 2)),
    ("gsd_no|snare_no|er=twiga:2040:2", ("twiga", 2040, 2)),
    ("er=gundi-dev:12:1|gsd_no", ("gundi-dev", 12, 1)),
    ("er=twiga:2040", None),
    ("gsd_no|snare_no", None),
    ("xer=twiga:1:1", None),
    (None, None),
])
def test_parse_stamp(remarks, expected):
    assert gcf.parse_stamp(remarks) == expected


def test_site_name_from_destination_address():
    assert site_name("https://twiga.pamdas.org/") == "twiga"
    assert site_name("gundi-dev.staging.pamdas.org") == "gundi-dev"


def test_giraffe_id_is_the_name_for_free_text():
    assert gcf.giraffe_id_value("LG-0054F", None) == "LG-0054F"


def test_giraffe_id_dropdown_matches_name_or_name_with_nickname():
    options = {"HSBM091": "id-1", "HNBF093_Aubrey": "id-2", "HNBF151_(HNBU056)": "id-3"}
    assert gcf.giraffe_id_value("HSBM091", options) == "id-1"
    assert gcf.giraffe_id_value("HNBF093", options) == "id-2"
    assert gcf.giraffe_id_value("HNBF151", options) == "id-3"
    assert gcf.giraffe_id_value("HNBF999", options) is None


def test_giraffe_id_dropdown_picks_nothing_when_two_names_fit():
    assert gcf.giraffe_id_value("HNBF093", {"HNBF093_A": "a", "HNBF093_B": "b"}) is None


@pytest.mark.parametrize("sex, expected", [
    ("female", "f"), ("Female", "f"), ("F", "f"), ("male", "m"), ("M", "m"), ("unknown", "u"),
    ("AF", None), ("JUV", None), ("", None), (None, None),
])
def test_sex_spellings(sex, expected):
    assert gcf.row_values({"sex": sex}, None, FIELDS)["giraffe_sex"][1] == expected


@pytest.mark.parametrize("life_stage, expected", [
    ("adult", "ad"), ("Adult", "ad"), ("sub-adult", "sa"), ("juvenile", "ju"), ("calf", "ca"), ("baby", None),
])
def test_age_spellings(life_stage, expected):
    assert gcf.row_values({"lifeStage": life_stage}, None, FIELDS)["giraffe_age"][1] == expected


def test_age_left_alone_when_the_type_has_no_such_option():
    nw_age = {"adult": "ad", "subadult": "sa", "calf": "ca", "unknown": "u"}
    assert gcf.row_values({"lifeStage": "juvenile"}, None, {**FIELDS, "giraffe_age": nw_age})["giraffe_age"][1] is None


def test_only_fields_the_type_has_are_written():
    kaza_survey = {"giraffe_sex": SEX, "giraffe_age": AGE}
    assert set(gcf.row_values({"sex": "m"}, "X", kaza_survey)) == {"giraffe_sex", "giraffe_age"}


# --- Wildbook paging -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_changed_encounters_split_windows_with_too_many_results(mocker):
    client = WildbookClient("https://example.org", "token")
    versions = list(range(1, 25_001))  # 25,000 changes, more than one search can return

    async def search(index, query, start=0, size=500):
        window = query["bool"]["filter"][0]["range"]["version"]
        hits = [{"id": v, "version": v} for v in versions if window["gt"] < v <= window["lte"]]
        return hits[start:start + size], len(hits)

    mocker.patch.object(client, "search", side_effect=search)
    found = await client.get_encounters_changed(0, 25_000, "*er=twiga:*")
    assert sorted(e["id"] for e in found) == versions
    await client._client.aclose()


# --- updating one event --------------------------------------------------------------------

class FakeER:

    def __init__(self, event, fields=FIELDS, edited_meanwhile=False):
        self.event = event
        self.fields = fields
        self.edited_meanwhile = edited_meanwhile
        self.reads = 0
        self.patches = []
        self.uploads = []

    async def find_event_by_serial(self, serial):
        return self.event if self.event and self.event["serial_number"] == serial else None

    async def find_copied_event(self, source_site, serial):
        return self.event

    async def get_list_fields(self, event_type, list_field):
        return self.fields

    async def get_event(self, event_id):
        self.reads += 1
        event = copy.deepcopy(self.event)
        if self.edited_meanwhile and self.reads > 1:
            event["updated_at"] = "2026-09-29T12:00:01+02:00"
        return event

    async def patch_event(self, event_id, body):
        self.patches.append(body)

    async def upload_file(self, filename, content):
        self.uploads.append(filename)
        return f"upload-{len(self.uploads)}"


class FakeWildbook:

    def __init__(self, photos=None):
        self.photos = photos or {}

    async def get_right_side_photos(self, encounter_ids):
        return {e: self.photos[e] for e in encounter_ids if e in self.photos}

    async def download(self, url):
        return b"jpeg"


def herd_event(event_type="giraffe_survey_encounter_zmb", rows=3):
    return {
        "id": "event-1", "serial_number": 2040, "event_type": event_type,
        "updated_at": "2026-09-29T12:00:00+02:00",
        "event_details": {
            "herd_size": rows,
            "Herd": [{"giraffe_notes": f"row {i}", "giraffe_sex": "u"} for i in range(1, rows + 1)],
            "updates": [{"message": "not sent back"}],
        },
    }


def encounter(eid="enc-2", sex="male", life_stage="adult", individual="ind-1"):
    return {"id": eid, "individualId": individual, "sex": sex, "lifeStage": life_stage, "version": 1,
            "occurrenceId": "ZMB_SLNP_20260720105126"}


async def update(er, items, names=None, wildbook=None, add_photos=False, copies_of=None):
    report = handlers.SiteReport("gundi-dev")
    await handlers._update_event(er, wildbook or FakeWildbook(), 2040, items, names or {"ind-1": "LG-0067M"},
                                 {}, add_photos, report, copies_of)
    return report


@pytest.mark.asyncio
async def test_only_the_stamped_row_changes():
    er = FakeER(herd_event())
    report = await update(er, [(2, encounter())])
    herd = er.patches[0]["event_details"]["Herd"]
    assert herd[1] == {"giraffe_notes": "row 2", "giraffe_sex": "m", "giraffe_id": "LG-0067M", "giraffe_age": "ad"}
    assert herd[0] == {"giraffe_notes": "row 1", "giraffe_sex": "u"}
    assert herd[2] == {"giraffe_notes": "row 3", "giraffe_sex": "u"}
    assert er.patches[0]["event_details"]["herd_size"] == 3
    assert "updates" not in er.patches[0]["event_details"]
    assert report.rows_updated == 1
    assert {c["field"] for c in report.changes} == {"giraffe_sex", "giraffe_id", "giraffe_age"}


@pytest.mark.asyncio
async def test_nothing_is_written_when_the_row_already_matches():
    event = herd_event()
    event["event_details"]["Herd"][1].update(giraffe_sex="m", giraffe_id="LG-0067M", giraffe_age="ad")
    er = FakeER(event)
    await update(er, [(2, encounter())])
    assert er.patches == []


@pytest.mark.asyncio
async def test_event_of_another_type_is_skipped():
    er = FakeER(herd_event(event_type="inat_observation"))
    report = await update(er, [(2, encounter())])
    assert er.patches == []
    assert "not a giraffe event type" in report.skipped[0]["reason"]


@pytest.mark.asyncio
async def test_missing_event_is_skipped():
    er = FakeER(None)
    report = await update(er, [(2, encounter())])
    assert "not found" in report.skipped[0]["reason"]


@pytest.mark.asyncio
async def test_row_beyond_the_herd_is_skipped():
    er = FakeER(herd_event())
    report = await update(er, [(9, encounter())])
    assert er.patches == []
    assert "has no row 9" in report.skipped[0]["reason"]


@pytest.mark.asyncio
async def test_second_sighting_for_the_same_row_is_skipped():
    er = FakeER(herd_event())
    report = await update(er, [(2, encounter("enc-a")), (2, encounter("enc-b", sex="female"))])
    assert er.patches[0]["event_details"]["Herd"][1]["giraffe_sex"] == "m"
    assert report.skipped[0]["encounter"] == "enc-b"


@pytest.mark.asyncio
async def test_event_edited_while_updating_is_not_overwritten():
    er = FakeER(herd_event(), edited_meanwhile=True)
    with pytest.raises(handlers.EventChangedDuringUpdate):
        await update(er, [(2, encounter())])
    assert er.patches == []


@pytest.mark.asyncio
async def test_value_without_a_matching_option_is_left_alone_and_noted():
    er = FakeER(herd_event())
    report = await update(er, [(2, encounter(sex="AF"))])
    assert er.patches[0]["event_details"]["Herd"][1]["giraffe_sex"] == "u"
    assert "no giraffe_sex option" in report.notes[0]["note"]


@pytest.mark.asyncio
async def test_right_side_photo_goes_into_the_row():
    er = FakeER(herd_event(), fields={**FIELDS, "giraffe_photo": None})
    wildbook = FakeWildbook({"enc-2": "https://media.example.org/abc.jpg"})
    report = await update(er, [(2, encounter())], wildbook=wildbook, add_photos=True)
    assert er.patches[0]["event_details"]["Herd"][1]["giraffe_photo"] == [{"uploadId": "upload-1"}]
    assert er.uploads == ["ZMB_SLNP_20260720105126_abc.jpg"]
    assert report.photos_added == 1


@pytest.mark.asyncio
async def test_row_with_a_photo_gets_no_second_one():
    event = herd_event()
    event["event_details"]["Herd"][1]["giraffe_photo"] = [{"uploadId": "existing"}]
    er = FakeER(event, fields={**FIELDS, "giraffe_photo": None})
    wildbook = FakeWildbook({"enc-2": "https://media.example.org/abc.jpg"})
    await update(er, [(2, encounter())], wildbook=wildbook, add_photos=True)
    assert er.uploads == []


@pytest.mark.asyncio
async def test_no_photo_when_the_type_has_no_photo_field():
    er = FakeER(herd_event())
    wildbook = FakeWildbook({"enc-2": "https://media.example.org/abc.jpg"})
    await update(er, [(2, encounter())], wildbook=wildbook, add_photos=True)
    assert er.uploads == []


# --- EarthRanger event types -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_types_are_read_from_every_page(mocker):
    from app.services.earthranger import EarthRangerClient
    client = EarthRangerClient("https://site.pamdas.org", "token")
    pages = {
        "https://site.pamdas.org/api/v2.0/activity/eventtypes/": {
            "results": [{"value": "a"}], "next": "https://site.pamdas.org/api/v2.0/activity/eventtypes/?page=2"},
        "https://site.pamdas.org/api/v2.0/activity/eventtypes/?page=2": {
            "results": [{"value": "giraffe_nw_monitoring"}], "next": None},
    }
    mocker.patch.object(client, "_get", side_effect=lambda url, **params: pages[url])
    assert await client.get_event_type_values() == ["a", "giraffe_nw_monitoring"]
    await client._client.aclose()


@pytest.mark.asyncio
async def test_event_types_as_a_plain_list(mocker):
    from app.services.earthranger import EarthRangerClient
    client = EarthRangerClient("https://site.pamdas.org", "token")
    mocker.patch.object(client, "_get", return_value=[{"value": "a"}])
    assert await client.get_event_type_values() == ["a"]
    await client._client.aclose()
