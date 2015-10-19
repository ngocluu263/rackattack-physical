import os
import yaml
import json
import random
import logging
import threading
import functools

from rackattack.physical.tests.integration import use_local_inaugurator
import rackattack.physical.config
import rackattack.physical.pikapatch
from rackattack.common import hoststatemachine
from inaugurator.server import config, pikapatchwakeupfromanotherthread
from rackattack.physical.tests.integration.main import RACK_CONFIG_FILE_PATH, FAKE_REBOOTS_PIPE_NAME
import pika

assert "egg" in pika.__file__
assert "build" not in pika.__file__
assert "bdist" not in pika.__file__
use_local_inaugurator.verify()


class RebootRequestListener(threading.Thread):
    # Read a large enough size in order to avoid the need for reassembly
    _READ_BUF_SIZE = 1024 ** 2

    def __init__(self, notifyOnNewRequestCallback):
        threading.Thread.__init__(self)
        self.daemon = True
        self._notifyOnNewRequestCallback = notifyOnNewRequestCallback
        self._logger = logging.getLogger("pipeListener")
        if not os.path.exists(FAKE_REBOOTS_PIPE_NAME):
            os.mkfifo(FAKE_REBOOTS_PIPE_NAME)
        self._fakeRebootRequestsPipe = None
        self.start()

    def run(self):
        while True:
            if self._fakeRebootRequestsPipe is None:
                self._logger.info("Opening msg pipe for reading...")
                try:
                    self._fakeRebootRequestsPipe = os.open(FAKE_REBOOTS_PIPE_NAME, os.O_RDONLY)
                except Exception as e:
                    self._logger.error("Failed opening fifo: %(msg)s.", dict(msg=e.message))
                    raise
            self._logger.info("Waiting on pipe for fake boot requests...")
            hostnames = os.read(self._fakeRebootRequestsPipe, self._READ_BUF_SIZE).strip(" ,")
            if not hostnames:
                os.close(self._fakeRebootRequestsPipe)
                self._fakeRebootRequestsPipe = None
                continue
            self._logger.info("Read '%(hostnames)s' from the pipe.", dict(hostnames=hostnames))
            for ipmiHostname in hostnames.split(","):
                if not ipmiHostname:
                    continue
                self._notifyOnNewRequestCallback(ipmiHostname)
        os.close(self._fakeRebootRequestsPipe)


class FakeHosts:
    def __init__(self):
        self._logger = logging.getLogger("fakeConsumersServer")
        self._isConnected = threading.Event()
        self._pikaPatcher = None
        self._hosts = self._getExistingHosts()
        self._rebootRequestListener = RebootRequestListener(self.fakeReboot)

    def fakeReboot(self, ipmiHostname):
        self._logger.info("Got a reboot request for '%(ipmiHostname)s'", dict(ipmiHostname=ipmiHostname))
        hostsWithThisIpmi = [hostname for (hostname, hostData) in self._hosts.iteritems() if
                             hostData["ipmiHostname"] == ipmiHostname]
        hostname = hostsWithThisIpmi.pop()
        assert not hostsWithThisIpmi
        self._logger.info("%(hostname)s has rebooted." % dict(hostname=hostname))
        if not self._isConnected.isSet():
            self._logger.info("Waiting for connection to RabbitMQ to be open...")
            self._isConnected.wait()
        self._hosts[hostname]["state"] = hoststatemachine.STATE_SLOW_RECLAIMATION_IN_PROGRESS
        self._hosts[hostname]["latestRebootID"] += 1
        rebootID = self._hosts[hostname]["latestRebootID"]
        self._logger.info("Invoking a fake reboot (#%(rebootID)s) in connection thread...",
                          dict(rebootID=rebootID))
        kwargs = dict(rebootID=rebootID, hostname=hostname)
        self._runInThreadInRebootContext(callback=self._fakeReboot, kwargs=kwargs, **kwargs)

    def _runInRebootContext(self, rebootID, hostname, callback):
        if rebootID != self._hosts[hostname]["latestRebootID"]:
            return
        callback()

    def _addTimeoutForHost(self, hostname, rebootID, timeout, callback):
        callbackInRebootContext = functools.partial(self._runInRebootContext,
                                                    rebootID=rebootID,
                                                    hostname=hostname,
                                                    callback=callback)
        self._connection.add_timeout(timeout, callbackInRebootContext)

    def _fakeReboot(self, rebootID, hostname):
        self._logger.info("Faking reboot for %(hostname)s..." % dict(hostname=hostname))
        bootTime = self._generateTipicalInauguratorBootTime()
        checkInCallback = functools.partial(self._checkIn, hostname=hostname, rebootID=rebootID)
        self._addTimeoutForHost(hostname, rebootID, bootTime, checkInCallback)

    def _getExistingHosts(self):
        hostsInConfiguration = yaml.load(open(rackattack.physical.config.RACK_YAML, "r"))
        hostsInConfiguration = hostsInConfiguration["HOSTS"]
        hosts = dict()
        for host in hostsInConfiguration:
            if not host.get("offline", False):
                hosts[host["id"]] = dict(ipmiHostname=host["ipmiLogin"]["hostname"],
                                         state=None,
                                         timeoutIDs=set(),
                                         labelQueue=None,
                                         latestRebootID=0,
                                         allQueuesExist=False)
        return hosts

    def _checkIn(self, hostname, rebootID):
        self._logger.info("Starting checkin sequence for %(hostname)s", dict(hostname=hostname))
        statusExchange = "inaugurator_status__%s" % hostname
        labelExchange = "inaugurator_label__%s" % hostname
        labelQueue = "inaugurator_label__%s" % hostname

        def sendDoneMessage(hostname):
            body = json.dumps(dict(status="done", id=hostname))
            self._channel.basic_publish(exchange=statusExchange, routing_key='', body=body)

        def sendProgress(hostname, percent):
            msg = dict(status="progress", id=hostname, progress=dict(state="fetching", percent=percent))
            body = json.dumps(msg)
            self._logger.info("Sending progress message for %(hostname)s: %(percent)s %%",
                              dict(hostname=hostname, percent=percent))
            self._channel.basic_publish(exchange=statusExchange, routing_key='', body=body)
            percent += 20
            if percent > 100:
                self._logger.info("Sending 'done' for %(hostname)s", dict(hostname=hostname))
                sendDoneMessage(hostname)
            else:
                interval = 1
                self._logger.info("Scheduling progress message of %(percent)s%% in %(interval)s seconds",
                                  dict(percent=percent, interval=interval))
                sendProgressCallback = functools.partial(sendProgress, hostname=hostname, percent=percent)
                self._addTimeoutForHost(hostname,
                                        self._hosts[hostname]["latestProgressRebootID"],
                                        interval,
                                        sendProgressCallback)

        def fakeProgress(hostname):
            labelExistsFully = random.choice([True, False])
            if labelExistsFully:
                sendDoneMessage(hostname)
            else:
                sendProgress(hostname, 0)

        def labelReceived(channel, frame, properties, body):
            self._hosts[hostname]["latestProgressRebootID"] = self._hosts[hostname]["latestRebootID"]
            label = body
            state = self._hosts[hostname]["state"]
            if state == hoststatemachine.STATE_CHECKED_IN:
                self._logger.info("Got label %(label)s for hostname %(hostname)s. Faking inauguration...",
                                  dict(label=label, hostname=hostname))
                fakeProgress(hostname)
            else:
                self._logger.info("Ignoring label %(label)s for %(hostname)s, since its state is %(state)s",
                                  dict(label=label, hostname=hostname, state=state))

        def sendCheckIn():
            body = json.dumps(dict(status="checkin", id=hostname))
            self._logger.info("Sending a checkin message via the status Exchange %(exchange)s...",
                              dict(exchange=statusExchange))
            self._channel.basic_publish(exchange=statusExchange, routing_key='', body=body)
            self._hosts[hostname]["state"] = hoststatemachine.STATE_CHECKED_IN
            if not self._hosts[hostname]["allQueuesExist"]:
                self._logger.info("Consuming from queue %(queue)s...", dict(queue=labelQueue))
                self._channel.basic_consume(labelReceived, queue=labelQueue)
                self._logger.info("Now consuming.", dict(queue=labelQueue))
                self._hosts[hostname]["allQueuesExist"] = True

        def labelQueueBinded(unused):
            if rebootID != self._hosts[hostname]["latestRebootID"]:
                return
            sendCheckIn()

        def labelQueueDeclared(frame):
            if rebootID != self._hosts[hostname]["latestRebootID"]:
                return
            assert labelQueue == frame.method.queue
            self._logger.info("Binding label queue %(queue)s with labels exchange...",
                              dict(queue=labelQueue))
            self._channel.queue_bind(callback=labelQueueBinded,
                                     queue=labelQueue,
                                     exchange=labelExchange)

        def labelExchangeDeclared(unused):
            if rebootID != self._hosts[hostname]["latestRebootID"]:
                return
            self._logger.info("Checkin for %(hostname)s. Declaring an exclusive label queue...",
                              dict(hostname=hostname))
            self._channel.queue_declare(queue=labelQueue, callback=labelQueueDeclared, exclusive=True)

        def statusExchangeDeclared(unused):
            if rebootID != self._hosts[hostname]["latestRebootID"]:
                return
            self._logger.info("Declaring a RabbitMQ exchange %(exchange)s...", dict(exchange=labelExchange))
            self._channel.exchange_declare(callback=labelExchangeDeclared, exchange=labelExchange,
                                           type='fanout')

        self._logger.info("Reboot %(rebootID)s for %(hostname)s", dict(rebootID=rebootID, hostname=hostname))
        if self._hosts[hostname]["allQueuesExist"]:
            sendCheckIn()
        else:
            self._logger.info("Declaring a RabbitMQ exchange %(exchange)s...", dict(exchange=statusExchange))
            self._channel.exchange_declare(callback=statusExchangeDeclared, exchange=statusExchange,
                                           type='fanout')

    def _generateTipicalInauguratorBootTime(self):
        return 0 + random.randint(0, 10)

    def _onConnectionOpen(self, unused_connection):
        self._logger.info('Connection to RabbitMQ broker is establised. Opening a channel...')
        self._connection.channel(on_open_callback=self._onChannelOpen)

    def _onChannelOpen(self, channel):
        self._logger.info("Channel is open. Ready for requests.")
        self._channel = channel
        self._isConnected.set()

    def _runInThreadInRebootContext(self, callback, kwargs, rebootID, hostname):
        callback = functools.partial(callback, **kwargs)
        callbackInRebootContext = functools.partial(self._runInRebootContext,
                                                    rebootID=rebootID,
                                                    hostname=hostname,
                                                    callback=callback)
        self._pikaPatcher.runInThread(callbackInRebootContext)

    def run(self):
        self._logger.info("Attempting to open a connection to the RabbitMQ broker...")
        self._connection = pika.SelectConnection(
            pika.URLParameters(config.AMQP_URL),
            self._onConnectionOpen,
            stop_ioloop_on_close=False)
        self._pikaPatcher = pikapatchwakeupfromanotherthread.PikaPatchWakeUpFromAnotherThread(
            self._logger,
            self._connection)
        self._connection.ioloop.start()
