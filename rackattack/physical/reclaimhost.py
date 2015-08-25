from rackattack.common.reclaimhostspooler import ReclaimHostSpooler


class ReclaimHost(ReclaimHostSpooler):
    def __init__(self, *args, **kwargs):
        ReclaimHostSpooler.__init__(self, *args, **kwargs)

    def _requestColdReclamationFromServer(self, host):
        credentials = host.ipmiLoginCredentials()
        args = [credentials["hostname"],
                credentials["username"],
                credentials["password"]]
        self._sendRequest("cold", args)

    def _handleColdReclamationRequest(self, host):
        host.validateSOLStarted()
        self._requestColdReclamationFromServer(host)
