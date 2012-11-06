telnetsrvlib
============

Telnet server using gevent or threading.

Copied from http://pytelnetsrvlib.sourceforge.net/
and modified to support gevent.
Licensed under the LGPL, as per the SourceForge notes.


This library includes two flavors of the server handler, one uses separate threads,
the other uses greenlets via gevent.

The threaded version uses a separate thread to process the input buffer and
semaphores reading and writing.  The provided test server only handles a single
connection at a time.

The green version moves the input buffer processing into a greenlet to allow 
cooperative multi-processing.  This results in significantly less memory usage
and nearly no idle processing.  The provided test server handles multiple connections,
limited only by available memory.


# To Use #

Import the TelnetHandler from either the green class or threaded class, then subclass it 
to add your own commands as specially named methods.  

Threaded:

```python
from telnetsrv.threaded import TelnetHandler
class MyHandler(TelnetHandler):
    ...
```

Green:

```python
from telnetsrv.green import TelnetHandler
class MyHandler(TelnetHandler):
    ...
```

## Add Commands ##

Commands are defined by creating specially named methods in your handler class.
Your command method name must with "cmd" and be followed by your command name in all caps.

```python
def cmdECHO(self, params):
```

Any command parameters will be passed to this function automatically.  The parameters are
contained in a list.  The user input is split(), strip()'ed then any quoted parameters 
are join()'ed and the quotes are stripped.  If you need to access the raw text input, 
inspect the self.raw_input variable.

> Telnet Server> echo 1  "2    3"

```python
    params == ['1', '2 3']
    self.raw_input == 'echo 1 "2    3"'
```

The command's docstring is used for generating the console help information, and must be formatted
with at least 3 lines:

 * Line 0:  Command paramater(s) if any. (Can be blank line)
 * Line 1:  Short descriptive text. (Mandatory)
 * Line 2+: Long descriptive text. (Can be blank line)

```python
    def cmdECHO(self, params):
        '''<text to echo>
        Echo text back to the console.
        This command simply echos the provided text
        back to the console.
        '''
        pass
```

> Telnet Server> help
> ? [<command>] - Display help
> BYE - Exit the command shell
> ECHO <text to echo> - Echo text back to the console.

...

> Telnet Server> help echo
> ECHO <text to echo>
> 
> This command simply echos the provided text
> back to the console.


To create an alias for the new command, set the method's member 'aliases' to a list:
 * cmdECHO.aliases = ['COPY']
 
To hide the command (and any alias) from the help text output, set its 'hidden' member to True:
 * cmdECHO.hidden = True



To communicate with the connected Telnet client, use:
 
 * self.writeline( TEXT )
 * self.write( TEXT )
 * self.readline( prompt=TEXT )

 * self.writemessage( TEXT ) - for clean, asynchronous writing
 * self.writeresult( TEXT ) - to emit expected output
 * self.writeerror( TEXT ) - to emit error messages

The writemessage method is intended to send messages to the console without
interrupting any current input.  It is ideal for asynchronous messages
that aren't necessarily generated from the direct user input.


## Set Up Handler Options ##

Override these class members to change the handler's behavior.

 * logging
    * Default: logging

 * PROMPT
    * Default: "Telnet Server> "
     
 * WELCOME
    * Displayed after a successful connection, after the username/password is accepted, 
     if configured.
    * Default: "You have connected to the telnet server."
 
 * session_start(self)
    * Called after the WELCOME text is displayed.
    
 * session_end(self)
    * Called after the console is disconnected.
     
 * authCallback(self, username, password) 
    * Reference to authentication function. If
     there is none, no un/pw is requested. Should
     raise an exception if authentication fails
    * Default: None

 * authNeedUser 
    * Should a username be requested?
    * Default: False

 * authNeedPass
    * Should a password be requested?
    * Default: False


## Modify Handler Display ##

If you want to change how the output is displayed, override one or all of the
write classes.  Make sure you call back to the base class when doing so.
These are good ways to provide color to your console by using ANSI color commands.
See http://en.wikipedia.org/wiki/ANSI_escape_code

 * writemessage( TEXT ) 
 * writeresult( TEXT ) 
 * writeerror( TEXT ) 

```python
    def writeerror(self, text):
        '''Write errors in red'''
        TelnetHandler.writeerror(self, "\x1b[91m%s\x1b[0m" % text )
```

# Use It With a Server #

An instance of the TelnetHandler class is created for each new connection.  It must
be called from either the gevent StreamServer (for the green version) or from a
SocketServer.TCPServer instance (for the threaded version).

Threaded:

```python
import SocketServer
class TelnetServer(SocketServer.TCPServer):
    allow_reuse_address = True
    
server = TelnetServer(("0.0.0.0", 8023), MyHandler)
server.serve_forever()
```

Green:

The TelnetHandler class includes a streamserver_handle class method to translate the 
required fields from a StreamServer, allowing use from the gevent StreamServer.

```python
import gevent.server
server = gevent.server.StreamServer(("", 8023), MyHandler.streamserver_handle)
server.server_forever()
```

# Short Example #
```python
import logging as my_special_logger

import gevent, gevent.server
from telnetsrv.green import TelnetHandler
 
class MyTelnetHandler(TelnetHandler):
    PROMPT = "MyTelnet> "
    WELCOME = "Welcome to my server."
    logging = my_special_logger
    
    def cmdECHO(self, params):
        '''<text to echo>
        Echo text back to the console.
        
        '''
        self.writeline( ' '.join(params) )
    
    cmdECHO.aliases = ['COPY', 'REPEAT']
    
    def cmdTIMER(self, params):
        '''<time> <message>
        In <time> seconds, display <message>.
        Send a message after a delay.
        <time> is in seconds.
        If <message> is more than one word, quotes are required.
        example: 
        > TIMER 5 "hello world!"
        '''
        try:
            timestr, message = params[:2]
            time = int(timestr)
        except ValueError:
            self.writeline( "Need both a time and a message" )
            return
        self.writeline("Waiting %d seconds...", time)
        gevent.spawn_later(time, self.writemessage, message)


server = gevent.server.StreamServer(("", 8023), MyTelnetHandler.streamserver_handle)
server.server_forever()
```

# Longer Example #

```python
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


# To run a green server, import gevent and the green version of telnetsrv.
if SERVERTYPE == 'green':
    import gevent, gevent.server
    
    from telnetsrv.green import TelnetHandler

# To run a threaded server, import threading and other libraries to help out.
if SERVERTYPE == 'threaded':
    import SocketServer
    import threading
    import time

    from telnetsrv.threaded import TelnetHandler
    
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

    def cmdDEBUG(self, params):
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
            timer = threading.Timer(delay, self.writemessage, args=[message])
            timer.start()
        
        # A real server should deal with this thread when the console closed
        # by defining a session_end method to ensure lingering threads don't
        # eat up resources and/or throw errors at strange times.

    
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


    
if SERVERTYPE == 'green':
    # Multi-green-threaded server
    server = gevent.server.StreamServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), TestTelnetHandler.streamserver_handle)
    
if SERVERTYPE == 'threaded':
    # Single threaded server - only one session at a time
    class TelnetServer(SocketServer.TCPServer):
        allow_reuse_address = True
        
    server = TelnetServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), TestTelnetHandler)


logging.info("Starting %s server at port %d.  (Ctrl-C to stop)" % (SERVERTYPE, TELNET_PORT_BINDING) )
server.serve_forever()
```
