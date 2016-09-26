#!/bin/bash

for server in "$@"
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
