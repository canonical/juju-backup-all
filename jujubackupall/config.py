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
import argparse
from typing import List

from jujubackupall.constants import SUPPORTED_BACKUP_CHARMS


class Config:
    def __init__(self):
        parser = argparse.ArgumentParser(description='Get a backup of all things Juju.')
        parser.add_argument('-o', '--output-directory', dest='output_dir', default='juju-backups')
        parser.add_argument('-c', '--charm', dest='charms', action='append', choices=SUPPORTED_BACKUP_CHARMS)
        group = parser.add_mutually_exclusive_group()
        group.add_argument('-C', '--controller', dest='controllers', action='append')
        group.add_argument('-A', '--all-controllers', dest='all_controllers', action='store_true')
        self.args = parser.parse_args()

    @property
    def output_dir(self) -> str:
        return self.args.output_dir

    @property
    def charms(self) -> List[str]:
        return self.args.charms

    @property
    def controllers(self) -> List[str]:
        return self.args.controllers

    @property
    def all_controllers(self) -> bool:
        return self.args.all_controllers

    @property
    def current_controller(self) -> bool:
        return not self.controllers and not self.controllers

