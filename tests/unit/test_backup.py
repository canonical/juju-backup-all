#!/usr/bin/python3
""" Unit tests for backup.py """
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from juju.errors import JujuAPIError

from jujubackupall.backup import (
    BackupTracker,
    EtcdBackup,
    JujuClientConfigBackup,
    JujuControllerBackup,
    MysqlInnodbBackup,
    PerconaClusterBackup,
    PostgresqlBackup,
    SwiftBackup,
    get_charm_backup_instance,
)
from jujubackupall.constants import MAX_CONTROLLER_BACKUP_RETRIES
from jujubackupall.errors import JujuControllerBackupError


class TestGetCharmBackupInstance(unittest.TestCase):
    def test_get_backup_instance(self):
        test_cases = [
            ("mysql-innodb-cluster", MysqlInnodbBackup),
            ("percona-cluster", PerconaClusterBackup),
            ("etcd", EtcdBackup),
            ("postgresql", PostgresqlBackup),
            ("swift-proxy", SwiftBackup),
        ]
        for charm_name, expected_backup_class in test_cases:
            with self.subTest(charm_name=charm_name, expected_backup_class=expected_backup_class):
                backup_instance = get_charm_backup_instance(charm_name, Mock())
                self.assertIsInstance(backup_instance, expected_backup_class)


class TestJujuControllerBackup(unittest.TestCase):
    def setUp(self):
        self.mock_controller = Mock()
        self.mock_save_path = Path("mypath")
        self.controller_backup = JujuControllerBackup(controller=self.mock_controller, save_path=self.mock_save_path)

    def get_juju_api_error(self):
        error_result = {
            "error": "my error",
            "error-code": 1,
            "response": "some response",
            "request-id": "123-abc",
        }
        return JujuAPIError(error_result)

    @patch("jujubackupall.backup.scp_from_machine")
    @patch("jujubackupall.backup.ssh_run_on_machine")
    @patch("jujubackupall.backup.backup_controller")
    @patch("jujubackupall.backup.get_datetime_string")
    @patch("jujubackupall.backup.ensure_path_exists")
    def test_backup_controller_first_success(
        self,
        mock_path_exists: Mock,
        mock_get_datetime_string: Mock,
        mock_backup_controller: Mock,
        mock_ssh: Mock,
        mock_scp: Mock,
    ):
        results_dict = {"filename": "myfile", "controller-machine-id": "0"}
        mock_controller_model = Mock()
        mock_backup_controller.return_value = (mock_controller_model, results_dict)

        return_path = self.controller_backup.backup()

        mock_backup_controller.assert_called_once_with(self.controller_backup.controller)
        self.assertEqual(mock_ssh.call_count, 2, "Ensure ssh_run_on_machine was called twice (chown and rm)")
        mock_scp.assert_called_once()
        mock_path_exists.assert_called_once_with(self.controller_backup.save_path)
        mock_get_datetime_string.assert_called_once()
        self.assertEqual(return_path.parent, self.mock_save_path.absolute())

    @patch("jujubackupall.backup.scp_from_machine")
    @patch("jujubackupall.backup.ssh_run_on_machine")
    @patch("jujubackupall.backup.backup_controller")
    @patch("jujubackupall.backup.get_datetime_string")
    @patch("jujubackupall.backup.ensure_path_exists")
    def test_backup_controller_one_fail_then_success(
        self,
        mock_path_exists: Mock,
        mock_get_datetime_string: Mock,
        mock_backup_controller: Mock,
        mock_ssh: Mock,
        mock_scp: Mock,
    ):
        results_dict = {"filename": "myfile", "controller-machine-id": "0"}
        mock_controller_model = Mock()
        mock_backup_controller.side_effect = [self.get_juju_api_error(), (mock_controller_model, results_dict)]

        result = self.controller_backup.backup()

        self.assertIsInstance(result, Path)
        self.assertEqual(mock_backup_controller.call_count, 2, "assert backup_controller was called twice")

    @patch("jujubackupall.backup.backup_controller")
    @patch("jujubackupall.backup.get_datetime_string")
    @patch("jujubackupall.backup.ensure_path_exists")
    def test_backup_controller_all_fail_raise_exception(
        self, mock_path_exists: Mock, mock_get_datetime_string: Mock, mock_backup_controller: Mock
    ):
        mock_backup_controller.side_effect = self.get_juju_api_error()
        self.assertRaises(JujuControllerBackupError, self.controller_backup.backup)
        self.assertEqual(
            mock_backup_controller.call_count,
            MAX_CONTROLLER_BACKUP_RETRIES,
            "assert check_output was called {} times.".format(MAX_CONTROLLER_BACKUP_RETRIES),
        )


class TestJujuClientConfigBackup(unittest.TestCase):
    @patch("jujubackupall.backup.os")
    def test_juju_client_config_backup_create_no_environ(self, mock_os: Mock):
        output_path = Path("mypath")
        mock_os.environ.get.return_value = None
        class_client_config_location = JujuClientConfigBackup.client_config_location
        juju_config_backup_inst = JujuClientConfigBackup(output_path)
        self.assertEqual(juju_config_backup_inst.client_config_location, class_client_config_location)

    @patch("jujubackupall.backup.os")
    def test_juju_client_config_backup_create_with_environ(self, mock_os: Mock):
        env_path = "alt-path"
        output_path = Path("mypath")
        mock_os.environ.get.return_value = env_path
        juju_config_backup_inst = JujuClientConfigBackup(output_path)
        self.assertEqual(juju_config_backup_inst.client_config_location, Path(env_path))

    @patch("jujubackupall.backup.shutil")
    @patch("jujubackupall.backup.ensure_path_exists")
    @patch("jujubackupall.backup.os")
    def test_juju_client_config_backup(self, mock_os: Mock, mock_ensure_path: Mock, mock_shutil: Mock):
        output_path = Path("my/path")
        mock_os.environ.get.return_value = None
        mock_shutil.make_archive.return_value = output_path / "archive.tar.gz"
        juju_config_backup_inst = JujuClientConfigBackup(output_path)
        juju_config_backup_inst.backup()
        mock_ensure_path.assert_called_once()
        mock_shutil.make_archive.assert_called_once()


class TestMysqlBackup(unittest.TestCase):
    @patch("jujubackupall.backup.check_output_unit_action")
    def test_backup_innodb(self, mock_check_output_unit_action: Mock):
        mock_unit = Mock()
        mysql_dumpfile = "mydumpfile"
        results_dict = {"results": {"mysqldump-file": mysql_dumpfile}}
        mock_check_output_unit_action.return_value = results_dict
        mysql_innodb_backup = MysqlInnodbBackup(mock_unit)
        mysql_innodb_backup.backup()
        self.assertEqual(mysql_innodb_backup.backup_filepath, Path(mysql_dumpfile))
        mock_check_output_unit_action.assert_called_once_with(mock_unit, mysql_innodb_backup.backup_action_name)

    @patch("jujubackupall.backup.ensure_path_exists")
    @patch("jujubackupall.backup.scp_from_unit")
    @patch("jujubackupall.backup.ssh_run_on_unit")
    def test_download_backup_innodb(
        self,
        mock_ssh_run_on_unit: Mock,
        mock_scp_from_unit: Mock,
        mock_ensure_path_exists: Mock,
    ):
        save_path = Path("my-path")
        backup_filepath = Path("some-path")
        mock_unit = Mock()
        mysql_innodb_backup = MysqlInnodbBackup(mock_unit)
        mysql_innodb_backup.backup_filepath = backup_filepath
        mysql_innodb_backup.download_backup(save_path)
        mock_ensure_path_exists.assert_called_once_with(path=save_path)
        mock_scp_from_unit.assert_called_once_with(
            unit=mock_unit, source=str("/tmp/" / backup_filepath), destination=str(save_path)
        )
        self.assertEqual(mock_ssh_run_on_unit.call_count, 2, "assert ssh run on unit called twice")

    @patch("jujubackupall.backup.check_output_unit_action")
    def test_percona_backup_setting_pxc(self, mock_check_output_unit_action: Mock):
        mock_unit = Mock()
        results_dict = {"results": {"mysqldump-file": "mysql_dumpfile"}}
        mock_check_output_unit_action.return_value = results_dict
        percona_backup = PerconaClusterBackup(mock_unit)
        percona_backup.backup()
        expected_calls = [
            call(mock_unit, "set-pxc-strict-mode", mode="MASTER"),
            call(mock_unit, "mysqldump"),
            call(mock_unit, "set-pxc-strict-mode", mode="ENFORCING"),
        ]
        mock_check_output_unit_action.assert_has_calls(expected_calls)


class TestEtcdBackup(unittest.TestCase):
    @patch("jujubackupall.backup.check_output_unit_action")
    def test_etcd_backup(self, mock_check_output_unit_action: Mock):
        mock_unit = Mock()
        expected_path_string = "my_path"
        results_dict = {"results": {"snapshot": {"path": expected_path_string}}}
        mock_check_output_unit_action.return_value = results_dict
        etcd_backup_inst = EtcdBackup(mock_unit)
        etcd_backup_inst.backup()
        mock_check_output_unit_action.assert_called_once()
        self.assertEqual(etcd_backup_inst.backup_filepath, Path(expected_path_string))


class TestBackupTracker(unittest.TestCase):
    app_backups = [
        dict(controller="controller1", model="model1", charm="charm1", app="app1", download_path="mypath1"),
        dict(controller="controller2", model="model2", charm="charm2", app="app2", download_path="mypath2"),
    ]

    config_backups = [
        dict(config="config1", download_path="mypath3"),
        dict(config="config2", download_path="mypath4"),
    ]

    controller_backups = [
        dict(controller="controller1", download_path="mypath5"),
        dict(controller="controller2", download_path="mypath6"),
    ]

    def setUp(self) -> None:
        self.tracker = BackupTracker()

    def assert_output(self, expected_output):
        actual_output = self.tracker.to_json()
        self.assertEqual(expected_output, actual_output)

    @staticmethod
    def generate_expected_output(apps, configs, controllers):
        d = dict(controller_backups=controllers, config_backups=configs, app_backups=apps)
        return json.dumps(d, indent=2)

    def add_app_backups_to_tracker(self, app_backup_dicts):
        for app_backup_dict in app_backup_dicts:
            self.tracker.add_app_backup(
                controller=app_backup_dict.get("controller"),
                model=app_backup_dict.get("model"),
                charm=app_backup_dict.get("charm"),
                app=app_backup_dict.get("app"),
                download_path=app_backup_dict.get("download_path"),
            )

    def add_controller_backups_to_tracker(self, controller_backup_dicts):
        for controller_backup_dict in controller_backup_dicts:
            self.tracker.add_controller_backup(
                controller=controller_backup_dict.get("controller"),
                download_path=controller_backup_dict.get("download_path"),
            )

    def add_config_backups_to_tracker(self, config_backup_dicts):
        for config_backup_dict in config_backup_dicts:
            self.tracker.add_config_backup(
                config=config_backup_dict.get("config"),
                download_path=config_backup_dict.get("download_path"),
            )

    def test_report_multi_apps(self):
        expected_output = self.generate_expected_output(apps=self.app_backups, controllers=[], configs=[])
        self.add_app_backups_to_tracker(self.app_backups)
        self.assert_output(expected_output)

    def test_report_one_app(self):
        expected_output = self.generate_expected_output(apps=self.app_backups[0:1], controllers=[], configs=[])
        self.add_app_backups_to_tracker(self.app_backups[0:1])
        self.assert_output(expected_output)

    def test_report_multi_controllers(self):
        expected_output = self.generate_expected_output(apps=[], controllers=self.controller_backups, configs=[])
        self.add_controller_backups_to_tracker(self.controller_backups)
        self.assert_output(expected_output)

    def test_multi_configs(self):
        expected_output = self.generate_expected_output(apps=[], controllers=[], configs=self.config_backups)
        self.add_config_backups_to_tracker(self.config_backups)
        self.assert_output(expected_output)

    def test_all_no_errors(self):
        expected_output = self.generate_expected_output(
            apps=self.app_backups, controllers=self.controller_backups, configs=self.config_backups
        )
        self.add_app_backups_to_tracker(self.app_backups)
        self.add_config_backups_to_tracker(self.config_backups)
        self.add_controller_backups_to_tracker(self.controller_backups)
        self.assert_output(expected_output)

    def test_all_errors(self):
        error_list = [
            dict(controller="controller1", error_reason="some reason"),
            dict(config="config2", error_reason="some other reason"),
            dict(controller="app", app="some-app", error_reason="some other reason"),
        ]
        expected_output = json.dumps(
            dict(controller_backups=[], config_backups=[], app_backups=[], errors=error_list), indent=2
        )
        for error in error_list:
            self.tracker.add_error(**error)
        self.assert_output(expected_output)
