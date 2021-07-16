"""Test backup-all-the-things on multi-model controller"""
import asyncio
import glob
from pathlib import Path
import subprocess

import pytest
from juju.model import Model
from juju.application import Application
from juju.controller import Controller
from juju.unit import Unit

from conftest import JujuModel

pytestmark = [pytest.mark.asyncio]


async def test_sanity_deployment(mysql_innodb_app: Application, percona_cluster_app: Application,):
    assert mysql_innodb_app.status == 'active'
    assert percona_cluster_app.status == 'active'


async def test_mysql_innodb_backup(mysql_innodb_model: JujuModel, tmp_path: Path, controller: Controller):
    model_name, model = mysql_innodb_model.model_name, mysql_innodb_model.model
    controller_name = controller.controller_name
    mysql_innodb_app_name = 'mysql'
    output = subprocess.check_output(
        'juju-backup-all --output-dir {} -C {} -c mysql-innodb-cluster'.format(tmp_path, controller_name),
        shell=True
    )
    expected_output_dir = (tmp_path / controller_name / model_name / mysql_innodb_app_name)
    assert str(tmp_path) in str(output)
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + '/mysqldump-all-databases*.gz')


async def test_percona_backup(percona_cluster_model: JujuModel, percona_cluster_app: Application,
                              tmp_path: Path, controller: Controller):
    model_name, model = percona_cluster_model.model_name, percona_cluster_model.model
    controller_name = controller.controller_name
    percona_app_name = 'percona-cluster'
    output = subprocess.check_output(
        'juju-backup-all --output-dir {} -C {} -c percona-cluster'.format(tmp_path, controller_name),
        shell=True
    )
    expected_output_dir = (tmp_path / controller_name / model_name / percona_app_name)
    assert str(tmp_path) in str(output)
    assert expected_output_dir.exists()
    assert glob.glob(str(expected_output_dir) + '/mysqldump-all-databases*.gz'.format(percona_app_name))
