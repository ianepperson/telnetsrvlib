# license: LGPL
# For distribution, see the COPYING.txt file that accompanies this file.
"""TELNET server class

Based on the telnet client in telnetlib.py

Presents a command line interface to the telnet client.
Various settings can affect the operation of the server:

    authCallback = Reference to authentication function. If
                   there is none, no un/pw is requested. Should
                   raise an exception if authentication fails
                   Default: None
    authNeedUser = Should a username be requested?
                   Default: False
    authNeedPass = Should a password be requested?
                   Default: False
    COMMANDS     = Dictionary of supported commands
                   Key = command (Must be upper case)
                   Value = List of (function, help text)
                   Function.__doc__ should be long help
                   Function.aliases may be a list of alternative spellings
"""

import socketserver
import socket
import sys
import traceback
import curses.ascii
import curses
import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

BELL = chr(7)
ESC = chr(27)
ANSI_START_SEQ = "["
ANSI_KEY_TO_CURSES = {
    "A": curses.KEY_UP,
    "B": curses.KEY_DOWN,
    "C": curses.KEY_RIGHT,
    "D": curses.KEY_LEFT,
}

IAC = chr(255)  # "Interpret As Command"
DONT = chr(254)
DO = chr(253)
WONT = chr(252)
WILL = chr(251)
theNULL = chr(0)

SE = chr(240)  # Subnegotiation End
NOP = chr(241)  # No Operation
DM = chr(242)  # Data Mark
BRK = chr(243)  # Break
IP = chr(244)  # Interrupt process
AO = chr(245)  # Abort output
AYT = chr(246)  # Are You There
EC = chr(247)  # Erase Character
EL = chr(248)  # Erase Line
GA = chr(249)  # Go Ahead
SB = chr(250)  # Subnegotiation Begin

BINARY = chr(0)  # 8-bit data path
ECHO = chr(1)  # echo
RCP = chr(2)  # prepare to reconnect
SGA = chr(3)  # suppress go ahead
NAMS = chr(4)  # approximate message size
STATUS = chr(5)  # give status
TM = chr(6)  # timing mark
RCTE = chr(7)  # remote controlled transmission and echo
NAOL = chr(8)  # negotiate about output line width
NAOP = chr(9)  # negotiate about output page size
NAOCRD = chr(10)  # negotiate about CR disposition
NAOHTS = chr(11)  # negotiate about horizontal tabstops
NAOHTD = chr(12)  # negotiate about horizontal tab disposition
NAOFFD = chr(13)  # negotiate about formfeed disposition
NAOVTS = chr(14)  # negotiate about vertical tab stops
NAOVTD = chr(15)  # negotiate about vertical tab disposition
NAOLFD = chr(16)  # negotiate about output LF disposition
XASCII = chr(17)  # extended ascii character set
LOGOUT = chr(18)  # force logout
BM = chr(19)  # byte macro
DET = chr(20)  # data entry terminal
SUPDUP = chr(21)  # supdup protocol
SUPDUPOUTPUT = chr(22)  # supdup output
SNDLOC = chr(23)  # send location
TTYPE = chr(24)  # terminal type
EOR = chr(25)  # end or record
TUID = chr(26)  # TACACS user identification
OUTMRK = chr(27)  # output marking
TTYLOC = chr(28)  # terminal location number
VT3270REGIME = chr(29)  # 3270 regime
X3PAD = chr(30)  # X.3 PAD
NAWS = chr(31)  # window size
TSPEED = chr(32)  # terminal speed
LFLOW = chr(33)  # remote flow control
LINEMODE = chr(34)  # Linemode option
XDISPLOC = chr(35)  # X Display Location
OLD_ENVIRON = chr(36)  # Old - Environment variables
AUTHENTICATION = chr(37)  # Authenticate
ENCRYPT = chr(38)  # Encryption option
NEW_ENVIRON = chr(39)  # New - Environment variables
# the following ones come from
# http://www.iana.org/assignments/telnet-options
# Unfortunately, that document does not assign identifiers
# to all of them, so we are making them up
TN3270E = chr(40)  # TN3270E
XAUTH = chr(41)  # XAUTH
CHARSET = chr(42)  # CHARSET
RSP = chr(43)  # Telnet Remote Serial Port
COM_PORT_OPTION = chr(44)  # Com Port Control Option
SUPPRESS_LOCAL_ECHO = chr(45)  # Telnet Suppress Local Echo
TLS = chr(46)  # Telnet Start TLS
KERMIT = chr(47)  # KERMIT
SEND_URL = chr(48)  # SEND-URL
FORWARD_X = chr(49)  # FORWARD_X
PRAGMA_LOGON = chr(138)  # TELOPT PRAGMA LOGON
SSPI_LOGON = chr(139)  # TELOPT SSPI LOGON
PRAGMA_HEARTBEAT = chr(140)  # TELOPT PRAGMA HEARTBEAT
EXOPL = chr(255)  # Extended-Options-List
NOOPT = chr(0)

# Codes used in SB SE data stream for terminal type negotiation
IS = chr(0)
SEND = chr(1)

# Maps curses key constants to terminal capability names for curses.tigetstr()
KEY_CAPABILITY_NAMES: dict[int, str] = {
    curses.KEY_UP: "kcuu1",
    curses.KEY_DOWN: "kcud1",
    curses.KEY_LEFT: "kcub1",
    curses.KEY_RIGHT: "kcuf1",
    curses.KEY_DC: "kdch1",
    curses.KEY_BACKSPACE: "kbs",
}

CMDS = {
    WILL: "WILL",
    WONT: "WONT",
    DO: "DO",
    DONT: "DONT",
    SE: "Subnegotiation End",
    NOP: "No Operation",
    DM: "Data Mark",
    BRK: "Break",
    IP: "Interrupt process",
    AO: "Abort output",
    AYT: "Are You There",
    EC: "Erase Character",
    EL: "Erase Line",
    GA: "Go Ahead",
    SB: "Subnegotiation Begin",
    BINARY: "Binary",
    ECHO: "Echo",
    RCP: "Prepare to reconnect",
    SGA: "Suppress Go-Ahead",
    NAMS: "Approximate message size",
    STATUS: "Give status",
    TM: "Timing mark",
    RCTE: "Remote controlled transmission and echo",
    NAOL: "Negotiate about output line width",
    NAOP: "Negotiate about output page size",
    NAOCRD: "Negotiate about CR disposition",
    NAOHTS: "Negotiate about horizontal tabstops",
    NAOHTD: "Negotiate about horizontal tab disposition",
    NAOFFD: "Negotiate about formfeed disposition",
    NAOVTS: "Negotiate about vertical tab stops",
    NAOVTD: "Negotiate about vertical tab disposition",
    NAOLFD: "Negotiate about output LF disposition",
    XASCII: "Extended ascii character set",
    LOGOUT: "Force logout",
    BM: "Byte macro",
    DET: "Data entry terminal",
    SUPDUP: "Supdup protocol",
    SUPDUPOUTPUT: "Supdup output",
    SNDLOC: "Send location",
    TTYPE: "Terminal type",
    EOR: "End or record",
    TUID: "TACACS user identification",
    OUTMRK: "Output marking",
    TTYLOC: "Terminal location number",
    VT3270REGIME: "3270 regime",
    X3PAD: "X.3 PAD",
    NAWS: "Window size",
    TSPEED: "Terminal speed",
    LFLOW: "Remote flow control",
    LINEMODE: "Linemode option",
    XDISPLOC: "X Display Location",
    OLD_ENVIRON: "Old - Environment variables",
    AUTHENTICATION: "Authenticate",
    ENCRYPT: "Encryption option",
    NEW_ENVIRON: "New - Environment variables",
}


class command:
    """Function decorator to define a telnet command."""

    def __init__(self, names: str | list[str], hidden: bool = False) -> None:
        if isinstance(names, str):
            self.name = names
            self.alias: list[str] = []
        else:
            self.name = names[0]
            self.alias = list(names[1:])
        self.hidden = hidden

    def __call__(self, fn: Callable) -> Callable:
        if hasattr(fn, "aliases"):
            # More than one decorator: prepend to the existing alias list.
            fn.aliases.append(fn.command_name)
            fn.aliases.extend(self.alias)
            fn.command_name = self.name
            fn.hidden = self.hidden or fn.hidden
        else:
            fn.aliases = self.alias
            fn.command_name = self.name
            fn.hidden = self.hidden
        return fn


class InputSimple:
    """Simple line handler.

    All spaces become one, can have quoted parameters, but not null.
    """

    quote_chars = ['"', "'"]

    def __init__(self, handler: Any, line: str) -> None:
        self.parts: list[str] = []
        self.process(line)

    @property
    def cmd(self) -> str:
        try:
            return self.parts[0]
        except IndexError:
            return ""

    @property
    def params(self) -> list[str]:
        return self.parts[1:]

    def process(self, line: str) -> None:
        line = line.strip()
        self.raw = line
        cmdlist = [item.strip() for item in line.split()]
        idx = 0
        while idx < (len(cmdlist) - 1):
            if cmdlist[idx][0] in ["'", '"']:
                cmdlist[idx] = cmdlist[idx] + " " + cmdlist.pop(idx + 1)
                if cmdlist[idx][0] != cmdlist[idx][-1]:
                    continue
                cmdlist[idx] = cmdlist[idx][1:-1]
            idx = idx + 1
        self.parts = cmdlist


class InputBashLike:
    """Handles escaped characters, quoted parameters and multi-line input like Bash."""

    quote_chars = ['"', "'"]
    whitespace = [" ", "\t"]
    escape_char = "\\"
    escape_results = {"\\": "\\", "t": "\t", "n": "\n", " ": " ", '"': '"', "'": "'"}
    continue_prompt = "... "
    eol_char = "\n"

    def __init__(self, handler: Any, line: str) -> None:
        self.raw = ""
        self.handler = handler
        self.complete = False
        self.inquote: str | bool = False
        self.parts: list[str] = []
        self.part: list[str] = []
        # Set up the initial processing state.
        self.process_char = self.process_delimiter
        self.process(line)

    @property
    def cmd(self) -> str:
        try:
            return self.parts[0]
        except IndexError:
            return ""

    @property
    def params(self) -> list[str]:
        return self.parts[1:]

    # The process_x functions handle different states while stepping through line chars.

    def process_delimiter(self, char: str) -> None:
        """Process chars while not in a part"""
        if char in self.whitespace:
            return
        if char in self.quote_chars:
            # Store the quote type (' or ") and switch to quote processing.
            self.inquote = char
            self.process_char = self.process_quote
            return
        if char == self.eol_char:
            self.complete = True
            return
        # Switch to processing a part.
        self.process_char = self.process_part
        self.process_char(char)

    def process_part(self, char: str) -> None:
        """Process chars while in a part"""
        if char in self.whitespace or char == self.eol_char:
            # End of the part.
            self.parts.append("".join(self.part))
            self.part = []
            # Switch back to processing a delimiter.
            self.process_char = self.process_delimiter
            if char == self.eol_char:
                self.complete = True
            return
        if char in self.quote_chars:
            # Store the quote type (' or ") and switch to quote processing.
            self.inquote = char
            self.process_char = self.process_quote
            return
        self.part.append(char)

    def process_quote(self, char: str) -> None:
        """Process character while in a quote"""
        if char == self.inquote:
            # Quote is finished, switch to part processing.
            self.process_char = self.process_part
            return
        self.part.append(char)

    def process_escape(self, char: str) -> None:
        """Handle the char after the escape char"""
        # Always only run once, switch back to the last processor.
        self.process_char = self.last_process_char
        if self.part == [] and char in self.whitespace:
            # Special case where \ is by itself and not at the EOL.
            self.parts.append(self.escape_char)
            return
        if char == self.eol_char:
            # Ignore a cr.
            return
        unescaped = self.escape_results.get(char, self.escape_char + char)
        self.part.append(unescaped)

    def process(self, line: str) -> None:
        """Step through the line and process each character"""
        self.raw = self.raw + line
        try:
            if not line[-1] == self.eol_char:
                # Should always be here, but add it just in case.
                line = line + self.eol_char
        except IndexError:
            # Thrown if line == ''
            line = self.eol_char

        for char in line:
            if char == self.escape_char:
                # Always handle escaped characters.
                self.last_process_char = self.process_char
                self.process_char = self.process_escape
                continue
            self.process_char(char)
        if not self.complete:
            # Ask for more.
            self.process(self.handler.readline(prompt=self.handler.CONTINUE_PROMPT))


class TelnetHandlerBase(socketserver.BaseRequestHandler):
    "A telnet server based on the client in telnetlib"

    # Several methods are not fully defined in this class, and are
    # very specific to either a threaded or green implementation.
    # These methods are noted as #abstracmethods to ensure they are
    # properly made concrete.
    # (abc doesn't like the BaseRequestHandler - sigh)
    # __metaclass__ = ABCMeta

    # What I am prepared to do?
    DOACK: dict[str, str] = {
        ECHO: WILL,
        SGA: WILL,
        NEW_ENVIRON: WONT,
    }
    # What do I want the client to do?
    WILLACK: dict[str, str] = {
        ECHO: DONT,
        SGA: DO,
        NAWS: DONT,
        TTYPE: DO,
        LINEMODE: DONT,
        NEW_ENVIRON: DO,
    }
    # Default terminal type - used if client doesn't tell us its termtype
    TERM: str = "ansi"
    # Keycode to name mapping - used to decide which keys to query
    KEYS: dict[int, str] = {  # Key escape sequences
        curses.KEY_UP: "Up",  # Cursor up
        curses.KEY_DOWN: "Down",  # Cursor down
        curses.KEY_LEFT: "Left",  # Cursor left
        curses.KEY_RIGHT: "Right",  # Cursor right
        curses.KEY_DC: "Delete",  # Delete right
        curses.KEY_BACKSPACE: "Backspace",  # Delete left
    }
    # Reverse mapping of KEYS - used for cooking key codes
    ESCSEQ: dict[str, int] = {}
    # Terminal output escape sequences
    CODES: dict[str, str] = {
        "DEOL": "",  # Delete to end of line
        "DEL": "",  # Delete and close up
        "INS": "",  # Insert space
        "CSRLEFT": "",  # Move cursor left 1 space
        "CSRRIGHT": "",  # Move cursor right 1 space
    }
    # What prompt to display
    PROMPT: str = "Telnet Server> "
    # What prompt to use for requesting more input
    CONTINUE_PROMPT: str = "... "
    # What to display upon connection
    WELCOME: str = "You have connected to the telnet server."
    # The function to call to verify authentication data
    authCallback: Callable | None = None
    # Does authCallback want a username?
    authNeedUser: bool = False
    # Does authCallback want a password?
    authNeedPass: bool = False
    # Default username
    username: str | None = None
    # What will handle our inputs?
    # input_reader = InputSimple
    input_reader = InputBashLike
    # Banner to display prior to telnet login
    TELNET_ISSUE: str | None = None
    # What prompt to use when requesting a telnet username
    PROMPT_USER: str = "Username: "
    # What prompt to use when requesting a telnet password
    PROMPT_PASS: str = "Password: "

    # --------------------------- Environment Setup ----------------------------

    def __init__(self, request: Any, client_address: Any, server: Any) -> None:
        """Constructor.

        When called without arguments, create an unconnected instance.
        With a hostname argument, it connects the instance; a port
        number is optional.
        """
        # Am I doing the echoing?
        self.DOECHO = True
        # What opts have I sent DO/DONT for and what did I send?
        self.DOOPTS: dict[str, bool | None] = {}
        # What opts have I sent WILL/WONT for and what did I send?
        self.WILLOPTS: dict[str, bool | str] = {}

        # What commands does this CLI support
        self.COMMANDS: dict[str, Callable] = {}
        self.sock = None  # TCP socket
        self.rawq = ""  # Raw input string
        self.sbdataq = ""  # Sub-Neg string
        self.eof = 0  # Has EOF been reached?
        self.iacseq = ""  # Buffer for IAC sequence.
        self.sb = 0  # Flag for SB and SE sequence.
        self.history: list[str] = []  # Command history
        self.RUNSHELL = True
        # A little magic - Everything called cmdXXX is a command
        # Also, check for decorated functions
        for k in dir(self):
            method = getattr(self, k)
            name = getattr(method, "command_name", None)
            if name is None:
                if k[:3] == "cmd":
                    name = k[3:]
                else:
                    continue

            name = name.upper()
            self.COMMANDS[name] = method
            for alias in getattr(method, "aliases", []):
                self.COMMANDS[alias.upper()] = self.COMMANDS[name]

        socketserver.BaseRequestHandler.__init__(self, request, client_address, server)

    class false_request:
        def __init__(self) -> None:
            self.sock = None

    @classmethod
    def streamserver_handle(cls, sock: Any, address: Any) -> None:
        """Translate this class for use in a StreamServer"""
        request = cls.false_request()
        request._sock = sock
        server = None
        log.debug("Accepted connection, starting telnet session.")
        try:
            cls(request, address, server)
        except socket.error:
            pass

    def setterm(self, term: str) -> None:
        "Set the curses structures for this terminal"
        log.debug("Setting termtype to %s" % (term,))
        curses.setupterm(term)  # This will raise if the termtype is not supported
        self.TERM = term
        self.ESCSEQ = {}
        for k in self.KEYS.keys():
            cap_name = KEY_CAPABILITY_NAMES.get(k)
            if cap_name is None:
                continue
            cap_bytes = curses.tigetstr(cap_name)
            if cap_bytes:
                self.ESCSEQ[cap_bytes.decode("latin-1")] = k
        # Create a copy to prevent altering the class
        self.CODES = self.CODES.copy()
        self.CODES["DEOL"] = (curses.tigetstr("el") or b"").decode("latin-1")
        self.CODES["DEL"] = (curses.tigetstr("dch1") or b"").decode("latin-1")
        self.CODES["INS"] = (curses.tigetstr("ich1") or b"").decode("latin-1")
        self.CODES["CSRLEFT"] = (curses.tigetstr("cub1") or b"").decode("latin-1")
        self.CODES["CSRRIGHT"] = (curses.tigetstr("cuf1") or b"").decode("latin-1")

    def setup(self) -> None:
        "Connect incoming connection to a telnet session"
        self.TERM = getattr(self.request, "term", self.TERM)
        self.setterm(self.TERM)
        # request._sock: gevent/eventlet StreamServer or SSH channel wrapper
        # request itself: raw socket from socketserver.TCPServer
        self.sock = getattr(self.request, "_sock", self.request)
        for k in self.DOACK.keys():
            self.sendcommand(self.DOACK[k], k)
        for k in self.WILLACK.keys():
            self.sendcommand(self.WILLACK[k], k)

    def finish(self) -> None:
        "End this session"
        log.debug("Session disconnected.")
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        self.session_end()

    def session_start(self) -> None:
        pass

    def session_end(self) -> None:
        pass

    # ------------------------- Telnet Options Engine --------------------------

    def options_handler(self, sock: Any, cmd: str, opt: str) -> None:
        "Negotiate options"
        if cmd == NOP:
            self.sendcommand(NOP)
        elif cmd == WILL or cmd == WONT:
            if opt in self.WILLACK:
                self.sendcommand(self.WILLACK[opt], opt)
            else:
                self.sendcommand(DONT, opt)
            if cmd == WILL and opt == TTYPE:
                self.writecooked(IAC + SB + TTYPE + SEND + IAC + SE)
        elif cmd == DO or cmd == DONT:
            if opt in self.DOACK:
                self.sendcommand(self.DOACK[opt], opt)
            else:
                self.sendcommand(WONT, opt)
            if opt == ECHO:
                self.DOECHO = cmd == DO
        elif cmd == SE:
            subreq = self.read_sb_data()
            if subreq[0] == TTYPE and subreq[1] == IS:
                try:
                    self.setterm(subreq[2:])
                except Exception:
                    log.debug("Terminal type not known")
            elif subreq[0] == NAWS:
                self.setnaws(subreq[1:])
        elif cmd == SB:
            pass
        else:
            log.debug("Unhandled option: %s %s" % (cmd, opt))

    def sendcommand(self, cmd: str, opt: str | None = None) -> None:
        "Send a telnet command (IAC)"
        if cmd in [DO, DONT]:
            if opt not in self.DOOPTS:
                self.DOOPTS[opt] = None
            if ((cmd == DO) and (self.DOOPTS[opt] is not True)) or (
                (cmd == DONT) and (self.DOOPTS[opt] is not False)
            ):
                self.DOOPTS[opt] = cmd == DO
                self.writecooked(IAC + cmd + opt)
        elif cmd in [WILL, WONT]:
            if opt not in self.WILLOPTS:
                self.WILLOPTS[opt] = ""
            if ((cmd == WILL) and (self.WILLOPTS[opt] is not True)) or (
                (cmd == WONT) and (self.WILLOPTS[opt] is not False)
            ):
                self.WILLOPTS[opt] = cmd == WILL
                self.writecooked(IAC + cmd + opt)
        else:
            self.writecooked(IAC + cmd)

    def read_sb_data(self) -> str:
        """Return any data available in the SB ... SE queue.

        Return '' if no SB ... SE available. Should only be called
        after seeing a SB or SE command. When a new SB command is
        found, old unread SB data will be discarded. Don't block.

        """
        buf = self.sbdataq
        self.sbdataq = ""
        return buf

    # ---------------------------- Input Functions -----------------------------

    def _readline_do_echo(self, echo: bool | None) -> bool:
        """Determine if we should echo or not"""
        return echo is True or (echo is None and self.DOECHO is True)

    def _readline_echo(self, char: str, echo: bool | None) -> None:
        """Echo a recieved character, move cursor etc..."""
        if self._readline_do_echo(echo):
            self.write(char)

    def _readline_insert(
        self, char: str, echo: bool | None, insptr: int, line: list[str]
    ) -> None:
        """Deal properly with inserted chars in a line."""
        if not self._readline_do_echo(echo):
            return
        # Write out the remainder of the line
        self.write(char + "".join(line[insptr:]))
        # Cursor Left to the current insert point
        char_count = len(line) - insptr
        self.write(self.CODES["CSRLEFT"] * char_count)

    _current_line: str | list[str] = ""
    _current_prompt: str = ""

    def ansi_to_curses(self, char: str | int) -> str | int:
        """Handles reading ANSI escape sequences"""
        # ANSI sequences are:
        # ESC [ <key>
        # If we see ESC, read a char
        if char != ESC:
            return char
        # If we see [, read another char
        if self.getc(block=True) != ANSI_START_SEQ:
            self._readline_echo(BELL, True)
            return theNULL
        key = self.getc(block=True)
        # Translate the key to curses
        try:
            return ANSI_KEY_TO_CURSES[key]
        except (KeyError, TypeError):
            self._readline_echo(BELL, True)
            return theNULL

    def readline(
        self, echo: bool | None = None, prompt: str = "", use_history: bool = True
    ) -> str:
        """Return a line of text, including the terminating LF
        If echo is true always echo, if echo is false never echo
        If echo is None follow the negotiated setting.
        prompt is the current prompt to write (and rewrite if needed)
        use_history controls if this line uses (and adds to) the command history.
        """

        line: list[str] = []
        insptr = 0
        histptr = len(self.history)

        if self.DOECHO:
            self.write(prompt)
            self._current_prompt = prompt
        else:
            self._current_prompt = ""

        self._current_line = ""

        while True:
            c = self.getc(block=True)
            c = self.ansi_to_curses(c)
            if c == theNULL:
                continue

            elif c == curses.KEY_LEFT:
                if insptr > 0:
                    insptr = insptr - 1
                    self._readline_echo(self.CODES["CSRLEFT"], echo)
                else:
                    self._readline_echo(BELL, echo)
                continue
            elif c == curses.KEY_RIGHT:
                if insptr < len(line):
                    insptr = insptr + 1
                    self._readline_echo(self.CODES["CSRRIGHT"], echo)
                else:
                    self._readline_echo(BELL, echo)
                continue
            elif c == curses.KEY_UP or c == curses.KEY_DOWN:
                if not use_history:
                    self._readline_echo(BELL, echo)
                    continue
                if c == curses.KEY_UP:
                    if histptr > 0:
                        histptr = histptr - 1
                    else:
                        self._readline_echo(BELL, echo)
                        continue
                elif c == curses.KEY_DOWN:
                    if histptr < len(self.history):
                        histptr = histptr + 1
                    else:
                        self._readline_echo(BELL, echo)
                        continue
                line = []
                if histptr < len(self.history):
                    line.extend(self.history[histptr])
                for char in range(insptr):
                    self._readline_echo(self.CODES["CSRLEFT"], echo)
                self._readline_echo(self.CODES["DEOL"], echo)
                self._readline_echo("".join(line), echo)
                insptr = len(line)
                continue
            elif c == chr(3):
                self._readline_echo("\n" + curses.ascii.unctrl(c) + " ABORT\n", echo)
                return ""
            elif c == chr(4):
                if len(line) > 0:
                    self._readline_echo(
                        "\n" + curses.ascii.unctrl(c) + " ABORT (QUIT)\n", echo
                    )
                    return ""
                self._readline_echo("\n" + curses.ascii.unctrl(c) + " QUIT\n", echo)
                return "QUIT"
            elif c == chr(10):
                self._readline_echo(c, echo)
                result = "".join(line)
                if use_history:
                    self.history.append(result)
                if echo is False:
                    if prompt:
                        self.write(chr(10))
                    log.debug("readline: %s(hidden text)", prompt)
                else:
                    log.debug("readline: %s%r", prompt, result)
                return result
            elif c == curses.KEY_BACKSPACE or c == chr(127) or c == chr(8):
                if insptr > 0:
                    self._readline_echo(self.CODES["CSRLEFT"] + self.CODES["DEL"], echo)
                    insptr = insptr - 1
                    del line[insptr]
                else:
                    self._readline_echo(BELL, echo)
                continue
            elif c == curses.KEY_DC:
                if insptr < len(line):
                    self._readline_echo(self.CODES["DEL"], echo)
                    del line[insptr]
                else:
                    self._readline_echo(BELL, echo)
                continue
            else:
                if isinstance(c, str) and ord(c) < 32:
                    c = curses.ascii.unctrl(c)
                if len(line) > insptr:
                    self._readline_insert(c, echo, insptr, line)
                else:
                    self._readline_echo(c, echo)
            line[insptr:insptr] = c
            insptr = insptr + len(c)
            if self._readline_do_echo(echo):
                self._current_line = line

    # abstractmethod
    def getc(self, block: bool = True) -> str | int:
        """Return one character from the input queue"""
        # This is very different between green threads and real threads.
        raise NotImplementedError("Please Implement the getc method")

    # --------------------------- Output Functions -----------------------------

    def writeresponse(self, text: str) -> None:
        """Write out any valid responses.  Easy to override with ANSI codes."""
        self.writeline(text)

    def writeerror(self, text: str) -> None:
        """Write out any error messages.  Easy to override with ANSI codes."""
        self.writeline(text)

    def writeline(self, text: str) -> None:
        """Send a packet with line ending."""
        log.debug("writing line %r" % text)
        self.write(text + chr(10))

    def writemessage(self, text: str) -> None:
        """Write an async message, then reconstruct the prompt and entered text."""
        log.debug("writing message %r", text)
        self.write(chr(10) + text + chr(10))
        self.write(self._current_prompt + "".join(self._current_line))

    def write(self, text: str) -> None:
        """Send a packet to the socket. This function cooks output."""
        text = str(text)
        text = text.replace(IAC, IAC + IAC)
        text = text.replace(chr(10), chr(13) + chr(10))
        self.writecooked(text)

    def writecooked(self, text: str) -> None:
        """Put data directly into the output queue (bypass output cooker)"""
        # Encode as latin-1: telnet protocol bytes map 1:1 to latin-1 code points
        self.sock.sendall(text.encode("latin-1"))

    # ------------------------------- Input Cooker -----------------------------
    def _inputcooker_getc(self, block: bool = True) -> str:
        """Get one character from the raw queue. Optionally blocking.
        Raise EOFError on end of stream. SHOULD ONLY BE CALLED FROM THE
        INPUT COOKER."""
        if self.rawq:
            ret = self.rawq[0]
            self.rawq = self.rawq[1:]
            return ret
        if not block:
            if not self.inputcooker_socket_ready():
                return ""
        data = self.sock.recv(20)
        self.eof = not bool(data)
        # Decode bytes to str using latin-1 (preserves all byte values 0-255)
        self.rawq = self.rawq + data.decode("latin-1")
        if self.eof:
            raise EOFError
        return self._inputcooker_getc(block)

    # abstractmethod
    def inputcooker_socket_ready(self) -> bool:
        """Indicate that the socket is ready to be read"""
        # Either use a green select or a real select
        raise NotImplementedError(
            "Please Implement the inputcooker_socket_ready method"
        )

    def _inputcooker_ungetc(self, char: str) -> None:
        """Put characters back onto the head of the rawq. SHOULD ONLY
        BE CALLED FROM THE INPUT COOKER."""
        self.rawq = char + self.rawq

    def _inputcooker_store(self, char: str | int) -> None:
        """Put the cooked data in the correct queue"""
        if self.sb:
            self.sbdataq = self.sbdataq + char
        else:
            self.inputcooker_store_queue(char)

    # abstractmethod
    def inputcooker_store_queue(self, char: str | int) -> None:
        """Put the cooked data in the output queue (possible locking needed)"""
        raise NotImplementedError("Please Implement the inputcooker_store_queue method")

    def inputcooker(self) -> None:
        """Input Cooker - Transfer from raw queue to cooked queue.

        Set self.eof when connection is closed.  Don't block unless in
        the midst of an IAC sequence.
        """
        try:
            while True:
                c = self._inputcooker_getc()
                if not self.iacseq:
                    if c == IAC:
                        self.iacseq += c
                        continue
                    elif c == chr(13) and not (self.sb):
                        c2 = self._inputcooker_getc(block=False)
                        if c2 == theNULL or c2 == "":
                            c = chr(10)
                        elif c2 == chr(10):
                            c = c2
                        else:
                            self._inputcooker_ungetc(c2)
                            c = chr(10)
                    elif c in [x[0] for x in self.ESCSEQ.keys()]:
                        # Looks like the beginning of a key sequence
                        codes = c
                        for keyseq in self.ESCSEQ.keys():
                            if len(keyseq) == 0:
                                continue
                            while (
                                codes == keyseq[: len(codes)] and len(codes) <= keyseq
                            ):
                                if codes == keyseq:
                                    c = self.ESCSEQ[keyseq]
                                    break
                                codes = codes + self._inputcooker_getc()
                            if codes == keyseq:
                                break
                            self._inputcooker_ungetc(codes[1:])
                            codes = codes[0]
                    self._inputcooker_store(c)
                elif len(self.iacseq) == 1:
                    # IAC: IAC CMD [OPTION only for WILL/WONT/DO/DONT]
                    if c in (DO, DONT, WILL, WONT):
                        self.iacseq += c
                        continue
                    self.iacseq = ""
                    if c == IAC:
                        self._inputcooker_store(c)
                    else:
                        if c == SB:  # SB ... SE start.
                            self.sb = 1
                            self.sbdataq = ""
                        elif c == SE:  # SB ... SE end.
                            self.sb = 0
                        # Callback is supposed to look into
                        # the sbdataq
                        self.options_handler(self.sock, c, NOOPT)
                elif len(self.iacseq) == 2:
                    cmd = self.iacseq[1]
                    self.iacseq = ""
                    if cmd in (DO, DONT, WILL, WONT):
                        self.options_handler(self.sock, cmd, c)
        except (EOFError, socket.error):
            pass

    # ------------------------------- Basic Commands ---------------------------

    # Format of docstrings for command methods:
    # Line 0:  Command paramater(s) if any. (Can be blank line)
    # Line 1:  Short descriptive text. (Mandatory)
    # Line 2+: Long descriptive text. (Can be blank line)

    def cmdHELP(self, params: list[str]) -> None:
        """[<command>]
        Display help
        Display either brief help on all commands, or detailed
        help on a single command passed as a parameter.
        """
        if params:
            cmd = params[0].upper()
            if cmd in self.COMMANDS:
                method = self.COMMANDS[cmd]
                doc = method.__doc__.split("\n")
                docp = doc[0].strip()
                docl = "\n".join([line_.strip() for line_ in doc[2:]])
                if not docl.strip():  # If there isn't anything here, use line 1
                    docl = doc[1].strip()
                self.writeline(
                    "%s %s\n\n%s"
                    % (
                        cmd,
                        docp,
                        docl,
                    )
                )
                return
            else:
                self.writeline("Command '%s' not known" % cmd)
        else:
            self.writeline("Help on built in commands\n")
        for cmd in sorted(self.COMMANDS.keys()):
            method = self.COMMANDS[cmd]
            if getattr(method, "hidden", False):
                continue
            if method.__doc__ is None:
                self.writeline("no help for command %s" % method)
                return
            doc = method.__doc__.split("\n")
            docp = doc[0].strip()
            docs = doc[1].strip()
            if len(docp) > 0:
                docps = "%s - %s" % (
                    docp,
                    docs,
                )
            else:
                docps = "- %s" % (docs,)
            self.writeline(
                "%s %s"
                % (
                    cmd,
                    docps,
                )
            )

    cmdHELP.aliases = ["?"]

    def cmdEXIT(self, params: list[str]) -> None:
        """
        Exit the command shell
        """
        self.RUNSHELL = False
        self.writeline("Goodbye")

    cmdEXIT.aliases = ["QUIT", "BYE", "LOGOUT"]

    def cmdHISTORY(self, params: list[str]) -> None:
        """
        Display the command history
        """
        cnt = 0
        self.writeline("Command history\n")
        for line in self.history:
            cnt = cnt + 1
            self.writeline("%-5d : %s" % (cnt, "".join(line)))

    # ----------------------- Command Line Processor Engine --------------------

    def handleException(
        self, exc_type: type, exc_param: BaseException, exc_tb: Any
    ) -> bool:
        "Exception handler (False to abort)"
        self.writeline("".join(traceback.format_exception(exc_type, exc_param, exc_tb)))
        return True

    def authentication_ok(self) -> bool:
        """Checks the authentication and sets the username. Returns True or False."""
        username = None
        password = None
        if self.authCallback:
            if self.authNeedUser:
                username = self.readline(prompt=self.PROMPT_USER, use_history=False)
            if self.authNeedPass:
                password = self.readline(
                    echo=False, prompt=self.PROMPT_PASS, use_history=False
                )
                if self.DOECHO:
                    self.write("\n")
            try:
                self.authCallback(username, password)
            except Exception:
                self.username = None
                return False
            else:
                # Successful authentication
                self.username = username
                return True
        else:
            # No authentication desired
            self.username = None
            return True

    def handle(self) -> None:
        "The actual service to which the user has connected."
        if self.TELNET_ISSUE:
            self.writeline(self.TELNET_ISSUE)
        if not self.authentication_ok():
            return
        if self.DOECHO:
            self.writeline(self.WELCOME)

        self.session_start()
        while self.RUNSHELL:
            raw_input = self.readline(prompt=self.PROMPT).strip()
            self.input = self.input_reader(self, raw_input)
            self.raw_input = self.input.raw
            if self.input.cmd:
                cmd = self.input.cmd.upper()
                params = self.input.params
                if cmd in self.COMMANDS:
                    try:
                        self.COMMANDS[cmd](params)
                    except Exception:
                        log.exception("Error calling %s." % cmd)
                        (t, p, tb) = sys.exc_info()
                        if self.handleException(t, p, tb):
                            break
                else:
                    self.writeerror("Unknown command '%s'" % cmd)
        log.debug("Exiting handler")


# vim: set syntax=python ai showmatch:
