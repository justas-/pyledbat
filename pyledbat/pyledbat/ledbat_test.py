import logging
import asyncio
import struct

T_INIT_ACK = 5.0    # Time to wait for INIT-ACK
T_INIT_DATA = 5.0   # Time to wait for DATA after sending INIT-ACK

class LedbatTest(object):
    """An instance representing a single LEDBAT test"""

    def __init__(self, is_client, remote_ip, remote_port, owner):
        self._is_client = is_client
        self._remote_ip = remote_ip
        self._remote_port = remote_port
        self._owner = owner
        
        self._num_init_sent = 0
        self._hdl_init_ack = None       # Receive INIT-ACK after ACK

        self._num_init_ack_sent = 0
        self._hdl_act_to_data = None    # Receive DATA after INIT-ACK
        
        self.is_init = False
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
        struct.pack_into('>III', msg_bytes, 0, 
                         1,                     # Type - ACK
                         0,                     # Remote Channel
                         self.local_channel     # Local channel
        ) 

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
        """Send the INIT-ACK reply to INIT"""

        # Send INIT-ACK
        self._build_and_send_init_ack()

        # Start timer to wait for data
        asyncio.get_event_loop().call_later(T_INIT_DATA, self._init_data_missing)

    def _init_data_missing(self):
        """Called when DATA is not received after INIT-ACK"""
        
        # Keep resending INIT-ACK up to 3 times
        if self._num_init_ack_sent < 3:
            self._build_and_send_init_ack()
            asyncio.get_event_loop().call_later(T_INIT_DATA, self._init_data_missing)
        else:
            # After 3 times dispose
            logging.info('{} DATA missing after 3 INIT-ACK'.format(self))
            self.dispose()

    def _build_and_send_init_ack(self):
        """Build and send INI-ACK message"""

        # Build message bytes
        msg_bytes = bytearray(12)
        struct.pack_into('>III', msg_bytes, 0,
                         1,                     # Type
                         self.remote_channel,   # Remote channel
                         self.local_channel     # Local channel
        )

        # Send it
        self._owner.send_data(msg_bytes, (self._remote_ip, self._remote_port))
        self._num_init_ack_sent += 1

        # Print log
        logging.info('{} Sent INIT-ACK message ({})'.format(self, self._num_init_ack_sent))

    def init_ack_received(self, remote_channel):
        """Handle INIT-ACK message from remote"""

        # Check if we are laready init
        if self.is_init:
            # Ignore message, most probably duplicate
            return
        else:
            # Save details. We are init now
            self.remote_channel = remote_channel
            self.is_init = True

            logging.info('%s Test initialized' %self)

            # Cancel timer
            self._hdl_init_ack.cancel()
            self._hdl_init_ack = None

            # Start the TEST
            self._start_test()
    
    def _start_test(self):
        """Start testing"""

        logging.info('{} Starting test'.format(self))

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