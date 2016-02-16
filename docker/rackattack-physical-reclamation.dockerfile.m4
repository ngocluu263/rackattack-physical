include(rackattack-physical-base.dockerfile)

ENV PYTHONPATH /usr/share/rackattack.physical/rackattack.physical.reclamation.egg

ENTRYPOINT ["/usr/bin/python", "-m", "rackattack.physical.main_reclamationserver"]
