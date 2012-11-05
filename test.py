import logging
logging.getLogger('').setLevel(logging.DEBUG)

TELNET_PORT_BINDING = 8023
TELNET_IP_BINDING = '' #all


#SERVERTYPE = 'green'
SERVERTYPE = 'threaded'

if SERVERTYPE == 'green':
    import gevent, gevent.server
    
    from telnetsrv.green import TelnetHandler


if SERVERTYPE == 'threaded':
    import SocketServer
    import threading
    import time

    from telnetsrv.threaded import TelnetHandler
    
    # The SocketServer needs *all to be 0.0.0.0
    if not TELNET_IP_BINDING:
        TELNET_IP_BINDING = '0.0.0.0'


    
TelnetHandler.logging = logging


class TestTelnetHandler(TelnetHandler):
    def cmdDEBUG(self, params):
        """
        Display some debugging data, wait 5 seconds, then display a message
        """
        for (v,k) in self.ESCSEQ.items():
            line = '%-10s : ' % (self.KEYS[k], )
            for c in v:
                if ord(c)<32 or ord(c)>126:
                    line = line + curses.ascii.unctrl(c)
                else:
                    line = line + c
            self.writeresponse(line)
    
    def cmdTIMER(self, params):
        '''<time> <message>
        In <time> seconds, display <message>.
        Send a message after a delay.
        <time> is in seconds.
        If <message> is more than one word, quotes are required.
        
        example: TIMER 5 "hello world!"
        '''
        try:
            timestr, message = params[:2]
            delay = int(timestr)
        except ValueError:
            self.writeerror( "Need both a time and a message" )
            return
        self.writeresponse("Waiting %d seconds..." % delay)
        
        if SERVERTYPE == 'green':
            gevent.spawn_later(delay, self.writemessage, message)

        if SERVERTYPE == 'threaded':
            def timer_function(self, delay, message):
                time.sleep(delay)
                self.writemessage(message)
            
            timer_thread = threading.Thread(target=timer_function, args=(self,delay,message,))
            timer_thread.start()
        
        # A real server would deal with this thread when the console closed
        # by overriding the session_end method to ensure lingering threads don't
        # eat up resources and/or throw errors at strange times.

    
    def cmdECHO(self, params):
        '''<text to echo>
        Echo text back to the console.
        
        '''
        self.writeresponse( ' '.join(params) )
    cmdECHO.aliases = ['REPEAT']
    
    def cmdTERM(self, params):
        '''
        Hidden command to print the current TERM
        
        '''
        self.writeresponse( self.TERM )
    cmdTERM.hidden = True


    
if SERVERTYPE == 'green':
    # Multi-green-threaded server
    server = gevent.server.StreamServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), TestTelnetHandler.streamserver_handle)
    
if SERVERTYPE == 'threaded':
    # Single threaded server - only one session at a time
    class TelnetServer(SocketServer.TCPServer):
        allow_reuse_address = True
        
    server = TelnetServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), TestTelnetHandler)


logging.info("Starting %s server.  (Ctrl-C to stop)" % SERVERTYPE)
server.serve_forever()
