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
from typing import TypeVar

from juju.action import Action
from juju.unit import Unit
from juju.controller import Controller

from jujubackupall.utils import ensure_path_exists


CharmBackupType = TypeVar('CharmBackupType', bound='CharmBackup')


class BaseBackup(object, metaclass=ABCMeta):
    """BaseBackup metaclass for backups."""
    @abstractmethod
    def backup(self):
        pass


class CharmBackup(BaseBackup, metaclass=ABCMeta):
    charm_name: str = NotImplemented

    def __init__(self, unit: Unit):
        self.unit = unit

    @abstractmethod
    def download_backup(self, save_path: Path):
        pass


class MysqlInnodbBackup(CharmBackup):
    charm_name = 'mysql-innodb-cluster'
    backup_action_name = 'mysqldump'
    mysqldump_file_path = None

    async def backup(self):
        backup_action: Action = await self.unit.run_action(self.backup_action_name)
        await backup_action.wait()
        self.mysqldump_file_path = Path(backup_action.safe_data.get('results').get('mysqldump-file'))

    async def download_backup(self, save_path: Path):
        filename = self.mysqldump_file_path.name
        tmp_path = Path('/tmp') / filename
        cp_chown_command = 'sudo cp {} /tmp && sudo chown ubuntu:ubuntu {}'.format(self.mysqldump_file_path, tmp_path)
        await self.unit.ssh(command=cp_chown_command, user='ubuntu')
        ensure_path_exists(path=save_path)
        await self.unit.scp_from(source=str(tmp_path), destination=str(save_path))
        rm_command = 'sudo rm -r {} {}'.format(self.mysqldump_file_path, tmp_path)
        await self.unit.ssh(command=rm_command, user='ubuntu')


class PerconaClusterBackup(CharmBackup):
    charm_name = 'percona-cluster'
    backup_action_name = 'mysqldump'
    mysqldump_file_path = None

    async def backup(self):
        set_pxc_strict_mode_permissive_action: Action = await self.unit.run_action('set-pxc-strict-mode',
                                                                                   mode='MASTER')
        await set_pxc_strict_mode_permissive_action.wait()
        assert set_pxc_strict_mode_permissive_action.status == 'completed'
        backup_action: Action = await self.unit.run_action(self.backup_action_name)
        await backup_action.wait()
        set_pxc_strict_mode_permissive_action: Action = await self.unit.run_action('set-pxc-strict-mode',
                                                                                   mode='ENFORCING')
        await set_pxc_strict_mode_permissive_action.wait()
        assert set_pxc_strict_mode_permissive_action.status == 'completed'
        print(backup_action.safe_data)
        self.mysqldump_file_path = Path(backup_action.safe_data.get('results').get('mysqldump-file'))

    async def download_backup(self, save_path: Path):
        filename = self.mysqldump_file_path.name
        tmp_path = Path('/tmp') / filename
        cp_chown_command = 'sudo cp {} /tmp && sudo chown ubuntu:ubuntu {}'.format(self.mysqldump_file_path, tmp_path)
        await self.unit.ssh(command=cp_chown_command, user='ubuntu')
        ensure_path_exists(path=save_path)
        await self.unit.scp_from(source=str(tmp_path), destination=str(save_path))
        rm_command = 'sudo rm -r {} {}'.format(self.mysqldump_file_path, tmp_path)
        await self.unit.ssh(command=rm_command, user='ubuntu')


class EtcdBackup(CharmBackup):
    charm_name = 'etcd'

    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class PostgresqlBackup(CharmBackup):
    charm_name = 'postgresql'

    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class SwiftBackup(CharmBackup):
    charm_name = 'swift-proxy'

    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class JujuControllerBackup(BaseBackup):

    def __init__(self, controller: Controller, save_path=Path()):
        super().__init__()
        self.controller = controller
        self.save_path = save_path

    def backup(self):
        pass


def get_charm_backup_instance(charm_name: str, unit: Unit) -> CharmBackupType:
    if charm_name == MysqlInnodbBackup.charm_name:
        return MysqlInnodbBackup(unit=unit)
    if charm_name == PerconaClusterBackup.charm_name:
        return PerconaClusterBackup(unit=unit)
    if charm_name == EtcdBackup.charm_name:
        return PerconaClusterBackup(unit=unit)
    if charm_name == PostgresqlBackup.charm_name:
        return EtcdBackup(unit=unit)
    if charm_name == SwiftBackup.charm_name:
        return SwiftBackup(unit=unit)
    raise Exception('{} is not a supported charm.'.format(charm_name))