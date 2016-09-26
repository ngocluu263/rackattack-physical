import os
from rackattack import clientfactory


def setLocalRackattack():
    localProvider = "tcp://localhost:1014@@amqp://guest:guest@localhost:1013@@http://localhost:1016"
    os.environ["RACKATTACK_PROVIDER"] = localProvider


if __name__ == '__main__':
    if "RACKATTACK_PROVIDER" not in os.environ:
        setLocalRackattack()
    client = clientfactory.factory()
    print client.call("admin__reloadStateMachineConfiguration")
