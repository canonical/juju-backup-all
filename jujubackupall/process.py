#!/usr/bin/env python3
# This file is part of juju-backup-all, a tool for backing up all things Juju:
# charm data, controllers, configs, etc.
#
# Copyright 2018-2021 Canonical Limited.
# License granted by Canonical Limited.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""Module that processes the desired backups."""
import logging
from pathlib import Path
from typing import List, NamedTuple

from juju.application import Application
from juju.controller import Controller
from juju.errors import JujuError
from juju.model import Model

from jujubackupall.async_handlers import run_async
from jujubackupall.backup import (
    BackupTracker,
    JujuClientConfigBackup,
    JujuControllerBackup,
    get_charm_backup_instance,
)
from jujubackupall.config import Config
from jujubackupall.constants import SUPPORTED_BACKUP_CHARMS
from jujubackupall.errors import (
    ActionError,
    JujuControllerBackupError,
    JujuTimeoutError,
    NoLeaderError,
)
from jujubackupall.utils import (
    connect_controller,
    connect_model,
    get_all_controllers,
    get_leader,
    parse_charm_name,
)

logger = logging.getLogger(__name__)
tracker = BackupTracker()


class JujuModel(NamedTuple):
    name: str
    model: Model


class BackupProcessor:
    _controller_names = None

    def __init__(self, config: Config):
        self.config = config

    @property
    def apps_to_backup(self) -> List[str]:
        # TODO: Refactor this logic into config.py
        if self.config.excluded_charms:
            return list(set(SUPPORTED_BACKUP_CHARMS) - set(self.config.excluded_charms))
        return SUPPORTED_BACKUP_CHARMS

    @property
    def controller_names(self) -> List[str]:
        # TODO: Refactor this logic into config.py
        if self._controller_names:
            return self._controller_names
        elif self.config.all_controllers:
            controllers = get_all_controllers()
            self._controller_names = controllers
        elif self.config.controllers:
            self._controller_names = self.config.controllers
        elif self.config.use_current_controller:
            # backup the current controller by passing blank string
            self._controller_names = [""]
        return self._controller_names

    def process_backups(self, omit_models=None):
        if self.config.backup_juju_client_config:
            config_backup_dir_path = Path(self.config.output_dir)
            backup_juju_client_config_inst = JujuClientConfigBackup(config_backup_dir_path)
            resulting_backup_path = backup_juju_client_config_inst.backup()
            tracker.add_config_backup(backup_juju_client_config_inst.client_config_name, str(resulting_backup_path))
        for controller_name in self.controller_names:
            with connect_controller(controller_name) as controller:
                logger.info("[{}] Processing backups.".format(controller.controller_name))
                controller_processor = ControllerProcessor(
                    controller,
                    self.apps_to_backup,
                    Path(self.config.output_dir),
                    Path(self.config.backup_location_on_postgresql),
                    Path(self.config.backup_location_on_mysql),
                    Path(self.config.backup_location_on_etcd),
                )
                controller_processor.backup_models(omit_models=omit_models)
                if self.config.backup_controller:
                    controller_processor.backup_controller()
        return tracker.to_json()


class ControllerProcessor:
    def __init__(
        self,
        controller: Controller,
        apps_to_backup: List[str],
        base_output_path: Path,
        backup_location_on_postgresql: Path,
        backup_location_on_mysql: Path,
        backup_location_on_etcd: Path,
    ):
        """Process all backups within a connected Juju controller.

        :param controller: connected Juju controller
        :param apps_to_backup: list of apps to backup
        :param base_output_path: base path for saving backups
        :param backup_location_on_postgresql: backup location on postgresql unit
        :param backup_location_on_mysql: backup location on mysql unit
        :param backup_location_on_etcd: backup location on etcd unit
        """
        self.controller = controller
        self.apps_to_backup = apps_to_backup
        self.base_output_path = base_output_path
        self.backup_location_on_postgresql = backup_location_on_postgresql
        self.backup_location_on_mysql = backup_location_on_mysql
        self.backup_location_on_etcd = backup_location_on_etcd

    def backup_controller(self):
        controller_backup_save_path = self.base_output_path / self.controller.controller_name
        controller_backup = JujuControllerBackup(controller=self.controller, save_path=controller_backup_save_path)
        try:
            self._log("Backing up controller.")
            resulting_backup_path = controller_backup.backup()
            tracker.add_controller_backup(self.controller.controller_name, str(resulting_backup_path))
            self._log("Controller backed up to: {}".format(controller_backup_save_path))
        except JujuControllerBackupError as controller_backup_error:
            self._log("Juju controller backup failed: {}".format(controller_backup_error))
            tracker.add_error(
                controller=self.controller.controller_name,
                error_reason=str(controller_backup_error),
            )

    def backup_models(self, omit_models=None):
        model_names: List[str] = run_async(self.controller.list_models())
        model_names = set(model_names) - set(omit_models or [])
        self._log("Models to process {}".format(model_names))
        for model_name in model_names:
            with connect_model(self.controller, model_name) as model:
                self._log("Backing up apps.", model_name=model_name)
                self.backup_apps(JujuModel(name=model_name, model=model))

    def backup_apps(self, model: JujuModel):
        model_name, model = model.name, model.model
        for app_name, app in model.applications.items():
            charm_url = app.data.get("charm-url")
            charm_name = parse_charm_name(charm_url)
            if charm_name in self.apps_to_backup:
                self.backup_app(app=app, app_name=app_name, charm_name=charm_name, model_name=model_name)

    def backup_app(self, app: Application, app_name: str, charm_name: str, model_name: str):
        try:
            leader_unit = get_leader(app.units)
            charm_backup_instance = get_charm_backup_instance(
                charm_name=charm_name,
                unit=leader_unit,
                backup_location_on_postgresql=self.backup_location_on_postgresql,
                backup_location_on_mysql=self.backup_location_on_mysql,
                backup_location_on_etcd=self.backup_location_on_etcd,
            )
            self._log("Backing up app.", app_name=app_name, model_name=model_name)
            charm_backup_instance.backup()
            self._log("Downloading backup.", app_name=app_name, model_name=model_name)
            full_backup_path = self.generate_full_backup_path(model_name, app_name)
            resulting_backup_path = charm_backup_instance.download_backup(full_backup_path)
            tracker.add_app_backup(
                controller=self.controller.controller_name,
                model=model_name,
                app=app_name,
                charm=charm_name,
                download_path=str(resulting_backup_path),
            )
            self._log(
                "Backups downloaded to {}".format(resulting_backup_path), app_name=app_name, model_name=model_name
            )
        except (ActionError, NoLeaderError, JujuError, JujuTimeoutError) as error:
            self._log(
                "App backup not completed: {}.".format(error),
                app_name=app_name,
                model_name=model_name,
                level=logging.ERROR,
            )
            tracker.add_error(
                controller=self.controller.controller_name,
                model=model_name,
                app=app_name,
                charm=charm_name,
                error_reason=str(error),
            )

    def generate_full_backup_path(self, model_name: str, app_name: str) -> Path:
        return self.base_output_path / self.controller.controller_name / model_name / app_name

    def _log(self, msg, app_name=None, model_name=None, level=logging.INFO):
        formatted_msg = "[{}] {}".format(
            " ".join([x for x in (self.controller.controller_name, model_name, app_name) if x]), msg
        )
        logger.log(level=level, msg=formatted_msg)
