telnetsrvlib
============

Telnet server using gevent

Copied from http://pytelnetsrvlib.sourceforge.net/
Licensed under the LGPL, as per the SourceForge notes.

telnetsrvlib_green requires gevent to function.

The original telnetsrvlib uses a separate thread to process the input buffer and
semaphores reading and writing - as well as a few sleeps sprinkled here and there.

Added a class function to make it easy to use with a gevent StreamServer:

    server = gevent.server.StreamServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), TelnetHandler.streamserver_handle)
    server.serve_forever()


# To Use #

Import the TelnetHandler, then subclass it to add your own commands as specially named methods.  
Your command method name must with "cmd" and be followed by your command name in all caps.
    def cmdECHO(self, params):

The params is a list containing any additional parameters passed to your command.  The user
input is split(), strip()'ed then any quoted parameters are join()'ed and the quotes are stripped.
> Telnet Server> echo 1  "2    3"

    params == ['1', '2 3']

The command's docstring is used for generating the console help information, and must be formatted
with at least 3 lines:

 * Line 0:  Command paramater(s) if any. (Can be blank line)
 * Line 1:  Short descriptive text. (Mandatory)
 * Line 2+: Long descriptive text. (Can be blank line)

    def cmdECHO(self, params):
        '''<text to echo>
        Echo text back to the console.
        This function doesn't really do much
        '''
        pass

> Telnet Server> help
> ? [<command>] - Display help
> BYE - Exit the command shell
> DEBUG - Display some debugging data
> ECHO <text to echo> - Echo text back to the console.
...
> Telnet Server> help echo
> ECHO <text to echo>
> 
> Echo text back to the console.
> This function doesn't really do much


To communicate with the client, use:
 
 * self.writeline( TEXT ) 
 * self.write( TEXT )
 * self.writemessage( TEXT ) - for clean, asynchronous writing
 * self.readline( prompt=TEXT )

You can check the connected terminal type via self.TERM

To create an alias for the command, set the method's member 'aliases' to a list:
 * cmdECHO.aliases = ['COPY']
 
To hide the command from the help text output, set its 'hidden' member to True:
 * cmdECHO.hidden = True


# Class Members to Override #


 * logging
    * Default: logging

 * PROMPT
    * Default: "Telnet Server> "
     
 * WELCOME
    * Displayed after a successful connection, 
     after the username/password is accepted, 
     if configured.
    * Default: "You have connected to the telnet server."
 
 * session_start(self)
    * Called after the WELCOME is displayed.
    
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


# Example #
    import logging as my_special_logger
    
    import gevent.server
    from telnetsrvlib_green import TelnetHandler
     
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
            gevent.spawn_later(time, self.writemessage, message)
    
    
    server = gevent.server.StreamServer(("", 8023), TelnetHandler.streamserver_handle)
    server.server_forever()

