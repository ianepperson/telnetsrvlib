#!/usr/bin/python
# Telnet handler concrete class using green threads

import gevent, gevent.queue, gevent.server

from telnetsrvlib import TelnetHandlerBase

class TelnetHandler(TelnetHandlerBase):
    "A telnet server handler using Gevent"
    def __init__(self, request, client_address, server):
        # Create a green queue for input handling
        self.cookedq = gevent.queue.Queue()
        # Call the base class init method
        TelnetHandlerBase.__init__(self, request, client_address, server)
        
    def setup(self):
        '''Called after institution'''
        TelnetHandlerBase.setup(self)
        # Spawn a greenlet to handle socket input
        self.greenlet = gevent.spawn(self.inputcooker)
        # Sleep for 0.5 second to allow options negotiation
        gevent.sleep(0.5)
        
    def finish(self):
        '''Called as the session is ending'''
        TelnetHandlerBase.finish(self)
        self.greenlet.kill()


    # -- Green input handling functions --

    def getc(self, block=True):
        """Return one character from the input queue"""
        try:
            return self.cookedq.get(block)
        except gevent.queue.Empty:
            return ''

    def inputcooker_socket_ready(self):
        """Indicate that the socket is ready to be read"""
        return gevent.select.select([self.sock.fileno()], [], [], 0) != ([], [], [])

    def inputcooker_store_queue(self, char):
        """Put the cooked data in the input queue (no locking needed)"""
        if type(char) in [type(()), type([]), type("")]:
            for v in char:
                self.cookedq.put(v)
        else:
            self.cookedq.put(char)



if __name__ == '__main__':
    '''Testing - Run a server'''

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
                self.writeline(line)
        
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
                time = int(timestr)
            except ValueError:
                self.writeline( "Need both a time and a message" )
                return
            self.writeline("Waiting %d seconds..." % time)
            gevent.spawn_later(time, self.writemessage, message)
                
        def cmdECHO(self, params):
            '''<text to echo>
            Echo text back to the console.
            
            '''
            self.writeline( ' '.join(params) )
        cmdECHO.aliases = ['REPEAT']
        
        def cmdTERM(self, params):
            '''
            Hidden command to print the current TERM
            
            '''
            self.writeline( self.TERM )
        cmdTERM.hidden = True
    
    import logging
    logging.getLogger('').setLevel(logging.DEBUG)
    TestTelnetHandler.logging = logging
    
    TELNET_PORT_BINDING = 8023
    TELNET_IP_BINDING = '' #all

    server = gevent.server.StreamServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), TestTelnetHandler.streamserver_handle)
    logging.info("Starting server.  (Ctrl-C to stop)")
    server.serve_forever()
