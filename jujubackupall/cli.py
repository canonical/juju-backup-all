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
import logging
import os

from jujubackupall.config import Config
from jujubackupall.constants import SUPPORTED_BACKUP_CHARMS
from jujubackupall.process import BackupProcessor

FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class Cli:
    def __init__(self):
        self.args = self._parse_args()
        self.config = Config(self.args)

    def run(self):
        self._configure_logging()
        self._configure_juju_data()
        backup_processor = BackupProcessor(self.config)
        backup_processor.process_backups()

    @staticmethod
    def _parse_args() -> dict:
        parser = make_cli_parser()
        args = parser.parse_args()
        args_dict = dict(
            all_controllers=args.all_controllers,
            backup_controller=args.backup_controller,
            backup_juju_client_config=args.backup_juju_client_config,
            excluded_charms=args.excluded_charms,
            controllers=args.controllers,
            output_dir=args.output_dir,
            log_level=args.log_level,
        )
        return args_dict

    def _configure_logging(self):
        logging.basicConfig(format=FORMAT, level=self.config.log_level)
        logging.getLogger("websockets").setLevel(logging.ERROR)
        logging.getLogger("juju").setLevel(logging.ERROR)
        logging.getLogger("connector").setLevel(logging.CRITICAL)
        logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    @staticmethod
    def _configure_juju_data():
        if os.environ.get("SNAP_REAL_HOME"):
            os.environ["JUJU_DATA"] = "{}/.local/share/juju".format(os.environ.get("SNAP_REAL_HOME"))


def make_cli_parser():
    parser = argparse.ArgumentParser(description="Get a backup of all things Juju.")
    parser.add_argument("-o", "--output-directory", dest="output_dir", default="juju-backups")
    parser.add_argument(
        "-e", "--exclude-charm", dest="excluded_charms", action="append", choices=SUPPORTED_BACKUP_CHARMS
    )
    parser.add_argument("-x", "--exclude-controller-backup", dest="backup_controller", action="store_false")
    parser.add_argument(
        "-j", "--exclude-juju-client-config-backup", dest="backup_juju_client_config", action="store_false"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--controller", dest="controllers", action="append")
    group.add_argument("-A", "--all-controllers", action="store_true")
    parser.add_argument(
        "-l",
        "--log",
        dest="log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="WARNING",
        type=str.upper,
    )
    return parser


def main():
    cli = Cli()
    cli.run()


if __name__ == "__main__":
    main()
