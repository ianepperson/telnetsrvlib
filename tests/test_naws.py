"""Tests for NAWS (Negotiate About Window Size, RFC 1073)."""

import struct

from telnetsrv.constants import NAWS, DO, SE, NOOPT


def naws_payload(width: int, height: int) -> str:
    """Build the 4-byte NAWS subnegotiation body as a latin-1 string."""
    return struct.pack(">HH", width, height).decode("latin-1")


class TestSetnaws:
    def test_sets_width_and_height(self, handler):
        handler.setnaws(naws_payload(132, 50))
        assert handler.WIDTH == 132
        assert handler.HEIGHT == 50

    def test_updates_on_second_call(self, handler):
        handler.setnaws(naws_payload(80, 24))
        handler.setnaws(naws_payload(200, 60))
        assert handler.WIDTH == 200
        assert handler.HEIGHT == 60

    def test_short_data_ignored(self, handler):
        original_w, original_h = handler.WIDTH, handler.HEIGHT
        handler.setnaws("xx")  # only 2 bytes — too short
        assert handler.WIDTH == original_w
        assert handler.HEIGHT == original_h

    def test_large_dimensions(self, handler):
        handler.setnaws(naws_payload(65535, 65535))
        assert handler.WIDTH == 65535
        assert handler.HEIGHT == 65535


class TestNawsDefaults:
    def test_width_has_default(self, handler):
        assert isinstance(handler.WIDTH, int)
        assert handler.WIDTH > 0

    def test_height_has_default(self, handler):
        assert isinstance(handler.HEIGHT, int)
        assert handler.HEIGHT > 0


class TestNawsNegotiation:
    def test_willack_requests_naws_from_client(self, handler):
        assert handler.WILLACK[NAWS] == DO

    def test_options_handler_se_naws_updates_dimensions(self, handler):
        handler.sbdataq = NAWS + naws_payload(120, 40)
        handler.options_handler(handler.sock, SE, NOOPT)
        assert handler.WIDTH == 120
        assert handler.HEIGHT == 40

    def test_options_handler_se_naws_resize_during_session(self, handler):
        handler.sbdataq = NAWS + naws_payload(80, 24)
        handler.options_handler(handler.sock, SE, NOOPT)
        # Simulate client resizing the window
        handler.sbdataq = NAWS + naws_payload(160, 48)
        handler.options_handler(handler.sock, SE, NOOPT)
        assert handler.WIDTH == 160
        assert handler.HEIGHT == 48
