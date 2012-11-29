from binascii import hexlify

from gevent.event import Event
import gevent.server
from gevent import monkey; monkey.patch_all()
import paramiko

from green import TelnetHandler

# Grab the key from the keyfile
host_key = paramiko.RSAKey(filename='test_rsa.key')
print 'Read key: ' + hexlify(host_key.get_fingerprint())

class Server(paramiko.ServerInterface):
    def __init__(self):
        self.shell_request = Event()
    
    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        print 'check_auth_password(%s, %s)' % (username, password)
        if (username == 'ian') and (password == 'yo'):
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        print 'Auth attempt with key: ' + hexlify(key.get_fingerprint())
        #if (username == 'ian') and (key == self.good_pub_key):
        #    return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return 'password,publickey'

    def check_channel_shell_request(self, channel):
        self.shell_request.set()
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth,
                                  pixelheight, modes):
        self.term = term
        print "term: %r, modes: %r" % (term, modes)
        # modes = http://www.ietf.org/rfc/rfc4254.txt page 18
        # for i in xrange(50):
        #    print "%r: %r" % (int(m[i*5].encode('hex'), 16), int(''.join(m[i*5+1:i*5+5]).encode('hex'), 16))
        return True

class Request2Channel(object):
    def __init__(self, request):
        self._orig_request = request
        self.client = request._sock
                
        self.transport = paramiko.Transport(self.client)
        try:
            self.transport.load_server_moduli()
        except:
            print '(Failed to load moduli -- gex will be unsupported.)'
            raise
        self.transport.add_server_key(host_key)
        
        self.server = Server()
        
        try:
            self.transport.start_server(server=self.server)
        except paramiko.SSHException, e:
           print('SSH negotiation failed. %s' % e)
           raise
        
        self.channel = self.transport.accept(20)
        if self.channel is None:
            raise RuntimeError('No Channel')
        
        self.server.shell_request.wait(10)
        if not self.server.shell_request.isSet():
            raise RuntimeError('Client never asked for a shell')
        
        self._sock = self.channel
               


class SSHHandler(TelnetHandler):
    def setup(self):
        "Connect incoming connection to a telnet session"
        
        # The connected socket should be an SSH transport,
        # not to be treated like a raw socket.
        # So, pull out the original request and replace with 
        # what the rest of the handler will expect: a socket to read/write
        
        self.request = Request2Channel(self.request)
        self.sock = self.request._sock
        self.setterm(self.request.server.term)
        
        # Don't mention these, client isn't listening for them.  Blank the dicts.
        self.DOACK = {}
        self.WILLACK = {}
        
        # Call the base class setup
        TelnetHandler.setup(self)
 
    def cmdTERM(self, params):
        '''
        Hidden command to print the current TERM
        
        '''
        self.writeresponse( self.TERM )

        
print 'Starting server...'        
server = gevent.server.StreamServer(('', 10444), SSHHandler.streamserver_handle)
server.serve_forever()
