from distutils.core import setup

setup(
    name = "telnetsrv",
    packages = ["telnetsrv"],
    version = "0.2",
    description = "Telnet server library",
    author = "Ian Epperson",
    author_email = "ian@epperson.com",
    url = "https://github.com/ianepperson/telnetsrvlib",
    keywords = ["gevent", "telnet", "server"],
    classifiers = [
        "Programming Language :: Python",
        "Development Status :: 4 - Beta",
        "Environment :: Other Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Communications",
        "Topic :: Communications :: BBS",
        "Topic :: Terminals :: Telnet",
        ],
    long_description = """\
Telnet server using gevent or threading
---------------------------------------

This library includes two flavors of the server handler, one uses separate threads,
the other uses greenlets via gevent.

The threaded version uses a separate thread to process the input buffer and
semaphores reading and writing.  The provided test server only handles a single
connection at a time.

The green version moves the input buffer processing into a greenlet to allow 
cooperative multi-processing.  This results in significantly less memory usage
and nearly no idle processing.  The provided test server handles multiple connections,
limited only by available memory.

Subclass the class within the library to create your own telnet server.  The new class
can be given to an appropriate StreamServer (such as from Gevent for the green version) 
or a SocketServer to provide the actual services.

>>> from telnetsrv.green import TelnetHandler
>>> class MyHandler(TelnetHandler):
>>>   ...
>>> server = gevent.server.StreamServer((TELNET_IP_BINDING, TELNET_PORT_BINDING), /
                                        MyHandler.streamserver_handle)

"""
)