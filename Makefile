# Artifact reproduction entry points.
#
# Requires GNU make and Python 3 with the bundled requirements installed.
# On machines without make, run the commands directly:
#   python code/reproduction/build_tables.py     # == make tables
#   python code/reproduction/smoke_test.py       # == make smoke-test

PYTHON ?= python

.PHONY: tables smoke-test all

all: tables smoke-test

tables:
	$(PYTHON) code/reproduction/build_tables.py

smoke-test:
	$(PYTHON) code/reproduction/smoke_test.py

inject:
	$(PYTHON) code/reproduction/injection_tests.py
