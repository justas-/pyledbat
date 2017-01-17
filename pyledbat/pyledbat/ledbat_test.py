import logging
import asyncio
import struct

T_INIT_ACK = 5.0     # Time to wait for INIT-ACK

class LedbatTest(object):
    """An instance representing a single LEDBAT test"""

    def __init__(self, is_client, remote_ip, remote_port, owner):
        self._is_client = is_client
        self._remote_ip = remote_ip
        self._remote_port = remote_port
        self._owner = owner
        
        self._is_init = False
        self._num_init_sent = 0
        self._hdl_init_ack = None

        self.local_channel = None
        self.remote_channel = None

    def start_init(self):
        """Start the test initialization procedure"""

        # We can start init only when er are the client
        assert self._is_client

        # Prevent re-starting the test
        assert not self._is_init

        # Send the init message
        self._build_and_send_init()

        # Schedule re-sender / disposer
        asyncio.get_event_loop().call_later(T_INIT_ACK, self._init_ack_missing)

    def _build_and_send_init(self):
        """Build and send the INIT message"""
        
        # Build the message
        msg_bytes = bytearray(12)
        struct.pack_into('>III', msg_bytes, 0, 1, 0, self.local_channel)

        # Send it to the remote
        self._owner.send_data(msg_bytes, (self._remote_ip, self._remote_port))
        self._num_init_sent += 1

        # Print log
        logging.info('{} Sent INI message ({})'.format(self, self._num_init_sent))

    def _init_ack_missing(self):
        """Called by when init ACK not received within time interval"""

        # Keep resending INIT for up to 3 times
        if self._num_init_sent < 3:
            self._build_and_send_init()
            asyncio.get_event_loop().call_later(T_INIT_ACK, self._init_ack_missing)
        else:
            # After 3 time, dispose the test
            logging.info('{} INI-ACK missing!'.format(self))
            self.dispose()

    def send_init_ack(self):
        pass

    def init_received(self):
        pass

    def init_ack_received(self):
        pass

    def start_test(self):
        pass

    def dispose(self):
        """Cleanup this test"""
        # Log information
        logging.info('{} Disposing'.format(self))

        # Cancel all event handles
        if self._hdl_init_ack is not None:
            self._hdl_init_ack.cancel()
            self._hdl_init_ack = None

        # Remove from the owner
        self._owner.remove_test(self)

    def __str__(self, **kwargs):
        return 'TEST: LC:{} RC: {} ({}:{}):'.format(self.local_channel, self.remote_channel,
            self._remote_ip, self._remote_port)