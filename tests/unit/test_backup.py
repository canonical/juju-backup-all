#!/usr/bin/python3
""" Unit tests for backup.py """
import unittest
from unittest.mock import Mock

from jujubackupall.backup import (
    MysqlInnodbBackup, PerconaClusterBackup, get_charm_backup_instance, PostgresqlBackup, EtcdBackup, SwiftBackup
)


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
