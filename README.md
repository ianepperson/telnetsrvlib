# telnetsrvlib

Telnet server using gevent, threading, or asyncio.

Copied from http://pytelnetsrvlib.sourceforge.net/
and modified to support gevent, eventlet, asyncio, better input handling, clean asynchronous messages and much more.
Licensed under the LGPL, as per the SourceForge notes.

**Requires Python 3.10 or later.**

This library allows you to easily create a Telnet or SSH server powered by your Python code.
The library negotiates with a Telnet client, parses commands, provides an automated
help command, optionally provides login queries, then allows you to define your own
commands. An optional SSH handler is provided to wrap the defined Telnet handler into
an SSH handler.

You use the library to create your own handler, then pass that handler to a StreamServer
or TCPServer to perform the actual connection tasks.

This library includes three flavors of the server handler: threaded, green, and asyncio.

The threaded version uses a separate thread to process the input buffer and
semaphores reading and writing. The provided test server only handles a single
connection at a time.

The green version moves the input buffer processing into a greenlet to allow
cooperative multi-processing. This results in significantly less memory usage
and nearly no idle processing. The provided test server handles a large number of connections.

The asyncio version integrates with Python's built-in asyncio event loop, requiring
no extra dependencies. It supports async command handlers and handles multiple
connections efficiently.


## Install

telnetsrv is available on PyPI and can be installed with pip:

```
pip install telnetsrv
```

Note that there are no required dependencies beyond the Python standard library, but if you want to use the green version you must also install gevent or eventlet, and if you wish to use the SSH server you must also install paramiko:

```
pip install telnetsrv[green]   # includes gevent
pip install telnetsrv[ssh]     # includes paramiko
```

## To Use

Import `TelnetHandler`, the `cmd` decorator, and the `Commands` base class from either
the threaded, green, or evtlet module. Define your commands by subclassing `Commands`,
then point your `TelnetHandler` subclass at that commands class.

### Threaded

```python
from telnetsrv.threaded import TelnetHandler, cmd, Commands

class MyCommands(Commands):
   ...

class MyHandler(TelnetHandler):
   commands_class = MyCommands
```

### Green

```python
from telnetsrv.green import TelnetHandler, cmd, Commands

class MyCommands(Commands):
   ...

class MyHandler(TelnetHandler):
   commands_class = MyCommands
```

### Eventlet

```python
from telnetsrv.evtlet import TelnetHandler, cmd, Commands

class MyCommands(Commands):
   ...

class MyHandler(TelnetHandler):
   commands_class = MyCommands
```

### Async (asyncio)

```python
from telnetsrv.aio import TelnetHandler, cmd, Commands

class MyCommands(Commands):
   ...

class MyHandler(TelnetHandler):
   commands_class = MyCommands
```

## Adding Commands

Commands are defined as methods of a `Commands` subclass, decorated with `@cmd`.

```python
class MyCommands(Commands):
    @cmd('echo')
    def echo(self, params):
        self.handler.writeresponse(' '.join(params))

class MyHandler(TelnetHandler):
    commands_class = MyCommands
```

Within a command method, `self` is the `Commands` instance. Use `self.handler`
to reach the telnet handler and all of its I/O methods and session attributes.

### Old Style

Commands can also be defined by prefixing any method name with `cmd`. For example,
this also creates an `echo` command:

```python
class MyCommands(Commands):
    def cmdECHO(self, params):
        self.handler.writeresponse(' '.join(params))
```

*This method is less flexible and may not be supported in future versions.*

### Command Parameters

Any command parameters will be passed to this function automatically. The parameters are
contained in a list. The user input is parsed similar to the way Bash parses text: space delimited,
quoted parameters are kept together and default behavior can be modified with the `\` character.
If you need to access the raw text input, inspect `self.handler.input.raw`.

```
Telnet Server> echo 1  "2    3"
```

```python
params == ['1', '2    3']
self.handler.input.raw == 'echo 1 "2    3"\n'
```

```
Telnet Server> echo 1 \
... 2 "3
... 4"  "5\
... 6"
```

```python
params == ['1', '2', '3\n4', '56']
```

```
Telnet Server> echo 1\ 2
```

```python
params == ['1 2']
```

### Command Help Text

The command's docstring is used for generating the console help information, and must be formatted
with at least 3 lines:

- Line 0: Command parameter(s) if any. (Can be blank line)
- Line 1: Short descriptive text. (Mandatory)
- Line 2+: Long descriptive text. (Can be blank line)

If there is no line 2, line 1 will be used for the long description as well.

```python
class MyCommands(Commands):
    @cmd('echo')
    def echo(self, params):
        '''<text to echo>
        Echo text back to the console.
        This command simply echos the provided text
        back to the console.
        '''
        self.handler.writeresponse(' '.join(params))
```

```
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
```

### Command Aliases

To create aliases for a command, pass a list of names to the decorator:

```python
@cmd(['echo', 'copy'])
def echo(self, params):
   ...
```

The decorator may be stacked, which adds each list to the aliases:

```python
@cmd('echo')
@cmd(['copy', 'repeat'])
@cmd('ditto')
def echo(self, params):
   ...
```

### Hidden Commands

To hide the command (and any alias for that command) from the help text output, pass in `hidden=True` to the decorator:

```python
@cmd('echo', hidden=True)
def echo(self, params):
   ...
```

The command will not show when the user invokes `help` by itself, but the detailed help text will show if
the user invokes `help echo`.

When stacking decorators, any one of the stack may define the hidden parameter to hide the command.

### Handling Unknown Commands

If the user enters a command that is not defined, `_command_not_found` is called on the `Commands`
instance. By default it writes a reasonable error message back to the client. Override this method
in your `Commands` subclass to provide custom handling — for example, to implement a dynamic command
dispatcher or to log unrecognised input.

```python
class MyCommands(Commands):
    def _command_not_found(self, command, params):
        '''
        Called when no registered command matches the user's input.

        ``command`` is the uppercased command name the user typed.
        ``params``  is the list of parsed arguments (may be empty).
        '''
        self.handler.writeerror(f"Unknown command '{command}'")
```

A common use is to act as a catch-all that forwards commands to another system:

```python
class MyCommands(Commands):
    def _command_not_found(self, command, params):
        result = my_backend.run(command, params)
        if result is None:
            self.handler.writeerror(f"Unknown command '{command}'")
        else:
            self.handler.writeresponse(result)
```

When using the async handler, `_command_not_found` may also be a coroutine:

```python
class MyCommands(Commands):
    async def _command_not_found(self, command, params):
        result = await my_backend.run(command, params)
        if result is None:
            self.handler.writeerror(f"Unknown command '{command}'")
        else:
            self.handler.writeresponse(result)
```


## Console Information

These handler attributes are available for inspection. Within a command method, access them
via `self.handler`; within handler lifecycle methods (`session_start`, `session_end`, etc.),
access them directly as `self`.

- **`TERM`** — String ID describing the currently connected terminal
- **`WIDTH`** — Integer describing the width of the terminal at connection time.
- **`HEIGHT`** — Integer describing the height of the terminal at connection time.
- **`username`** — Set after authentication succeeds, name of the logged in user. If no authentication was requested, will be `None`.
- **`history`** — List containing the command history. This can be manipulated directly.

```python
class MyCommands(Commands):
    @cmd('info')
    def info(self, params):
        '''
        Provides some information about the current terminal.
        '''
        self.handler.writeresponse(
            "Username: %s, terminal type: %s" % (self.handler.username, self.handler.TERM)
        )
        self.handler.writeresponse(
            "Width: %s, height: %s" % (self.handler.WIDTH, self.handler.HEIGHT)
        )
        self.handler.writeresponse("Command history:")
        for c in self.handler.history:
            self.handler.writeresponse("  %r" % c)
```


## Console Communication

### Send Text to the Client

Within a command method, reach the handler via `self.handler`:

Lower level functions:

- `self.handler.writeline( TEXT )`
- `self.handler.write( TEXT )`

Higher level functions:

- `self.handler.writemessage( TEXT )` — for clean, asynchronous writing. Any interrupted input is rebuilt.
- `self.handler.writeresponse( TEXT )` — to emit a line of expected output
- `self.handler.writeerror( TEXT )` — to emit error messages

The `writemessage` method is intended to send messages to the console without
interrupting any current input. If the user has entered text at the prompt,
the prompt and text will be seamlessly regenerated following the message.
It is ideal for asynchronous messages that aren't generated from the direct user input.

### Receive Text from the Client

`self.handler.readline( prompt=TEXT )`

Setting the prompt is important to recreate the user input following a `writemessage`
interruption.

When requesting sensitive information from the user (such as requesting a new password) the input should
not be shown nor should the input line be written to the command history. `readline` accepts
two optional parameters to control this, `echo` and `use_history`.

`self.handler.readline( prompt=TEXT, echo=False, use_history=False )`

When `echo` is set to False, the input will not echo back to the user. When `use_history` is set
to False, the user will not have access to the command history (up arrow) nor will the entered data
be stored in the command history.

## Handler Options

Override these class members on `TelnetHandler` to change the handler's behavior.
Within these methods, `self` is the handler, so I/O methods are called directly (`self.writeline`, etc.).

- **`PROMPT`** — Default: `"Telnet Server> "`
- **`CONTINUE_PROMPT`** — Default: `"... "`
- **`WELCOME`** — Displayed after a successful connection, after the username/password is accepted, if configured. Default: `"You have connected to the telnet server."`
- **`session_start(self)`** — Called after the `WELCOME` text is displayed. Default: pass
- **`session_end(self)`** — Called after the console is disconnected. Default: pass
- **`authCallback(self, username, password)`** — Reference to authentication function. If this is not defined, no username or password is requested. Should raise an exception if authentication fails. Default: None
- **`authNeedUser`** — Should a username be requested? Default: `False`
- **`authNeedPass`** — Should a password be requested? Default: `False`


## Handler Display Modification

If you want to change how the output is displayed, override one or all of the
write methods on `TelnetHandler`. Make sure you call back to the base class when doing so.
This is a good way to provide color to your console by using ANSI color commands.
See [the ANSI Wikipedia article](https://en.wikipedia.org/wiki/ANSI_escape_code)

- `writemessage( TEXT )`
- `writeresponse( TEXT )`
- `writeerror( TEXT )`

```python
class MyHandler(TelnetHandler):
    def writeerror(self, text):
        '''Write errors in red'''
        TelnetHandler.writeerror(self, "\x1b[91m%s\x1b[0m" % text )
```

## Serving the Handler

Now you have a shiny new handler class, but it doesn't serve itself - it must be called
from an appropriate server. The server will create an instance of the TelnetHandler class
for each new connection. The handler class will work with a gevent StreamServer instance (for the green version),
a `socketserver.TCPServer` instance (for the threaded version), or `asyncio.start_server`
(for the asyncio version).

### Threaded

```python
import socketserver
class TelnetServer(socketserver.TCPServer):
    allow_reuse_address = True

server = TelnetServer(("0.0.0.0", 8023), MyHandler)
server.serve_forever()
```

### Green

The TelnetHandler class includes a `streamserver_handle` class method to translate the
required fields from a StreamServer, allowing use with the gevent StreamServer (and possibly
others).

```python
import gevent.server
server = gevent.server.StreamServer(("", 8023), MyHandler.streamserver_handle)
server.serve_forever()
```

### Async

Pass the `asyncio_handle` classmethod to `asyncio.start_server`. No extra dependencies are
required — asyncio is part of the Python standard library.

```python
import asyncio

async def main():
    server = await asyncio.start_server(
        MyHandler.asyncio_handle, host="", port=8023
    )
    async with server:
        await server.serve_forever()

asyncio.run(main())
```

Command methods may be regular functions **or** coroutines; the handler detects and awaits
coroutines automatically:

```python
class MyCommands(Commands):
    @cmd('timer')
    async def timer(self, params):
        '''<time> <message>
        In <time> seconds, display <message>.
        '''
        try:
            delay, message = int(params[0]), params[1]
        except (ValueError, IndexError):
            self.handler.writeerror("Need both a time and a message")
            return
        self.handler.writeresponse(f"Waiting {delay} seconds...")
        await asyncio.sleep(delay)
        self.handler.writemessage(message)
```

The write methods (`writeresponse`, `writeerror`, `writemessage`, `writeline`, `write`) are
**not** coroutines and should not be awaited. They buffer output synchronously into the asyncio
stream; the data is flushed to the network automatically between command invocations.

`session_start` and `session_end` may also be defined as coroutines in the async handler.


## Short Example

```python
import asyncio
from telnetsrv.aio import TelnetHandler, cmd, Commands

class MyCommands(Commands):
    @cmd(['echo', 'copy', 'repeat'])
    def echo(self, params):
        '''<text to echo>
        Echo text back to the console.

        '''
        self.handler.writeresponse(' '.join(params))

    @cmd('timer')
    async def timer(self, params):
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
            delay = int(timestr)
        except ValueError:
            self.handler.writeerror("Need both a time and a message")
            return
        self.handler.writeresponse("Waiting %d seconds..." % delay)
        await asyncio.sleep(delay)
        self.handler.writemessage(message)


class MyTelnetHandler(TelnetHandler):
    WELCOME = "Welcome to my server."
    commands_class = MyCommands


async def main():
    server = await asyncio.start_server(
        MyTelnetHandler.asyncio_handle, host="", port=8023
    )
    async with server:
        await server.serve_forever()

asyncio.run(main())
```


## SSH

If the paramiko library is installed, the TelnetHandler can be used via an SSH server for significantly
improved security. `paramiko_ssh` contains `SSHHandler` and `getRsaKeyFile` to make setting
up the server trivial. Since the authentication is done prior to invoking the TelnetHandler,
any `authCallback` defined in the TelnetHandler is ignored.

### Green

If using the green version of the TelnetHandler, you must use Gevent's monkey `patch_all` prior to
importing from `paramiko_ssh`.

```python
from gevent import monkey; monkey.patch_all()
from telnetsrv.paramiko_ssh import SSHHandler, getRsaKeyFile
```

### Eventlet

If using the eventlet version of the TelnetHandler, you must use Eventlet's monkey `patch_all` prior to
importing from `paramiko_ssh`.

```python
import eventlet; eventlet.monkey_patch(all=True)
from telnetsrv.paramiko_ssh import SSHHandler, getRsaKeyFile
```

### Async

The `aio_ssh` module provides `AsyncSSHHandler`, which pairs with an `aio.TelnetHandler` subclass.
Paramiko's SSH transport is still blocking and thread-based; once a PTY channel is established,
`asyncio.run()` creates a fresh event loop in that thread and runs the async handler inside it.
No monkey-patching is needed.

```python
from telnetsrv.aio_ssh import AsyncSSHHandler, getRsaKeyFile
from telnetsrv.aio import TelnetHandler, cmd, Commands
```


### Operation Overview

The `socketserver.TCPServer` or gevent/eventlet `StreamServer` sets up the socket then passes that
to an SSHHandler class which authenticates then starts the SSH transport. Within the SSH transport,
the client requests a PTY channel (and possibly other channel types, which are denied) and the
SSHHandler sets up a TelnetHandler class as the PTY for the channel. If the client never requests
a PTY channel, the transport will disconnect after a timeout.

### SSH Host Key

To thwart man-in-the-middle attacks, every SSH server provides a key as a unique fingerprint. This unique key
should never change, and should be stored in a local file or a database. `getKeyFile` makes this
easy by reading the given key file if it exists, or generating a new Ed25519 key if it does not. The result should be
read once and set in the class definition.

Easy way:

`host_key = getKeyFile( FILENAME )` — If FILENAME can be read, the key is read in and returned. Reads any key type supported by paramiko (Ed25519, RSA, ECDSA). If the file can't be read, generates a new Ed25519 key and stores it in that file.

Long way:

```python
from paramiko import Ed25519Key, PKey

# Generate a new key - should only be done once per server during setup
new_key = Ed25519Key.generate()
new_key.write_private_key_file('server.key')

...

host_key = PKey.from_path('server.key')
```

> **Upgrading from paramiko < 5:** Existing RSA host key files are read without modification — `getKeyFile` auto-detects the key type. Clients connecting via the legacy `ssh-rsa` algorithm (SHA-1) will no longer be able to connect; modern SSH clients use `rsa-sha2-256`, `rsa-sha2-512`, or Ed25519 and are unaffected.

> **`getRsaKeyFile` is deprecated** but still works as an alias for `getKeyFile`.

### SSH Authentication

Users can authenticate with just a username, a username/publickey or a username/password. Up to three callbacks
can be defined, and if all three are defined, all three will be tried before denying the authentication attempt.
An SSH client will always provide a username. If no `authCallbackXX` is defined, the SSH authentication will be
set to "none" and any username will be able to log in.

When "none" authentication is active, a warning is logged each time a connection is established as a reminder
that the server is unauthenticated. If this is intentional (e.g. a local development server), suppress the
warning by setting `warn_of_insecure_auth = False` in your `SSHHandler` subclass:

```python
class MySSHHandler(SSHHandler):
    host_key = getKeyFile('server_fingerprint.key')
    telnet_handler = MyTelnetHandler
    warn_of_insecure_auth = False  # suppress warning: no auth is intentional
```

- **`authCallbackUsername(self, username)`** — Reference to username-only authentication function. Define this function to permit specific usernames to log in without any further authentication. Raise any exception to deny this authentication attempt. If defined, this is always tried first. Default: None
- **`authCallbackKey(self, username, key)`** — Reference to username/key authentication function. If this is defined, users can log in the SSH client automatically with a key. Raise any exception to deny this authentication attempt. Default: None
- **`authCallback(self, username, password)`** — Reference to username/password authentication function. If this is defined, a password is requested. Raise any exception to deny this authentication attempt. If defined, this is always tried last. Default: None

SSHHandler uses Paramiko's ServerInterface as one of its base classes. If you are familiar with Paramiko, feel free
to instead override the authentication callbacks as needed.


### Short SSH Example

```python
from gevent import monkey; monkey.patch_all()
import gevent.server
from telnetsrv.paramiko_ssh import SSHHandler, getKeyFile
from telnetsrv.green import TelnetHandler, cmd, Commands

class MyCommands(Commands):
    @cmd(['echo', 'copy', 'repeat'])
    def echo(self, params):
        '''<text to echo>
        Echo text back to the console.

        '''
        self.handler.writeresponse(' '.join(params))

class MyTelnetHandler(TelnetHandler):
    WELCOME = "Welcome to my server."
    commands_class = MyCommands

class MySSHHandler(SSHHandler):
    # Set the unique host key
    host_key = getKeyFile('server_fingerprint.key')

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
```


## Short Async SSH Example

```python
import socketserver
from telnetsrv.aio_ssh import AsyncSSHHandler, getKeyFile
from telnetsrv.aio import TelnetHandler, cmd, Commands

class MyCommands(Commands):
    @cmd(['echo', 'copy', 'repeat'])
    async def echo(self, params):
        '''<text to echo>
        Echo text back to the console.

        '''
        self.handler.writeresponse(' '.join(params))

class MyTelnetHandler(TelnetHandler):
    WELCOME = "Welcome to my server."
    commands_class = MyCommands

class MySSHHandler(AsyncSSHHandler):
    host_key = getKeyFile('server_fingerprint.key')
    telnet_handler = MyTelnetHandler

    def authCallbackUsername(self, username):
        if username not in ['john', 'eric', 'terry', 'graham']:
            raise RuntimeError('Not a Python!')

    def authCallback(self, username, password):
        if password != 'concord':
            raise RuntimeError('Wrong password!')

class TelnetServer(socketserver.TCPServer):
    allow_reuse_address = True

server = TelnetServer(('', 8022), MySSHHandler)
server.serve_forever()
```


## Longer Example

See https://github.com/ianepperson/telnetsrvlib/blob/master/example.py

Demonstrates the threaded and green flavors of the library. Accepts `--green`
(gevent), `--eventlet`, or defaults to threaded. Also supports `--ssh` via
`SSHHandler` with Paramiko. The `timer` command uses `gevent.spawn_later`,
`eventlet.spawn_after`, or `threading.Timer` depending on the selected backend,
and `passwd` uses the synchronous `handler.readline()` for secure input.

## Asyncio Example

See https://github.com/ianepperson/telnetsrvlib/blob/master/example-asyncio.py

Demonstrates the asyncio flavor of the library. Supports both plain telnet
(served via `asyncio.start_server`) and SSH (served via `socketserver.TCPServer`
with `AsyncSSHHandler`, which runs each session's async handler in its own
`asyncio.run()` call). The `timer` command uses `asyncio.create_task` for
non-blocking delayed messages, and `passwd` uses `await handler.readline()`
for secure input.
