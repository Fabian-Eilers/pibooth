"""Plugin to upload pictures to Microsoft OneDrive.
"""
import asyncio
from configparser import ConfigParser
import logging
import threading
from queue import Queue
import os
import httpx

from graph_onedrive import OneDrive as GraphOneDrive
import pibooth


__version__ = "1.0.0"


async def worker(worker_id: int, queue: Queue, onedrive_client: GraphOneDrive):
    """Asynchroner worker zum hochladen von Fotos in OneDrive

    :param (int) worker_id: Identifier für Worker Unit.
    :param (Queue) queue: FIFO Queue zum Hochladen der Bilder.
    :param (GraphOneDrive) onedrive_client: OneDrive Graph API Client.
    """
    while True:
        file_path, parent_folder_id  = queue.get()
        fname = os.path.basename(file_path)
        logging.info("W%i %s/ %s Started.", worker_id, parent_folder_id, fname)
        try:
            onedrive_client.upload_file(
                file_path=file_path,
                new_file_name=fname,
                parent_folder_id=parent_folder_id
            )
            logging.info("W%i %s/%s Finished.", worker_id, parent_folder_id, fname)
            queue.task_done()
        except httpx.ConnectError:
            queue.put((file_path, parent_folder_id))
            await asyncio.sleep(10)
            logging.error("W%i %s/%s", worker_id, parent_folder_id, fname)


class OneDrive:
    """Hauptklasse für Komminikation mit OneDrive.

    :attr (GraphOneDrive) client: Wird in setup_client erstellt.
    :attr (str) private_folder: Wird in initialize_client festgelegt.
    :attr (str) public_folder: Wird in initialize_client festgelegt.
    :attr (Queue) queue: FIFO Queue mit den hochzuladenen Bildern.
    :attr (threading.Thread) daemon: Event thread für async Upload.
    """
    def __init__(self, cfg: ConfigParser):
        self.client = None
        self.private_folder = None
        self.public_folder = None

        # self.client = self.setup_client(cfg)
        self.queue = Queue()
        self.daemon = threading.Thread(
            target=lambda: asyncio.run(self.loop()),
            name="onedrive-pull-loop", daemon=True)
        self.daemon.start()

        self._cfg = cfg

    async def loop(self):
        """Mainloop for async thread."""
        await self.setup_client()
        tasks = [asyncio.create_task(worker(worker_id, self.queue, self.client))
                 for worker_id in range(3)]
        await asyncio.gather(*tasks)

    async def setup_client(self):
        """Connect to OneDrive using GraphOneDrive API."""
        connection_established = False
        while not connection_established:
            try:
                self.client = GraphOneDrive(
                    client_id = self._cfg.get('ONEDRIVE', 'client_id'),
                    client_secret = self._cfg.get('ONEDRIVE', 'client_secret'),
                    tenant = self._cfg.get('ONEDRIVE', 'tenant'),
                    redirect_url = self._cfg.get('ONEDRIVE', 'redirect_url'),
                    refresh_token = self._cfg.get('ONEDRIVE', 'refresh_token')
                )
                # initialize client
                self.initialize_client()
                connection_established = True
                logging.info("OneDrive connection established.")
            except httpx.ConnectError:
                # wait for 10 seconds and try to establish connection again.
                logging.info(("Connection could not be established. "
                              "Next Try in 10 seconds."))
                await asyncio.sleep(10.0)

    def initialize_client(self):
        """Create required Folder Struture."""
        self.public_folder = self.client.make_folder('FotoBox')
        self.private_folder = self.client.make_folder('FotoBox (private)')


@pibooth.hookimpl
def pibooth_startup(cfg, app):
    """Connect to OneDrive via Graph api and create folder for image upload."""
    logging.info("Initializing OneDrive")
    app.onedrive = OneDrive(cfg)

    plugins = app._pm.get_plugins()
    for plugin in plugins:
        if plugin.__class__.__name__ == "ViewPlugin":
            app.onedrive.view_plugin = plugin


@pibooth.hookimpl
def state_print_exit(cfg, app, win):
    """Hook to initialize the file upload."""
    del cfg, win
    if app.onedrive.view_plugin.forgotten:
        parent_folder_id = app.onedrive.private_folder
        fname = app.forget_file
    else:
        parent_folder_id = app.onedrive.public_folder
        fname = app.previous_picture_file
    logging.info("state_print_exit: %s/%s", parent_folder_id, fname)
    app.onedrive.queue.put_nowait((fname, parent_folder_id))


@pibooth.hookimpl
def pibooth_cleanup(app):
    """Cleanup hook close OneDrive connection and save config."""
    try:
        app._config.set('ONEDRIVE', app.onedrive.client.refresh_token)
        logging.info("OneDrive connection has been closed.")
    except AttributeError:
        logging.info("Ondrive Instance was never created.")


@pibooth.hookimpl
def state_print_enter(cfg, app, win):
    """Empty printer Queue when disconnected"""
    logging.info("hookimpl: state_print_enter")
    app.printer.cancel_all_tasks()