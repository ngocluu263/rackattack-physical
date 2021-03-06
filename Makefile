RACKATTACK_VAR_DIR=`python -c "from rackattack.physical import config; print config.RUNTIME_VAR_DIR"`
RACKATTACK_PHYSICAL_DOCKER_CIDFILE = ${RUNTIME_VAR_DIR}/cid
UPSETO_REQUIREMENTS_FULFILLED = $(shell upseto checkRequirements 2> /dev/null; echo $$?)
VERSION=$(shell git describe --tags --dirty)
UT_BLACKLIST = rackattack.physical.logconfig \
               rackattack.physical.main \
               rackattack.physical.main_reclamationserver \
               rackattack.physical.configurenat \
               rackattack.physical.setup_networking_for_docker_idempotently \

all: validate_requirements unittest build check_convention

clean:
	sudo rm -fr build

unittest:
	@UPSETO_JOIN_PYTHON_NAMESPACES=Yes PYTHONPATH=. python -m coverage run -m rackattack.physical.tests.runner --blackList ${UT_BLACKLIST}
	@python -m coverage report --show-missing --fail-under=75 --include=rackattack/* --omit="rackattack/physical/tests/*"

.PHONY: integration_test
integration_test:
	sudo ./sh/integration_test

check_convention:
	pep8 rackattack --max-line-length=109

check_before_commit: check_convention unittest

.PHONY: build
build: build/rackattack.physical.egg build/rackattack.physical.reclamation.egg

build/rackattack.physical.egg: rackattack/physical/main.py
	-mkdir $(@D)
	python -m upseto.packegg --entryPoint=$< --output=$@ --createDeps=$@.dep --compile_pyc --joinPythonNamespaces
-include build/rackattack.physical.egg.dep

build/rackattack.physical.reclamation.egg: rackattack/physical/main_reclamationserver.py
	-mkdir $(@D)
	python -m upseto.packegg --entryPoint=$< --output=$@ --createDeps=$@.dep --compile_pyc --joinPythonNamespaces
-include build/rackattack.physical.reclamation.egg.dep

ifeq ($(HOST),local)
install: validate_requirements build/rackattack.physical.egg build/rackattack.physical.reclamation.egg
	-sudo systemctl stop rackattack-physical.service
	-sudo systemctl stop rackattack-physical-reclamation.service
	-sudo mkdir /usr/share/rackattack.physical
	sudo cp build/rackattack.physical.egg /usr/share/rackattack.physical
	sudo cp build/rackattack.physical.reclamation.egg /usr/share/rackattack.physical
	sudo cp rackattack-physical.service /usr/lib/systemd/system/rackattack-physical.service
	sudo cp rackattack-physical-reclamation.service /usr/lib/systemd/system/rackattack-physical-reclamation.service
	sudo systemctl enable rackattack-physical.service
	sudo systemctl enable rackattack-physical-reclamation.service
	if ["$(DONT_START_SERVICE)" == ""]; then sudo systemctl start rackattack-physical; systemctl start rackattack-physical-reclamation; fi

uninstall:
	-sudo systemctl stop rackattack-physical
	-sudo systemctl disable rackattack-physical.service
	-sudo systemctl disable rackattack-physical-reclamation.service
	-sudo rm -fr /usr/lib/systemd/system/rackattack-physical.service
	-sudo rm -fr /usr/lib/systemd/system/rackattack-physical-reclamation.service
	sudo rm -fr /usr/share/rackattack.physical
else
ifeq ($(HOST),docker)
install: run-rackattack-physical-reclamation-container run-rackattack-physical-reclamation-container
endif
endif

prepareForCleanBuild:

.PHONY: validate_python_requirements
validate_python_requirements:
ifneq ($(SKIP_REQUIREMENTS),1)
ifeq ($(UPSETO_REQUIREMENTS_FULFILLED),1)
	$(error Upseto requirements not fulfilled. Run with SKIP_REQUIREMENTS=1 to skip requirements validation.)
	exit 1
else
	$(info ***********************************************************************)
	$(info * Note: Run with SKIP_REQUIREMENTS=1 to skip requirements validation. *)
	$(info ***********************************************************************)
	@sleep 4
endif
	@echo "Validating PIP requirements..."
	@sudo pip install -r requirements.txt
	@echo "PIP requirements satisfied."
else
	@echo "Skipping requirements validation."
endif

.PHONY: validate_requirements
validate_requirements: validate_python_requirements
ifneq ($(SKIP_REQUIREMENTS),1)
	sh/validate_packages_prerequisites.sh
else
	@echo "Skipping requirements validation."
endif

.PHONY: configure_nat
configure_nat:
ifeq ($(INTERFACE),)
	$(error Please set the INTERFACE makefile argument to the name of the network interface which is used as the public gateway.)
endif
	sudo UPSETO_JOIN_PYTHON_NAMESPACES=Yes PYTHONPATH=. python -m rackattack.physical.configurenat $(INTERFACE)

build/rackattack-physical.dockerfile: docker/rackattack-physical.dockerfile.m4 docker/rackattack-physical-base.dockerfile
	-mkdir -p $(@D)
	m4 -Idocker $< > $@

build/rackattack-physical-reclamation.dockerfile: docker/rackattack-physical-reclamation.dockerfile.m4 docker/rackattack-physical-base.dockerfile
	-mkdir -p $(@D)
	m4 -Idocker $< > $@

build/rackattack-virtual: ../rackattack-virtual
	cp -rf ../rackattack-virtual $@

build/rackattack-api:
	cp -rf ../rackattack-api $@

ifeq ($(HOST),docker)
.PHONY: rackattack-physical-docker-image
rackattack-physical-docker-image: build/rackattack-physical.dockerfile build/rackattack-virtual build/rackattack-api
ifeq ($(shell sudo docker images | egrep -Ec "^rackattack-physical[ ]+$(VERSION)" | xargs echo -n),0)
	$(info Building the rackattack-physical docker image for version '$(VERSION)'...)
	@docker build -f $< -t "rackattack-physical:$(VERSION)" .
else
	$(info It seems that a rackattack-physical Docker image for version '$(VERSION)' already exists. Skipping build.)
endif

.PHONY: rackattack-physical-reclamation-docker-image
rackattack-physical-reclamation-docker-image: build/rackattack-physical-reclamation.dockerfile
ifeq ($(shell sudo docker images | egrep -Ec "^rackattack-physical-reclamation[ ]+$(VERSION)" | xargs echo -n),0)
	$(info Building the rackattack-physical-reclamation docker image for version '$(VERSION)'...)
	@docker build -f $< -t "rackattack-physical-reclamation:$(VERSION)" .
else
	$(info It seems that a rackattack-physical-reclamation Docker image for version '$(VERSION)' already exists. Skipping build.)
endif

build/pipework:
	-wget --no-check-certificate https://raw.github.com/jpetazzo/pipework/master/pipework -O build/pipework
	-chmod +x build/pipework

.PHONY: run-rackattack-physical-docker-container
run-rackattack-physical-docker-container: rackattack-physical-docker-image build/pipework
ifneq ($(shell docker ps | grep -c "rackattack-physical:$(VERSION)" | xargs echo -n),0)
	$(error Cannot start rackattack while another rackattack container is running.)
	exit 1
endif
	-rm "$(RACKATTACK_PHYSICAL_DOCKER_CIDFILE)"
	docker run -d=true -v /etc/rackattack-physical:/etc/rackattack-physical -v /usr/share/rackattack.physical/reclamation_requests_fifo:/usr/share/rackattack.physical/reclamation_requests_fifo -v /usr/share/rackattack.physical/soft_reclamations_failure_msg_fifo:/usr/share/rackattack.physical/soft_reclamations_failure_msg_fifo -v ${RUNTIME_VAR_DIR}/:${RUNTIME_VAR_DIR}/ -p 1013:1013 -p 1014:1014 -p 1015:1015 -p 1016:1016 -p 67:67/udp -p 69:69 -p 53:53/udp --cap-add NET_ADMIN --cidfile="$(RACKATTACK_PHYSICAL_DOCKER_CIDFILE)" "rackattack-physical:$(VERSION)"
	@echo "Setting up networking for the rackattack-physical container..."
	@UPSETO_JOIN_PYTHON_NAMESPACES=Yes PYTHONPATH=. python rackattack/physical/setup_networking_for_docker_idempotently.py "`cat ${RUNTIME_VAR_DIR}/cid`" build/pipework
	@echo "Done."

.PHONY: run-rackattack-physical-reclamation-docker-container
run-rackattack-physical-reclamation-docker-container: rackattack-physical-reclamation-docker-image
ifneq ($(shell docker ps | grep -c "rackattack-physical-reclamation:"),0)
	$(error Cannot start rackattack while another rackattack container is running.)
	exit 1
endif
	docker run -d=true -v /etc/rackattack-physical:/etc/rackattack-physical -v /usr/share/rackattack.physical/reclamation_requests_fifo:/usr/share/rackattack.physical/reclamation_requests_fifo -v /usr/share/rackattack.physical/soft_reclamations_failure_msg_fifo:/usr/share/rackattack.physical/soft_reclamations_failure_msg_fifo "rackattack-physical-reclamation:$(VERSION)"
endif
