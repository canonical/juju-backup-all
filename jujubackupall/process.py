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
from contextlib import contextmanager
from pathlib import Path
import logging
from typing import List, NamedTuple

from juju.controller import Controller
from juju.model import Model

from jujubackupall.backup import get_charm_backup_instance, JujuControllerBackup
from jujubackupall.config import Config
from jujubackupall.constants import SUPPORTED_BACKUP_CHARMS
from jujubackupall.utils import parse_charm_name, get_all_controllers, get_leader, connect_controller, connect_model


logger = logging.getLogger(__name__)


class JujuModel(NamedTuple):
    name: str
    model: Model


class BackupProcessor:
    controllers_to_backup = None

    def __init__(self, config: Config):
        self.config = config

    @property
    def apps_to_backup(self) -> List[str]:
        if self.config.excluded_charms:
            return list(set(SUPPORTED_BACKUP_CHARMS) - set(self.config.excluded_charms))
        return SUPPORTED_BACKUP_CHARMS

    @property
    def controller_names(self) -> List[str]:
        if self.controllers_to_backup:
            return self.controllers_to_backup
        elif self.config.all_controllers:
            controllers = get_all_controllers()
            self.controllers_to_backup = controllers
        elif self.controllers_to_backup:
            self.controllers_to_backup = self.config.controllers
        elif self.config.use_current_controller:
            # backup the current controller by passing blank string
            self.controllers_to_backup = ['']
        return self.controllers_to_backup

    async def process_backups(self):
        for controller_name in self.controller_names:
            async with connect_controller(controller_name) as controller:
                controller_processor = ControllerProcessor(controller,
                                                           self.apps_to_backup,
                                                           Path(self.config.output_dir))
                await controller_processor.backup_models()
                if self.config.backup_controller:
                    controller_processor.backup_controller()


class ControllerProcessor:
    def __init__(self, controller: Controller, apps_to_backup: List[str], base_output_path: Path):
        """ Processes all backups within a connected Juju controller.

        :param controller: connected Juju controller
        :param apps_to_backup: list of apps to backup
        :param base_output_path: base path for saving backups
        """
        self.controller = controller
        self.apps_to_backup = apps_to_backup
        self.base_output_path = base_output_path

    def backup_controller(self):
        controller_backup_save_path = self.base_output_path / self.controller.controller_name
        controller_backup = JujuControllerBackup(controller=self.controller,
                                                 save_path=controller_backup_save_path)
        controller_backup.backup()

    async def backup_models(self):
        model_names = await self.controller.list_models()
        for model_name in model_names:
            async with connect_model(model_name) as model:
                await self.backup_apps(JujuModel(name=model_name, model=model))

    async def backup_apps(self, model: JujuModel):
        model_name, model = model.name, model.model
        for app_name, app in model.applications.items():
            charm_url = app.data.get('charm-url')
            charm_name = parse_charm_name(charm_url)
            if charm_name in self.apps_to_backup:
                leader_unit = await get_leader(app.units)
                charm_backup_instance = get_charm_backup_instance(charm_name=charm_name,
                                                                  unit=leader_unit)
                logger.info('Backing up {} app ({} charm)'.format(app_name, charm_name))
                await charm_backup_instance.backup()
                logger.info('App {} backed up'.format(app_name))
                logger.info('Downloading backups'.format(app_name))
                await charm_backup_instance.download_backup(self.generate_full_backup_path(model_name, app_name))
                logger.info('Backups downloaded to {}'.format(self.generate_full_backup_path(model_name, app_name)))

    def generate_full_backup_path(self, model_name: str, app_name: str) -> Path:
        return self.base_output_path / self.controller.controller_name / model_name / app_name
