RUN_IN_ENV=poetry run

.make:
	mkdir -p .make

.make/run-tests coverage.xml: .make/deps .make/test-deps |.make
	$(RUN_IN_ENV) pytest --cov-report xml

.make/deps: pyproject.toml | .make
	poetry install
	touch $@

.make/%-deps: pyproject.toml | .make
	poetry install --with $*
	touch $@

doc: .make/dev-deps 
	cd doc && poetry run make html

clean: .make/dev-deps
	cd doc && poetry run make clean

.PHONY: doc


