#!/bin/bash

./getStatus.sh | egrep "DESTROYED|SLOW" -B 6 | grep -e "-server" | grep rack > ~/removeme_slowreclamation.txt
cat ~/removeme_slowreclamation.txt | sort > ~/remove_slowreclamation_sorted.txt

for server in `cat ~/removeme_slowreclamation_sorted.txt` 
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
