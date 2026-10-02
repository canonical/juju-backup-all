# Copyright 2026 Canonical Limited
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

import base64
import glob
import json
import subprocess
import tempfile
from pathlib import Path

import jubilant
import pytest
from pytest_jubilant import JujuFactory

from jujubackupall import constants
from jujubackupall.utils import parse_charm_revision
from tests.functional.conftest import K8S_CLOUD, expose_via_loadbalancer, resolve_controller_name

WAIT_TIMEOUT = 30 * 60  # 30 minutes
LONG_WAIT_TIMEOUT = 90 * 60  # 90 minutes
K8S_WAIT_TIMEOUT = 20 * 60  # 20 minutes
MINIO_ACCESS_KEY = "ahs9ao#Fua"
MINIO_SECRET_KEY = "ohCa!uB6oo"


def get_supported_backup_charms_but(app):
    """Return the list of charms that support backup except the one provided."""
    if app not in constants.SUPPORTED_BACKUP_CHARMS and app != "":
        raise ValueError(f"{app} is not a supported backup charm.")
    return filter(lambda charm: charm != app, constants.SUPPORTED_BACKUP_CHARMS)


@pytest.fixture(scope="module")
def s3_secret_lxd(juju_lxd: jubilant.Juju):
    """Create LXD-model S3 credentials for integrators used by the test suite."""
    return juju_lxd.add_secret(
        "s3-credentials", {"access-key": MINIO_ACCESS_KEY, "secret-key": MINIO_SECRET_KEY}
    )


@pytest.mark.juju_setup
def test_deploy_k8s_cloud(k8s_host_juju: jubilant.Juju, request: pytest.FixtureRequest):
    """Deploy and configure the k8s charm, and register it as a Juju cloud."""
    k8s_host_juju.deploy(
        "k8s",
        channel="1.32/stable",
        base="ubuntu@24.04",
        constraints={
            "cores": "4",
            "mem": "16G",
            "root-disk": "100G",
            "virt-type": "virtual-machine",
        },
        config={
            "load-balancer-enabled": True,
            "local-storage-enabled": True,
        },
    )
    k8s_host_juju.wait(lambda status: jubilant.all_active(status, "k8s"), timeout=K8S_WAIT_TIMEOUT)

    k8s_unit_ip = k8s_host_juju.status().apps["k8s"].units["k8s/0"].public_address
    k8s_host_juju.config("k8s", {"load-balancer-cidrs": f"{k8s_unit_ip}/32"})

    kubeconfig = k8s_host_juju.ssh("k8s/0", "sudo k8s config")
    controller_name = resolve_controller_name(request)

    jubilant.Juju().cli(
        "add-k8s",
        K8S_CLOUD,
        "--controller",
        controller_name,
        include_model=False,
        stdin=kubeconfig,
    )


@pytest.mark.juju_setup
def test_build_and_deploy(
    juju_lxd: jubilant.Juju,
    juju_k8s: jubilant.Juju,
    k8s_host_juju: jubilant.Juju,
    s3_secret_lxd,
):
    """Deploy all applications."""
    # --- Minio S3 storage ---

    minio_credentials = {"access-key": MINIO_ACCESS_KEY, "secret-key": MINIO_SECRET_KEY}

    juju_k8s.deploy(
        "minio",
        channel="ckf-1.10/stable",
        trust=True,
        config=minio_credentials,
    )

    # --- Database Applications ---

    # Mysql InnoDB Cluster
    juju_lxd.deploy(
        "mysql-innodb-cluster",
        app="mysql-innodb",
        base="ubuntu@22.04",
        channel="8.0/stable",
        num_units=3,
    )

    # PostgreSQL
    juju_lxd.deploy(
        "postgresql",
        app="postgresql",
        base="ubuntu@22.04",
        channel="14/stable",
        num_units=1,
    )

    # MySQL
    juju_lxd.deploy(
        "mysql",
        app="mysql",
        base="ubuntu@22.04",
        channel="8.0/stable",
        num_units=3,
    )

    # MySQL K8s
    juju_k8s.deploy(
        "mysql-k8s",
        app="mysql-k8s",
        base="ubuntu@22.04",
        channel="8.0/stable",
        trust=True,
        num_units=3,
    )

    # MongoDB
    juju_lxd.deploy(
        "mongodb",
        app="mongodb",
        base="ubuntu@24.04",
        channel="8/stable",
        num_units=3,
    )

    # MongoDB K8s
    juju_k8s.deploy(
        "mongodb-k8s",
        app="mongodb-k8s",
        base="ubuntu@22.04",
        channel="6/stable",
        trust=True,
        num_units=3,
    )

    # ZooKeeper
    juju_lxd.deploy(
        "zookeeper",
        app="zookeeper",
        base="ubuntu@22.04",
        channel="3/stable",
        num_units=3,
    )

    # ZooKeeper K8s
    juju_k8s.deploy(
        "zookeeper-k8s",
        app="zookeeper-k8s",
        base="ubuntu@22.04",
        channel="3/stable",
        num_units=3,
    )

    # Etcd and EasyRSA for TLS certificates
    juju_lxd.deploy(
        "etcd",
        app="etcd",
        base="ubuntu@22.04",
        channel="stable",
        num_units=1,
    )
    juju_lxd.deploy(
        "easyrsa",
        app="easyrsa",
        base="ubuntu@22.04",
        channel="stable",
        num_units=1,
    )
    juju_lxd.integrate("etcd:certificates", "easyrsa:client")

    # --- Deploy s3-integrators and configure s3-credentials for charms ---

    juju_k8s.wait(lambda status: jubilant.all_active(status, "minio"), timeout=WAIT_TIMEOUT)

    minio_ip = expose_via_loadbalancer(k8s_host_juju, juju_k8s, "minio")
    s3_secret_k8s = juju_k8s.add_secret("s3-credentials", minio_credentials)
    for juju, secret, app in [
        (juju_lxd, s3_secret_lxd, "mysql"),
        (juju_lxd, s3_secret_lxd, "mongodb"),
        (juju_lxd, s3_secret_lxd, "postgresql"),
        (juju_lxd, s3_secret_lxd, "zookeeper"),
        (juju_k8s, s3_secret_k8s, "mysql-k8s"),
        (juju_k8s, s3_secret_k8s, "mongodb-k8s"),
        (juju_k8s, s3_secret_k8s, "zookeeper-k8s"),
    ]:
        juju.deploy(
            "s3-integrator",
            app=f"s3-integrator-{app}",
            channel="2/stable",
            config={
                "endpoint": f"http://{minio_ip}:9000",
                "bucket": f"{app}-backups",
                "region": "us-east-1",
                "s3-uri-style": "path",
            },
        )
        juju.integrate(app, f"s3-integrator-{app}")
        juju.grant_secret("s3-credentials", f"s3-integrator-{app}")
        juju.config(f"s3-integrator-{app}", {"credentials": secret})

    # --- Wait all to be ready ---

    juju_lxd.wait(
        lambda status: jubilant.all_active(
            status,
            "mysql-innodb",
            "mysql",
            "mongodb",
            "zookeeper",
            "etcd",
            "easyrsa",
            "s3-integrator-mysql",
            "s3-integrator-mongodb",
            "s3-integrator-zookeeper",
        ),
        error=jubilant.any_error,
        timeout=LONG_WAIT_TIMEOUT,
    )
    juju_k8s.wait(jubilant.all_active, error=jubilant.any_error, timeout=LONG_WAIT_TIMEOUT)


def _model_and_controller(juju: jubilant.Juju):
    model_status = juju.status().model
    return model_status.name, model_status.controller


@pytest.mark.parametrize("backup_location", ["/var/backups/mysql", "/home/ubuntu/abc"])
def test_mysql_innodb_backup(backup_location, juju_lxd: jubilant.Juju, tmp_path: Path):
    mysql_innodb_app_name = "mysql-innodb"
    model_name, controller_name = _model_and_controller(juju_lxd)
    mysql_innodb_app = juju_lxd.status().apps[mysql_innodb_app_name]

    exclude_opts = " -e ".join(get_supported_backup_charms_but("mysql-innodb-cluster"))
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x -j "
        f"--backup-location-on-mysql {backup_location}",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / mysql_innodb_app_name
    app_backup_entry = output_dict.get("app_backups")[0]
    assert any(str(tmp_path) in x.get("download_path") for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("controller") == controller_name
    assert any(x.get("model") == model_name for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("charm") in mysql_innodb_app.charm
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/mysqldump-all-databases*.gz")


def test_mysql_operator_backup(juju_lxd: jubilant.Juju, tmp_path: Path):
    mysql_app_name = "mysql"
    model_name, controller_name = _model_and_controller(juju_lxd)
    status = juju_lxd.status()
    mysql_app = status.apps.get(mysql_app_name)

    exclude_opts = " -e ".join(get_supported_backup_charms_but("mysql"))
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x -j ",
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
    assert app_backup_entry.get("charm") in mysql_app.charm
    assert expected_output_dir.exists()

    metadata_files = list(expected_output_dir.glob(f"{mysql_app_name}-backup-metadata-*.txt"))
    assert len(metadata_files) == 1
    assert metadata_files[0].read_text() != ""


def test_mongodb_operator_backup(juju_lxd: jubilant.Juju, tmp_path: Path):
    mongodb_app_name = "mongodb"
    model_name, controller_name = _model_and_controller(juju_lxd)
    status = juju_lxd.status()
    mongodb_app = status.apps.get(mongodb_app_name)

    exclude_opts = " -e ".join(get_supported_backup_charms_but(mongodb_app_name))
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x -j ",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / mongodb_app_name
    app_backup_entries = output_dict.get("app_backups")
    assert len(app_backup_entries) == 1
    app_backup_entry = app_backup_entries[0]
    assert str(tmp_path) in app_backup_entry.get("download_path")
    assert app_backup_entry.get("controller") == controller_name
    assert app_backup_entry.get("model") == model_name
    assert app_backup_entry.get("charm") in mongodb_app.charm
    assert expected_output_dir.exists()

    metadata_files = list(expected_output_dir.glob(f"{mongodb_app_name}-backup-metadata-*.txt"))
    assert len(metadata_files) == 1
    assert metadata_files[0].read_text() != ""


def test_mysql_k8s_operator_backup(juju_k8s: jubilant.Juju, tmp_path: Path):
    mysql_k8s_app_name = "mysql-k8s"
    model_name, controller_name = _model_and_controller(juju_k8s)
    status = juju_k8s.status()
    mysql_k8s_app = status.apps.get(mysql_k8s_app_name)

    exclude_opts = " -e ".join(get_supported_backup_charms_but("mysql-k8s"))
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x -j ",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / mysql_k8s_app_name
    app_backup_entries = output_dict.get("app_backups")
    assert len(app_backup_entries) == 1
    app_backup_entry = app_backup_entries[0]
    assert str(tmp_path) in app_backup_entry.get("download_path")
    assert app_backup_entry.get("controller") == controller_name
    assert app_backup_entry.get("model") == model_name
    assert app_backup_entry.get("charm") in mysql_k8s_app.charm
    assert expected_output_dir.exists()

    metadata_files = list(expected_output_dir.glob(f"{mysql_k8s_app_name}-backup-metadata-*.txt"))
    assert len(metadata_files) == 1
    assert metadata_files[0].read_text() != ""


def test_mongodb_k8s_operator_backup(juju_k8s: jubilant.Juju, tmp_path: Path):
    app_name = "mongodb-k8s"
    model_name, controller_name = _model_and_controller(juju_k8s)
    app = juju_k8s.status().apps[app_name]

    exclude_opts = " -e ".join(get_supported_backup_charms_but(app_name))
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x -j ",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / app_name
    app_backup_entries = output_dict.get("app_backups")
    assert len(app_backup_entries) == 1
    app_backup_entry = app_backup_entries[0]
    assert str(tmp_path) in app_backup_entry.get("download_path")
    assert app_backup_entry.get("controller") == controller_name
    assert app_backup_entry.get("model") == model_name
    assert app_backup_entry.get("charm") in app.charm
    assert expected_output_dir.exists()

    metadata_files = list(expected_output_dir.glob(f"{app_name}-backup-metadata-*.txt"))
    assert len(metadata_files) == 1
    assert metadata_files[0].read_text() != ""


def test_zookeeper_operator_backup(juju_lxd: jubilant.Juju, tmp_path: Path):
    zookeeper_app_name = "zookeeper"
    model_name, controller_name = _model_and_controller(juju_lxd)
    status = juju_lxd.status()
    zookeeper_app = status.apps.get(zookeeper_app_name)

    exclude_opts = " -e ".join(get_supported_backup_charms_but("zookeeper"))
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x -j ",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / zookeeper_app_name
    app_backup_entries = output_dict.get("app_backups")
    assert len(app_backup_entries) == 1
    app_backup_entry = app_backup_entries[0]
    assert str(tmp_path) in app_backup_entry.get("download_path")
    assert app_backup_entry.get("controller") == controller_name
    assert app_backup_entry.get("model") == model_name
    assert app_backup_entry.get("charm") in zookeeper_app.charm
    assert expected_output_dir.exists()

    metadata_files = list(expected_output_dir.glob(f"{zookeeper_app_name}-backup-metadata-*.txt"))
    assert len(metadata_files) == 1
    assert metadata_files[0].read_text() != ""


def test_zookeeper_k8s_operator_backup(juju_k8s: jubilant.Juju, tmp_path: Path):
    zookeeper_app_name = "zookeeper-k8s"
    model_name, controller_name = _model_and_controller(juju_k8s)
    status = juju_k8s.status()
    zookeeper_app = status.apps.get(zookeeper_app_name)

    exclude_opts = " -e ".join(get_supported_backup_charms_but("zookeeper-k8s"))
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x -j ",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / zookeeper_app_name
    app_backup_entries = output_dict.get("app_backups")
    assert len(app_backup_entries) == 1
    app_backup_entry = app_backup_entries[0]
    assert str(tmp_path) in app_backup_entry.get("download_path")
    assert app_backup_entry.get("controller") == controller_name
    assert app_backup_entry.get("model") == model_name
    assert app_backup_entry.get("charm") in zookeeper_app.charm
    assert expected_output_dir.exists()

    metadata_files = list(expected_output_dir.glob(f"{zookeeper_app_name}-backup-metadata-*.txt"))
    assert len(metadata_files) == 1
    assert metadata_files[0].read_text() != ""


@pytest.mark.parametrize("backup_location", ["/home/ubuntu/etcd-snapshots", "/home/ubuntu/abc"])
def test_etcd_backup(backup_location, juju_lxd: jubilant.Juju, tmp_path: Path):
    etcd_app_name = "etcd"
    model_name, controller_name = _model_and_controller(juju_lxd)
    etcd_app = juju_lxd.status().apps[etcd_app_name]

    exclude_opts = " -e ".join(get_supported_backup_charms_but("etcd"))
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x -j "
        f"--backup-location-on-etcd {backup_location}",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / etcd_app_name
    app_backup_entry = output_dict.get("app_backups")[0]
    assert any(str(tmp_path) in x.get("download_path") for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("controller") == controller_name
    assert any(x.get("model") == model_name for x in output_dict.get("app_backups"))
    assert app_backup_entry.get("charm") in etcd_app.charm
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/etcd-snapshot*.gz")


def test_juju_controller_backup(juju_lxd: jubilant.Juju, tmp_path: Path):
    _, controller_name = _model_and_controller(juju_lxd)

    exclude_opts = " -e ".join(get_supported_backup_charms_but(""))  # all charms are excluded
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -j ",
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
    exclude_opts = " -e ".join(get_supported_backup_charms_but(""))  # all charms are excluded
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x ",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / "local_configs"
    config_backup_entry = output_dict.get("config_backups")[0]
    assert str(tmp_path) in config_backup_entry.get("download_path")
    assert config_backup_entry.get("config") == "juju"
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + "/juju-*.gz")


# postgresql backup requires minio to be exposed via load balancer and SSL certificates
@pytest.mark.parametrize("backup_location", ["/home/ubuntu", "/home/ubuntu/abc"])
def test_postgresql_backup(
    backup_location,
    juju_lxd: jubilant.Juju,
    juju_k8s: jubilant.Juju,
    k8s_host_juju: jubilant.Juju,
    s3_secret_lxd,
    tmp_path: Path,
):
    postgresql_app_name = "postgresql"
    model_name, controller_name = _model_and_controller(juju_lxd)
    postgresql_app = juju_lxd.status().apps.get(postgresql_app_name)
    charm_revision = parse_charm_revision(postgresql_app.charm) or 0

    if charm_revision >= constants.POSTGRESQL_OPERATOR_MIN_REVISION:
        s3_integrator_app_name = "s3-integrator-postgresql-tls"
        if s3_integrator_app_name not in juju_lxd.status().apps:
            minio_ip = expose_via_loadbalancer(k8s_host_juju, juju_k8s, "minio")
            with tempfile.TemporaryDirectory() as cert_dir:
                cert_path = Path(cert_dir) / "minio.crt"
                key_path = Path(cert_dir) / "minio.key"
                subprocess.run(
                    [
                        "openssl",
                        "req",
                        "-x509",
                        "-newkey",
                        "rsa:2048",
                        "-nodes",
                        "-keyout",
                        str(key_path),
                        "-out",
                        str(cert_path),
                        "-days",
                        "365",
                        "-subj",
                        "/CN=minio.example.test",
                        "-addext",
                        f"subjectAltName=IP:{minio_ip}",
                    ],
                    check=True,
                )
                cert_base64 = base64.b64encode(cert_path.read_bytes()).decode("ascii")
                key_base64 = base64.b64encode(key_path.read_bytes()).decode("ascii")

            juju_k8s.config("minio", {"ssl-cert": cert_base64, "ssl-key": key_base64})
            juju_k8s.wait(
                lambda status: jubilant.all_active(status, "minio"), timeout=WAIT_TIMEOUT
            )
            juju_lxd.deploy(
                "s3-integrator",
                app=s3_integrator_app_name,
                channel="2/stable",
                config={
                    "endpoint": f"https://{minio_ip}:9000",
                    "bucket": "juju-backup-all-postgresql",
                    "path": "postgresql",
                    "region": "",
                    "s3-uri-style": "path",
                    "tls-ca-chain": cert_base64,
                },
            )
            juju_lxd.grant_secret("s3-credentials", s3_integrator_app_name)
            juju_lxd.config(s3_integrator_app_name, {"credentials": s3_secret_lxd})
            juju_lxd.integrate(postgresql_app_name, s3_integrator_app_name)

        juju_lxd.wait(
            lambda status: jubilant.all_active(
                status, postgresql_app_name, s3_integrator_app_name
            ),
            timeout=WAIT_TIMEOUT,
        )

    exclude_opts = " -e ".join(get_supported_backup_charms_but(postgresql_app_name))
    output = subprocess.check_output(
        f"juju-backup-all -o {tmp_path} -e {exclude_opts} -x -j "
        f"--backup-location-on-postgresql {backup_location}",
        shell=True,
    )
    output_dict = json.loads(output)
    expected_output_dir = tmp_path / controller_name / model_name / postgresql_app_name
    app_backup_entries = output_dict.get("app_backups")
    assert len(app_backup_entries) == 1
    app_backup_entry = app_backup_entries[0]
    assert str(tmp_path) in app_backup_entry.get("download_path")
    assert app_backup_entry.get("controller") == controller_name
    assert app_backup_entry.get("model") == model_name
    assert app_backup_entry.get("charm") in postgresql_app.charm
    assert expected_output_dir.exists()
    if charm_revision >= constants.POSTGRESQL_OPERATOR_MIN_REVISION:
        metadata_files = list(expected_output_dir.glob("postgresql-backup-metadata-*.json"))
        assert len(metadata_files) == 1
        metadata = json.loads(metadata_files[0].read_text())
        assert metadata.get("backup-status") == "backup created"
    else:
        assert glob.glob(str(expected_output_dir) + "/pgdump-all-databases*.gz")


@pytest.mark.juju_teardown
def test_remove_k8s_cloud(
    juju_factory: JujuFactory,
    juju_k8s: jubilant.Juju,
    request: pytest.FixtureRequest,
):
    """Destroy the k8s model, then unregister the k8s cloud created for this test session.

    The k8s model must be destroyed before the cloud is unregistered, since the cloud
    can't be removed while a model is still deployed on it. We destroy it explicitly here
    (rather than relying on juju_factory's own teardown, which only runs after this test
    completes) and drop it from juju_factory's tracked models so its teardown doesn't try
    to destroy it a second time, which would raise and abort destruction of the remaining
    models (juju_lxd, k8s_host_juju).
    """
    model_name = juju_k8s.model
    assert model_name is not None
    juju_k8s.destroy_model(model_name, destroy_storage=True, force=True)

    # Reach into juju_factory's private state to prevent it from re-destroying this model.
    juju_factory._models.pop(model_name, None)  # pyright: ignore[reportPrivateUsage]

    controller_name = resolve_controller_name(request)
    try:
        jubilant.Juju().cli(
            "remove-k8s", K8S_CLOUD, "--controller", controller_name, include_model=False
        )
    except jubilant.CLIError as e:
        raise RuntimeError(f"Failed to remove k8s cloud: {e.stderr}") from e
