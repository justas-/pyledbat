"""
Implementation of the client role in the test application.
"""

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
            logging.warning('Discarded unknown message type (%s) from %s', msg_type, addr)

    def start_client(self, **kwargs):
        """Start the functioning of the client by starting a new test"""

        # Create instance of this test
        ledbattest = ledbat_test.LedbatTest(is_client=True,
                                            remote_ip=kwargs.get('remote_ip'),
                                            remote_port=kwargs.get('remote_port'),
                                            owner=self,
                                            make_log=kwargs.get('make_log'))
        ledbattest.local_channel = random.randint(1, 65534)

        # Save in the list of tests
        self._tests[ledbattest.local_channel] = ledbattest

        # Send the init message to the server
        ledbattest.start_init()

    def remove_test(self, test):
        """Extend remove_test to close client when the last test is removed"""
        super().remove_test(test)

        if not self._tests:
            logging.info('Last test removed. Closing client')
            asyncio.get_event_loop().stop()

    def stop_all_tests(self):
        """Request to stop all tests"""

        # Make copy not to iterate over list being removed
        tests_copy = self._tests.copy()
        for test in tests_copy.values():
            test.stop_test()
            test.dispose()
