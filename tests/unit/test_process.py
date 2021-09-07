#!/usr/bin/python3
""" Unit tests for cli.py """
from collections import namedtuple
from pathlib import Path
import unittest
from unittest.mock import Mock, patch, call, ANY

from jujubackupall.constants import SUPPORTED_BACKUP_CHARMS
from jujubackupall.errors import JujuControllerBackupError, ActionError
from jujubackupall.process import BackupProcessor, ControllerProcessor, JujuModel

SubtestCase = namedtuple("SubtestCase", ["name", "input", "expected"])


class TestBackupProcessor(unittest.TestCase):
    @patch("jujubackupall.process.Config", return_value=Mock())
    def setUp(self, mock_config) -> None:
        self.mock_config = mock_config
        self.mock_config.backup_juju_client_config = False

    def test_apps_to_backup(self):
        all_charms_but_mysql_innodb = list(set(SUPPORTED_BACKUP_CHARMS) - {"mysql-innodb-cluster"})
        test_cases = [
            SubtestCase(name="none excluded", input=[], expected=SUPPORTED_BACKUP_CHARMS),
            SubtestCase(name="all excluded", input=SUPPORTED_BACKUP_CHARMS, expected=[]),
            SubtestCase(
                name="mysql-innodb excluded", input=["mysql-innodb-cluster"], expected=all_charms_but_mysql_innodb
            ),
        ]
        for test_case in test_cases:
            with self.subTest(test_case=test_cases):
                self.mock_config.excluded_charms = test_case.input
                backup_processor = BackupProcessor(self.mock_config)
                self.assertEqual(backup_processor.apps_to_backup, test_case.expected)

    def test_controller_names_already_set_current_controller(self):
        self.mock_config.use_current_controller = True
        self.mock_config.all_controllers = False
        self.mock_config.controllers = None
        backup_processor = BackupProcessor(self.mock_config)
        self.assertIsNone(backup_processor._controller_names)
        current_controller = backup_processor.controller_names
        self.assertIsNotNone(backup_processor._controller_names)
        self.assertEqual(current_controller, [""])
        cached_controller = backup_processor.controller_names
        self.assertEqual(cached_controller, [""])

    @patch("jujubackupall.process.get_all_controllers")
    def test_controller_names_all_controllers(self, mock_get_all_controllers: Mock):
        self.mock_config.all_controllers = True
        expected_controllers = ["controller1", "controller2"]
        mock_get_all_controllers.return_value = expected_controllers
        backup_processor = BackupProcessor(self.mock_config)
        actual_controllers = backup_processor.controller_names
        self.assertListEqual(actual_controllers, expected_controllers)
        mock_get_all_controllers.assert_called_once()

    def test_controller_names_controller_list(self):
        controller_list = ["controller1", "controller2"]
        self.mock_config.all_controllers = False
        self.mock_config.use_current_controller = False
        self.mock_config.controllers = controller_list
        backup_processor = BackupProcessor(self.mock_config)
        actual_controllers = backup_processor.controller_names
        self.assertListEqual(actual_controllers, controller_list)

    @patch("jujubackupall.process.connect_controller")
    @patch("jujubackupall.process.ControllerProcessor")
    def test_process_backups_backup_controller(
        self, mock_controller_processor_class: Mock, mock_connect_controller: Mock
    ):
        controller_list = ["controller1", "controller2"]
        self.mock_config.all_controllers = False
        self.mock_config.use_current_controller = False
        self.mock_config.backup_controller = True
        self.mock_config.controllers = controller_list
        self.mock_config.output_dir = "juju-backups"

        mock_controller_processor = Mock()
        mock_controller_processor_class.return_value = mock_controller_processor

        backup_processor = BackupProcessor(self.mock_config)
        backup_processor.process_backups()

        connect_controller_calls = [call(name) for name in controller_list]
        mock_connect_controller.assert_has_calls(connect_controller_calls, any_order=True)
        self.assertEqual(
            mock_controller_processor.backup_models.call_count,
            len(controller_list),
            "assert backup_models called correct number of times",
        )
        self.assertEqual(
            mock_controller_processor.backup_models.call_count,
            len(controller_list),
            "assert backup_models called correct number of times",
        )
        mock_controller_processor.backup_controller.assert_called()

    @patch("jujubackupall.process.connect_controller")
    @patch("jujubackupall.process.ControllerProcessor")
    def test_process_backups_no_backup_controller(
        self, mock_controller_processor_class: Mock, mock_connect_controller: Mock
    ):
        controller_list = ["controller1", "controller2"]
        self.mock_config.all_controllers = False
        self.mock_config.use_current_controller = False
        self.mock_config.backup_controller = False
        self.mock_config.controllers = controller_list
        self.mock_config.output_dir = "juju-backups"

        mock_controller_processor = Mock()
        mock_controller_processor_class.return_value = mock_controller_processor

        backup_processor = BackupProcessor(self.mock_config)
        backup_processor.process_backups()

        connect_controller_calls = [call(name) for name in controller_list]
        mock_connect_controller.assert_has_calls(connect_controller_calls, any_order=True)
        self.assertEqual(
            mock_controller_processor.backup_models.call_count,
            len(controller_list),
            "assert backup_models called correct number of times",
        )
        mock_controller_processor.backup_controller.assert_not_called()

    @patch("jujubackupall.process.tracker")
    @patch("jujubackupall.process.JujuClientConfigBackup")
    def test_process_backups_backup_juju_config(self, mock_juju_config_backup: Mock, mock_tracker: Mock):
        self.mock_config.all_controllers = False
        self.mock_config.use_current_controller = False
        self.mock_config.backup_controller = False
        self.mock_config.backup_juju_client_config = True
        self.mock_config.controllers = []
        self.mock_config.output_dir = "juju-backups"

        mock_juju_config_backup_inst = Mock()
        mock_juju_config_backup.return_value = mock_juju_config_backup_inst

        backup_processor = BackupProcessor(self.mock_config)
        backup_processor._controller_names = []
        backup_processor.process_backups()
        mock_juju_config_backup.assert_called_with(Path(self.mock_config.output_dir))
        mock_juju_config_backup_inst.backup.assert_called_once()
        mock_tracker.print_report.assert_called_once()


class TestControllerProcessor(unittest.TestCase):
    @patch("jujubackupall.process.Controller")
    def setUp(self, mock_controller) -> None:
        self.mock_controller = mock_controller
        self.base_output_path = Path("juju-backups")
        self.apps_to_backup = SUPPORTED_BACKUP_CHARMS

    def create_controller_processor(self):
        return ControllerProcessor(
            controller=self.mock_controller, base_output_path=self.base_output_path, apps_to_backup=self.apps_to_backup
        )

    @staticmethod
    def create_app_tuple(app_name):
        """Helper function that takes in an app name and returns a tuple with name and properly set up mock"""
        mock_app = Mock()
        mock_app.data.get.return_value = "cs:{}-1".format(app_name)
        return app_name, mock_app

    @patch("jujubackupall.process.JujuControllerBackup", return_value=Mock())
    def test_backup_controller(self, mock_juju_controller_backup_class: Mock):
        controller_name = "my-controller"
        self.mock_controller.controller_name = controller_name
        mock_juju_controller_backup_inst = Mock()
        mock_juju_controller_backup_class.return_value = mock_juju_controller_backup_inst

        controller_processor = self.create_controller_processor()
        controller_processor.backup_controller()

        mock_juju_controller_backup_class.assert_called_with(
            controller=self.mock_controller, save_path=(self.base_output_path / controller_name)
        )
        mock_juju_controller_backup_inst.backup.assert_called_once()

    @patch("jujubackupall.process.tracker")
    @patch("jujubackupall.process.JujuControllerBackup", return_value=Mock())
    def test_backup_controller_fails(self, mock_juju_controller_backup_class: Mock, mock_tracker: Mock):
        controller_name = "my-controller"
        self.mock_controller.controller_name = controller_name
        mock_juju_controller_backup_inst = Mock()
        mock_juju_controller_backup_class.return_value = mock_juju_controller_backup_inst

        juju_backup_error = JujuControllerBackupError(Mock())

        mock_juju_controller_backup_inst.backup.side_effect = [juju_backup_error]
        controller_processor = self.create_controller_processor()
        controller_processor.backup_controller()

        mock_tracker.add_error.assert_called_once_with(controller=controller_name, error_reason=str(juju_backup_error))

    @patch("jujubackupall.process.ControllerProcessor._log")
    @patch("jujubackupall.process.ControllerProcessor.backup_apps")
    @patch("jujubackupall.process.connect_model")
    @patch("jujubackupall.process.run_async")
    def test_backup_models(
        self, mock_run_async: Mock, mock_connect_model: Mock, mock_backup_apps: Mock, mock_log: Mock
    ):
        model_names = ["model1", "model2"]
        mock_run_async.return_value = model_names

        controller_processor = self.create_controller_processor()
        controller_processor.backup_models()

        connect_model_calls = [call(self.mock_controller, name) for name in model_names]
        print(mock_connect_model)
        mock_connect_model.assert_has_calls(connect_model_calls, any_order=True)
        self.assertEqual(
            mock_backup_apps.call_count, len(model_names), "assert backup_apps called expected number of times"
        )

    @patch("jujubackupall.process.ControllerProcessor.generate_full_backup_path")
    @patch("jujubackupall.process.ControllerProcessor._log")
    @patch("jujubackupall.process.get_leader")
    @patch("jujubackupall.process.get_charm_backup_instance")
    def test_backup_apps_all_supported(
        self,
        mock_get_backup_instance: Mock,
        mock_get_leader: Mock,
        mock_generate_full_backup_path: Mock,
        mock_log: Mock,
    ):
        model_name = "my-model"
        mock_model = Mock()
        apps = [self.create_app_tuple(app_name) for app_name in ["mysql-innodb-cluster", "percona-cluster", "my-app"]]
        apps_dict = dict()
        for app_name, app in apps:
            apps_dict[app_name] = app
        mock_model.applications.items.return_value = apps_dict.items()
        juju_model = JujuModel(name=model_name, model=mock_model)

        controller_processor = self.create_controller_processor()
        controller_processor.backup_apps(juju_model)

        calls_get_backup_instance = [
            call(charm_name="mysql-innodb-cluster", unit=ANY),
            call(charm_name="percona-cluster", unit=ANY),
        ]
        mock_get_backup_instance.assert_has_calls(calls_get_backup_instance, any_order=True)
        mock_generate_full_backup_path.assert_called()
        self.assertEqual(mock_get_leader.call_count, 2, "assert get_leader called twice (for the 2 charms in scope)")

    @patch("jujubackupall.process.get_leader")
    @patch("jujubackupall.process.get_charm_backup_instance")
    @patch("jujubackupall.process.ControllerProcessor._log")
    @patch("jujubackupall.process.tracker")
    def test_backup_app_action_error(
        self, mock_tracker: Mock, mock_log: Mock, mock_get_charm_backup_instance: Mock, mock_get_leader: Mock
    ):
        model_name = "my-model"
        charm_name = "my-charm"
        app_name = "my-app"
        controller_name = "my-controller"
        self.mock_controller.controller_name = controller_name
        mock_leader_unit = Mock()
        mock_application = Mock()
        mock_charm_backup_instance = Mock()

        mock_get_leader.return_value = mock_leader_unit
        mock_get_charm_backup_instance.return_value = mock_charm_backup_instance

        action_error = ActionError(Mock())
        mock_charm_backup_instance.backup.side_effect = [action_error]

        controller_processor = self.create_controller_processor()
        controller_processor.backup_app(
            app=mock_application, app_name=app_name, model_name=model_name, charm_name=charm_name
        )

        mock_tracker.add_error.assert_called_once_with(
            controller=controller_name, model=model_name, app=app_name, charm=charm_name, error_reason=str(action_error)
        )

    def test_generate_full_backup_path(self):
        app_name = "my-app"
        controller_name = "my-controller"
        model_name = "my-model"
        self.mock_controller.controller_name = controller_name
        controller_processor = self.create_controller_processor()
        actual_path = controller_processor.generate_full_backup_path(model_name=model_name, app_name=app_name)
        expected_path = Path("{}/{}/{}/{}".format(self.base_output_path, controller_name, model_name, app_name))
        self.assertEqual(actual_path, expected_path)
