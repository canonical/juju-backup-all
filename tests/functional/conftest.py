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

"""Shared fixtures for the juju-backup-all functional test suite.

This module provides Juju contexts for the two clouds used by the test suite:

- juju_lxd: the default lxd/machine cloud, used to host machine charms to be tested
- juju_k8s: the k8s cloud backed by a machine-deployed k8s charm, used to host MinIO
- k8s_host_juju: the secondary lxd/machine cloud, used to host the k8s charm that provides the k8s
                 cloud for juju_k8s
"""

import json

import jubilant
import pytest
from pytest_jubilant import JujuFactory

K8S_CLOUD = "jba-k8s-cloud"


def _resolve_lxd_cloud(request: pytest.FixtureRequest) -> str:
    """Return the lxd cloud name to use for the test suite.

    If --juju-cloud is given, use that. Otherwise, use the default lxd cloud.
    """
    return request.config.getoption("--juju-cloud") or "localhost"


@pytest.fixture(scope="module")
def k8s_host_juju(juju_factory: JujuFactory, request: pytest.FixtureRequest) -> jubilant.Juju:
    """Juju bound to the model hosting the ``k8s`` charm.

    That charm provides our Kubernetes cloud.
    """
    return juju_factory.get_juju("k8s-host", cloud=_resolve_lxd_cloud(request))


@pytest.fixture(scope="module")
def juju_lxd(juju_factory: JujuFactory, request: pytest.FixtureRequest) -> jubilant.Juju:
    """Juju bound to a model on the lxd/machine cloud.

    Used for machine charms (mysql-innodb-cluster, mysql, postgresql, etcd,
    easyrsa, s3-integrator-*).
    """
    return juju_factory.get_juju("lxd", cloud=_resolve_lxd_cloud(request))


@pytest.fixture(scope="module")
def juju_k8s(juju_factory: JujuFactory) -> jubilant.Juju:
    """Juju bound to a model on the registered k8s cloud, for k8s charms (minio)."""
    return juju_factory.get_juju("k8s", cloud=K8S_CLOUD)


def expose_via_loadbalancer(
    k8s_host_juju: jubilant.Juju, juju_k8s: jubilant.Juju, app: str
) -> str:
    """Patch ``app``'s Kubernetes Service to type LoadBalancer.

    Returns its external IP address once assigned. Runs ``kubectl`` over SSH via
    the model hosting the ``k8s`` charm.
    """
    assert juju_k8s.model is not None
    model = juju_k8s.model.rpartition(":")[-1]
    k8s_host_juju.ssh(
        "k8s/0",
        "sudo k8s kubectl",
        f"-n {model} patch svc {app}",
        '-p \'{"spec": {"type": "LoadBalancer"}}\'',
    )
    k8s_host_juju.ssh(
        "k8s/0",
        "sudo k8s kubectl",
        f"-n {model} wait svc {app}",
        "--for=jsonpath='{.status.loadBalancer.ingress[0].ip}'",
        "--timeout=5m",
    )
    return k8s_host_juju.ssh(
        "k8s/0",
        "sudo k8s kubectl",
        f"-n {model} get svc {app}",
        "-o",
        "jsonpath='{.status.loadBalancer.ingress[0].ip}'",
    ).strip()


def expose_via_nodeport(
    k8s_host_juju: jubilant.Juju, juju_k8s: jubilant.Juju, app: str, port: int
) -> int:
    """Patch ``app``'s Kubernetes Service to type NodePort.

    Returns the node port mapped to ``port``, reachable on the ``k8s`` unit's address. Use this
    when the single LoadBalancer IP is already taken. Runs ``kubectl`` over SSH via the model
    hosting the ``k8s`` charm.
    """
    assert juju_k8s.model is not None
    model = juju_k8s.model.rpartition(":")[-1]
    k8s_host_juju.ssh(
        "k8s/0",
        "sudo k8s kubectl",
        f"-n {model} patch svc {app}",
        '-p \'{"spec": {"type": "NodePort"}}\'',
    )
    return int(
        k8s_host_juju.ssh(
            "k8s/0",
            "sudo k8s kubectl",
            f"-n {model} get svc {app}",
            "-o",
            f"jsonpath='{{.spec.ports[?(@.port=={port})].nodePort}}'",
        ).strip()
    )


def resolve_controller_name(request: pytest.FixtureRequest) -> str:
    """Return --juju-controller if given, else the currently active controller."""
    juju = jubilant.Juju()
    controllers = json.loads(juju.cli("controllers", "--format", "json", include_model=False))
    current_controller = controllers.get("current-controller")

    controller = request.config.getoption("--juju-controller")
    return controller or current_controller
