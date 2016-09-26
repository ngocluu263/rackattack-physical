import psutil
import time
from procfs import Proc


SLEEP_TIME = 10.0

p = Proc()
mem_total = p.meminfo.MemTotal
network_before = psutil.network_io_counters(pernic=True)
io_before = psutil.disk_io_counters()
print "warming up (%f seconds)" % SLEEP_TIME
time.sleep(SLEEP_TIME)
while True:
    print "CPU usage: %f" % psutil.cpu_percent()
    
    print "Memory usage (pct) : %f, Memory Free: %f" % ( ( ( mem_total - p.meminfo.MemFree )*1.0 / mem_total ) * 100.0 , p.meminfo.MemFree )
    
    network_after = psutil.network_io_counters(pernic=True)
    print "Network usage: sent (Mb) %f, recv %f" % ( ( ( network_after['p50p1'].bytes_sent - network_before['p50p1'].bytes_sent ) / SLEEP_TIME / 1024.0 / 1024.0 * 8 ), ( ( network_after['p50p1'].bytes_recv - network_before['p50p1'].bytes_recv ) / SLEEP_TIME / 1024.0 / 1024.0 * 8 ) )
    
    d = psutil.disk_usage('/')
    print "Disk statistics: total %d, used %d, free %d, percentage %.1f" % (d.total, d.used, d.free, d.percent)
    
    io_after = psutil.disk_io_counters()
    print "I/O: read %d, write  %d, read (MBs): %f, write (MBs): %f, read_time %d, write_time %d" % ( io_after.read_count - io_before.read_count, io_after.write_count - io_before.write_count,(( io_after.read_bytes - io_before.read_bytes ) / SLEEP_TIME / 1024.0 / 1024.0 ), (( io_after.write_bytes - io_before.write_bytes ) / SLEEP_TIME / 1024.0 / 1024.0 ), io_after.read_time, io_after.write_time )

    network_before = network_after
    io_before = io_after
    time.sleep(SLEEP_TIME)
