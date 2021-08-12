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
import os
import shutil
import subprocess
from abc import ABCMeta, abstractmethod
from logging import getLogger
from pathlib import Path
from typing import TypeVar

from juju.action import Action
from juju.controller import Controller
from juju.loop import run as run_async
from juju.unit import Unit

from jujubackupall.constants import MAX_CONTROLLER_BACKUP_RETRIES
from jujubackupall.errors import JujuControllerBackupError
from jujubackupall.utils import ensure_path_exists, get_datetime_string

CharmBackupType = TypeVar("CharmBackupType", bound="CharmBackup")
logger = getLogger(__name__)


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


class MysqlBackup(CharmBackup, metaclass=ABCMeta):
    backup_action_name = "mysqldump"
    _mysqldump_file_path = None

    @property
    def mysqldump_file_path(self):
        return self._mysqldump_file_path

    @mysqldump_file_path.setter
    def mysqldump_file_path(self, path):
        self._mysqldump_file_path = path

    def backup(self):
        backup_action: Action = run_async(self.unit.run_action(self.backup_action_name))
        run_async(backup_action.wait())
        self.mysqldump_file_path = Path(backup_action.safe_data.get("results").get("mysqldump-file"))

    def download_backup(self, save_path: Path):
        filename = self.mysqldump_file_path.name
        tmp_path = Path("/tmp") / filename
        cp_chown_command = "sudo cp {} /tmp && sudo chown ubuntu:ubuntu {}".format(self.mysqldump_file_path, tmp_path)
        run_async(self.unit.ssh(command=cp_chown_command, user="ubuntu"))
        ensure_path_exists(path=save_path)
        run_async(self.unit.scp_from(source=str(tmp_path), destination=str(save_path)))
        rm_command = "sudo rm -r {} {}".format(self.mysqldump_file_path, tmp_path)
        run_async(self.unit.ssh(command=rm_command, user="ubuntu"))


class MysqlInnodbBackup(MysqlBackup):
    charm_name = "mysql-innodb-cluster"

    def backup(self):
        super().backup()

    def download_backup(self, save_path: Path):
        super().download_backup(save_path)


class PerconaClusterBackup(MysqlBackup):
    charm_name = "percona-cluster"

    def _set_pxc_mode(self, mode: str):
        set_pxc_strict_mode_permissive_action: Action = run_async(
            self.unit.run_action("set-pxc-strict-mode", mode=mode)
        )
        run_async(set_pxc_strict_mode_permissive_action.wait())
        assert set_pxc_strict_mode_permissive_action.status == "completed"

    def backup(self):
        self._set_pxc_mode("MASTER")
        super().backup()
        self._set_pxc_mode("ENFORCING")


class EtcdBackup(CharmBackup):
    charm_name = "etcd"

    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class PostgresqlBackup(CharmBackup):
    charm_name = "postgresql"

    def backup(self):
        pass

    def download_backup(self, save_path: Path):
        pass


class SwiftBackup(CharmBackup):
    charm_name = "swift-proxy"

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
        """Run `juju create-backup` against Juju controller.

        As juju controller backups tend to be flaky, this method will retry the backups.
        If backups fail all retries, a JujuControllerBackupError is raised with info on the
        last failure.

        :raise: JujuControllerBackupError: If all tried backups fail
        """
        filename = "juju-controller-backup-{}.tar.gz".format(get_datetime_string())
        save_file_path = self.save_path / filename
        command = "juju create-backup -m {}:controller --filename {}".format(
            self.controller.controller_name, save_file_path
        )
        ensure_path_exists(path=self.save_path)

        def try_backup():
            output = subprocess.check_output(command.split(), stderr=subprocess.STDOUT)
            logger.debug("juju create-backup output:\n{}".format(output.decode() if output else ""))

        # retry controller backup commands. If all fail, raise last error
        last_error = None
        for i in range(MAX_CONTROLLER_BACKUP_RETRIES):
            try:
                logger.info("[{}] Attempt #{} for controller backup.".format(self.controller.controller_name, i + 1))
                try_backup()
                break
            except subprocess.CalledProcessError as called_proc_error:
                error_msg = "[{}] Attempt #{} Encountered controller backup error: {}\nCommand output: {}".format(
                    self.controller.controller_name,
                    i + 1,
                    called_proc_error,
                    called_proc_error.output.decode() if called_proc_error.output else "",
                )
                last_error = called_proc_error
                logger.warning("{}".format(error_msg))
                continue
        else:
            error_msg = "[{}] All {} controller backup attempts failed.\nLast error: {}".format(
                self.controller.controller_name, MAX_CONTROLLER_BACKUP_RETRIES, last_error
            )
            logger.error(error_msg)
            raise JujuControllerBackupError(last_error)


class ClientConfigBackup(BaseBackup, metaclass=ABCMeta):
    client_config_name: str = NotImplemented
    client_config_location: Path = NotImplemented

    def __init__(self, base_output_dir: Path):
        self.base_output_dir = base_output_dir

    def backup(self):
        output_path = (
            self.base_output_dir / "local_configs" / "{}-{}".format(self.client_config_name, get_datetime_string())
        )
        ensure_path_exists(output_path.parent)
        shutil.make_archive(
            base_name=str(output_path), format="gztar", root_dir=self.client_config_location.expanduser()
        )
        logger.info("{} client config backed up".format(self.client_config_name))


class JujuClientConfigBackup(ClientConfigBackup):
    client_config_name = "juju"
    client_config_location = Path("~/.local/share/juju")

    def __init__(self, base_output_dir: Path):
        super().__init__(base_output_dir)
        if os.environ.get("JUJU_DATA"):
            self.client_config_location = Path(os.environ.get("JUJU_DATA"))


def get_charm_backup_instance(charm_name: str, unit: Unit) -> CharmBackupType:
    if charm_name == MysqlInnodbBackup.charm_name:
        return MysqlInnodbBackup(unit=unit)
    if charm_name == PerconaClusterBackup.charm_name:
        return PerconaClusterBackup(unit=unit)
    if charm_name == EtcdBackup.charm_name:
        return EtcdBackup(unit=unit)
    if charm_name == PostgresqlBackup.charm_name:
        return PostgresqlBackup(unit=unit)
    if charm_name == SwiftBackup.charm_name:
        return SwiftBackup(unit=unit)
    raise Exception("{} is not a supported charm.".format(charm_name))
