telnetsrvlib
============

Telnet server using gevent or threading.

Copied from http://pytelnetsrvlib.sourceforge.net/
and modified to support gevent, better input handling, clean asynchronous messages and much more.
Licensed under the LGPL, as per the SourceForge notes.

This library allows you to easily create a Telnet server, powered by your Python code.
The library negotiates with a Telnet client, parses commands, provides an automated 
help command, optionally provides login queries, then allows you to define your own
commands.

You use the library to create your own handler, then pass that handler to a StreamServer
or TCPServer to perform the actual connection tasks.

This library includes two flavors of the server handler, one uses separate threads,
the other uses greenlets (green pseudo-threads) via gevent.

The threaded version uses a separate thread to process the input buffer and
semaphores reading and writing.  The provided test server only handles a single
connection at a time.

The green version moves the input buffer processing into a greenlet to allow 
cooperative multi-processing.  This results in significantly less memory usage
and nearly no idle processing.  The provided test server handles a large number of connections.


To Use
------

Import the ``TelnetHandler`` base class and ``command`` function decorator from either the green class or threaded class, 
then subclass ``TelnetHandler`` to add your own commands as specially named methods.  

Threaded:

::

> from telnetsrv.threaded import TelnetHandler, command
> class MyHandler(TelnetHandler):
>    ...

Green:

::

> from telnetsrv.green import TelnetHandler, command
> class MyHandler(TelnetHandler):
>    ...

Add Commands
------------

Commands can be defined by using the ``command`` function decorator.

::

>   @command('echo')
>   def command_echo(self, params):
>      ...

Command Parameters
++++++++++++++++++

Any command parameters will be passed to this function automatically.  The parameters are
contained in a list.  The user input is parsed similar to the way Bash parses text - space delimited,
quoted parameters are kept together and default behavior can be modified with the ``\`` character.  
If you need to access the raw text input, inspect the self.input.raw variable.

::

   Telnet Server> echo 1  "2    3"

::

>   params == ['1', '2    3']
>   self.raw_input == 'echo 1 "2    3"'

::

    Telnet Server> echo 1 \
    ... 2 "3
    ... 4"  "5\
    ... 6"
    
::

>   params == ['1', '2', '3\n4', '56']

::

    Telnet Server> echo 1\ 2
    
::

>   params == ['1 2']

Command Help Text
+++++++++++++++++

The command's docstring is used for generating the console help information, and must be formatted
with at least 3 lines:

- Line 0:  Command parameter(s) if any. (Can be blank line)
- Line 1:  Short descriptive text. (Mandatory)
- Line 2+: Long descriptive text. (Can be blank line)

If there is no line 2, line 1 will be used for the long description as well.

::

>    @command('echo')
>    def command_echo(self, params):
>        '''<text to echo>
>        Echo text back to the console.
>        This command simply echos the provided text
>        back to the console.
>        '''
>        pass


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

::

>   @command(['echo', 'copy'])
>   def comand_echo(self, params):
>      ...

The decorator may be stacked, which adds each list to the aliases:

::

>   @command('echo')
>   @command(['copy', 'repeat'])
>   @command('ditto')
>   def comand_echo(self, params):
>      ...



Hidden Commands
+++++++++++++++

To hide the command (and any alias for that command) from the help text output, pass in hidden=True to the decorator:

::

>   @command('echo', hidden=True)
>   def comand_echo(self, params):
>      ...

The command will not show when the user invokes ``help`` by itself, but the detailed help text will show if
the user invokes ``help echo``.

When stacking decorators, any one of the stack may define the hidden parameter to hide the command.

Console Communication
---------------------

To communicate with the connected Telnet client, use:
 
- self.writeline( TEXT )
- self.write( TEXT )
- self.readline( prompt=TEXT )

- self.writemessage( TEXT ) - for clean, asynchronous writing.  Any interrupted input is rebuilt.
- self.writeresult( TEXT ) - to emit a line of expected output
- self.writeerror( TEXT ) - to emit error messages

The writemessage method is intended to send messages to the console without
interrupting any current input.  If the user has entered text at the prompt, 
the prompt and text will be seamlessly regenerated following the message.  
It is ideal for asynchronous messages that aren't generated from the direct user input.


Handler Options
---------------

Override these class members to change the handler's behavior.

``logging``
  Default: pass

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
- writeresult( TEXT ) 
- writeerror( TEXT ) 

::

>    def writeerror(self, text):
>        '''Write errors in red'''
>        TelnetHandler.writeerror(self, "\x1b[91m%s\x1b[0m" % text )

Serving the Handler
-------------------

Now you have a shiny new handler class, but it doesn't serve itself - it must be called
from an appropriate server.  The server will create an instance of the TelnetHandler class
for each new connection.  The handler class will work with either a gevent StreamServer instance
(for the green version) or with a SocketServer.TCPServer instance (for the threaded version).

Threaded
++++++++

::

> import SocketServer
> class TelnetServer(SocketServer.TCPServer):
>     allow_reuse_address = True
>    
> server = TelnetServer(("0.0.0.0", 8023), MyHandler)
> server.serve_forever()

Green
+++++

The TelnetHandler class includes a streamserver_handle class method to translate the 
required fields from a StreamServer, allowing use with the gevent StreamServer (and possibly
others).

::

> import gevent.server
> server = gevent.server.StreamServer(("", 8023), MyHandler.streamserver_handle)
> server.server_forever()


Short Example
-------------

::

> import gevent, gevent.server
> from telnetsrv.green import TelnetHandler, command
> 
> class MyTelnetHandler(TelnetHandler):
>     WELCOME = "Welcome to my server."
>     
>     @command(['echo', 'copy', 'repeat'])
>     def command_echo(self, params):
>         '''<text to echo>
>         Echo text back to the console.
>         
>         '''
>         self.writeresult( ' '.join(params) )
>
>     @command('timer')
>     def command_timer(self, params):
>         '''<time> <message>
>         In <time> seconds, display <message>.
>         Send a message after a delay.
>         <time> is in seconds.
>         If <message> is more than one word, quotes are required.
>         example: 
>         > TIMER 5 "hello world!"
>         '''
>         try:
>             timestr, message = params[:2]
>             time = int(timestr)
>         except ValueError:
>             self.writeerror( "Need both a time and a message" )
>             return
>         self.writeresult("Waiting %d seconds...", time)
>         gevent.spawn_later(time, self.writemessage, message)
>
>
> server = gevent.server.StreamServer(("", 8023), MyTelnetHandler.streamserver_handle)
> server.server_forever()

Longer Example
--------------

See https://github.com/ianepperson/telnetsrvlib/blob/master/test.py
