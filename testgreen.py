import gevent
import time

tick = 5

'''Simple module that can be imported anywhere and used to verify if the thread is being green'''

def timer():
	while True:
		print time.strftime("%H:%M:%S: tick.")
		lasttime = time.clock() * 100
		gevent.sleep(tick)
		diff = ( time.clock() * 100 ) - lasttime
		if diff > (tick+1):
			print 'GREEN ERROR!  Lost %s somewhere.  Not being green!' % (diff - tick)
print 'Starting test timer.  (you should see a "tick" every 5 seconds)'
green_watch = gevent.spawn( timer )
