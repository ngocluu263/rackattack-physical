all: unittest build check_convention

clean:
	sudo rm -fr build

COVERED_FILES=rackattack/physical/alloc/priority.py,rackattack/physical/dynamicconfig.py,rackattack/physical/alloc/freepool.py,rackattack/physical/alloc/allocation.py
unittest:
	UPSETO_JOIN_PYTHON_NAMESPACES=Yes PYTHONPATH=. python -m coverage run -m rackattack.physical.tests.runner
	python -m coverage report --show-missing --rcfile=coverage.config --fail-under=86 --include=$(COVERED_FILES)

check_convention:
	pep8 rackattack --max-line-length=109

.PHONY: build
build: build/rackattack.physical.egg

build/rackattack.physical.egg: rackattack/physical/main.py
	-mkdir $(@D)
	python -m upseto.packegg --entryPoint=$< --output=$@ --createDeps=$@.dep --compile_pyc --joinPythonNamespaces
-include build/rackattack.physical.egg.dep

install_pika:
	-sudo mkdir /usr/share/rackattack.physical
	sudo cp pika-stable/pika-git-ref-6226dc0.egg /usr/share/rackattack.physical

install: install_pika build/rackattack.physical.egg
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
