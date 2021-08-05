#!/usr/bin/python3
""" Unit tests for config.py """
import unittest

from jujubackupall.config import Config


all_controllers = False
backup_controller = True
controllers = ['controller1', 'controller2']
excluded_charms = ['mysql']
output_dir = 'my_output_dir'


def get_default_config():
    return dict(
        all_controllers=all_controllers,
        backup_controller=backup_controller,
        controllers=controllers,
        excluded_charms=excluded_charms,
        output_dir=output_dir
    )


class TestConfig(unittest.TestCase):
    def test_config_init(self):
        res_config = Config(get_default_config())
        self.assertEqual(res_config.all_controllers, all_controllers)
        self.assertEqual(res_config.backup_controller, backup_controller)
        self.assertEqual(res_config.controllers, controllers)
        self.assertEqual(res_config.excluded_charms, excluded_charms)
        self.assertEqual(res_config.output_dir, output_dir)
        self.assertEqual(res_config.use_current_controller, False)

    def test_config_use_current_controller(self):
        config_dict = get_default_config()
        config_dict['all_controller'] = False
        config_dict['controllers'] = []
        res_config = Config(config_dict)
        self.assertTrue(res_config.use_current_controller)


if __name__ == '__main__':
    unittest.main()
