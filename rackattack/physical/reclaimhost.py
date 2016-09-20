from rackattack.common.reclaimhostspooler import ReclaimHostSpooler


class ReclaimHost(ReclaimHostSpooler):
    def __init__(self, *args, **kwargs):
        ReclaimHostSpooler.__init__(self, *args, **kwargs)

    def _requestColdReclamationFromServer(self, host, hardReset):
        credentials = host.ipmiLoginCredentials()
        assert isinstance(hardReset, bool)
        args = dict(hostname=credentials["hostname"],
                    username=credentials["username"],
                    password=credentials["password"],
                    isHardReset=str(hardReset))
        self._sendRequest("cold", args)

    def _handleColdReclamationRequest(self, host, hardReset):
        host.validateSOLStarted()
        self._requestColdReclamationFromServer(host, hardReset)
