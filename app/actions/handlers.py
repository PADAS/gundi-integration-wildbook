import logging
import time
from collections import defaultdict
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Dict, List, Optional

import httpx
from gundi_core.events import LogLevel

from app import settings
from app.services.action_scheduler import crontab_schedule
from app.services.activity_logger import activity_logger, log_action_activity
from app.services.earthranger import EarthRangerClient, site_name
from app.services.gundi import get_er_credentials_from_destinations
from app.services.state import IntegrationStateManager
from app.services.wildbook import WildbookClient
from .configurations import AuthenticateConfig, PullGiraffeUpdatesConfig, get_auth_config
from .core import action_title
from . import gcf

logger = logging.getLogger(__name__)
state_manager = IntegrationStateManager()

ACTION_ID = "pull_giraffe_updates"
# Wildbook changes can take a moment to reach its search index, so each run stops
# this far before now; the next run picks them up.
INDEXING_LAG = timedelta(minutes=5)
# Leave time to save progress before the runner's own limit ends the run.
TIME_BUDGET_SECONDS = max(settings.MAX_ACTION_EXECUTION_TIME - 90, 60)
MAX_LOGGED_SKIPS = 100
MAX_LOGGED_CHANGES = 300


class EventChangedDuringUpdate(Exception):
    """Someone edited the event between our read and our write; retried on the next run."""


class SiteReport:

    def __init__(self, site: str):
        self.site = site
        self.encounters = 0
        self.rows_updated = 0
        self.skipped: List[dict] = []
        self.notes: List[dict] = []
        self.changes: List[dict] = []

    def skip(self, encounter: dict, reason: str):
        self.skipped.append({"encounter": encounter.get("id"), "remarks": encounter.get("occurrenceRemarks"),
                             "reason": reason})

    def note(self, encounter: dict, reason: str):
        self.notes.append({"encounter": encounter.get("id"), "note": reason})

    def summary(self) -> dict:
        return {
            "site": self.site,
            "sightings_read": self.encounters,
            "rows_updated": self.rows_updated,
            "sightings_skipped": len(self.skipped),
        }


@action_title("Test Wildbook Connection")
async def action_auth(integration, action_config: AuthenticateConfig):
    try:
        async with WildbookClient(integration.base_url, action_config.api_token.get_secret_value()) as wildbook:
            await wildbook.check_token()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            return {"valid_credentials": False,
                    "message": "Wildbook didn't accept the API token. Check that it's current and try again."}
        raise
    return {"valid_credentials": True}


@action_title("Update Giraffe Events")
@crontab_schedule("*/20 * * * *")
@activity_logger()
async def action_pull_giraffe_updates(integration, action_config: PullGiraffeUpdatesConfig):
    """Update GCF's giraffe events in each EarthRanger destination with Giraffe ID, Sex and
    Age from Wildbook. Never creates events."""
    integration_id = str(integration.id)
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    auth = get_auth_config(integration)
    destinations = await get_er_credentials_from_destinations(integration_id)

    results = []
    async with WildbookClient(integration.base_url, auth.api_token.get_secret_value()) as wildbook:
        for er_url, er_token in destinations:
            results.append(await _sync_site(integration_id, wildbook, er_url, er_token, action_config, deadline))
    return {"sites": results}


async def _sync_site(integration_id, wildbook, er_url, er_token, config, deadline) -> dict:
    # Stamps name the site their event is on; a test site holding copies reads another site's stamps.
    copies_of = (config.test_copies_of or "").strip().lower() or None
    site = copies_of or site_name(er_url)
    report = SiteReport(site_name(er_url))
    state = await state_manager.get_state(integration_id, ACTION_ID, source_id=er_url)
    now = datetime.now(timezone.utc)
    until_ms = int((now - INDEXING_LAG).timestamp() * 1000)

    if "since_ms" in state:
        since_ms = state["since_ms"]
    elif config.start_from:
        since_ms = int(datetime.combine(config.start_from, dt_time.min, timezone.utc).timestamp() * 1000) - 1
    else:
        # First run with no start date: start from now.
        await _save_state(integration_id, er_url, {**state, "since_ms": until_ms})
        await _log_report(integration_id, report)
        return report.summary()
    if since_ms >= until_ms:
        return report.summary()

    async with EarthRangerClient(er_url, er_token) as er:
        encounters = await wildbook.get_encounters_changed(since_ms, until_ms, f"*er={site}:*")
        report.encounters = len(encounters)
        by_event = defaultdict(list)
        for encounter in encounters:
            stamp = gcf.parse_stamp(encounter.get("occurrenceRemarks"))
            if not stamp:
                report.skip(encounter, "the stamp can't be read")
            elif stamp[0] != site:
                report.skip(encounter, f"the stamp is for another site ({stamp[0]})")
            elif not encounter.get("individualId"):
                report.skip(encounter, "the giraffe isn't identified in Wildbook yet")
            else:
                by_event[stamp[1]].append((stamp[2], encounter))

        names = await wildbook.get_individual_names(
            [e["individualId"] for items in by_event.values() for _, e in items])
        list_fields_cache: Dict[str, Optional[dict]] = {}
        pending_versions = []  # sightings to retry on the next run
        for serial, items in sorted(by_event.items(), key=lambda kv: min(e["version"] for _, e in kv[1])):
            if time.monotonic() > deadline:
                pending_versions.extend(e["version"] for _, e in items)
                continue
            try:
                await _update_event(er, serial, items, names, list_fields_cache, report, copies_of)
            except Exception as exc:
                logger.exception(f"Could not update event #{serial} on {site}: {exc}")
                reason = ("the event was edited in EarthRanger while updating it"
                          if isinstance(exc, EventChangedDuringUpdate) else f"error updating event #{serial}: {exc}")
                for _, encounter in items:
                    report.skip(encounter, f"{reason}; retried on the next run")
                pending_versions.extend(e["version"] for _, e in items)

    # Everything changed up to the new starting point is done.
    new_since = min(pending_versions) - 1 if pending_versions else until_ms
    await _save_state(integration_id, er_url, {**state, "since_ms": max(new_since, since_ms)})
    await _log_report(integration_id, report)
    return report.summary()


async def _update_event(er, serial, items, names, list_fields_cache, report, copies_of=None):
    event = await (er.find_copied_event(copies_of, serial) if copies_of else er.find_event_by_serial(serial))
    if not event:
        for _, encounter in items:
            report.skip(encounter, f"event #{serial}" + (f" (a copy of {copies_of}'s)" if copies_of else "")
                        + " not found")
        return
    event_type = event.get("event_type")
    if event_type not in list_fields_cache:
        list_fields_cache[event_type] = await er.get_list_fields(event_type, gcf.LIST_FIELD)
    fields = list_fields_cache[event_type]
    if not fields or not any(f in fields for f in gcf.WRITTEN_FIELDS):
        for _, encounter in items:
            report.skip(encounter, f"event type '{event_type}' has none of the giraffe fields "
                                   f"({', '.join(gcf.WRITTEN_FIELDS)}) in its {gcf.LIST_FIELD} list")
        return

    event = await er.get_event(event["id"])
    read_at = event.get("updated_at")
    details = {k: v for k, v in (event.get("event_details") or {}).items() if k != "updates"}
    herd = [dict(row) for row in details.get(gcf.LIST_FIELD) or []]

    changed_rows, seen_rows, changes = set(), set(), []
    for row, encounter in items:
        if not 1 <= row <= len(herd):
            report.skip(encounter, f"event #{serial} has no row {row}")
            continue
        if row in seen_rows:
            report.skip(encounter, f"another sighting is stamped for event #{serial} row {row}")
            continue
        seen_rows.add(row)
        current = herd[row - 1]
        for field, (wildbook_value, er_value) in gcf.row_values(
                encounter, names.get(encounter["individualId"]), fields).items():
            if er_value is None:
                if wildbook_value:
                    report.note(encounter, f"no {field} option for Wildbook value '{wildbook_value}', left as is")
                continue
            if current.get(field) != er_value:
                changes.append({"event": serial, "row": row, "field": field, "from": current.get(field),
                                "to": er_value, "encounter": encounter["id"]})
                current[field] = er_value
                changed_rows.add(row)

    if not changed_rows:
        return
    latest = await er.get_event(event["id"])
    if latest.get("updated_at") != read_at:
        raise EventChangedDuringUpdate()
    await er.patch_event(event["id"], {"event_details": {**details, gcf.LIST_FIELD: herd}})
    report.rows_updated += len(changed_rows)
    report.changes.extend(changes)


async def _log_report(integration_id, report: SiteReport):
    summary = report.summary()
    if not report.encounters:
        await log_action_activity(
            integration_id=integration_id,
            action_id=ACTION_ID,
            title=f"{report.site}: no new Wildbook sightings for this site, nothing to update",
            level=LogLevel.INFO,
            data=summary,
        )
        return
    await log_action_activity(
        integration_id=integration_id,
        action_id=ACTION_ID,
        title=f"{report.site}: {report.rows_updated} giraffe row(s) updated, {len(report.skipped)} sighting(s) skipped",
        level=LogLevel.WARNING if report.skipped else LogLevel.INFO,
        data={**summary, "changes": report.changes[:MAX_LOGGED_CHANGES],
              "skipped": report.skipped[:MAX_LOGGED_SKIPS], "notes": report.notes[:MAX_LOGGED_SKIPS]},
    )


async def _save_state(integration_id, er_url, state):
    await state_manager.set_state(integration_id=integration_id, action_id=ACTION_ID, source_id=er_url, state=state)
