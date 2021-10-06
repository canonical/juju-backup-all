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
"""Module containing package specific errors."""
from typing import List

from juju.action import Action
from juju.errors import JujuAPIError
from juju.unit import Unit


class BackupError(Exception):
    pass


class JujuControllerBackupError(BackupError):
    def __init__(self, juju_api_error: JujuAPIError):
        super().__init__()
        self.juju_api_error = juju_api_error

    def __str__(self):
        """Return string representation of JujuControllerBackupError."""
        return "{}: {}".format(self.__class__.__name__, self.juju_api_error)


class ActionError(Exception):
    def __init__(self, action: Action):
        super().__init__()
        self.action = action

    def __str__(self):
        """Return string representation of ActionError."""
        return (
            "{}: Action '{}' on unit '{}' with parameters '{}' failed with status '{}' and message '{}'."
            "\nFailed action results: {}".format(
                self.__class__.__name__,
                self.action.safe_data.get("name"),
                self.action.safe_data.get("receiver"),
                self.action.safe_data.get("parameters"),
                self.action.safe_data.get("status"),
                self.action.safe_data.get("message"),
                self.action.safe_data.get("results"),
            )
        )

    def results(self) -> dict:
        return self.action.safe_data.get("results")


class NoLeaderError(Exception):
    def __init__(self, units: List[Unit]):
        super().__init__()
        self.units = units

    def __str__(self):
        """Return string representation of NoLeaderError."""
        return "{}: No leader could be found for units: {}".format(self.__class__.__name__, self.units)
