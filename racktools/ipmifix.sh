#!/bin/bash

RACKATTACK_VAR_DIR=`python -c "from rackattack.physical import config; print config.SERIAL_LOGS_DIRECTORY"`
for server in `grep -R "Unable to establish IPMI v2" ${SERIAL_LOGS_DIRECTORY} | cut -d/ -f 6- | cut -d'-' -f  1-2` 
do
	echo ${server}
	python /root/racktools/ipmi-fixer.py --server ${server}
	#:echo $?
	if [ $? -eq 0 ]
	then 
		echo "Restarting" ${server}
        	/root/racktools/rackconfig.sh --servers ${server} --state offline
		/root/racktools/rackconfig.sh --servers ${server} --state online
	fi
done
