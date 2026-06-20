"""Telnet protocol constants.

Single-character command/option codes, ANSI helper tables, and the CMDS
human-readable name map.  All values are defined here so that other modules
can import them without pulling in the full handler machinery.
"""

import curses

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
