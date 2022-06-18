"""Plugin to upload pictures to Microsoft OneDrive.
- [ ] postpone upload to idle state

"""

from graph_onedrive import OneDriveManager, OneDrive
from distutils.command.config import config
import os

import pibooth
from pibooth.utils import LOGGER
from pibooth.config import PiConfigParser

__version__ = "0.0.1"

@pibooth.hookimpl
def pibooth_startup(cfg, app):
    """Connect to OneDrive via Graph api and create folder for image upload."""

    LOGGER.info("Setup OneDrive Client")
    app.onedrive = OneDrive(
        client_id = cfg.get('ONEDRIVE', 'client_id'),
        client_secret = cfg.get('ONEDRIVE', 'client_secret'),
        tenant = cfg.get('ONEDRIVE', 'tenant'),
        redirect_url = cfg.get('ONEDRIVE', 'redirect_url'),
        refresh_token = cfg.get('ONEDRIVE', 'refresh_token')
    )

    app.folder_id = app.onedrive.make_folder('FotoBox')
    LOGGER.info(f"USING FOLDER: {app.folder_id}")


@pibooth.hookimpl
def state_print_enter(app):
    """Upload prefious picture to OneDrive."""
    name = os.path.basename(app.previous_picture_file)
    LOGGER.info(f"Upload {name} to Onedrive")
    app.onedrive.upload_file(
        file_path=app.previous_picture_file,
        new_file_name=name,
        parent_folder_id=app.folder_id,
    )
    LOGGER.info(f"Upload Completed")


@pibooth.hookimpl
def pibooth_cleanup(app):
    """Save access Token to Config File."""
    LOGGER.info("Close OneDrive.")
    app._config.set('ONEDRIVE', app.onedrive.refresh_token)
