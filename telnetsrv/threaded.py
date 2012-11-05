#!/usr/bin/python
# Telnet handler concrete class using true threads.

import threading
import time
import select

from telnetsrvlib import TelnetHandlerBase

class TelnetHandler(TelnetHandlerBase):
    "A telnet server handler using Gevent"
    def __init__(self, request, client_address, server):
        # This is the cooked input stream (list of charcodes)
        self.cookedq = []   

        # Create the locks for handing the input/output queues
        self.IQUEUELOCK = threading.Lock()
        self.OQUEUELOCK = threading.Lock()

        # Call the base class init method
        TelnetHandlerBase.__init__(self, request, client_address, server)
        
    def setup(self):
        '''Called after instantiation'''
        TelnetHandlerBase.setup(self)
        # Spawn a thread to handle socket input
        self.thread_ic = threading.Thread(target=self.inputcooker)
        self.thread_ic.setDaemon(True)
        self.thread_ic.start()
        # Sleep for 0.5 second to allow options negotiation
        time.sleep(0.5)
        

    def finish(self):
        '''Called as the session is ending'''
        TelnetHandlerBase.finish(self)
        # Should the thread_ic be killed here?


    # -- Threaded input handling functions --

    def getc(self, block=True):
        """Return one character from the input queue"""
        if not block:
            if not len(self.cookedq):
                return ''
        while not len(self.cookedq):
            time.sleep(0.05)
        self.IQUEUELOCK.acquire()
        ret = self.cookedq[0]
        self.cookedq = self.cookedq[1:]
        self.IQUEUELOCK.release()
        return ret

    def inputcooker_socket_ready(self):
        """Indicate that the socket is ready to be read"""
        return select.select([self.sock.fileno()], [], [], 0) != ([], [], [])

    def inputcooker_store_queue(self, char):
        """Put the cooked data in the input queue (with locking)"""
        self.IQUEUELOCK.acquire()
        if type(char) in [type(()), type([]), type("")]:
            for v in char:
                self.cookedq.append(v)
        else:
            self.cookedq.append(char)
        self.IQUEUELOCK.release()


    # -- Threaded output handling functions --

    def writemessage(self, text):
        """Put data in output queue, rebuild the prompt and entered data"""
        # Need to grab the input queue lock to ensure the entered data doesn't change
        # before we're done rebuilding it.
        self.IQUEUELOCK.acquire()
        TelnetHandlerBase.writemessage(self, text)
        self.IQUEUELOCK.release()
    
    def writecooked(self, text):
        """Put data directly into the output queue"""
        # Ensure this is the only thread writing
        self.OQUEUELOCK.acquire()
        TelnetHandlerBase.writecooked(self, text)
        self.OQUEUELOCK.release()


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
                time = int(timestr)
            except ValueError:
                self.writeerror( "Need both a time and a message" )
                return
            self.writeresponse("Waiting %d seconds..." % time)
            timer_thread = threading.Thread(target=self.timer_function, args=(time,message,))
            timer_thread.start()
        
        def timer_function(self, sleeptime, message):
            time.sleep(sleeptime)
            self.writemessage(message)
                
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
    
    import logging
    logging.getLogger('').setLevel(logging.DEBUG)
    TestTelnetHandler.logging = logging
    
    TELNET_PORT_BINDING = 8023
    TELNET_IP_BINDING = '0.0.0.0' #all
    
    import SocketServer
    #Testing - Accept a single connection
    class TelnetServer(SocketServer.TCPServer):
        allow_reuse_address = True
        
    server = TelnetServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), TestTelnetHandler)
    logging.info("Starting server.  (Ctrl-C to stop)")
    server.serve_forever()
