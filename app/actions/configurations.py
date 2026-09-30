from datetime import date
from typing import Optional

import pydantic

from app.actions.core import AuthActionConfiguration, ExecutableActionMixin, PullActionConfiguration
from app.services.errors import ConfigurationNotFound
from app.services.utils import FieldWithUIOptions, GlobalUISchemaOptions, UIOptions, find_config_for_action


class AuthenticateConfig(AuthActionConfiguration, ExecutableActionMixin):
    api_token: pydantic.SecretStr = FieldWithUIOptions(
        ...,
        format="password",
        title="API Token",
        description="Wildbook API token, created in your Wildbook account.",
    )

    ui_global_options: GlobalUISchemaOptions = GlobalUISchemaOptions(
        order=["api_token"],
    )


class PullGiraffeUpdatesConfig(PullActionConfiguration):
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
            "site's name (for example twiga): Wildbook sightings for that site then update the "
            "copies here, found by the \"Copied from ... event #...\" note on each copy."
        ),
    )

    ui_global_options: GlobalUISchemaOptions = GlobalUISchemaOptions(
        order=["run_on_schedule", "start_from", "test_copies_of"],
    )


def get_auth_config(integration) -> AuthenticateConfig:
    auth_config = find_config_for_action(configurations=integration.configurations, action_id="auth")
    if not auth_config:
        raise ConfigurationNotFound(
            f"Authentication settings for integration {integration.id} are missing. "
            "Please fix the integration setup in the portal."
        )
    return AuthenticateConfig.parse_obj(auth_config.data)
