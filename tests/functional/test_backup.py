"""Test juju-backup-all on multi-model controller"""
import glob
import json
import subprocess
from pathlib import Path

import pytest
from conftest import JujuModel
from juju.application import Application
from juju.controller import Controller


async def test_mysql_innodb_backup(mysql_innodb_model: JujuModel, tmp_path: Path, controller: Controller):
    model_name = mysql_innodb_model.model_name
    controller_name = controller.controller_name
    mysql_innodb_app = mysql_innodb_model.model.applications.get("mysql")
    mysql_innodb_app_name = "mysql"
    output = subprocess.check_output("juju-backup-all -o {} -e etcd -e postgresql -x -j".format(tmp_path), shell=True)
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / mysql_innodb_app_name
    app_backup_entry = output_dict.get("app_backups")[0]
    assert any(str(tmp_path) in x.get("download_path") for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("controller") == controller_name
    assert any(x.get("model") == model_name for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("charm") in mysql_innodb_app.data.get("charm-url")
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/mysqldump-all-databases*.gz")


async def test_postgresql_backup(postgresql_model: JujuModel, tmp_path: Path, controller: Controller):
    model_name = postgresql_model.model_name
    controller_name = controller.controller_name
    postgresql_app = postgresql_model.model.applications.get("postgresql")
    postgresql_app_name = "postgresql"
    output = subprocess.check_output(
        "juju-backup-all -o {} -e etcd -e mysql-innodb-cluster -x -j".format(tmp_path), shell=True
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / postgresql_app_name
    app_backup_entry = output_dict.get("app_backups")[0]
    assert any(str(tmp_path) in x.get("download_path") for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("controller") == controller_name
    assert any(x.get("model") == model_name for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("charm") in postgresql_app.data.get("charm-url")
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/pgdump-all-databases*.gz")


async def test_juju_controller_backup(tmp_path: Path, controller: Controller):
    output = subprocess.check_output(
        "juju-backup-all -o {} -e etcd -e mysql-innodb-cluster -e postgresql -j".format(tmp_path),
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller.controller_name
    controller_backup_entry = output_dict.get("controller_backups")[0]
    assert str(tmp_path) in controller_backup_entry.get("download_path")
    assert controller_backup_entry.get("controller") == controller.controller_name
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/juju-controller-backup*.gz")


async def test_juju_client_config_backup(tmp_path: Path):
    output = subprocess.check_output(
        "juju-backup-all -o {} -e etcd -e mysql-innodb-cluster -e postgresql -x".format(tmp_path),
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / "local_configs"
    config_backup_entry = output_dict.get("config_backups")[0]
    assert str(tmp_path) in config_backup_entry.get("download_path")
    assert config_backup_entry.get("config") == "juju"
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/juju-*.gz")


async def test_etcd_backup(etcd_model: JujuModel, tmp_path: Path, controller: Controller):
    model_name = etcd_model.model_name
    controller_name = controller.controller_name
    etcd_app: Application = etcd_model.model.applications.get("etcd")
    etcd_app_name = "etcd"
    output = subprocess.check_output(
        "juju-backup-all -o {} -e mysql-innodb-cluster -e postgresql -x -j".format(tmp_path),
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / etcd_app_name
    app_backup_entry = output_dict.get("app_backups")[0]
    assert any(str(tmp_path) in x.get("download_path") for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("controller") == controller_name
    assert any(x.get("model") == model_name for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("charm") in etcd_app.data.get("charm-url")
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/etcd-snapshot*.gz")
