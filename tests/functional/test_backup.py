"""Test backup-all-the-things on multi-model controller"""
import asyncio
import subprocess

import pytest
from juju.model import Model

pytestmark = [pytest.mark.asyncio]


@pytest.fixture
async def mysql_innodb_app(model_mysql_innodb: Model):
    mysql_innodb_app = model_mysql_innodb.applications.get('mysql')
    if mysql_innodb_app:
        return mysql_innodb_app
    mysql_innodb_app = await model_mysql_innodb.deploy(
        'cs:mysql-innodb-cluster',
        application_name='mysql',
        series='focal',
        channel='stable',
        num_units=3
    )
    await model_mysql_innodb.block_until(lambda: mysql_innodb_app.status == 'active')
    return mysql_innodb_app


async def test_mysql_innodb_backup(model_mysql_innodb, mysql_innodb_app):
    assert mysql_innodb_app.status == 'active'
