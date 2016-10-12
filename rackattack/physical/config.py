import os.path

RUNTIME_VAR_DIR = "/var/lib/rackattackphysical"
ROOT_PASSWORD = 'rackattack'
CONFIGURATION_FILE = "/etc/rackattack-physical/conf.yaml"
RACK_YAML = "/etc/rackattack-physical/rack.yaml"
LOG_CONFIG = "/etc/rackattack-physical/log.conf"
SERIAL_LOGS_DIRECTORY = os.path.join(RUNTIME_VAR_DIR, "seriallogs")
MANAGED_POST_MORTEM_PACKS_DIRECTORY = os.path.join(RUNTIME_VAR_DIR, "postMortemPacks")
RABBIT_MQ_DIRECTORY = os.path.join(RUNTIME_VAR_DIR, "mq")
WITH_LOCAL_OBJECT_STORE = True
RECLAMATION_REQUESTS_FIFO_PATH = os.path.join(RUNTIME_VAR_DIR, "reclamation_requests_fifo")
SOFT_RECLAMATION_FAILURE_MSG_FIFO_PATH = os.path.join(RUNTIME_VAR_DIR, "soft_reclamations_failure_msg_fifo")
EXAMPLE_CONF_YAML = "etc.rackattack-physical.conf.yaml.example"
ARE_IPMI_COMMANDS_SYNCHRONOUS = False
