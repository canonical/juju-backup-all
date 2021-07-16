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
"""Module that provides the backup classes for the various charms."""
from abc import ABCMeta, abstractmethod
from pathlib import Path

from juju.unit import Unit
from juju.controller import Controller


class BaseBackup(object, metaclass=ABCMeta):
    """BaseBackup metaclass for backups."""
    @abstractmethod
    def backup(self):
        pass


class CharmBackup(BaseBackup, metaclass=ABCMeta):
    def __init__(self, unit: Unit):
        self.unit = unit

    @abstractmethod
    def download_backup(self, save_path: Path):
        pass


class MysqlInnodbBackup(CharmBackup):

    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class PerconaClusterBackup(CharmBackup):

    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class EtcdBackup(CharmBackup):

    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class PostgresqlBackup(CharmBackup):
    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class SwiftBackup(CharmBackup):
    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class JujuControllerBackup(BaseBackup):

    def __init__(self, controller: Controller, save_path: Path):
        super().__init__()
        self.controller = controller
        self.save_path = save_path

    def backup(self):
        pass
