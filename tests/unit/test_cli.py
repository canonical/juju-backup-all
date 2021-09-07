#!/usr/bin/python3
""" Unit tests for cli.py """
import argparse
import unittest
from io import StringIO
from unittest.mock import Mock, patch

from jujubackupall.cli import Cli, make_cli_parser
from jujubackupall.constants import SUPPORTED_BACKUP_CHARMS

all_controllers = False
backup_controller = True
backup_juju_client_config = True
controllers = ["controller1", "controller2"]
excluded_charms = ["mysql"]
output_dir = "my_output_dir"
log_level = "INFO"


class TestCli(unittest.TestCase):
    @staticmethod
    def args() -> dict:
        """Premade args dict for quick args config."""
        args_dict = dict(
            all_controllers=all_controllers,
            backup_controller=backup_controller,
            backup_juju_client_config=backup_juju_client_config,
            controllers=controllers,
            excluded_charms=excluded_charms,
            output_dir=output_dir,
            log_level=log_level,
        )
        return args_dict

    @patch("jujubackupall.cli.Config")
    @patch("jujubackupall.cli.make_cli_parser")
    def test_cli_init(self, mock_make_parser: Mock, mock_config: Mock):
        arg_namespace = argparse.Namespace(**self.args())
        mock_parser = Mock()
        mock_parser.parse_args.return_value = arg_namespace
        mock_make_parser.return_value = mock_parser
        cli = Cli()
        mock_config.assert_called_once_with(self.args())
        self.assertIsInstance(cli, Cli)

    @patch("jujubackupall.cli.logging")
    @patch("jujubackupall.cli.Config")
    @patch("jujubackupall.cli.make_cli_parser")
    @patch("jujubackupall.cli.BackupProcessor")
    def test_cli_run(
        self, mock_backup_processor_class: Mock, mock_make_parser: Mock, mock_config_class: Mock, mock_logging: Mock
    ):
        mock_config_inst = Mock()
        mock_backup_processor_inst = Mock()
        mock_config_class.return_value = mock_config_inst
        mock_backup_processor_class.return_value = mock_backup_processor_inst
        cli = Cli()
        cli.run()
        mock_backup_processor_class.assert_called_once_with(mock_config_inst)
        mock_backup_processor_inst.process_backups.assert_called_once()


class TestMakeParser(unittest.TestCase):
    def test_exclude_charms_individual(self):
        parser = make_cli_parser()
        for charm in SUPPORTED_BACKUP_CHARMS:
            with self.subTest(charm=charm):
                res = parser.parse_args(["--exclude-charm", charm])
                self.assertListEqual(res.excluded_charms, [charm])

    def test_exclude_all_charms(self):
        parser = make_cli_parser()
        full_args = []
        for i in range(len(SUPPORTED_BACKUP_CHARMS)):
            full_args.append("--exclude-charm")
            full_args.append(SUPPORTED_BACKUP_CHARMS[i])
        res = parser.parse_args(full_args)
        self.assertListEqual(res.excluded_charms, SUPPORTED_BACKUP_CHARMS)

    @patch("sys.stderr", new_callable=StringIO)
    def test_exclude_charm_not_supported_fails(self, mock_stderr):
        parser = make_cli_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--exclude-charm", "a-charm"])
        self.assertRegexpMatches(mock_stderr.getvalue(), r"a-charm")


if __name__ == "__main__":
    unittest.main()
