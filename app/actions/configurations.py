from datetime import date
from typing import Optional

import pydantic

from app.actions.core import AuthActionConfiguration, ExecutableActionMixin, PullActionConfiguration
from app.services.errors import ConfigurationNotFound
from app.services.utils import FieldWithUIOptions, GlobalUISchemaOptions, UIOptions, find_config_for_action


class AuthenticateConfig(AuthActionConfiguration, ExecutableActionMixin):
    wildbook_url: str = FieldWithUIOptions(
        ...,
        title="Wildbook Address",
        description="The web address of your Wildbook, as you open it in the browser.",
        ui_options=UIOptions(placeholder="e.g. https://your-wildbook.org"),
    )
    api_token: pydantic.SecretStr = FieldWithUIOptions(
        ...,
        format="password",
        title="API Token",
        description="Wildbook API token, created in your Wildbook account.",
    )

    ui_global_options: GlobalUISchemaOptions = GlobalUISchemaOptions(
        order=["wildbook_url", "api_token"],
    )

    @pydantic.validator("wildbook_url")
    def check_wildbook_url(cls, v):
        v = (v or "").strip().rstrip("/")
        if not v.startswith(("https://", "http://")):
            raise ValueError("Enter the full address, starting with https://")
        return v


class PullEventUpdatesConfig(PullActionConfiguration):
    list_field: str = FieldWithUIOptions(
        ...,
        title="List Field",
        description=(
            "The EarthRanger field ID of the list on the event that holds one row per animal, "
            "as written in the event type's schema (not its display name)."
        ),
        ui_options=UIOptions(placeholder="e.g. Animals"),
    )
    id_field: Optional[str] = FieldWithUIOptions(
        None,
        title="ID Field",
        description=(
            "The EarthRanger field ID, inside that list, that takes the animal's Wildbook name. "
            "Leave empty to not update it."
        ),
        ui_options=UIOptions(placeholder="e.g. animal_id"),
    )
    sex_field: Optional[str] = FieldWithUIOptions(
        None,
        title="Sex Field",
        description=(
            "The EarthRanger field ID, inside that list, that takes the animal's sex from Wildbook. "
            "Leave empty to not update it."
        ),
        ui_options=UIOptions(placeholder="e.g. animal_sex"),
    )
    age_field: Optional[str] = FieldWithUIOptions(
        None,
        title="Age Field",
        description=(
            "The EarthRanger field ID, inside that list, that takes the animal's life stage from Wildbook. "
            "Leave empty to not update it."
        ),
        ui_options=UIOptions(placeholder="e.g. animal_age"),
    )
    notes_field: Optional[str] = FieldWithUIOptions(
        None,
        title="Notes Field",
        description=(
            "The EarthRanger field ID, inside that list, that takes the animal's remarks from Wildbook "
            "(without the er= tag), added after the notes already there. Leave empty to not update it."
        ),
        ui_options=UIOptions(placeholder="e.g. animal_notes"),
    )
    photo_field: Optional[str] = FieldWithUIOptions(
        None,
        title="Photo Field",
        description=(
            "The EarthRanger field ID, inside that list, of an attachment field that takes one photo "
            "of the animal from Wildbook. Leave empty to not add photos."
        ),
        ui_options=UIOptions(placeholder="e.g. animal_photo"),
    )
    photo_viewpoint: Optional[str] = FieldWithUIOptions(
        None,
        title="Photo Viewpoint",
        description=(
            "Only use Wildbook photos taken from this side, as Wildbook names it. "
            "Leave empty to use the first photo of any side."
        ),
        ui_options=UIOptions(placeholder="e.g. right"),
    )
    start_from: Optional[date] = FieldWithUIOptions(
        None,
        title="Start From",
        description=(
            "Update events from Wildbook sightings changed on or after this date. "
            "Leave empty to start from the first run."
        ),
        ui_options=UIOptions(widget="date"),
    )
    test_copies_of: Optional[str] = FieldWithUIOptions(
        None,
        title="Test Only: Copies Of Site",
        description=(
            "Leave empty. On a test site holding copies of another site's events, enter that "
            "site's name: Wildbook sightings for that site then update the "
            "copies here, found by the \"Copied from ... event #...\" note on each copy."
        ),
        ui_options=UIOptions(placeholder="e.g. mysite"),
    )

    ui_global_options: GlobalUISchemaOptions = GlobalUISchemaOptions(
        order=["run_on_schedule", "list_field", "id_field", "sex_field", "age_field", "notes_field", "photo_field", "photo_viewpoint", "start_from", "test_copies_of"],
    )

    @pydantic.validator("list_field", "id_field", "sex_field", "age_field", "notes_field", "photo_field", "photo_viewpoint", pre=True)
    def strip_field_names(cls, v):
        return v.strip() or None if isinstance(v, str) else v

    @pydantic.root_validator(skip_on_failure=True)
    def check_some_field(cls, values):
        if not values.get("list_field"):
            raise ValueError("Enter the list field.")
        if not any(values.get(f) for f in ("id_field", "sex_field", "age_field", "notes_field", "photo_field")):
            raise ValueError("Enter at least one of the ID, sex, age, notes or photo fields.")
        return values


def get_auth_config(integration) -> AuthenticateConfig:
    auth_config = find_config_for_action(configurations=integration.configurations, action_id="auth")
    if not auth_config:
        raise ConfigurationNotFound(
            f"Authentication settings for integration {integration.id} are missing. "
            "Please fix the integration setup in the portal."
        )
    return AuthenticateConfig.parse_obj(auth_config.data)
