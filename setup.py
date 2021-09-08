from setuptools import find_packages, setup

setup(
    name="juju-backup-all",
    author="Canonical",
    description="Automatic discovery backup tool for charms, controllers, and configs",
    url="https://launchpad.net/juju-backup-all",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    packages=find_packages(),
    entry_points={"console_scripts": ["juju-backup-all = jujubackupall.cli:main"]},
)
