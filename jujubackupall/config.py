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
"""Config for backups passed in by operator."""
from typing import List


class Config:
    def __init__(self, args: dict):
        self.args = args

    @property
    def all_controllers(self) -> bool:
        return self.args.get("all_controllers")

    @property
    def backup_controller(self) -> bool:
        return self.args.get("backup_controller")

    @property
    def backup_juju_client_config(self) -> bool:
        return self.args.get("backup_juju_client_config")

    @property
    def controllers(self) -> List[str]:
        return self.args.get("controllers")

    @property
    def excluded_charms(self) -> List[str]:
        return self.args.get("excluded_charms")

    @property
    def output_dir(self) -> str:
        return self.args.get("output_dir")

    @property
    def use_current_controller(self) -> bool:
        return not self.controllers and not self.all_controllers
