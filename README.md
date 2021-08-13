# Juju Backup-All-the-Things

## Introduction

This Juju plugin allows operators to backup juju controllers as well as the following charms:
- [MySQL Innodb Cluster](https://charmhub.io/mysql-innodb-cluster)
- [Percona Cluster](https://charmhub.io/percona-cluster)
- [PostgreSQL](https://charmhub.io/postgresql)
- [etcd](https://charmhub.io/etcd)

The plugin enumerates through all controllers, backing up the controller and scanning through each model for any 
applications that can be backed up. It then saves these backups 

## Usage

## Development and Testing

To set up development environment:

```bash
make venv
. venv-all/bin/activate
```

To run functional tests:

```bash
make functional
```

or

```bash
tox -e functional
```

## Building and Installing Snap Locally

To build the snap locally, simply run:

```bash
make snap
```

You can then install the locally built snap with:

```bash
sudo snap install --classic --dangerous ./juju-backup-all_${VERSION}.snap
```

To clean up the snapcraft build environment, run the following:

```bash
make snap-clean
```
