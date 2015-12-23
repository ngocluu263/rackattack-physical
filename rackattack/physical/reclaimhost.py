from rackattack.common.reclaimhostspooler import ReclaimHostSpooler


class ReclaimHost(ReclaimHostSpooler):
    def __init__(self, *args, **kwargs):
        ReclaimHostSpooler.__init__(self, *args, **kwargs)

    def _requestColdReclamationFromServer(self, host, hardReset):
        credentials = host.ipmiLoginCredentials()
        assert isinstance(hardReset, bool)
        args = [credentials["hostname"], credentials["username"], credentials["password"], str(hardReset)]
        self._sendRequest("cold", args)

    def _handleColdReclamationRequest(self, host, hardReset):
        host.validateSOLStarted()
        self._requestColdReclamationFromServer(host, hardReset)
