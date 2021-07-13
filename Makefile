FUNCTEST_VARS=PYTEST_KEEP_MODELS=$(PYTEST_KEEP_MODELS) \
			  PYTEST_MYSQL_MODEL=$(PYTEST_MYSQL_MODEL)

ifneq ($(PYTEST_SELECT_TESTS),)
	FUNCTEST_VARS+=PYTEST_SELECT_TESTS="$(PYTESTS_SELECT_TESTS)"
endif

functional:
		@echo Executing functional tests with: $(FUNCTEST_VARS) tox -e functional
		@$(FUNCTEST_VARS) tox -e functional

venv:
		@echo "Creating venv. Grabbing requirements.txt from root, tests/unit and tests/functional"
		@test -d venv-all || python3 -m venv venv-all
		@. venv-all/bin/activate && pip install \
			-r requirements.txt \
			-r tests/functional/requirements.txt \
			-r tests/unit/requirements.txt

clean:
		@echo "Cleaning tox, report, and egg-infos"
		@if [ -d .tox ] ; then rm -r .tox ; fi
		@if [ -d *.egg-info ] ; then rm -r *.egg-info ; fi
		@if [ -d report ] ; then rm -r report ; fi
		@find . -iname __pycache__ -exec rm -r {} +
