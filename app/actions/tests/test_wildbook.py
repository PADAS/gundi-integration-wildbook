import copy

import pytest

from app.actions import handlers, mapping
from app.actions.configurations import PullEventUpdatesConfig
from app.services.earthranger import site_name
from app.services.errors import ConfigurationNotFound
from app.services.wildbook import WildbookClient

SEX = {"male": "m", "female": "f", "unknown": "u"}
AGE = {"adult": "ad", "subadult": "sa", "juvenile": "ju", "calf": "ca"}
FIELDS = {"animal_id": None, "animal_sex": SEX, "animal_age": AGE, "animal_notes": None}
FIELD_NAMES = ("animal_id", "animal_sex", "animal_age")
CONFIG = PullEventUpdatesConfig(list_field="Animals", id_field="animal_id", sex_field="animal_sex", age_field="animal_age")


# --- stamps and values -------------------------------------------------------------------

@pytest.mark.parametrize("remarks, expected", [
    ("er=site-a:2040:2", ("site-a", 2040, 2)),
    ("flag_a|flag_b|er=site-a:2040:2", ("site-a", 2040, 2)),
    ("er=gundi-dev:12:1|gsd_no", ("gundi-dev", 12, 1)),
    ("er=site-a:2040", None),
    ("flag_a|flag_b", None),
    ("xer=site-a:1:1", None),
    (None, None),
])
def test_parse_stamp(remarks, expected):
    assert mapping.parse_stamp(remarks) == expected


def test_wildbook_address_is_required():
    with pytest.raises(ConfigurationNotFound):
        WildbookClient("", "token")


def test_wildbook_address_setting_needs_a_full_address():
    from app.actions.configurations import AuthenticateConfig
    assert AuthenticateConfig(wildbook_url=" https://wb.example.org/ ", api_token="t").wildbook_url == "https://wb.example.org"
    with pytest.raises(ValueError):
        AuthenticateConfig(wildbook_url="wb.example.org", api_token="t")


def test_site_name_from_destination_address():
    assert site_name("https://site-a.pamdas.org/") == "site-a"
    assert site_name("gundi-dev.staging.pamdas.org") == "gundi-dev"


def test_id_is_the_name_for_free_text():
    assert mapping.individual_id_value("LG-0054F", None) == "LG-0054F"


def test_id_dropdown_matches_name_or_name_with_nickname():
    options = {"HSBM091": "id-1", "HNBF093_Aubrey": "id-2", "HNBF151_(HNBU056)": "id-3"}
    assert mapping.individual_id_value("HSBM091", options) == "id-1"
    assert mapping.individual_id_value("HNBF093", options) == "id-2"
    assert mapping.individual_id_value("HNBF151", options) == "id-3"
    assert mapping.individual_id_value("HNBF999", options) is None


def test_id_dropdown_picks_nothing_when_two_names_fit():
    assert mapping.individual_id_value("HNBF093", {"HNBF093_A": "a", "HNBF093_B": "b"}) is None


@pytest.mark.parametrize("sex, expected", [
    ("female", "f"), ("Female", "f"), ("F", "f"), ("male", "m"), ("M", "m"), ("unknown", "u"),
    ("AF", None), ("JUV", None), ("", None), (None, None),
])
def test_sex_spellings(sex, expected):
    assert mapping.row_values({"sex": sex}, None, FIELDS, *FIELD_NAMES)["animal_sex"][1] == expected


@pytest.mark.parametrize("life_stage, expected", [
    ("adult", "ad"), ("Adult", "ad"), ("sub-adult", "sa"), ("juvenile", "ju"), ("calf", "ca"), ("baby", None),
])
def test_age_spellings(life_stage, expected):
    assert mapping.row_values({"lifeStage": life_stage}, None, FIELDS, *FIELD_NAMES)["animal_age"][1] == expected


def test_juvenile_takes_subadult_when_the_type_has_no_juvenile_option():
    no_juvenile = {"adult": "ad", "subadult": "sa", "calf": "ca", "unknown": "u"}
    assert mapping.row_values({"lifeStage": "juvenile"}, None, {**FIELDS, "animal_age": no_juvenile}, *FIELD_NAMES)["animal_age"][1] == "sa"


def test_age_left_alone_when_no_option_fits():
    only_adult = {"adult": "ad"}
    assert mapping.row_values({"lifeStage": "calf"}, None, {**FIELDS, "animal_age": only_adult}, *FIELD_NAMES)["animal_age"][1] is None


@pytest.mark.parametrize("remarks, expected", [
    ("gsd_no|snare_no|er=site-a:2040:2", "gsd_no|snare_no"),
    ("UNIDENTIFIED; er=site-a:50325:3", "UNIDENTIFIED"),
    ("reprojected from lon=31.9, lat=-12.9 (bearing=314° from EXIF, distance=186m); er=site-a:1:4", ""),
    ("Tagged; reprojected from lon=1, lat=2 (bearing=90°, distance=155m); er=site-a:1:1", "Tagged"),
    ("Male with lumps on face; er=site-a:51584:1", "Male with lumps on face"),
])
def test_notes_leave_out_the_label_and_the_upload_location_note(remarks, expected):
    assert mapping.remarks_without_stamp(remarks) == expected


def test_notes_are_added_after_the_team_notes_once():
    assert mapping.appended_notes("Torn ear", "Limping; er=site-a:1:1", None) == "Torn ear; Limping"
    assert mapping.appended_notes("Torn ear; Limping", "Limping; er=site-a:1:1", None) == "Torn ear; Limping"
    assert mapping.appended_notes("Torn ear", "er=site-a:1:1", None) is None


def test_background_detections_sharing_a_label_are_ignored():
    found = [{"id": "a", "occurrenceRemarks": "er=site-a:1:1", "sex": "male"},
             {"id": "b", "occurrenceRemarks": "er=site-a:1:1"},
             {"id": "c", "occurrenceRemarks": "er=site-a:2:1"}]
    assert [e["id"] for e in handlers._without_extra_detections(found)] == ["a", "c"]


def test_only_fields_the_type_has_are_written():
    no_id_field = {"animal_sex": SEX, "animal_age": AGE}
    assert set(mapping.row_values({"sex": "m"}, "X", no_id_field, *FIELD_NAMES)) == {"animal_sex", "animal_age"}


def test_only_configured_fields_are_written():
    assert set(mapping.row_values({"sex": "m"}, "X", FIELDS, "animal_id", None, None)) == {"animal_id"}


def test_settings_need_a_list_and_at_least_one_field():
    with pytest.raises(ValueError):
        PullEventUpdatesConfig(list_field="Animals")
    with pytest.raises(ValueError):
        PullEventUpdatesConfig(list_field=" ", id_field="animal_id")


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
    found = await client.get_encounters_changed(0, 25_000, "*er=site-a:*")
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
        self.viewpoints = []

    async def get_photos(self, encounter_ids, viewpoint=None):
        self.viewpoints.append(viewpoint)
        return {e: self.photos[e] for e in encounter_ids if e in self.photos}

    async def download(self, url):
        return b"jpeg"


def list_event(event_type="animal_survey", rows=3):
    return {
        "id": "event-1", "serial_number": 2040, "event_type": event_type,
        "updated_at": "2026-09-29T12:00:00+02:00",
        "event_details": {
            "group_size": rows,
            "Animals": [{"animal_notes": f"row {i}", "animal_sex": "u"} for i in range(1, rows + 1)],
            "updates": [{"message": "not sent back"}],
        },
    }


def encounter(eid="enc-2", sex="male", life_stage="adult", individual="ind-1"):
    return {"id": eid, "individualId": individual, "sex": sex, "lifeStage": life_stage, "version": 1,
            "occurrenceId": "SITE_20260720105126"}


async def update(er, items, names=None, copies_of=None, wildbook=None, config=CONFIG):
    report = handlers.SiteReport("gundi-dev")
    await handlers._update_event(er, wildbook or FakeWildbook(), 2040, items, names or {"ind-1": "LG-0067M"}, {},
                                 report, config, copies_of)
    return report


PHOTO_CONFIG = PullEventUpdatesConfig(list_field="Animals", id_field="animal_id", photo_field="animal_photo",
                                      photo_viewpoint="right")


@pytest.mark.asyncio
async def test_photo_goes_into_the_row():
    er = FakeER(list_event(), fields={**FIELDS, "animal_photo": None})
    wildbook = FakeWildbook({"enc-2": "https://media.example.org/abc.jpg"})
    report = await update(er, [(2, encounter())], wildbook=wildbook, config=PHOTO_CONFIG)
    assert er.patches[0]["event_details"]["Animals"][1]["animal_photo"] == [{"uploadId": "upload-1"}]
    assert er.uploads == ["SITE_20260720105126_abc.jpg"]
    assert wildbook.viewpoints == ["right"]
    assert report.photos_added == 1


@pytest.mark.asyncio
async def test_row_with_a_photo_gets_no_second_one():
    event = list_event()
    event["event_details"]["Animals"][1]["animal_photo"] = [{"uploadId": "existing"}]
    er = FakeER(event, fields={**FIELDS, "animal_photo": None})
    await update(er, [(2, encounter())], wildbook=FakeWildbook({"enc-2": "https://m.example.org/a.jpg"}),
                 config=PHOTO_CONFIG)
    assert er.uploads == []


@pytest.mark.asyncio
async def test_no_photo_when_the_type_has_no_photo_field():
    er = FakeER(list_event())
    await update(er, [(2, encounter())], wildbook=FakeWildbook({"enc-2": "https://m.example.org/a.jpg"}),
                 config=PHOTO_CONFIG)
    assert er.uploads == []


@pytest.mark.asyncio
async def test_only_the_stamped_row_changes():
    er = FakeER(list_event())
    report = await update(er, [(2, encounter())])
    rows = er.patches[0]["event_details"]["Animals"]
    assert rows[1] == {"animal_notes": "row 2", "animal_sex": "m", "animal_id": "LG-0067M", "animal_age": "ad"}
    assert rows[0] == {"animal_notes": "row 1", "animal_sex": "u"}
    assert rows[2] == {"animal_notes": "row 3", "animal_sex": "u"}
    assert er.patches[0]["event_details"]["group_size"] == 3
    assert "updates" not in er.patches[0]["event_details"]
    assert report.rows_updated == 1
    assert {c["field"] for c in report.changes} == {"animal_sex", "animal_id", "animal_age"}


@pytest.mark.asyncio
async def test_nothing_is_written_when_the_row_already_matches():
    event = list_event()
    event["event_details"]["Animals"][1].update(animal_sex="m", animal_id="LG-0067M", animal_age="ad")
    er = FakeER(event)
    await update(er, [(2, encounter())])
    assert er.patches == []


@pytest.mark.asyncio
async def test_event_of_any_type_with_the_fields_is_updated():
    er = FakeER(list_event(event_type="any_other_type"))
    await update(er, [(2, encounter())])
    assert er.patches[0]["event_details"]["Animals"][1]["animal_id"] == "LG-0067M"


@pytest.mark.asyncio
async def test_event_without_the_fields_is_skipped():
    er = FakeER(list_event(event_type="inat_observation"), fields=None)
    report = await update(er, [(2, encounter())])
    assert er.patches == []
    assert "has none of the fields" in report.skipped[0]["reason"]


@pytest.mark.asyncio
async def test_missing_event_is_skipped():
    er = FakeER(None)
    report = await update(er, [(2, encounter())])
    assert "not found" in report.skipped[0]["reason"]


@pytest.mark.asyncio
async def test_row_beyond_the_list_is_skipped():
    er = FakeER(list_event())
    report = await update(er, [(9, encounter())])
    assert er.patches == []
    assert "has no row 9" in report.skipped[0]["reason"]


@pytest.mark.asyncio
async def test_second_sighting_for_the_same_row_is_skipped():
    er = FakeER(list_event())
    report = await update(er, [(2, encounter("enc-a")), (2, encounter("enc-b", sex="female"))])
    assert er.patches[0]["event_details"]["Animals"][1]["animal_sex"] == "m"
    assert report.skipped[0]["encounter"] == "enc-b"


@pytest.mark.asyncio
async def test_event_edited_while_updating_is_not_overwritten():
    er = FakeER(list_event(), edited_meanwhile=True)
    with pytest.raises(handlers.EventChangedDuringUpdate):
        await update(er, [(2, encounter())])
    assert er.patches == []


@pytest.mark.asyncio
async def test_value_without_a_matching_option_is_left_alone_and_noted():
    er = FakeER(list_event())
    report = await update(er, [(2, encounter(sex="AF"))])
    assert er.patches[0]["event_details"]["Animals"][1]["animal_sex"] == "u"
    assert "no animal_sex option" in report.notes[0]["note"]


# --- Activity Log ------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_run_with_nothing_to_update_logs_an_info_entry(mocker):
    log = mocker.patch.object(handlers, "log_action_activity")
    await handlers._log_report("integration-1", handlers.SiteReport("site-a"))
    assert log.call_args.kwargs["title"] == "site-a: no new Wildbook sightings for this site, nothing to update"
    assert log.call_args.kwargs["level"] == handlers.LogLevel.INFO
