telnetsrvlib
============

Telnet server using gevent or threading.

Copied from http://pytelnetsrvlib.sourceforge.net/
and modified to support gevent and eventlet, better input handling, clean asynchronous messages and much more.
Licensed under the LGPL, as per the SourceForge notes.

This library allows you to easily create a Telnet or SSH server powered by your Python code.
The library negotiates with a Telnet client, parses commands, provides an automated 
help command, optionally provides login queries, then allows you to define your own
commands.  An optional SSH handler is provided to wrap the defined Telnet handler into
an SSH handler.

You use the library to create your own handler, then pass that handler to a StreamServer
or TCPServer to perform the actual connection tasks.

This library includes two flavors of the server handler, one uses separate threads,
the other uses greenlets (green pseudo-threads) via gevent or eventlet.

The threaded version uses a separate thread to process the input buffer and
semaphores reading and writing.  The provided test server only handles a single
connection at a time.

The green version moves the input buffer processing into a greenlet to allow 
cooperative multi-processing.  This results in significantly less memory usage
and nearly no idle processing.  The provided test server handles a large number of connections.


Install
-------

telnetsrv is available through the Cheeseshop.  You can use easy_install or pip to perform the installation.

:: 

 easy_install telnetsrv

or

::

 pip install telnetsrv

Note that there are no dependancies defined, but if you want to use the green version, you must also install gevent or eventlet.
If you wish to use the SSH server, you must also install paramiko.

To Use
------

Import the ``TelnetHandler`` base class and ``command`` function decorator from either the green class, evtlet class or threaded class,
then subclass ``TelnetHandler`` to add your own commands which are methods decorated with ``@command``.  

Threaded
++++++++

.. code:: python

 from telnetsrv.threaded import TelnetHandler, command
 class MyHandler(TelnetHandler):
    ...

Green
+++++

.. code:: python

 from telnetsrv.green import TelnetHandler, command
 class MyHandler(TelnetHandler):
    ...

Eventlet
++++++++

.. code:: python

 from telnetsrv.evtlet import TelnetHandler, command
 class MyHandler(TelnetHandler):
    ...

Adding Commands
---------------

Commands can be defined by using the ``command`` function decorator.

.. code:: python

  @command('echo')
  def command_echo(self, params):
     ...

Old Style
+++++++++

Commands can also be defined by prefixing any method with "cmd".  For example, 
this also creates an ``echo`` command:

.. code:: python

  def cmdECHO(self, params):
     ...

*This method is less flexible and may not be supported in future versions.*

Command Parameters
++++++++++++++++++

Any command parameters will be passed to this function automatically.  The parameters are
contained in a list.  The user input is parsed similar to the way Bash parses text: space delimited,
quoted parameters are kept together and default behavior can be modified with the ``\`` character.  
If you need to access the raw text input, inspect the self.input.raw variable.

::

   Telnet Server> echo 1  "2    3"

.. code:: python

  params == ['1', '2    3']
  self.input.raw == 'echo 1 "2    3"\n'

::

    Telnet Server> echo 1 \
    ... 2 "3
    ... 4"  "5\
    ... 6"
    
.. code:: python

  params == ['1', '2', '3\n4', '56']

::

    Telnet Server> echo 1\ 2
    
.. code:: python

  params == ['1 2']

Command Help Text
+++++++++++++++++

The command's docstring is used for generating the console help information, and must be formatted
with at least 3 lines:

- Line 0:  Command parameter(s) if any. (Can be blank line)
- Line 1:  Short descriptive text. (Mandatory)
- Line 2+: Long descriptive text. (Can be blank line)

If there is no line 2, line 1 will be used for the long description as well.

.. code:: python

   @command('echo')
   def command_echo(self, params):
       '''<text to echo>
       Echo text back to the console.
       This command simply echos the provided text
       back to the console.
       '''
       pass


::

    Telnet Server> help
    ? [<command>] - Display help
    BYE - Exit the command shell
    ECHO <text to echo> - Echo text back to the console.
    ...


    Telnet Server> help echo
    ECHO <text to echo>

    This command simply echos the provided text
    back to the console.
    Telnet Server>


Command Aliases
+++++++++++++++

To create an alias for the new command, set the method's name to a list:

.. code:: python

  @command(['echo', 'copy'])
  def command_echo(self, params):
     ...

The decorator may be stacked, which adds each list to the aliases:

.. code:: python

  @command('echo')
  @command(['copy', 'repeat'])
  @command('ditto')
  def command_echo(self, params):
     ...



Hidden Commands
+++++++++++++++

To hide the command (and any alias for that command) from the help text output, pass in hidden=True to the decorator:

.. code:: python

  @command('echo', hidden=True)
  def command_echo(self, params):
     ...

The command will not show when the user invokes ``help`` by itself, but the detailed help text will show if
the user invokes ``help echo``.

When stacking decorators, any one of the stack may define the hidden parameter to hide the command.

Console Information
-------------------

These will be provided for inspection.

``TERM``
  String ID describing the currently connected terminal

``WIDTH``
  Integer describing the width of the terminal at connection time.

``HEIGHT``
  Integer describing the height of the terminal at connection time.
  
``username``
  Set after authentication succeeds, name of the logged in user.
  If no authentication was requested, will be ``None``.
  
``history``
  List containing the command history.  This can be manipulated directly.
  

.. code:: python

    @command('info')
    def command_info(self, params):
        '''
        Provides some information about the current terminal.
        '''
        self.writeresponse( "Username: %s, terminal type: %s" % (self.username, self.TERM) )
        self.writeresponse( "Width: %s, height: %s" % (self.WIDTH, self.HEIGHT) )
        self.writeresponse( "Command history:" )
        for c in self.history:
            self.writeresponse("  %r" % c)


Console Communication
---------------------

Send Text to the Client
+++++++++++++++++++++++
 
Lower level functions:

``self.writeline( TEXT )``

``self.write( TEXT )``

Higher level functions:

``self.writemessage( TEXT )`` - for clean, asynchronous writing.  Any interrupted input is rebuilt.

``self.writeresponse( TEXT )`` - to emit a line of expected output

``self.writeerror( TEXT )`` - to emit error messages

The ``writemessage`` method is intended to send messages to the console without
interrupting any current input.  If the user has entered text at the prompt, 
the prompt and text will be seamlessly regenerated following the message.  
It is ideal for asynchronous messages that aren't generated from the direct user input.

Receive Text from the Client
++++++++++++++++++++++++++++

``self.readline( prompt=TEXT )``

Setting the prompt is important to recreate the user input following a ``writemessage``
interruption.

When requesting sensitive information from the user (such as requesting a new password) the input should
not be shown nor should the input line be written to the command history.  ``readline`` accepts
two optional parameters to control this, ``echo`` and ``use_history``.

``self.readline( prompt=TEXT, echo=False, use_history=False )``

When ``echo`` is set to False, the input will not echo back to the user.  When ``use_history`` is set 
to False, the user will not have access to the command history (up arrow) nor will the entered data
be stored in the command history.

Handler Options
---------------

Override these class members to change the handler's behavior.

``PROMPT``
  Default: ``"Telnet Server> "``
    
``CONTINUE_PROMPT``
  Default: ``"... "``
     
``WELCOME``
  Displayed after a successful connection, after the username/password is accepted, if configured.
  
  Default: ``"You have connected to the telnet server."``

``session_start(self)``
  Called after the ``WELCOME`` text is displayed.
  
  Default:  pass
    
``session_end(self)``
  Called after the console is disconnected.
  
  Default:  pass
  
``authCallback(self, username, password)`` 
  Reference to authentication function. If
  this is not defined, no username or password is requested. Should
  raise an exception if authentication fails
  
  Default: None

``authNeedUser`` 
  Should a username be requested?
  
  Default: ``False``

``authNeedPass``
  Should a password be requested?
  
  Default: ``False``


Handler Display Modification
----------------------------

If you want to change how the output is displayed, override one or all of the
write classes.  Make sure you call back to the base class when doing so.
This is a good way to provide color to your console by using ANSI color commands.
See http://en.wikipedia.org/wiki/ANSI_escape_code

- writemessage( TEXT ) 
- writeresponse( TEXT ) 
- writeerror( TEXT ) 

.. code:: python

    def writeerror(self, text):
        '''Write errors in red'''
        TelnetHandler.writeerror(self, "\x1b[91m%s\x1b[0m" % text )

Serving the Handler
-------------------

Now you have a shiny new handler class, but it doesn't serve itself - it must be called
from an appropriate server.  The server will create an instance of the TelnetHandler class
for each new connection.  The handler class will work with either a gevent StreamServer instance
(for the green version) or with a SocketServer.TCPServer instance (for the threaded version).

Threaded
++++++++

.. code:: python

 import SocketServer
 class TelnetServer(SocketServer.TCPServer):
     allow_reuse_address = True
    
 server = TelnetServer(("0.0.0.0", 8023), MyHandler)
 server.serve_forever()

Green
+++++

The TelnetHandler class includes a streamserver_handle class method to translate the 
required fields from a StreamServer, allowing use with the gevent StreamServer (and possibly
others).

.. code:: python

 import gevent.server
 server = gevent.server.StreamServer(("", 8023), MyHandler.streamserver_handle)
 server.serve_forever()


Short Example
-------------

.. code:: python

 import gevent, gevent.server
 from telnetsrv.green import TelnetHandler, command
 
 class MyTelnetHandler(TelnetHandler):
     WELCOME = "Welcome to my server."
     
     @command(['echo', 'copy', 'repeat'])
     def command_echo(self, params):
         '''<text to echo>
         Echo text back to the console.
         
         '''
         self.writeresponse( ' '.join(params) )
 
     @command('timer')
     def command_timer(self, params):
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
             self.writeerror( "Need both a time and a message" )
             return
         self.writeresponse("Waiting %d seconds...", time)
         gevent.spawn_later(time, self.writemessage, message)
 
 
 server = gevent.server.StreamServer(("", 8023), MyTelnetHandler.streamserver_handle)
 server.serve_forever()


SSH
---

If the paramiko library is installed, the TelnetHanlder can be used via an SSH server for significantly
improved security.  ``paramiko_ssh`` contains ``SSHHandler`` and ``getRsaKeyFile`` to make setting
up the server trivial.  Since the authentication is done prior to invoking the TelnetHandler,
any ``authCallback`` defined in the TelnetHandler is ignored.

Green
+++++

If using the green version of the TelnetHandler, you must use Gevent's monkey patch_all prior to
importing from ``paramiko_ssh``.

.. code:: python

    from gevent import monkey; monkey.patch_all()
    from telnetsrv.paramiko_ssh import SSHHandler, getRsaKeyFile

Eventlet
++++++++

If using the eventlet version of the TelnetHandler, you must use Eventlet's monkey patch_all prior to
importing from ``paramiko_ssh``.

.. code:: python

    import eventlet; eventlet.monkey_patch(all=True)
    from telnetsrv.paramiko_ssh import SSHHandler, getRsaKeyFile



Operation Overview
++++++++++++++++++

The SocketServer/StreamServer sets up the socket then passes that to an SSHHandler class which 
authenticates then starts the SSH transport.  Within the SSH transport, the client requests a PTY channel
(and possibly other channel types, which are denied) and the SSHHandler sets up a TelnetHandler class 
as the PTY for the channel.  If the client never requests a PTY channel, the transport will disconnect
after a timeout.

SSH Host Key
++++++++++++

To thwart man-in-the-middle attacks, every SSH server provides an RSA key as a unique fingerprint.  This unique key
should never change, and should be stored in a local file or a database.  The ``getRsaKeyFile`` makes this
easy by reading the given key file if it exists, or creating the key if it does not.  The result should be
read once and set in the class definition.

Easy way:

``host_key = getRsaKeyFile( FILENAME )``
  If the FILENAME can be read, the RSA key is read in and returned as an RSAKey object.  
  If the file can't be read, it generates a new RSA key and stores it in that file.

Long way:

.. code:: python

   from paramiko_ssh import RSAKey
   
   # Make a new key - should only be done once per server during setup
   new_key = RSAKey.generate(1024)
   save_to_my_database( 'server_fingerprint',  str(new_key) )
   
   ...
   
   host_key = RSAKey( data=get_from_my_database('server_fingerprint') )
   

SSH Authentication
++++++++++++++++++

Users can authenticate with just a username, a username/publickey or a username/password.  Up to three callbacks
can be defined, and if all three are defined, all three will be tried before denying the authentication attempt.
An SSH client will always provide a username.  If no ``authCallbackXX`` is defined, the SSH authentication will be
set to "none" and any username will be able to log in.

``authCallbackUsername(self, username)``
  Reference to username-only authentication function.  Define this function to permit specific usernames
  to log in without any futher authentication.  Raise any exception to deny this authentication attempt.
  
  If defined, this is always tried first.
  
  Default: None

``authCallbackKey(self, username, key)``
  Reference to username/key authentication function.  If this is defined,
  users can log in the SSH client automatically with a key.  Raise any exception to deny this authentication attempt.
  
  Default: None
  
``authCallback(self, username, password)`` 
  Reference to username/password authentication function. If
  this is defined, a password is requested. Raise any exception to deny this authentication attempt.
  
  If defined, this is always tried last.
  
  Default: None

  
SSHHandler uses Paramiko's ServerInterface as one of its base classes.  If you are familiar with Paramiko, feel free
to instead override the authentication callbacks as needed.


Short SSH Example
+++++++++++++++++

.. code:: python

 from gevent import monkey; monkey.patch_all()
 import gevent.server
 from telnetsrv.paramiko_ssh import SSHHandler, getRsaKeyFile
 from telnetsrv.green import TelnetHandler, command
 
 class MyTelnetHandler(TelnetHandler):
     WELCOME = "Welcome to my server."
     
     @command(['echo', 'copy', 'repeat'])
     def command_echo(self, params):
         '''<text to echo>
         Echo text back to the console.
         
         '''
         self.writeresponse( ' '.join(params) ) 
 
 class MySSHHandler(SSHHandler):
     # Set the unique host key
     host_key = getRsaKeyFile('server_fingerprint.key') 
     
     # Instruct this SSH handler to use MyTelnetHandler for any PTY connections
     telnet_handler = MyTelnetHandler
     
     def authCallbackUsername(self, username):
         # These users do not require a password
         if username not in ['john', 'eric', 'terry', 'graham']:
            raise RuntimeError('Not a Python!')
 
     def authCallback(self, username, password):
         # Super secret password:
         if password != 'concord':
            raise RuntimeError('Wrong password!')
 
 # Start a telnet server for just the localhost on port 8023.  (Will not request any authentication.)
 telnetserver = gevent.server.StreamServer(('127.0.0.1', 8023), MyTelnetHandler.streamserver_handle)
 telnetserver.start()
 
 # Start an SSH server for any local or remote host on port 8022
 sshserver = gevent.server.StreamServer(("", 8022), MySSHHandler.streamserver_handle)
 sshserver.serve_forever()


Longer Example
--------------

See https://github.com/ianepperson/telnetsrvlib/blob/master/test.py
