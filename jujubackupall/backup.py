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
import json
import os
import shutil
from abc import ABCMeta, abstractmethod
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import Dict, List, TypeVar

import attr
from juju.controller import Controller
from juju.errors import JujuAPIError
from juju.unit import Unit

from jujubackupall.constants import MAX_CONTROLLER_BACKUP_RETRIES
from jujubackupall.errors import JujuControllerBackupError
from jujubackupall.utils import (
    backup_controller,
    check_output_unit_action,
    ensure_path_exists,
    get_datetime_string,
    scp_from_unit,
    ssh_run_on_unit,
)

CharmBackupType = TypeVar("CharmBackupType", bound="CharmBackup")
logger = getLogger(__name__)


class BaseBackup(object, metaclass=ABCMeta):
    """BaseBackup metaclass for backups."""

    @abstractmethod
    def backup(self):
        pass


class CharmBackup(BaseBackup, metaclass=ABCMeta):
    charm_name: str = NotImplemented
    _backup_filepath: Path = None

    def __init__(self, unit: Unit, backup_basedir: Path):
        self.unit = unit
        self.backup_basedir = backup_basedir

    @property
    def backup_filepath(self):
        return self._backup_filepath

    @backup_filepath.setter
    def backup_filepath(self, path: Path):
        self._backup_filepath = path

    def download_backup(self, save_path: Path) -> Path:
        ensure_path_exists(path=save_path)
        scp_from_unit(unit=self.unit, source=str(self.backup_filepath), destination=str(save_path))
        rm_command = "sudo rm {}".format(self.backup_filepath)
        ssh_run_on_unit(unit=self.unit, command=rm_command)
        return (save_path / self.backup_filepath.name).absolute()


class MysqlBackup(CharmBackup, metaclass=ABCMeta):
    backup_action_name = "mysqldump"

    def backup(self):
        action_output = check_output_unit_action(self.unit, self.backup_action_name, basedir=str(self.backup_basedir))
        self.backup_filepath = Path(action_output.get("mysqldump-file"))

    def download_backup(self, save_path: Path) -> Path:
        filename = self.backup_filepath.name
        tmp_path = Path("/tmp") / filename
        cp_chown_command = "sudo mv {} /tmp && sudo chown ubuntu:ubuntu {}".format(self.backup_filepath, tmp_path)
        ssh_run_on_unit(unit=self.unit, command=cp_chown_command)
        self.backup_filepath = tmp_path
        return super().download_backup(save_path)


class MysqlInnodbBackup(MysqlBackup):
    charm_name = "mysql-innodb-cluster"


class EtcdBackup(CharmBackup):
    charm_name = "etcd"
    backup_action_name = "snapshot"

    def backup(self):
        action_output = check_output_unit_action(self.unit, self.backup_action_name, target=str(self.backup_basedir))
        self.backup_filepath = Path(action_output.get("snapshot").get("path"))


class PostgresqlBackup(CharmBackup):
    charm_name = "postgresql"
    date_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    pgdump_filename = f"pgdump-all-databases-{date_suffix}.gz"

    def backup(self):
        ssh_run_on_unit(unit=self.unit, command=f"mkdir -p {self.backup_basedir}")
        self.backup_filepath = self.backup_basedir / self.pgdump_filename
        backup_cmd = f"sudo -u postgres pg_dumpall | gzip > {self.backup_filepath}"
        ssh_run_on_unit(unit=self.unit, command=backup_cmd)


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

    def backup(self) -> Path:
        """Run `juju create-backup` against Juju controller.

        As juju controller backups tend to be flaky, this method will retry the backups.
        If backups fail all retries, a JujuControllerBackupError is raised with info on the
        last failure.

        :raise: JujuControllerBackupError: If all tried backups fail
        """
        # retry controller backup commands. If all fail, raise last error
        last_error = None
        for i in range(MAX_CONTROLLER_BACKUP_RETRIES):
            try:
                logger.info("[{}] Attempt #{} for controller backup.".format(self.controller.controller_name, i + 1))
                local_backup_filename, result_dict = backup_controller(self.controller)
                break
            except JujuAPIError as juju_api_error:
                error_msg = "[{}] Attempt #{} Encountered controller backup error: {}".format(
                    self.controller.controller_name,
                    i + 1,
                    juju_api_error,
                )
                last_error = juju_api_error
                logger.warning("{}".format(error_msg))
        else:
            error_msg = "[{}] All {} controller backup attempts failed.\nLast error: {}".format(
                self.controller.controller_name, MAX_CONTROLLER_BACKUP_RETRIES, last_error
            )
            logger.error(error_msg)
            raise JujuControllerBackupError(last_error)

        # as of libjuju 2.9.4 the library downloads the backup for us, but we cannot
        # specify the filename/location. It's downloaded to CWD and we only get the
        # filename. Need to relocate it to the configured save path.
        # https://github.com/juju/python-libjuju/issues/553
        save_filename = "juju-controller-backup-{}.tar.gz".format(get_datetime_string())
        save_file_path = self.save_path / save_filename
        ensure_path_exists(self.save_path)
        shutil.move(local_backup_filename, save_file_path.absolute())

        return Path(save_file_path).absolute()


class ClientConfigBackup(BaseBackup, metaclass=ABCMeta):
    client_config_name: str = NotImplemented
    client_config_location: Path = NotImplemented

    def __init__(self, base_output_dir: Path):
        self.base_output_dir = base_output_dir

    def backup(self) -> Path:
        output_path = (
            self.base_output_dir / "local_configs" / "{}-{}".format(self.client_config_name, get_datetime_string())
        )
        ensure_path_exists(output_path.parent)
        archive_path = shutil.make_archive(
            base_name=str(output_path), format="gztar", root_dir=self.client_config_location.expanduser()
        )
        logger.info("[config] {} client config backed up.".format(self.client_config_name))
        return Path(archive_path).absolute()


class JujuClientConfigBackup(ClientConfigBackup):
    client_config_name = "juju"
    client_config_location = Path("~/.local/share/juju")

    def __init__(self, base_output_dir: Path):
        super().__init__(base_output_dir)
        if os.environ.get("JUJU_DATA"):
            self.client_config_location = Path(os.environ.get("JUJU_DATA"))


@attr.s
class AppBackupEntry:
    controller: str = attr.ib(validator=attr.validators.instance_of(str))
    model: str = attr.ib(validator=attr.validators.instance_of(str))
    charm: str = attr.ib(validator=attr.validators.instance_of(str))
    app: str = attr.ib(validator=attr.validators.instance_of(str))
    download_path: str = attr.ib(validator=attr.validators.instance_of(str))


@attr.s
class ConfigBackupEntry:
    config: str = attr.ib(validator=attr.validators.instance_of(str))
    download_path: str = attr.ib(validator=attr.validators.instance_of(str))


@attr.s
class ControllerBackupEntry:
    controller: str = attr.ib(validator=attr.validators.instance_of(str))
    download_path: str = attr.ib(validator=attr.validators.instance_of(str))


class BackupTracker:
    """Class to keep track of and output successful and failed backups."""

    def __init__(self):
        self.controller_backups: List[ControllerBackupEntry] = list()
        self.config_backups: List[ConfigBackupEntry] = list()
        self.app_backups: List[AppBackupEntry] = list()
        self.errors: List[Dict] = list()

    def add_app_backup(self, controller: str, model: str, charm: str, app: str, download_path: str):
        app_backup = AppBackupEntry(
            controller=controller, model=model, charm=charm, app=app, download_path=download_path
        )
        self.app_backups.append(app_backup)

    def add_config_backup(self, config: str, download_path: str):
        config_backup_entry = ConfigBackupEntry(config=config, download_path=download_path)
        self.config_backups.append(config_backup_entry)

    def add_controller_backup(self, controller: str, download_path: str):
        controller_backup_entry = ControllerBackupEntry(controller=controller, download_path=download_path)
        self.controller_backups.append(controller_backup_entry)

    def add_error(self, **kwargs):
        self.errors.append(kwargs)

    def to_json(self):
        """Generate JSON representation of backups.

        The output will look something like the following:
        {
          "controller_backups": [
            {
              "controller": "my-controller",
              "download_path": "/home/user/juju-backups/controller1/juju-controller-backup.tar.gz"
            }
          ],
          "config_backups": [
            {
              "config": "juju",
              "download_path": "/home/user/juju-backups/local_configs/juju.tar.gz"
            }
          ],
          "app_backups": [
            {
              "controller": "my-controller",
              "model": "my-model1",
              "charm": "etcd",
              "app": "etcd",
              "download_path": "/home/user/juju-backups/my-controller/my-model1/etcd/etcd.tar.gz"
            },
            {
              "controller": "my-controller",
              "model": "my-model2",
              "charm": "mysql-innodb-cluster",
              "app": "mysql",
              "download_path": "/home/user/juju-backups/my-controller/my-model2/mysql/mysqldump-all-databases.gz"
            }
          ]
          "errors":  [
            {
              "controller": "my-other-controller",
              "error-reason": "reason for error"
            }
          ]
        }
        """
        report = dict(
            controller_backups=[attr.asdict(x) for x in self.controller_backups],
            config_backups=[attr.asdict(x) for x in self.config_backups],
            app_backups=[attr.asdict(x) for x in self.app_backups],
        )
        if self.errors:
            report["errors"] = self.errors
        return json.dumps(report, indent=2)


def get_charm_backup_instance(
    charm_name: str,
    unit: Unit,
    backup_location_on_postgresql: Path,
    backup_location_on_mysql: Path,
    backup_location_on_etcd: Path,
) -> CharmBackupType:
    if charm_name == MysqlInnodbBackup.charm_name:
        return MysqlInnodbBackup(unit=unit, backup_basedir=backup_location_on_mysql)
    if charm_name == EtcdBackup.charm_name:
        return EtcdBackup(unit=unit, backup_basedir=backup_location_on_etcd)
    if charm_name == PostgresqlBackup.charm_name:
        return PostgresqlBackup(unit=unit, backup_basedir=backup_location_on_postgresql)
    if charm_name == SwiftBackup.charm_name:  # Not implemented
        return SwiftBackup(unit=unit, backup_basedir="/home/ubuntu")
    raise Exception("{} is not a supported charm.".format(charm_name))
