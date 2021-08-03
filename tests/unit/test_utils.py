#!/usr/bin/python3
""" Unit tests for utils.py """
import unittest

from jujubackupall.utils import parse_charm_name


class TestParseCharmName(unittest.TestCase):
    def test_parse_nonpromulgated_charm(self):
        charm_url = 'cs:~containers/containerd-146'
        result = parse_charm_name(charm_url)
        self.assertEqual(result, 'containerd')

    def test_parse_promulgated_charm(self):
        charm_url = 'cs:mysql-innodb-cluster-9'
        result = parse_charm_name(charm_url)
        self.assertEqual(result, 'mysql-innodb-cluster')


if __name__ == '__main__':
    unittest.main()
