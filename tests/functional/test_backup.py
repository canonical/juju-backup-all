# Copyright 2024 Canonical Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test juju-backup-all on multi-model controller"""

import glob
import json
import subprocess
from pathlib import Path

import pytest

WAIT_TIMEOUT = 20 * 60


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy(ops_test):
    """Deploy all applications."""

    await ops_test.model.deploy(
        "ch:mysql-innodb-cluster", application_name="mysql", series="jammy", channel="8.0/stable", num_units=3
    )
    await ops_test.model.deploy(
        "ch:postgresql", application_name="postgresql", series="jammy", channel="14/stable", num_units=1
    )
    await ops_test.model.deploy("ch:etcd", application_name="etcd", series="jammy", channel="stable", num_units=1)
    await ops_test.model.deploy("ch:easyrsa", application_name="easyrsa", series="jammy", channel="stable", num_units=1)
    await ops_test.model.relate("etcd:certificates", "easyrsa:client")

    await ops_test.model.wait_for_idle(timeout=WAIT_TIMEOUT, status="active", check_freq=3)


@pytest.mark.parametrize("backup_location", ["/var/backups/mysql", "/home/ubuntu/abc"])
def test_mysql_innodb_backup(backup_location, ops_test, tmp_path: Path):
    mysql_innodb_app_name = "mysql"
    model_name = ops_test.model.name
    controller_name = ops_test.controller_name
    mysql_innodb_app = ops_test.model.applications.get(mysql_innodb_app_name)

    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e etcd -e postgresql -x -j --backup-location-on-mysql {backup_location}",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / mysql_innodb_app_name
    app_backup_entry = output_dict.get("app_backups")[0]
    assert any(str(tmp_path) in x.get("download_path") for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("controller") == controller_name
    assert any(x.get("model") == model_name for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("charm") in mysql_innodb_app.data.get("charm-url")
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/mysqldump-all-databases*.gz")


@pytest.mark.parametrize("backup_location", ["/home/ubuntu", "/home/ubuntu/abc"])
def test_postgresql_backup(backup_location, ops_test, tmp_path: Path):
    postgresql_app_name = "postgresql"
    model_name = ops_test.model.name
    controller_name = ops_test.controller_name
    postgresql_app = ops_test.model.applications.get(postgresql_app_name)

    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e etcd -e mysql-innodb-cluster -x -j --backup-location-on-postgresql {backup_location}",
        shell=True,
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


@pytest.mark.parametrize("backup_location", ["/home/ubuntu/etcd-snapshots", "/home/ubuntu/abc"])
def test_etcd_backup(backup_location, ops_test, tmp_path: Path):
    etcd_app_name = "etcd"
    model_name = ops_test.model.name
    controller_name = ops_test.controller_name
    etcd_app = ops_test.model.applications.get(etcd_app_name)
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e mysql-innodb-cluster -e postgresql -x -j --backup-location-on-etcd {backup_location}",
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


def test_juju_controller_backup(ops_test, tmp_path: Path):
    controller_name = ops_test.controller_name
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e etcd -e mysql-innodb-cluster -e postgresql -j", shell=True
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name
    controller_backup_entry = output_dict.get("controller_backups")[0]
    assert str(tmp_path) in controller_backup_entry.get("download_path")
    assert controller_backup_entry.get("controller") == controller_name
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/juju-controller-backup*.gz")


def test_juju_client_config_backup(tmp_path: Path):
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e etcd -e mysql-innodb-cluster -e postgresql -x", shell=True
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / "local_configs"
    config_backup_entry = output_dict.get("config_backups")[0]
    assert str(tmp_path) in config_backup_entry.get("download_path")
    assert config_backup_entry.get("config") == "juju"
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/juju-*.gz")
