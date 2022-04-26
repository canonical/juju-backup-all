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
import os
from asyncio import wait_for, TimeoutError as AIOTimeoutError
from concurrent.futures import TimeoutError as CFTimeoutError
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Coroutine, List, Tuple

from juju.action import Action
from juju.controller import Controller
from juju.juju import Juju
from juju.loop import run as run_async
from juju.machine import Machine
from juju.model import Model
from juju.unit import Unit

from jujubackupall import globals
from jujubackupall.constants import MAX_FRAME_SIZE
from jujubackupall.errors import ActionError, JujuTimeoutError, NoLeaderError


@contextmanager
def connect_controller(controller_name: str) -> Controller:
    """Handle connecting to and disconnecting from a Juju Controller."""
    controller = Controller(max_frame_size=MAX_FRAME_SIZE)
    if controller_name:
        run_async(controller.connect(controller_name))
    else:
        run_async(controller.connect())
    try:
        yield controller
    finally:
        run_async(controller.disconnect())


@contextmanager
def connect_model(controller: Controller, model_name: str) -> Model:
    """Handle connecting to and disconnecting from a Juju Model."""
    model = run_async(controller.get_model(model_name))
    try:
        yield model
    finally:
        run_async(model.disconnect())


def ensure_path_exists(path):
    os.makedirs(path, exist_ok=True)


def get_all_controllers() -> List[str]:
    juju_local_env = Juju()
    juju_controller_names = list(juju_local_env.get_controllers().keys())
    return juju_controller_names


def get_leader(units: List[Unit]) -> Unit:
    for unit in units:
        is_leader = run_async(unit.is_leader_from_status())
        if is_leader:
            return unit
    raise NoLeaderError(units=units)


def parse_charm_name(charm_url: str) -> str:
    parsed_charm_name = charm_url.split(":")[1].rsplit("-", 1)[0]
    if "/" in parsed_charm_name:
        return parsed_charm_name.split("/")[-1]
    return parsed_charm_name


def get_datetime_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def check_output_unit_action(unit: Unit, action_name: str, **params) -> dict:
    backup_action: Action = run_async(unit.run_action(action_name, **params))
    run_with_timeout(backup_action.wait(), action_name)
    if backup_action.safe_data.get("status") != "completed":
        raise ActionError(backup_action)
    return backup_action.safe_data


def ssh_run_on_unit(unit: Unit, command: str, user="ubuntu"):
    run_with_timeout(
        unit.ssh(command=command, user=user),
        "unit ssh with command={} on unit {}".format(command, unit.safe_data.get("name")),
    )


def ssh_run_on_machine(machine: Machine, command: str, user="ubuntu"):
    run_with_timeout(
        machine.ssh(command=command, user=user),
        "machine ssh with command={} on machine {}".format(command, machine.safe_data.get("hostname")),
    )


def scp_from_unit(unit: Unit, source: str, destination: str):
    run_with_timeout(
        unit.scp_from(source=source, destination=destination),
        "unit scp with source={}:{} and destination={}".format(unit.safe_data.get("name"), source, destination),
    )


def scp_from_machine(machine: Machine, source: str, destination: str):
    run_with_timeout(
        machine.scp_from(source=source, destination=destination),
        "machine scp with source={}:{} and destination={}".format(
            machine.safe_data.get("hostname"), source, destination
        ),
    )


def backup_controller(controller: Controller) -> Tuple[Model, dict]:
    controller_model: Model = run_async(controller.get_model("controller"))
    return run_with_timeout(
        controller_model.create_backup(), "controller backup on controller {}".format(controller.controller_name)
    )


def run_with_timeout(coroutine: Coroutine, task: str):
    timeout = globals.async_timeout
    try:
        return run_async(wait_for(coroutine, timeout))
    except (AIOTimeoutError, CFTimeoutError):
        raise JujuTimeoutError("Task '{}' timed out (timeout={}).".format(task, timeout))
