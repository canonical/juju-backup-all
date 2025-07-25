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
"""Contains constants used throughout the package."""

SUPPORTED_BACKUP_CHARMS = ["mysql-innodb-cluster", "etcd", "postgresql"]
MAX_CONTROLLER_BACKUP_RETRIES = 3
# NOTE: Workaround for https://github.com/juju/python-libjuju/issues/523
MAX_FRAME_SIZE = 2**64
DEFAULT_BACKUP_LOCATION_ON_POSTGRESQL_UNIT = "/home/ubuntu"
DEFAULT_BACKUP_LOCATION_ON_MYSQL_UNIT = "/var/backups/mysql"
DEFAULT_BACKUP_LOCATION_ON_ETCD_UNIT = "/home/ubuntu/etcd-snapshots"
DEFAULT_TASK_TIMEOUT = 60 * 10  # 10 minutes
