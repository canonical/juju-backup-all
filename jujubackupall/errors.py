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
import subprocess


class BackupError(Exception):
    pass


class JujuControllerBackupError(BackupError):
    def __init__(self, cmd_error: subprocess.CalledProcessError):
        super().__init__()
        self.cmd_error = cmd_error

    def __str__(self):
        """Return string representation of JujuControllerBackupError."""
        return "{}: {}\nCommand Output: {}".format(
            self.__class__.__name__, self.cmd_error, self.cmd_error.output.decode()
        )
