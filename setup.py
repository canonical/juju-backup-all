from setuptools import setup, find_packages

setup(
    packages=find_packages(),
    entry_points={
        'console_scripts': ['juju-backup-all = jujubackupall.cli:main']
    }
)
