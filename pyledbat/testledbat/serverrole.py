"""
Server class for LEDBAT test. Server acts as a "dumb" client by ACKIN data only.
All protocol intelligence is in the client. One server can be replying to multipe
clients concurrently.
"""
import logging
import struct
import random
import time

from testledbat import ledbat_test
from testledbat import baserole

class ServerRole(baserole.BaseRole):
    """description of class"""

    def start_server(self):
        """Start acting as a server"""
        pass

    def datagram_received(self, data, addr):
        """Process the received datagram"""

        # Take time msg received for later use
        rx_time = time.time()

        # Extract the header
        (msg_type, rem_ch, loc_ch) = struct.unpack('>III', data[0:12])

        # Either init new test or get the running test
        if msg_type == 1 and rem_ch == 0:
            self._test_init_req(loc_ch, addr)
            return
        else:
            # All other combinations must have remote_channel set
            lt = self._tests.get(rem_ch)

            if lt is None:
                logging.warning('Could not find ledbat test with our id: %s' %rem_ch)
                return

            if msg_type == 1:
                logging.warning('Server should not receive INIT-ACK')
            elif msg_type == 2:
                lt.data_received(data[12:], rx_time)
            elif msg_type == 3:
                logging.warning('Server should not receive ACK message')
            else:
                logging.warning('Discarded unknown message type (%s) from %s' %(msg_type, addr))

    def _test_init_req(self, their_channel, addr):
        """Initialize new test as requested"""

        # This is attempt to start a new test
        lt = ledbat_test.LedbatTest(False, addr[0], addr[1], self)
        lt.remote_channel = their_channel
        lt.local_channel = random.randint(1, 65534)

        # Add to a list of tests
        self._tests[lt.local_channel] = lt

        # Send INIT-ACK
        lt.send_init_ack()
