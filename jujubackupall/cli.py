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
"""Main entry point for juju-backup-all CLI tool."""
import argparse
from collections import namedtuple
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import List

from juju import loop
from juju.controller import Controller
from juju.model import Model
from juju.application import Application
from juju.unit import Unit
from juju.action import Action

from jujubackupall.config import Config
from jujubackupall.constants import SUPPORTED_BACKUP_CHARMS


class Cli:
    def __init__(self):
        self.config = Config()

    def run(self):
        pass


# The following is a quick implementation of the tool. This will be refactored in the stub classes/modules
# defined in the package.

JujuApp = namedtuple('JujuApp', ['app_name', 'app', 'charm_name'])
JujuModel = namedtuple('JujuModel', ['model_name', 'model'])
JujuController = namedtuple('JujuModel', ['controller_name', 'controller'])


def _parse_args():
    parser = argparse.ArgumentParser(description='Get a backup of all things Juju.')
    parser.add_argument('-o', '--output-directory', dest='output_dir', default='juju-backups')
    parser.add_argument('-c', '--charm', dest='charms', action='append', choices=SUPPORTED_BACKUP_CHARMS)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-C', '--controller', dest='controllers', action='append')
    group.add_argument('-A', '--all-controllers', action='store_true')
    return parser.parse_args()


def main():
    loop.run(_main())


async def _main():
    args = _parse_args()
    if not args.charms:
        args.charms = SUPPORTED_BACKUP_CHARMS
    if args.all_controllers:
        controller_names = _list_controllers()
    elif args.controllers:
        controller_names = args.controllers

    for controller_name in controller_names:
        controller = Controller()
        await controller.connect_controller(controller_name)
        model_names = await controller.list_models()
        for model_name in model_names:
            model = Model()
            await model.connect(model_name)
            for app_name, app in model.applications.items():
                charm_name = _parse_charm_name(app.data.get('charm-url'))
                if charm_name in args.charms:
                    print('Backing up app {}'.format(app_name))
                    juju_app = JujuApp(app_name=app_name, app=app, charm_name=charm_name)
                    juju_controller = JujuController(controller_name=controller_name, controller=controller)
                    juju_model = JujuModel(model_name=model_name, model=model)
                    await get_backup(app=juju_app, model=juju_model, controller=juju_controller, output_dir=args.output_dir)


async def get_backup(app, controller, model, output_dir):
    if app.charm_name == 'mysql-innodb-cluster':
        await backup_and_download_mysql_innodb_cluster(app, controller, model, output_dir)
    elif app.charm_name == 'percona-cluster':
        await backup_and_download_percona(app, controller, model, output_dir)
    else:
        raise Exception('Should not get here.')


async def backup_and_download_mysql_innodb_cluster(app: JujuApp, controller: JujuController, model: JujuModel, output_dir):
    leader_unit = await _get_leader(app.app.units)
    backup_action = await _take_backup(leader_unit, app.charm_name)
    output_path = _setup_output_dir(output_dir, controller.controller_name, model.model_name, app.app_name)
    await _download_mysqldump(backup_action, output_path, leader_unit)
    print('Mysql-innodb-cluster backed up at: {}'.format(output_path))


async def backup_and_download_percona(app, controller, model, output_dir):
    leader_unit = await _get_leader(app.app.units)
    backup_action = await _take_backup(leader_unit, app.charm_name)
    output_path = _setup_output_dir(output_dir, controller.controller_name, model.model_name, app.app_name)
    await _download_mysqldump(backup_action, output_path, leader_unit)
    print('percona-cluster backed up at: {}'.format(output_path))


def _list_controllers():
    juju_controllers_output = subprocess.check_output('juju controllers --format json', shell=True)
    juju_controllers_json = json.loads(juju_controllers_output)
    juju_controller_names = [key for key in juju_controllers_json.get('controllers').keys()]
    return juju_controller_names


def _parse_charm_name(full_charm_name: str) -> str:
    return full_charm_name.split(':')[1].rsplit('-', 1)[0]


async def _take_backup(unit: Unit, charm_name) -> Action:
    if charm_name == 'mysql-innodb-cluster':
        backup_action: Action = await unit.run_action('mysqldump')
        await backup_action.wait()
        return backup_action
    if charm_name == 'percona-cluster':
        set_pxc_strict_mode_permissive_action: Action = await unit.run_action('set-pxc-strict-mode', mode='PERMISSIVE')
        await set_pxc_strict_mode_permissive_action.wait()
        assert set_pxc_strict_mode_permissive_action.status == 'completed'
        backup_action: Action = await unit.run_action('mysqldump')
        await backup_action.wait()
        set_pxc_strict_mode_permissive_action: Action = await unit.run_action('set-pxc-strict-mode', mode='ENFORCING')
        await set_pxc_strict_mode_permissive_action.wait()
        assert set_pxc_strict_mode_permissive_action.status == 'completed'
        return backup_action


async def _get_leader(units: List[Unit]) -> Unit:
    for unit in units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            return unit


async def _download_mysqldump(backup_action, output_path, unit: Unit):
    mysqldump_path = Path(backup_action.safe_data.get('results').get('mysqldump-file'))
    mysqldump_filename = mysqldump_path.name
    tmp_mysqldump_path = Path('/tmp/{}'.format(mysqldump_filename))
    await unit.ssh(command='sudo cp {} /tmp && sudo chown ubuntu:ubuntu {}'.format(mysqldump_path, tmp_mysqldump_path),
                   user='ubuntu')
    await unit.scp_from(source=str(tmp_mysqldump_path), destination=output_path)
    await unit.ssh(command='sudo rm -r {} {}'.format(mysqldump_path, tmp_mysqldump_path), user='ubuntu')


def _setup_output_dir(output_dir, controller_name, model_name, app_name):
    output_path = os.path.join(output_dir, controller_name, model_name, app_name)
    if not os.path.isdir(output_path):
        os.makedirs(output_path)
    return output_path


if __name__ == '__main__':
    main()
