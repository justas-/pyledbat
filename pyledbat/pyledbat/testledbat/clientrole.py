import asyncio
import random
import struct
import logging
import time

from testledbat import baserole
from testledbat import ledbat_test

class ClientRole(baserole.BaseRole):
    """description of class"""

    def datagram_received(self, data, addr):
        """Process the received datagram"""

        # save time of reception
        rx_time = time.time()

        # Extract the header
        (msg_type, rem_ch, loc_ch) = struct.unpack('>III', data[0:12])

        if msg_type == 1 and rem_ch == 0:
            logging.warning('Client should not get INIT messages')
            return

        # Get the LEDBAT test
        ledbattest = self._tests.get(rem_ch)
        if ledbattest is None:
            logging.warning('Could not find ledbat test with our id: %s', rem_ch)
            return

        if msg_type == 1:       # INIT-ACK
            ledbattest.init_ack_received(loc_ch)
        elif msg_type == 2:     # DATA
            logging.warning('Client should not receive DATA messages')
        elif msg_type == 3:     # ACK
            ledbattest.ack_received(data[12:], rx_time)
        else:
            logging.warning('Discarded unknown message type (%s) from %s' % (msg_type, addr))

    def start_client(self, remote_ip, remote_port):
        """Start the functioning of the client"""

        # Create instance of this test
        ledbattest = ledbat_test.LedbatTest(True, remote_ip, remote_port, self)
        ledbattest.local_channel = random.randint(1, 65534)

        # Save in the list of tests
        self._tests[ledbattest.local_channel] = ledbattest

        # Send the init message to the server
        ledbattest.start_init()

    def remove_test(self, test):
        """Extend remove_test to close client when the last test is removed"""
        super().remove_test(test)

        if len(self._tests) == 0:
            logging.info('Last test removed. Closing client')
            asyncio.get_event_loop().stop()

    def stop_all_tests(self):
        """Request to stop all tests"""

        # Make copy not to iterate over list being removed
        tests_copy = self._tests.copy()
        for test in tests_copy.values():
            test.stop_test()
            test.dispose()
