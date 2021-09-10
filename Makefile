FUNCTEST_VARS=PYTEST_KEEP_MODELS=$(PYTEST_KEEP_MODELS) \
			  PYTEST_MYSQL_MODEL=$(PYTEST_MYSQL_MODEL) \
			  PYTEST_PERCONA_MODEL=$(PYTEST_PERCONA_MODEL) \
			  PYTEST_ETCD_MODEL=$(PYTEST_ETCD_MODEL) \
			  JUJU_DATA=$(JUJU_DATA)

ifneq ($(PYTEST_SELECT_TESTS),)
	FUNCTEST_VARS+=PYTEST_SELECT_TESTS="$(PYTEST_SELECT_TESTS)"
endif
ifeq ($(JUJU_DATA),)
	JUJU_DATA=~/.local/share/juju
endif

functional:
		@echo Executing functional tests with: $(FUNCTEST_VARS) tox -e functional
		@echo Using JUJU_DATA=$(JUJU_DATA)
		@$(FUNCTEST_VARS) tox -e functional

unit:
		@echo Executing unit tests with coverage reports
		@tox -e unit

unit-coverage: unit
		@echo Generating html unit test coverage report
		@tox -e cover

install: venv
		@echo "Installing base requirements."
		( \
			. venv/bin/activate; \
			pip install --upgrade pip setuptools wheel; \
			pip install -r requirements.txt; \
		)

install-dev: install
		@echo "Grabbing requirements from requirements-dev, tests/unit, and tests/functional."
		( \
			. venv/bin/activate; \
			pip install \
				-r requirements-dev.txt \
				-r tests/functional/requirements.txt \
				-r tests/unit/requirements.txt; \
			python setup.py develop; \
		)


venv:
		@echo "Creating venv."
		@test -d venv || python3 -m venv venv

clean:
		@echo "Cleaning tox, eggs, caches, coverages, and juju-backups"
		@if [ -d .tox ] ; then rm -r .tox ; fi
		@if [ -d *.egg-info ] ; then rm -r *.egg-info ; fi
		@if [ -d .eggs ] ; then rm -r .eggs ; fi
		@if [ -d report ] ; then rm -r report ; fi
		@if [ -d .pytest_cache ] ; then rm -r .pytest_cache ; fi
		@if [ -d htmlcov ] ; then rm -r htmlcov ; fi
		@if [ -f .coverage ] ; then rm .coverage ; fi
		@if [ -d juju-backups ] ; then rm -r juju-backups ; fi
		@if [ -d build ] ; then rm -r build ; fi
		@find . -iname __pycache__ -exec rm -r {} +

lint:
		@tox -e lint

format:
		@tox -e format

build:
		@python setup.py build

snap:
		@echo "Building snap using lxd"
		@snapcraft --use-lxd

snap-clean:
		@echo "Cleaning up snap"
		@snapcraft clean --use-lxd

.PHONY: build clean format install install-dev lint snap snap-clean venv
