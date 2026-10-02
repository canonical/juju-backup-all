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
import json
import os
from asyncio import TimeoutError as AIOTimeoutError
from asyncio import wait_for
from concurrent.futures import TimeoutError as CFTimeoutError
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Coroutine, List, Tuple

from juju.action import Action
from juju.controller import Controller
from juju.juju import Juju
from juju.machine import Machine
from juju.model import Model
from juju.unit import Unit

from jujubackupall.async_handlers import run_async
from jujubackupall.constants import MAX_FRAME_SIZE
from jujubackupall.errors import (
    ActionError,
    BackupMetadataError,
    JujuTimeoutError,
    ModelAccessError,
    NoLeaderError,
    NoNonPrimaryError,
)


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


def _lookup_ignoring_case(mapping: dict, name: str):
    # Charm revisions differ in the casing they use for cluster status keys.
    for key, value in mapping.items():
        if key.lower() == name.lower():
            return value
    return None


def get_non_primary(units: List[Unit], timeout: int) -> Unit:
    """Return an online unit that is not the MySQL cluster primary.

    However, if there is only one unit, the unit will be returned, even if it is primary.

    The MySQL charms reject backups on the cluster primary, which is not necessarily the
    Juju leader, so the primary is resolved from the charm's reported cluster topology.
    """
    if len(units) == 1:
        return units[0]

    action_output = check_output_unit_action(get_leader(units), "get-cluster-status", timeout)
    status = _lookup_ignoring_case(action_output, "status") or {}
    if isinstance(status, str):
        status = json.loads(status)
    replica_set = _lookup_ignoring_case(status, "defaultReplicaSet") or {}
    topology = _lookup_ignoring_case(replica_set, "topology") or {}

    eligible_unit_names = set()
    for label, member in topology.items():
        role = str(_lookup_ignoring_case(member, "memberRole") or "").upper()
        state = str(_lookup_ignoring_case(member, "status") or "").upper()
        if role != "PRIMARY" and state == "ONLINE":
            eligible_unit_names.add("/".join(label.rsplit("-", 1)))

    for unit in units:
        if unit.name in eligible_unit_names:
            return unit
    raise NoNonPrimaryError(units=units)


def get_mongodb_primary(units: List[Unit], timeout: int) -> Unit:
    """Return the MongoDB primary reported by the charm's get-primary action."""
    action_output = check_output_unit_action(get_leader(units), "get-primary", timeout)
    primary_name = action_output.get("replica-set-primary")
    for unit in units:
        if unit.name == primary_name:
            return unit
    raise BackupMetadataError("get-primary did not return a matching primary unit")


def get_postgresql_primary(units: List[Unit], timeout: int) -> Unit:
    """Return the PostgreSQL primary identified by the get-primary action."""
    action_output = check_output_unit_action(get_leader(units), "get-primary", timeout)
    primary_name = action_output.get("primary")
    for unit in units:
        if unit.name == primary_name:
            return unit
    raise BackupMetadataError("get-primary did not return a matching primary unit")


def get_postgresql_primary(units: List[Unit], timeout: int) -> Unit:
    """Return the PostgreSQL primary identified by the get-primary action."""
    action_output = check_output_unit_action(get_leader(units), "get-primary", timeout)
    primary_name = action_output.get("primary")
    for unit in units:
        if unit.name == primary_name:
            return unit
    raise BackupMetadataError("get-primary did not return a matching primary unit")


def parse_charm_name(charm_url: str) -> str:
    parsed_charm_name = charm_url.split(":")[1].rsplit("-", 1)[0]
    if "/" in parsed_charm_name:
        return parsed_charm_name.split("/")[-1]
    return parsed_charm_name


def get_datetime_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def check_output_unit_action(unit: Unit, action_name: str, timeout: int, **params) -> dict:
    backup_action: Action = run_async(unit.run_action(action_name, **params))
    run_with_timeout(backup_action.wait(), action_name, timeout)
    if backup_action.safe_data.get("status") != "completed":
        raise ActionError(backup_action)
    return backup_action.results


def _fake_machine_public_address(machine):
    """Copy local-fan address as fake public address when necessary.

    In libjuju[0], machine.dns_name will look for `public` or `local-cloud` address.
    For lxd, neither exists, it will return None and cause ssh/scp functions fail.[1]

    Example addresses data for lxd:

        "addresses": [
            {
                "value": "252.152.11.61",
                "type": "ipv4",
                "scope": "local-fan"
            },
            {
                "value": "127.0.0.1",
                "type": "ipv4",
                "scope": "local-machine"
            },
            {
                "value": "::1",
                "type": "ipv6",
                "scope": "local-machine"
            }
        ],

    This function detect such situation, and use `local-fan` address as public address,
    so machine.dns_name can still get a valid address.

    [0]: https://github.com/juju/python-libjuju/blob/master/juju/machine.py#L231
    [1]: https://github.com/juju/python-libjuju/issues/611
    """
    # a reference to the address list, will change value in place
    addresses = machine.safe_data["addresses"]

    local_fan_addr = None
    for address in addresses:
        scope = address["scope"]
        if scope in ("public", "local-cloud"):
            return  # no issue, nothing needed
        if scope == "local-fan":
            local_fan_addr = address

    if local_fan_addr:
        public_addr = local_fan_addr.copy()
        public_addr["scope"] = "public"
        addresses.insert(0, public_addr)


def ssh_run_on_unit(unit: Unit, command: str, timeout: int, user="ubuntu"):
    run_with_timeout(
        unit.ssh(command=command, user=user),
        "unit ssh with command={} on unit {}".format(command, unit.safe_data.get("name")),
        timeout,
    )


def ssh_run_on_machine(machine: Machine, command: str, timeout: int, user="ubuntu"):
    run_with_timeout(
        machine.ssh(command=command, user=user),
        "machine ssh with command={} on machine {}".format(
            command,
            machine.safe_data.get("hostname"),
        ),
        timeout,
    )


def scp_from_unit(unit: Unit, source: str, destination: str, timeout: int):
    _fake_machine_public_address(unit.machine)
    run_with_timeout(
        unit.scp_from(source=source, destination=destination),
        "unit scp with source={}:{} and destination={}".format(
            unit.safe_data.get("name"), source, destination
        ),
        timeout,
    )


def scp_from_machine(machine: Machine, source: str, destination: str, timeout: int):
    _fake_machine_public_address(machine)
    run_with_timeout(
        machine.scp_from(source=source, destination=destination),
        "machine scp with source={}:{} and destination={}".format(
            machine.safe_data.get("hostname"), source, destination
        ),
        timeout,
    )


def backup_controller(controller: Controller, timeout: int) -> Tuple[Model, dict]:
    uuids = run_async(controller.model_uuids())
    controller_uuid = uuids.get("controller")
    if not controller_uuid:
        raise ModelAccessError(
            model_name="controller",
            controller_name=controller.controller_name,
            visible_models=list(uuids.keys()),
        )
    controller_model: Model = run_async(controller.get_model(controller_uuid))
    return run_with_timeout(
        controller_model.create_backup(),
        f"controller backup on controller {controller.controller_name}",
        timeout,
    )


def run_with_timeout(coroutine: Coroutine, task: str, timeout: int):
    """Run an asyncio coroutine with an explicit timeout."""
    try:
        return run_async(wait_for(coroutine, timeout))
    except (AIOTimeoutError, CFTimeoutError):
        raise JujuTimeoutError(f"Task '{task}' timed out (timeout={timeout}).")
