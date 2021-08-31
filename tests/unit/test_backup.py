#!/usr/bin/python3
""" Unit tests for backup.py """
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch, ANY, call

from jujubackupall.backup import (
    MysqlInnodbBackup, PerconaClusterBackup, get_charm_backup_instance,
    PostgresqlBackup, EtcdBackup, SwiftBackup, JujuControllerBackup, JujuClientConfigBackup
)
from jujubackupall.constants import MAX_CONTROLLER_BACKUP_RETRIES
from jujubackupall.errors import JujuControllerBackupError


class TestGetCharmBackupInstance(unittest.TestCase):
    def test_get_backup_instance(self):
        test_cases = [('mysql-innodb-cluster', MysqlInnodbBackup),
                      ('percona-cluster', PerconaClusterBackup),
                      ('etcd', EtcdBackup),
                      ('postgresql', PostgresqlBackup),
                      ('swift-proxy', SwiftBackup)]
        for charm_name, expected_backup_class in test_cases:
            with self.subTest(charm_name=charm_name, expected_backup_class=expected_backup_class):
                backup_instance = get_charm_backup_instance(charm_name, Mock())
                self.assertIsInstance(backup_instance, expected_backup_class)


class TestJujuControllerBackup(unittest.TestCase):
    def setUp(self):
        self.mock_controller = Mock()
        self.mock_save_path = Path('mypath')
        self.controller_backup = JujuControllerBackup(
            controller=self.mock_controller,
            save_path=self.mock_save_path
        )

    @patch("jujubackupall.backup.subprocess")
    @patch("jujubackupall.backup.get_datetime_string")
    @patch("jujubackupall.backup.ensure_path_exists")
    def test_backup_controller_first_success(
            self,
            mock_path_exists: Mock,
            mock_get_datetime_string: Mock,
            mock_subprocess: Mock
    ):
        self.controller_backup.backup()
        mock_subprocess.check_output.assert_called_once()

    @patch("jujubackupall.backup.subprocess.check_output")
    @patch("jujubackupall.backup.get_datetime_string")
    @patch("jujubackupall.backup.ensure_path_exists")
    def test_backup_controller_one_fail_then_success(
            self,
            mock_path_exists: Mock,
            mock_get_datetime_string: Mock,
            mock_subprocess_check_output: Mock
    ):
        called_proc_error = subprocess.CalledProcessError(returncode=2, cmd=["bad"], stderr='something')
        mock_subprocess_check_output.side_effect = [called_proc_error, "", 10]
        self.controller_backup.backup()
        self.assertEqual(mock_subprocess_check_output.call_count, 2, "assert check_output was called twice.")

    @patch("jujubackupall.backup.subprocess.check_output")
    @patch("jujubackupall.backup.get_datetime_string")
    @patch("jujubackupall.backup.ensure_path_exists")
    def test_backup_controller_one_fail_then_success(
            self,
            mock_path_exists: Mock,
            mock_get_datetime_string: Mock,
            mock_subprocess_check_output: Mock
    ):
        called_proc_error = subprocess.CalledProcessError(returncode=2, cmd=["bad"], stderr='something')
        mock_subprocess_check_output.side_effect = [called_proc_error, None]
        self.controller_backup.backup()
        self.assertEqual(mock_subprocess_check_output.call_count, 2, "assert check_output was called twice.")

    @patch("jujubackupall.backup.subprocess.check_output")
    @patch("jujubackupall.backup.get_datetime_string")
    @patch("jujubackupall.backup.ensure_path_exists")
    def test_backup_controller_all_fail_raise_exception(
            self,
            mock_path_exists: Mock,
            mock_get_datetime_string: Mock,
            mock_subprocess_check_output: Mock
    ):
        called_proc_error = subprocess.CalledProcessError(returncode=2, cmd=["bad"], stderr='something')
        mock_subprocess_check_output.side_effect = called_proc_error
        self.assertRaises(JujuControllerBackupError, self.controller_backup.backup)
        self.assertEqual(
            mock_subprocess_check_output.call_count,
            MAX_CONTROLLER_BACKUP_RETRIES,
            "assert check_output was called {} times.".format(MAX_CONTROLLER_BACKUP_RETRIES)
        )


class TestJujuClientConfigBackup(unittest.TestCase):
    @patch("jujubackupall.backup.os")
    def test_juju_client_config_backup_create_no_environ(self, mock_os: Mock):
        output_path = Path('mypath')
        mock_os.environ.get.return_value = None
        class_client_config_location = JujuClientConfigBackup.client_config_location
        juju_config_backup_inst = JujuClientConfigBackup(output_path)
        self.assertEqual(juju_config_backup_inst.client_config_location, class_client_config_location)

    @patch("jujubackupall.backup.os")
    def test_juju_client_config_backup_create_with_environ(self, mock_os: Mock):
        env_path = "alt-path"
        output_path = Path('mypath')
        mock_os.environ.get.return_value = env_path
        juju_config_backup_inst = JujuClientConfigBackup(output_path)
        self.assertEqual(juju_config_backup_inst.client_config_location, Path(env_path))

    @patch("jujubackupall.backup.shutil")
    @patch("jujubackupall.backup.ensure_path_exists")
    @patch("jujubackupall.backup.os")
    def test_juju_client_config_backup(
            self, mock_os: Mock, mock_ensure_path: Mock, mock_shutil: Mock
    ):
        output_path = Path('my/path')
        mock_os.environ.get.return_value = None
        juju_config_backup_inst = JujuClientConfigBackup(output_path)
        juju_config_backup_inst.backup()
        mock_ensure_path.assert_called_once()
        mock_shutil.make_archive.assert_called_once()


class TestMysqlBackup(unittest.TestCase):
    @patch("jujubackupall.backup.check_output_unit_action")
    def test_backup_innodb(self, mock_check_output_unit_action: Mock):
        mock_unit = Mock()
        mysql_dumpfile = "mydumpfile"
        results_dict = {
            "results": {
                "mysqldump-file": mysql_dumpfile
            }
        }
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
            unit=mock_unit,
            source=str("/tmp/" / backup_filepath),
            destination=str(save_path)
        )
        self.assertEqual(mock_ssh_run_on_unit.call_count, 2, "assert ssh run on unit called twice")

    @patch("jujubackupall.backup.check_output_unit_action")
    def test_percona_backup_setting_pxc(self, mock_check_output_unit_action: Mock):
        mock_unit = Mock()
        results_dict = {
            "results": {
                "mysqldump-file": "mysql_dumpfile"
            }
        }
        mock_check_output_unit_action.return_value = results_dict
        percona_backup = PerconaClusterBackup(mock_unit)
        percona_backup.backup()
        expected_calls = [
            call(mock_unit, "set-pxc-strict-mode", mode="MASTER"),
            call(mock_unit, "mysqldump"),
            call(mock_unit, "set-pxc-strict-mode", mode="ENFORCING")
        ]
        mock_check_output_unit_action.assert_has_calls(expected_calls)


class TestEtcdBackup(unittest.TestCase):
    @patch("jujubackupall.backup.check_output_unit_action")
    def test_etcd_backup(self, mock_check_output_unit_action: Mock):
        mock_unit = Mock()
        expected_path_string = "my_path"
        results_dict = {
            "results": {
                "snapshot": {
                    "path": expected_path_string
                }
            }
        }
        mock_check_output_unit_action.return_value = results_dict
        etcd_backup_inst = EtcdBackup(mock_unit)
        etcd_backup_inst.backup()
        mock_check_output_unit_action.assert_called_once()
        self.assertEqual(etcd_backup_inst.backup_filepath, Path(expected_path_string))
