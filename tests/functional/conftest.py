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

import pytest
from juju.controller import Controller
from juju.model import Model
from juju.errors import JujuConnectionError


@pytest.fixture(scope="module")
def event_loop():
    """Override the default pytest event loop to allow for fixtures using a broader scope."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_debug(True)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture(scope='module')
async def controller():
    """Connect to the current controller."""
    controller = Controller()
    await controller.connect_current()
    yield controller
    await controller.disconnect()


@pytest.fixture(scope="module")
async def model_mysql_innodb(controller):
    """Return the model for the test."""
    model_name = os.getenv("PYTEST_MYSQL_MODEL")
    if model_name:
        # Reuse existing mysql model
        model = Model()
        full_name = "{}:{}".format(controller.controller_name, os.getenv("PYTEST_MYSQL_MODEL"))
        try:
            await model.connect(full_name)
        except JujuConnectionError:
            # Let's create it since it's missing
            model = await controller.add_model(
                model_name
            )
    else:
        # Create a new random model
        model_name = "functest-mysql-{}".format(str(uuid.uuid4())[-12:])
        model = await controller.add_model(
            model_name
        )
    while model_name not in await controller.list_models():
        await asyncio.sleep(1)
    yield model
    await model.disconnect()
    if not os.getenv("PYTEST_KEEP_MODELS"):
        await controller.destroy_model(model_name)
        while model_name in await controller.list_models():
            await asyncio.sleep(1)


@pytest.fixture(scope="module")
async def model_postgresql(controller):
    pass


@pytest.fixture(scope="module")
async def model_mixed(controller):
    pass