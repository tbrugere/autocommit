RUN_IN_ENV=poetry run

.make:
	mkdir -p .make

.make/run-tests .coverage: .make/deps .make/test-deps |.make
	$(RUN_IN_ENV) pytest

coverage.xml: .make/run-tests
	$(RUN_IN_ENV) coverage xml

.make/deps: pyproject.toml | .make
	poetry install
	touch $@

.make/%-deps: pyproject.toml | .make
	poetry install --with $*
	touch $@

doc: .make/dev-deps 
	cd docs && poetry run make html

clean: .make/dev-deps
	cd docs && poetry run make clean

.PHONY: doc


