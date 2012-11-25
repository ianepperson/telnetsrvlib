#!/usr/bin/python

import sys
import logging

logging.getLogger('').setLevel(logging.DEBUG)

TELNET_IP_BINDING = '' #all

# Obtain the port to use from the command line:
try:
    TELNET_PORT_BINDING = int(sys.argv[1])
except:
    print "Usage:  %s <port> [green]" % sys.argv[0]
    print "  <port> is the port to bind to."
    print '  "green" tells the server to use gevent.'
    sys.exit(1)

# Determine the type of server to run: green or threaded
try:
    SERVERTYPE = sys.argv[2].lower()
except:
    SERVERTYPE = 'threaded'

if not SERVERTYPE in ['green', 'threaded']:
    print "I didn't understand that server type.  Did you mean to type:"
    print " > %s %d green" % (sys.argv[0], TELNET_PORT_BINDING)
    print " or"
    print " > %s %d threaded" % (sys.argv[0], TELNET_PORT_BINDING)
    sys.exit(1)


# To run a green server, import gevent and the green version of telnetsrv.
if SERVERTYPE == 'green':
    import gevent, gevent.server
    
    from telnetsrv.green import TelnetHandler, command

# To run a threaded server, import threading and other libraries to help out.
if SERVERTYPE == 'threaded':
    import SocketServer
    import threading
    import time

    from telnetsrv.threaded import TelnetHandler, command
    
    # The SocketServer needs *all IPs* to be 0.0.0.0
    if not TELNET_IP_BINDING:
        TELNET_IP_BINDING = '0.0.0.0'


TelnetHandler.logging = logging


# The TelnetHandler instance is re-created for each connection.
# Therfore, in order to store data between connections, create
# a seperate object to deal with any logic that needs to persist
# after the user logs off.
# Here is a simple example that just counts the number of connections
# as well as the number of times this user has connected.

class MyServer(object):
    '''A simple server class that just keeps track of a connection count.'''
    def __init__(self):
        # Var to track the total connections.
        self.connection_count = 0
        
        # Dictionary to track individual connections.
        self.user_connect = {}
        
    def new_connection(self, username):
        '''Register a new connection by username, return the count of connections.'''
        self.connection_count += 1
        try:
            self.user_connect[username] += 1
        except:
            self.user_connect[username] = 1
        return self.connection_count, self.user_connect[username]
        
        

# Subclass TelnetHandler to add our own commands and to call back
# to myserver.

class TestTelnetHandler(TelnetHandler):
    # Create the instance of the server within the class for easy use
    myserver = MyServer()

    # -- Override items to customize the server --

    WELCOME = 'You have connected to my test telnet server.'
    PROMPT = "MyServer> "
    authNeedUser = True
    authNeedPass = False
    
    def authCallback(self, username, password):
        '''Called to validate the username/password.'''
        # We accept everyone here, as long as any name is given!
        if not username:
            # complain by raising any exception
            raise
        self.username = username

    def session_start(self):
        '''Called after the user successfully logs in.'''
        self.writeline('This server is running %s.' % SERVERTYPE)
        
        # Tell myserver that we have a new connection, and provide the username.
        # We get back the login count information.
        globalcount, usercount = self.myserver.new_connection( self.username )
        
        self.writeline('Hello %s!' % self.username)
        self.writeline('You are connection #%d, you have logged in %s time(s).' % (globalcount, usercount))
        
    def writeerror(self, text):
        '''Called to write any error information (like a mistyped command).
        Add a splash of color using ANSI to render the error text in red.
        see http://en.wikipedia.org/wiki/ANSI_escape_code'''
        TelnetHandler.writeerror(self, "\x1b[91m%s\x1b[0m" % text )


    # -- Custom Commands --
    @command('debug')
    def command_debug(self, params):
        """
        Display some debugging data
        """
        for (v,k) in self.ESCSEQ.items():
            line = '%-10s : ' % (self.KEYS[k], )
            for c in v:
                if ord(c)<32 or ord(c)>126:
                    line = line + curses.ascii.unctrl(c)
                else:
                    line = line + c
            self.writeresponse(line)

    @command('params')
    def command_params(self, params):
        '''[<params>]*
        Echos back the raw recevied parameters.
        '''
        self.writeresponse("params == %r" % params)
    
    @command(['timer', 'timeit'])
    def command_timer(self, params):
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
            timer = threading.Timer(delay, self.writemessage, args=[message])
            timer.start()
        
        # A real server should deal with this thread when the console closed
        # by defining a session_end method to ensure lingering threads don't
        # eat up resources and/or throw errors at strange times.

    
    # Older method of defining a command
    # must start with "cmd" and end wtih the command name.
    # Aliases may be attached after the method definitions.
    def cmdECHO(self, params):
        '''<text to echo>
        Echo text back to the console.
        
        '''
        self.writeresponse( ' '.join(params) )
    # Create an alias for this command
    cmdECHO.aliases = ['REPEAT']

    
    def cmdTERM(self, params):
        '''
        Hidden command to print the current TERM
        
        '''
        self.writeresponse( self.TERM )
    # Hide this command.  Will not show in the help list.
    cmdTERM.hidden = True


    @command('hide-me', hidden=True)
    @command(['hide-me-too', 'also-me'])
    def command_do_nothing(self, params):
        '''
        Hidden command to perform no action
        
        '''
        self.writeresponse( 'Nope, did nothing.')
    
if SERVERTYPE == 'green':
    # Multi-green-threaded server
    server = gevent.server.StreamServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), TestTelnetHandler.streamserver_handle)
    
if SERVERTYPE == 'threaded':
    # Single threaded server - only one session at a time
    class TelnetServer(SocketServer.TCPServer):
        allow_reuse_address = True
        
    server = TelnetServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), TestTelnetHandler)


logging.info("Starting %s server at port %d.  (Ctrl-C to stop)" % (SERVERTYPE, TELNET_PORT_BINDING) )
try:
    server.serve_forever()
except KeyboardInterrupt:
    logging.info("Server shut down.")
