#!/usr/bin/python3
"""
Reusable pytest fixtures for functional testing.

Environment Variables
---------------------
test_preserve_model:
    if set, the testing model won't be torn down at the end of the testing session
"""
import asyncio
from collections import namedtuple
import os
import uuid

import pytest
from juju.application import Application
from juju.controller import Controller
from juju.model import Model
from juju.errors import JujuConnectionError


JujuModel = namedtuple('JujuModel', ['model_name', 'model'])


@pytest.fixture(scope="session")
def event_loop():
    """Override the default pytest event loop to allow for fixtures using a broader scope."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_debug(True)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture(scope='session', autouse=True)
async def controller():
    """Connect to the current controller."""
    controller = Controller()
    await controller.connect_current()
    yield controller
    await controller.disconnect()


@pytest.fixture(scope="session", autouse=True)
async def mysql_innodb_model(controller):
    """Return the MYSQL model for the test."""
    juju_model = await _get_or_create_model(controller, app_name='mysql', env_var='PYTEST_MYSQL_MODEL')
    yield juju_model
    await juju_model.model.disconnect()
    if not os.getenv("PYTEST_KEEP_MODELS"):
        await _cleanup_model(controller, juju_model.model_name)


@pytest.fixture(scope="session", autouse=True)
async def percona_cluster_model(controller):
    """Return the percona-cluster model for the test."""
    juju_model = await _get_or_create_model(controller, app_name='percona-cluster', env_var='PYTEST_PERCONA_MODEL')
    yield juju_model
    await juju_model.model.disconnect()
    if not os.getenv("PYTEST_KEEP_MODELS"):
        await _cleanup_model(controller, juju_model.model_name)


@pytest.fixture(scope="session", autouse=True)
async def etcd_model(controller):
    """Return the etcd model for the test."""
    juju_model = await _get_or_create_model(controller, app_name='etcd', env_var='PYTEST_ETCD_MODEL')
    yield juju_model
    await juju_model.model.disconnect()
    if not os.getenv("PYTEST_KEEP_MODELS"):
        await _cleanup_model(controller, juju_model.model_name)


@pytest.fixture(scope='module')
async def mysql_innodb_app(mysql_innodb_model):
    model = mysql_innodb_model.model
    mysql_innodb_app = model.applications.get('mysql')
    if mysql_innodb_app:
        return mysql_innodb_app
    mysql_innodb_app = await model.deploy(
        'cs:mysql-innodb-cluster',
        application_name='mysql',
        series='focal',
        channel='stable',
        num_units=3
    )
    await model.block_until(lambda: mysql_innodb_app.status == 'active')
    return mysql_innodb_app


@pytest.fixture(scope='module')
async def percona_cluster_app(percona_cluster_model: JujuModel):
    model = percona_cluster_model.model
    percona_cluster_app = model.applications.get('percona-cluster')
    if percona_cluster_app:
        return percona_cluster_app
    percona_cluster_app = await model.deploy(
        'cs:percona-cluster',
        application_name='percona-cluster',
        series='bionic',
        channel='stable',
        num_units=1
    )
    await model.block_until(lambda: percona_cluster_app.status == 'active')
    return percona_cluster_app


@pytest.fixture(scope='module')
async def etcd_app(etcd_model):
    model = etcd_model.model
    etcd_app: Application = model.applications.get('etcd')
    easyrsa_app: Application = model.applications.get('easyrsa')
    if not etcd_app:
        etcd_app = await model.deploy(
            'cs:etcd',
            application_name='etcd',
            series='focal',
            channel='stable',
            num_units=1
        )
    if not easyrsa_app:
        await model.deploy(
            'cs:~containers/easyrsa',
            application_name='easyrsa',
            series='focal',
            channel='stable',
            num_units=1
        )
    await etcd_app.add_relation(
        'certificates', 'easyrsa:client'
    )
    await model.block_until(lambda: etcd_app.status == 'active')
    return etcd_app


async def _get_or_create_model(controller, env_var, app_name):
    model_name = os.getenv(env_var)
    if model_name:
        # Reuse existing mysql model
        model = Model()
        full_name = "{}:{}".format(controller.controller_name, os.getenv(env_var))
        try:
            await model.connect(full_name)
        except JujuConnectionError:
            # Let's create it since it's missing
            model = await controller.add_model(
                model_name
            )
    else:
        # Create a new random model
        model_name = "functest-{}-{}".format(app_name, str(uuid.uuid4())[-12:])
        model = await controller.add_model(
            model_name
        )
    while model_name not in await controller.list_models():
        await asyncio.sleep(1)
    return JujuModel(model_name, model)


async def _cleanup_model(controller, model_name):
    await controller.destroy_model(model_name)
    while model_name in await controller.list_models():
        await asyncio.sleep(1)


@pytest.fixture(scope="module")
async def model_mixed(controller):
    pass
