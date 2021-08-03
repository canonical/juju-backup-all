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
"""Module that provides utility functions."""
from contextlib import asynccontextmanager
import json
import os
import subprocess
from typing import List

from juju.controller import Controller
from juju.model import Model
from juju.unit import Unit


@asynccontextmanager
async def connect_controller(controller_name: str) -> Controller:
    """Handle connecting to and disconnecting from a Juju Controller."""
    controller = Controller()
    if controller_name:
        await controller.connect(controller_name)
    else:
        await controller.connect()
    try:
        yield controller
    finally:
        await controller.disconnect()


@asynccontextmanager
async def connect_model(model_name: str) -> Model:
    """Handle connecting to and disconnecting from a Juju Model."""
    model = Model()
    await model.connect(model_name)
    try:
        yield model
    finally:
        await model.disconnect()


def ensure_path_exists(path):
    os.makedirs(path, exist_ok=True)


def get_all_controllers() -> List[str]:
    juju_controllers_output = subprocess.check_output('juju controllers --format json', shell=True)
    juju_controllers_json = json.load(juju_controllers_output)
    juju_controller_names = [key for key in juju_controllers_json.get('controllers').keys()]
    return juju_controller_names


async def get_leader(units: List[Unit]) -> Unit:
    for unit in units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            return unit


def parse_charm_name(charm_url: str) -> str:
    parsed_charm_name = charm_url.split(':')[1].rsplit('-', 1)[0]
    if '/' in parsed_charm_name:
        return parsed_charm_name.split('/')[-1]
    return parsed_charm_name
