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

unit-html-report: unit
		@echo Generating html unit test coverage report
		@tox -e htmlreport

venv:
		@echo "Creating venv. Grabbing requirements.txt from root, tests/unit and tests/functional"
		@test -d venv-all || python3 -m venv venv-all
		@. venv-all/bin/activate && pip install \
			-r requirements.txt \
			-r tests/functional/requirements.txt \
			-r tests/unit/requirements.txt

lint-report:
		@tox -e lintreport

lint:
		@tox -e lint

clean:
		@echo "Cleaning tox, report, and egg-infos"
		@if [ -d .tox ] ; then rm -r .tox ; fi
		@if [ -d *.egg-info ] ; then rm -r *.egg-info ; fi
		@if [ -d report ] ; then rm -r report ; fi
		@find . -iname __pycache__ -exec rm -r {} +

black-check:
		@tox -e blackcheck

snap:
		@echo "Building snap using lxd"
		@snapcraft --use-lxd

snap-clean:
		@echo "Cleaning up snap"
		@snapcraft clean --use-lxd

.PHONY: snap
