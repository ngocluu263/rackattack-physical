include(rackattack-physical-base.dockerfile)

# Install DNSMasq
RUN yum install -y dnsmasq

EXPOSE 1013 1014 1015 1016 53 67/udp 68 69

ENV PYTHONPATH /usr/share/rackattack.physical/rackattack.physical.egg

RUN wget --no-check-certificate https://raw.github.com/jpetazzo/pipework/master/pipework && \
    chmod +x pipework

CMD \
    echo "Waiting for eth1 to be created..." && \
    ./pipework --wait && \
    rm pipework && \
    /usr/bin/python -m rackattack.physical.main
