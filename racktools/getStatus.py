import pprint
from rackattack import clientfactory

client = clientfactory.factory()

pprint.pprint(client.call("admin__queryStatus"))
