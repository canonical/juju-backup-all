#!/usr/bin/python3
"""Unit tests for utils.py"""
import unittest
from concurrent.futures import TimeoutError
from unittest.mock import Mock, patch

from jujubackupall.errors import ActionError, JujuTimeoutError, NoLeaderError
from jujubackupall.utils import (
    backup_controller,
    check_output_unit_action,
    connect_controller,
    connect_model,
    get_all_controllers,
    get_leader,
    parse_charm_name,
    run_with_timeout,
)


class TestParseCharmName(unittest.TestCase):
    def test_parse_nonpromulgated_charm(self):
        charm_url = "cs:~containers/containerd-146"
        result = parse_charm_name(charm_url)
        self.assertEqual(result, "containerd")

    def test_parse_promulgated_charm(self):
        charm_url = "cs:mysql-innodb-cluster-9"
        result = parse_charm_name(charm_url)
        self.assertEqual(result, "mysql-innodb-cluster")


class TestConnectController(unittest.TestCase):
    @patch("jujubackupall.utils.Controller", return_value=Mock())
    @patch("jujubackupall.utils.run_async")
    def test_connect_controller_with_name(self, mock_run_async: Mock, mock_controller: Mock):
        my_controller_name = "my-controller"
        mock_controller_instance = mock_controller.return_value
        with connect_controller(my_controller_name):
            pass
        mock_controller_instance.connect.assert_called_with(my_controller_name)
        mock_controller_instance.disconnect.assert_called_once()

    @patch("jujubackupall.utils.Controller", return_value=Mock())
    @patch("jujubackupall.utils.run_async")
    def test_connect_controller_with_empty_name(self, mock_run_async: Mock, mock_controller: Mock):
        empty_controller_name = ""
        mock_controller_instance = mock_controller.return_value
        with connect_controller(empty_controller_name):
            pass
        mock_controller_instance.connect.assert_called_once_with()
        mock_controller_instance.disconnect.assert_called_once()


class TestConnectModel(unittest.TestCase):
    @patch("jujubackupall.utils.run_async")
    def test_connect_model(self, mock_run_async: Mock):
        model_name = "my-model"
        mock_model = Mock()
        mock_controller = Mock()
        mock_run_async.return_value = mock_model
        with connect_model(mock_controller, model_name):
            pass
        mock_controller.get_model.assert_called_with(model_name)
        mock_model.disconnect.assert_called_once()


class TestGetAllControllers(unittest.TestCase):
    @patch("jujubackupall.utils.Juju")
    def test_get_all_controllers(self, mock_juju_class: Mock):
        controller_name_1 = "my-controller-1"
        controller_name_2 = "my-controller-2"
        controller_dict = {controller_name_1: None, controller_name_2: None}
        mock_juju_inst = Mock()
        mock_juju_inst.get_controllers.return_value = controller_dict
        mock_juju_class.return_value = mock_juju_inst
        actual_controller_names = get_all_controllers()
        self.assertEqual(len(actual_controller_names), 2, "assert excpected number of controller names returned")
        self.assertIn(controller_name_1, actual_controller_names)
        self.assertIn(controller_name_2, actual_controller_names)


class TestGetLeader(unittest.TestCase):
    @patch("jujubackupall.utils.run_async")
    def test_get_leader(self, mock_run_async: Mock):
        mock_units = [Mock() for _ in range(3)]
        mock_units[0].is_leader_from_status.return_value = False
        mock_units[1].is_leader_from_status.return_value = False
        mock_units[2].is_leader_from_status.return_value = True
        mock_run_async.side_effect = [False, False, True]
        actual_leader = get_leader(mock_units)
        mock_units[2].is_leader_from_status.assert_called_once()
        self.assertEqual(actual_leader, mock_units[2])

    @patch("jujubackupall.utils.run_async")
    def test_get_leader_no_leader(self, mock_run: Mock):
        mock_units = [Mock() for _ in range(3)]
        mock_units[0].is_leader_from_status.return_value = False
        mock_units[1].is_leader_from_status.return_value = False
        mock_units[2].is_leader_from_status.return_value = False
        mock_run.side_effect = [False, False, False]
        with self.assertRaises(NoLeaderError):
            get_leader(mock_units)
        mock_units[2].is_leader_from_status.assert_called_once()


class TestCheckOutputUnitAction(unittest.TestCase):
    @patch("jujubackupall.utils.wait_for")
    @patch("jujubackupall.utils.run_async")
    def test_check_output_unit_action_success_no_params(self, mock_run_async: Mock, mock_wait_for: Mock):
        action_name = "my-action"
        safe_data = dict(status="completed")
        mock_unit = Mock()
        mock_action = Mock()
        mock_action.safe_data = safe_data
        mock_run_async.return_value = mock_action
        mock_run_async.return_value.results = "foo"
        result = check_output_unit_action(mock_unit, action_name)
        self.assertEqual(mock_run_async.call_count, 2, "assert run_async called twice")
        self.assertEqual(result, "foo")
        mock_unit.run_action.assert_called_once_with(action_name)
        mock_action.wait.assert_called_once()

    @patch("jujubackupall.utils.wait_for")
    @patch("jujubackupall.utils.run_async")
    def test_check_output_unit_action_success_with_params(self, mock_run_async: Mock, mock_wait_for: Mock):
        action_name = "my-action"
        action_params = dict(param_one="hello", param_two="world")
        safe_data = dict(status="completed")
        mock_unit = Mock()
        mock_action = Mock()
        mock_action.safe_data = safe_data
        mock_run_async.return_value = mock_action
        mock_run_async.return_value.results = "foo"
        result = check_output_unit_action(mock_unit, action_name, **action_params)
        self.assertEqual(mock_run_async.call_count, 2, "assert run_async called twice")
        self.assertEqual(result, "foo")
        mock_unit.run_action.assert_called_once_with(action_name, **action_params)
        mock_action.wait.assert_called_once()

    @patch("jujubackupall.utils.wait_for")
    @patch("jujubackupall.utils.run_async")
    def test_check_output_unit_action_failure(self, mock_run_async: Mock, mock_wait_for: Mock):
        action_name = "my-action"
        failure_status = "failure"
        failure_results = dict(status=failure_status)
        safe_data = dict(status=failure_status, results=failure_results)
        mock_unit = Mock()
        mock_action = Mock()
        mock_action.safe_data = safe_data
        mock_run_async.return_value = mock_action
        with self.assertRaises(ActionError) as context:
            check_output_unit_action(mock_unit, action_name)
        self.assertTrue(failure_status in str(context.exception))
        self.assertTrue(context.exception.results(), failure_results)


class TestBackupController(unittest.TestCase):
    @patch("jujubackupall.utils.run_with_timeout")
    @patch("jujubackupall.utils.run_async")
    def test_backup_controller_success(self, mock_run_async: Mock, mock_run_with_timeout: Mock):
        mock_model = Mock()
        mock_controller = Mock()
        expected_dict = dict()
        controller_name = "my-controller"
        local_backup_filename = "local_filename"

        mock_run_async.return_value = mock_model
        mock_run_with_timeout.return_value = (local_backup_filename, expected_dict)
        mock_controller.controller_name = controller_name

        actual_filename, actual_dict = backup_controller(mock_controller)

        mock_controller.get_model.assert_called_once_with("controller")
        mock_run_with_timeout.assert_called_once_with(
            mock_model.create_backup(), "controller backup on controller {}".format(controller_name)
        )
        self.assertEqual(actual_filename, local_backup_filename)
        self.assertEqual(actual_dict, expected_dict)


class TestRunWithTimeout(unittest.TestCase):
    @patch("jujubackupall.utils.globals")
    @patch("jujubackupall.utils.run_async")
    @patch("jujubackupall.utils.wait_for")
    def test_ran_with_no_timeout(self, mock_wait_for: Mock, mock_run_async: Mock, mock_globals: Mock):
        mock_coroutine = Mock()
        task = "some task"
        expected_result = "my result"
        timeout = 60

        mock_globals.async_timeout = timeout
        mock_run_async.return_value = expected_result

        actual_result = run_with_timeout(mock_coroutine, task)

        mock_wait_for.assert_called_once_with(mock_coroutine, timeout)
        self.assertEqual(actual_result, expected_result)

    @unittest.skip("reason: LP#1951914")
    @patch("jujubackupall.utils.run_async")
    @patch("jujubackupall.utils.wait_for")
    def test_ran_with_timeout(self, mock_wait_for: Mock, mock_run_async: Mock):
        mock_coroutine = Mock()
        task = "some task"

        mock_wait_for.side_effect = TimeoutError()

        with self.assertRaises(JujuTimeoutError) as context:
            run_with_timeout(mock_coroutine, task)

        self.assertIn(task, str(context.exception))


if __name__ == "__main__":
    unittest.main()
