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

"""Test juju-backup-all on multi-model controller."""

import glob
import json
import os
import subprocess
from pathlib import Path

import pytest

from jujubackupall.utils import parse_charm_name

WAIT_TIMEOUT = 20 * 60
K8S_HOST_MODEL = "juju-backup-all-k8s-host-model"
K8S_CLOUD = "juju-backup-all-k8s-cloud"
MINIO_MODEL = "juju-backup-all-minio-model"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin123"
S3_INTEGRATOR_CONFIG_ENVIRONMENT_VARIABLES = (
    "S3_INTEGRATOR_ENDPOINT",
    "S3_INTEGRATOR_BUCKET",
    "S3_INTEGRATOR_PATH",
    "S3_INTEGRATOR_ACCESS_KEY",
    "S3_INTEGRATOR_SECRET_KEY",
)


def run_command(command: str) -> str:
    return subprocess.check_output(command, shell=True, text=True)


def k8s_cloud_available() -> bool:
    try:
        clouds_output = run_command("juju clouds --format=json")
    except subprocess.CalledProcessError:
        return False
    clouds = json.loads(clouds_output).get("clouds", {})
    return K8S_CLOUD in clouds


def configure_minio_for_mysql_backups():
    if get_s3_integrator_config() or not k8s_cloud_available():
        return

    run_command(f'juju add-model "{MINIO_MODEL}" "{K8S_CLOUD}"')
    run_command(
        f'juju deploy minio -m "{MINIO_MODEL}" '
        "--channel=ckf-1.10/stable "
        "--trust "
        f'--config="access-key={MINIO_ACCESS_KEY}" '
        f'--config="secret-key={MINIO_SECRET_KEY}"'
    )
    run_command(
        f'juju wait-for application -m "{MINIO_MODEL}" minio '
        '--query=\'name=="minio" && (status=="active" || status=="idle")\' '
        "--timeout=20m"
    )

    k8s_status = json.loads(run_command(f'juju status -m "{K8S_HOST_MODEL}" --format=json'))
    load_balancer_cidrs = " ".join(
        f"{machine['ip-addresses'][0]}/32"
        for machine in k8s_status.get("machines", {}).values()
        if machine.get("ip-addresses")
    )
    run_command(
        f'juju config k8s -m "{K8S_HOST_MODEL}" '
        "load-balancer-enabled=true local-storage-enabled=true "
        f'load-balancer-cidrs="{load_balancer_cidrs}"'
    )
    run_command(
        f'juju ssh -m "{K8S_HOST_MODEL}" k8s/0 -- '
        f'sudo k8s kubectl -n "{MINIO_MODEL}" patch svc minio '
        '-p \'{"spec": {"type": "LoadBalancer"}}\''
    )
    run_command(
        f'juju ssh -m "{K8S_HOST_MODEL}" k8s/0 -- sudo k8s kubectl wait '
        f"--for=jsonpath='{{.status.loadBalancer.ingress[0].ip}}' "
        f'service/minio -n "{MINIO_MODEL}" --timeout=5m'
    )

    load_balancer_ip = run_command(
        f'juju ssh -m "{K8S_HOST_MODEL}" k8s/0 -- '
        f'"sudo k8s kubectl -n {MINIO_MODEL} get service minio '
        "-o jsonpath='{.status.loadBalancer.ingress[0].ip}'"
    ).strip()

    os.environ.update(
        {
            "S3_INTEGRATOR_ENDPOINT": f"http://{load_balancer_ip}:9000",
            "S3_INTEGRATOR_BUCKET": MINIO_MODEL,
            "S3_INTEGRATOR_PATH": f"/{MINIO_MODEL}/mysql",
            "S3_INTEGRATOR_ACCESS_KEY": MINIO_ACCESS_KEY,
            "S3_INTEGRATOR_SECRET_KEY": MINIO_SECRET_KEY,
        }
    )


def get_s3_integrator_config():
    missing_variables = [
        variable
        for variable in S3_INTEGRATOR_CONFIG_ENVIRONMENT_VARIABLES
        if not os.environ.get(variable)
    ]
    if missing_variables:
        return None
    return {
        "endpoint": os.environ["S3_INTEGRATOR_ENDPOINT"],
        "bucket": os.environ["S3_INTEGRATOR_BUCKET"],
        "path": os.environ["S3_INTEGRATOR_PATH"],
        "region": "us-east-1",
        "s3-uri-style": "path",
    }


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy(ops_test):
    """Deploy all applications."""
    configure_minio_for_mysql_backups()

    await ops_test.model.deploy(
        "ch:mysql-innodb-cluster",
        application_name="mysqlinnodb",
        series="jammy",
        channel="8.0/stable",
        num_units=3,
    )
    s3_integrator_config = get_s3_integrator_config()
    if s3_integrator_config:
        await ops_test.model.deploy(
            "ch:mysql",
            application_name="mysql",
            series="jammy",
            channel="8.0/stable",
            num_units=3,
        )
        s3_integrator = await ops_test.model.deploy("ch:s3-integrator", channel="2/stable")
        await ops_test.model.wait_for_idle(
            apps=["s3-integrator"], timeout=WAIT_TIMEOUT, check_freq=3
        )
        action = await s3_integrator.units[0].run_action(
            "sync-s3-credentials",
            **{
                "access-key": os.environ["S3_INTEGRATOR_ACCESS_KEY"],
                "secret-key": os.environ["S3_INTEGRATOR_SECRET_KEY"],
            },
        )
        await action.wait()
        await s3_integrator.set_config(s3_integrator_config)
        await ops_test.model.relate("mysql", "s3-integrator")
    await ops_test.model.deploy(
        "ch:postgresql",
        application_name="postgresql",
        series="jammy",
        channel="14/stable",
        num_units=1,
    )
    await ops_test.model.deploy(
        "ch:etcd", application_name="etcd", series="jammy", channel="stable", num_units=1
    )
    await ops_test.model.deploy(
        "ch:easyrsa", application_name="easyrsa", series="jammy", channel="stable", num_units=1
    )
    await ops_test.model.relate("etcd:certificates", "easyrsa:client")

    await ops_test.model.wait_for_idle(timeout=WAIT_TIMEOUT, status="active", check_freq=3)


@pytest.mark.parametrize("backup_location", ["/var/backups/mysql", "/home/ubuntu/abc"])
def test_mysql_innodb_backup(backup_location, ops_test, tmp_path: Path):
    mysql_innodb_app_name = "mysqlinnodb"
    model_name = ops_test.model.name
    controller_name = ops_test.controller_name
    mysql_innodb_app = ops_test.model.applications.get(mysql_innodb_app_name)

    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e etcd -e mysql -e postgresql -x -j --backup-location-on-mysql {backup_location}",
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


def test_mysql_operator_backup(ops_test, tmp_path: Path):
    if not get_s3_integrator_config():
        pytest.skip("requires S3_INTEGRATOR_* environment variables")
    mysql_app_name = "mysql"
    model_name = ops_test.model.name
    controller_name = ops_test.controller_name
    mysql_app = ops_test.model.applications.get(mysql_app_name)
    charm_name = parse_charm_name(mysql_app.data.get("charm-url"))
    if charm_name != "mysql":
        pytest.skip("requires a configured ch:mysql application")

    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e etcd -e mysql-innodb-cluster -e postgresql -x -j",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / mysql_app_name
    app_backup_entries = output_dict.get("app_backups")
    assert len(app_backup_entries) == 1
    app_backup_entry = app_backup_entries[0]
    assert str(tmp_path) in app_backup_entry.get("download_path")
    assert app_backup_entry.get("controller") == controller_name
    assert app_backup_entry.get("model") == model_name
    assert app_backup_entry.get("charm") in mysql_app.data.get("charm-url")
    assert expected_output_dir.exists()

    metadata_files = list(expected_output_dir.glob("mysql-backup-metadata-*.json"))
    assert len(metadata_files) == 1
    metadata = json.loads(metadata_files[0].read_text())
    assert metadata.get("backup-id")
    assert metadata.get("return-code") == 0


@pytest.mark.parametrize("backup_location", ["/home/ubuntu", "/home/ubuntu/abc"])
def test_postgresql_backup(backup_location, ops_test, tmp_path: Path):
    postgresql_app_name = "postgresql"
    model_name = ops_test.model.name
    controller_name = ops_test.controller_name
    postgresql_app = ops_test.model.applications.get(postgresql_app_name)

    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e etcd -e mysql -e mysql-innodb-cluster -x -j --backup-location-on-postgresql {backup_location}",
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
        f"juju-backup-all -o {tmp_path} -e mysql -e mysql-innodb-cluster -e postgresql -x -j --backup-location-on-etcd {backup_location}",
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
        f"juju-backup-all -o {tmp_path} -e etcd -e mysql -e mysql-innodb-cluster -e postgresql -j",
        shell=True,
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
        f"juju-backup-all -o {tmp_path} -e etcd -e mysql -e mysql-innodb-cluster -e postgresql -x",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / "local_configs"
    config_backup_entry = output_dict.get("config_backups")[0]
    assert str(tmp_path) in config_backup_entry.get("download_path")
    assert config_backup_entry.get("config") == "juju"
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/juju-*.gz")
