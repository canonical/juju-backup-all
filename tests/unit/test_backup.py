#!/usr/bin/python3
""" Unit tests for backup.py """
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

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
