#!/usr/bin/python

import logging
import argparse

logging.getLogger('').setLevel(logging.DEBUG)

TELNET_IP_BINDING = '' #all

# Parse the input arguments
# Normally, these would be down in "if __name__ == '__main__'", but we need to know green-vs-threaded for the base class and other imports
parser = argparse.ArgumentParser( description='Run a telnet server.')
parser.add_argument( 'port', metavar="PORT", type=int, help="The port on which to listen on." )
parser.add_argument( '-s', '--ssh', action='store_const', const=True, default=False, help="Run as SSH server using Paramiko library.")
parser.add_argument( '-g', '--green', action='store_const', const=True, default=False, help="Run with cooperative multitasking using Gevent library.")
parser.add_argument( '-e', '--eventlet', action='store_const', const=True, default=False, help="Run with cooperative multitasking using Eventlet library.")
console_args = parser.parse_args()

TELNET_PORT_BINDING = console_args.port

if console_args.ssh:
    SERVERPROTOCOL = 'SSH'
else:
    SERVERPROTOCOL = 'telnet'

if console_args.green:
    SERVERTYPE = 'green'
    # To run a green server, import gevent and the green version of telnetsrv.
    import gevent, gevent.server
    from telnetsrv.green import TelnetHandler, cmd, Commands
elif console_args.eventlet:
    SERVERTYPE = 'eventlet'
    # To run a eventlet server, import eventlet and the eventlet version of telnetsrv.
    import eventlet
    from telnetsrv.evtlet import TelnetHandler, cmd, Commands
else:
    SERVERTYPE = 'threaded'
    # To run a threaded server, import threading and other libraries to help out.
    import socketserver
    import threading
    import time

    from telnetsrv.threaded import TelnetHandler, cmd, Commands

    # The SocketServer needs *all IPs* to be 0.0.0.0
    if not TELNET_IP_BINDING:
        TELNET_IP_BINDING = '0.0.0.0'


class MyCommands(Commands):
    """
    A set of commands to query the connection information stored in MyServer.
    """
    @cmd
    def debug(self, params):
        """
        Display some debugging data
        """
        for (v,k) in self.handler.ESCSEQ.items():
            line = '%-10s : ' % (self.handler.KEYS[k], )
            for c in v:
                if ord(c)<32 or ord(c)>126:
                    line = line + curses.ascii.unctrl(c)
                else:
                    line = line + c
            self.handler.writeresponse(line)

    @cmd
    def params(self, params):
        '''[<params>]*
        Echos back the raw received parameters.
        '''
        self.writeresponse("params == %r" % params)

    @cmd
    def info(self, params):
        '''
        Provides some information about the current terminal.
        '''
        self.writeresponse( "Username: %s, terminal type: %s" % (self.username, self.TERM) )
        self.writeresponse( "Command history:" )
        for c in self.history:
            self.writeresponse("  %r" % c)

    @cmd(['timer', 'timeit'])
    def timer(self, params):
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
            self.handler.writeerror( "Need both a time and a message" )
            return
        self.handler.writeresponse("Waiting %d seconds..." % delay)

        if SERVERTYPE == 'green':
            event = gevent.spawn_later(delay, self.handler.writemessage, message)

        if SERVERTYPE == 'eventlet':
            event = eventlet.spawn_after(delay, self.handler.writemessage, message)

        if SERVERTYPE == 'threaded':
            event = threading.Timer(delay, self.handler.writemessage, args=[message])
            event.start()

        # Used by session_end to stop all timer events when the user logs off.
        self.handler.timer_events.append(event)

    @cmd('passwd')
    def set_password(self, params):
        '''[<password>]
        Pretends to set a console password.
        Pretends to set a console password.
        Demonostrates how sensative information may be handled
        '''
        try:
            password = params[0]
        except:
            password = self.handler.readline(prompt="New Password: ", echo=False, use_history=False)
        else:
            # If the password was a parameter, it will have been stored in the history.
            # snip it out to prevent easy snooping
            self.handler.history[-1] = 'passwd'

        password2 = self.handler.readline(prompt="Retype New Password: ", echo=False, use_history=False)
        if password == password2:
            self.handler.writeresponse('Pretending to set new password, but not really.')
        else:
            self.handler.writeerror('Passwords don\'t match.')


    # Older method of defining a command
    # must start with "cmd" and end wtih the command name.
    # Aliases may be attached after the method definitions.
    def cmdECHO(self, params):
        '''<text to echo>
        Echo text back to the console.

        '''
        self.handler.writeresponse( ' '.join(params) )
    # Create an alias for this command
    cmdECHO.aliases = ['REPEAT']


    def cmdTERM(self, params):
        '''
        Hidden command to print the current TERM
        '''
        self.handler.writeresponse( self.handler.TERM )
    # Hide this command, old-style syntax.  Will not show in the help list.
    cmdTERM.hidden = True


    @cmd('hide-me', hidden=True)
    @cmd(['hide-me-too', 'also-me'])  # This adds these as aliases
    def command_do_nothing(self, params):
        '''
        Hidden command to perform no action
        '''
        self.handler.writeresponse( 'Nope, did nothing.')


    @cmd
    def connections(self, param: list[str]) -> None:
        """
        Show how many logins there have been.
        """
        self.handler.writeline(
            f"There have been {self.handler.myserver.connection_count} connections"
        )

    @cmd(["who", "users"])
    def users(self, params: list[str]) -> None:
        """
        Show who has logged in.
        """
        for user, count in self.handler.myserver.user_connect.items():
            self.handler.writeline(f"{user} : {count}")


# The TelnetHandler instance is re-created for each connection.
# Therfore, in order to store data between connections, create
# a seperate object to deal with any logic that needs to persist
# after the user logs off.
# Here is a simple example that just counts the number of connections
# as well as the number of times this user has connected.

class MyServer:
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
    # Instruct the handler to use these defined commands
    commands_class = MyCommands

    # Create the instance of the server within the class for easy use
    myserver = MyServer()

    # -- Override items to customize the server --

    WELCOME = 'You have connected to the test server.'
    PROMPT = "TestServer> "
    authNeedUser = True
    authNeedPass = False

    def authCallback(self, username, password):
        '''Called to validate the username/password.'''
        # Note that this method will be ignored if the SSH server is invoked.
        # We accept everyone here, as long as any name is given!
        if not username:
            # complain by raising any exception
            raise

    def session_start(self):
        '''Called after the user successfully logs in.'''
        self.writeline('This server is running %s.' % SERVERTYPE)

        # Tell myserver that we have a new connection, and provide the username.
        # We get back the login count information.
        globalcount, usercount = self.myserver.new_connection( self.username )

        self.writeline('Hello %s!' % self.username)
        self.writeline('You are connection #%d, you have logged in %s time(s).' % (globalcount, usercount))

        # Track any asyncronous events registered with the timer command
        self.timer_events = []

    def session_end(self):
        '''Called after the user logs off.'''

        # Cancel any pending timer events.  Done a bit different between Greenlets and threads
        if SERVERTYPE == 'green':
            for event in self.timer_events:
                event.kill()

        if SERVERTYPE == 'eventlet':
            for event in self.timer_events:
                event.kill()

        if SERVERTYPE == 'threaded':
            for event in self.timer_events:
                event.cancel()

    def writeerror(self, text):
        '''Called to write any error information (like a mistyped command).
        Add a splash of color using ANSI to render the error text in red.
        see http://en.wikipedia.org/wiki/ANSI_escape_code'''
        TelnetHandler.writeerror(self, "\x1b[91m%s\x1b[0m" % text )


    # -- Custom Commands --


if __name__ == '__main__':

    if SERVERPROTOCOL == 'SSH':
        # Import the SSH stuff
        # If we're using gevent, we have to monkey patch for the paramiko and paramiko_ssh libraries
        if SERVERTYPE == 'green':
            from gevent import monkey; monkey.patch_all()

        if SERVERTYPE == 'eventlet':
            eventlet.monkey_patch(all=True)

        from telnetsrv.paramiko_ssh import SSHHandler, getRsaKeyFile


        # Create the handler for SSH, register the defined handler for use as the PTY
        class TestSSHHandler(SSHHandler):
            telnet_handler = TestTelnetHandler
            # Create or open the server key file
            host_key = getRsaKeyFile("server_rsa.key")

        # Define which handler the server should use:
        Handler = TestSSHHandler
    else:
        Handler = TestTelnetHandler

    if SERVERTYPE == 'green':
        # Multi-green-threaded server
        server = gevent.server.StreamServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), Handler.streamserver_handle)

    if SERVERTYPE == 'eventlet':

        class EvtletStreamServer(object):
            def __init__(self, addr, handle):
                self.ip = addr[0]
                self.port = addr[1]
                self.handle = handle

            def serve_forever(self):
                eventlet.serve(
                    eventlet.listen((self.ip, self.port)),
                    self.handle
                )

        # Multi-eventlet server
        server = EvtletStreamServer(
            (TELNET_IP_BINDING, TELNET_PORT_BINDING),
            Handler.streamserver_handle
        )

    if SERVERTYPE == 'threaded':
        # Single threaded server - only one session at a time
        class TelnetServer(socketserver.TCPServer):
            allow_reuse_address = True

        server = TelnetServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), Handler)


    logging.info("Starting %s %s server at port %d.  (Ctrl-C to stop)" % (SERVERTYPE, SERVERPROTOCOL, TELNET_PORT_BINDING) )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Server shut down.")
