#!/usr/bin/python3
"""
Reusable pytest fixtures for functional testing.

Environment Variables
---------------------
test_preserve_model:
    if set, the testing model won't be torn down at the end of the testing session
"""
import asyncio
import os
import uuid
from collections import namedtuple

import pytest
from juju.application import Application
from juju.controller import Controller
from juju.errors import JujuConnectionError
from juju.model import Model

JujuModel = namedtuple("JujuModel", ["model_name", "model"])


@pytest.fixture(scope="session")
def event_loop():
    """Override the default pytest event loop to allow for fixtures using a broader scope."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_debug(True)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture(scope="session", autouse=True)
async def controller():
    """Connect to the current controller."""
    controller = Controller()
    await controller.connect_current()
    yield controller
    await controller.disconnect()


@pytest.fixture(scope="session", autouse=True)
async def models(controller):
    """Create all models and deploy each app in its respective model.

    Returns a dict containing all the models.

    This fixture is used in order to setup the models and applications
    in a concurrent manner at the start of the test session.

    Otherwise, if the setup for each model/application happens one after
    the other, it would take a long time and result in a timeout error.

    Therefore, the code for each application containing `model.block_until()`
    statements are separated out so that when the deployment for one
    model/application occurs, it doesn't block the deployment of the other
    ones.
    """
    # create models for each application
    mysql_innodb_model = await _get_or_create_model(controller, app_name="mysql", env_var="PYTEST_MYSQL_MODEL")
    postgresql_model = await _get_or_create_model(controller, app_name="postgresql", env_var="PYTEST_POSTGRESQL_MODEL")
    etcd_model = await _get_or_create_model(controller, app_name="etcd", env_var="PYTEST_ETCD_MODEL")

    models = {
        "mysql": mysql_innodb_model,
        "postgresql": postgresql_model,
        "etcd": etcd_model,
    }

    # try to fetch apps from their models
    mysql_innodb_app = models["mysql"].model.applications.get("mysql")
    postgresql_app = models["postgresql"].model.applications.get("postgresql")
    etcd_app = models["etcd"].model.applications.get("etcd")
    easyrsa_app = models["etcd"].model.applications.get("easyrsa")

    # deploy apps if they haven't been deployed previously
    if not mysql_innodb_app:
        await models["mysql"].model.deploy(
            "ch:mysql-innodb-cluster", application_name="mysql", series="focal", channel="stable", num_units=3
        )
    if not postgresql_app:
        await models["postgresql"].model.deploy(
            "ch:postgresql", application_name="postgresql", series="jammy", channel="14/stable", num_units=1
        )
    if not etcd_app:
        await models["etcd"].model.deploy(
            "ch:etcd", application_name="etcd", series="focal", channel="stable", num_units=1
        )
    if not easyrsa_app:
        await models["etcd"].model.deploy(
            "ch:easyrsa", application_name="easyrsa", series="focal", channel="stable", num_units=1
        )

    # return dict of all models
    yield models

    # cleanup
    for current_model in models.values():
        await current_model.model.disconnect()
    if not os.getenv("PYTEST_KEEP_MODELS"):
        for model in models.values():
            await _cleanup_model(controller, model.model_name)


@pytest.fixture
async def mysql_innodb_model(models):
    """
    Return the mysql innodb model. Also block execution until
    the mysql unit is active.
    """
    model = models["mysql"].model
    mysql_innodb_app = model.applications.get("mysql")
    await model.block_until(lambda: mysql_innodb_app.status == "active")
    return models["mysql"]


@pytest.fixture
async def postgresql_model(models):
    """
    Return the postgresql model. Also block execution until
    the postgresql unit is active.
    """
    model = models["postgresql"].model
    postgresql_app = model.applications.get("postgresql")
    await model.block_until(lambda: postgresql_app.status == "active")
    return models["postgresql"]


@pytest.fixture
async def etcd_model(models):
    """
    Return the etcd model. Also block execution until
    the etcd and easyrsa units are active.
    """
    model = models["etcd"].model
    etcd_app = model.applications.get("etcd")
    easyrsa_app = model.applications.get("easyrsa")
    await etcd_app.relate("certificates", "easyrsa:client")
    await model.block_until(lambda: etcd_app.status == "active")
    await model.block_until(lambda: easyrsa_app.status == "active")
    return models["etcd"]


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
            model = await controller.add_model(model_name)
    else:
        # Create a new random model
        model_name = "functest-{}-{}".format(app_name, str(uuid.uuid4())[-12:])
        model = await controller.add_model(model_name)
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
