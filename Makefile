REQUIREMENTS_FULFILLED = $(shell upseto checkRequirements 2> /dev/null; echo $$?)
all: check_requirements unittest build check_convention

clean:
	sudo rm -fr build

COVERED_FILES=rackattack/physical/alloc/priority.py,rackattack/physical/dynamicconfig.py,rackattack/physical/alloc/freepool.py,rackattack/physical/alloc/allocation.py,rackattack/physical/host.py,rackattack/physical/alloc/allocations.py
unittest: check_requirements
	UPSETO_JOIN_PYTHON_NAMESPACES=Yes PYTHONPATH=. python -m coverage run -m rackattack.physical.tests.runner
	python -m coverage report --show-missing --rcfile=coverage.config --fail-under=86 --include=$(COVERED_FILES)

check_convention:
	pep8 rackattack --max-line-length=109

.PHONY: build
build: check_requirements build/rackattack.physical.egg

build/rackattack.physical.egg: rackattack/physical/main.py
	-mkdir $(@D)
	python -m upseto.packegg --entryPoint=$< --output=$@ --createDeps=$@.dep --compile_pyc --joinPythonNamespaces
-include build/rackattack.physical.egg.dep

install_pika:
	-sudo mkdir /usr/share/rackattack.physical
	sudo cp pika-stable/pika-git-ref-6226dc0.egg /usr/share/rackattack.physical

install: check_requirements install_pika build/rackattack.physical.egg
	-sudo systemctl stop rackattack-physical.service
	-sudo mkdir /usr/share/rackattack.physical
	sudo cp build/rackattack.physical.egg /usr/share/rackattack.physical
	sudo cp rackattack-physical.service /usr/lib/systemd/system/rackattack-physical.service
	sudo systemctl enable rackattack-physical.service
	if ["$(DONT_START_SERVICE)" == ""]; then sudo systemctl start rackattack-physical; fi

uninstall:
	-sudo systemctl stop rackattack-physical
	-sudo systemctl disable rackattack-physical.service
	-sudo rm -fr /usr/lib/systemd/system/rackattack-physical.service
	sudo rm -fr /usr/share/rackattack.physical

prepareForCleanBuild: install_pika

.PHONY: check_requirements
check_requirements:
ifeq ($(REQUIREMENTS_FULFILLED),1)
ifneq ($(SKIP_REQUIREMENTS),1)
	$(error Upseto requirements not fulfilled. Run with SKIP_REQUIREMENTS=1 to skip requirements validation.)
	exit 1
endif
endif
