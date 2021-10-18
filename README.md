# Juju Backup-All-the-Things

## Introduction

This Juju plugin allows operators to backup juju controllers as well as the following charms:
- [MySQL Innodb Cluster](https://charmhub.io/mysql-innodb-cluster)
- [Percona Cluster](https://charmhub.io/percona-cluster)
- [PostgreSQL](https://charmhub.io/postgresql)
- [etcd](https://charmhub.io/etcd)

The plugin enumerates through all controllers, backing up the controller and scanning through each model for any
applications that can be backed up. It then saves these backups.

Find it on the Snap Store!

<a href="https://snapcraft.io/juju-backup-all" title="Get it from the Snap Store">
    <img src="https://snapcraft.io/static/images/badges/en/snap-store-black.svg" alt="Get it from the Snap Store" width="200" />
</a>

## Install

Install juju-backup-all from Snap Store with:

```bash
snap install juju-backup-all
```

Then, make sure the appropriate interfaces are plugged:

```bash
snap connect juju-backup-all:juju-client-observe
snap connect juju-backup-all:ssh-keys
```

## Usage

This tool primarily auto-discovers controllers/charms that need backing up. To backup the current controller, simply run:

```bash
juju-backup-all
```

This will backup all apps of all models (in the current controller) of supported charms and output them into
`juju-backups/` directory. It will also backup the local juju client config.

For a more complex command, here's an example that specifies an output directory, excludes certain charms, excludes the
juju client config backup, and runs backups on all controllers.

```bash
juju-backup-all -o my/backups/ \
  -e postgresql \
  -e etcd \
  --all-controllers
```

The following command will give all the possible arguments that can be passed to the tool:

```bash
juju-backup-all -h
```

The backup directory structure will look like the following:

```bash
juju-backups/
├── local_configs/
│   └── juju.tar.gz
├── controller1/
│   ├── model1/
│   │   ├── mysql-innodb-cluster/
│   │   │   └── mysqldump.tar.gz
│   │   └── percona-cluster-app/
│   │       └── mysqldump.tar.gz
│   └── model2/
│       └── percona-cluster-app/
│           └── mysqldump.tar.gz
└── controller2/
    └── model1/
        └── etcd-app/
            └── backups.tar.gz
```

## Development and Testing

To set up development environment:

```bash
make install-dev
. venv/bin/activate

# if pre-commit hooks desired:
pre-commit install
```

### Functional tests

To run functional tests:

```bash
make functional
```

or

```bash
tox -e functional
```

Several environment variables are available for setting to help expedite testing.
These include:

- `PYTEST_KEEP_MODELS`: keeps the models after running functional tests. This helps in debugging and reuse of models
for quicker testing
- `PYTEST_MYSQL_MODEL`, `PYTEST_PERCONA_MODEL`, `PYTEST_ETCD_MODEL`: setting these to a current model will have the functional tests use
that model instead of deploying another one.
- `JUJU_DATA`: Specify where your juju client config directory is located. If not set, it will default to
`~/.local/share/juju`. This is needed in functional testing as the tool runs some subprocess `juju` commands
(like `juju create-backup`) and without this set, the environment for functional tests has no info on controllers.
- `PYTEST_SELECT_TESTS`: use to select tests based on their name (via
[pytest `-k` expression docs](https://docs.pytest.org/en/latest/example/markers.html#using-k-expr-to-select-tests-based-on-their-name))

### Unit tests

To run unit tests:

```bash
make unit
```

To run unit tests and also generate html coverage reports:

```bash
make unit-coverage
```

## Building and Installing Snap Locally

To build the snap locally, simply run:

```bash
make snap
```

You can then install the locally built snap with:

```bash
sudo snap install --dangerous ./juju-backup-all_${VERSION}.snap
```

To clean up the snapcraft build environment, run the following:

```bash
make snap-clean
```
