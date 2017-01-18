import asyncio
import random
import struct
import logging
import time

import baserole
import ledbat_test

class clientrole(baserole.baserole):
    """description of class"""

    def __init__(self, udp_protocol):
        return super().__init__(udp_protocol)

    def datagram_received(self, data, addr):
        """Process the received datagram"""

        # save time of reception
        rx_time = time.time()

        # Extract the header
        (msg_type, rem_ch, loc_ch) = struct.unpack('>III', data[0:12])

        if msg_type == 1 and rem_ch == 0:
            logging.warn('Client should not get INIT messages')
            return

        # Get the LEDBAT test
        lt = self._tests.get(rem_ch)
        if lt is None:
            logging.warn('Could not find ledbat test with our id: %s' %rem_ch)
            return

        if msg_type == 1:       # INIT-ACK
            lt.init_ack_received(loc_ch)
        elif msg_type == 2:     # DATA
            logging.warn('Client should not receive DATA messages')
        elif msg_type == 3:     # ACK
            lt.ack_received(data[12:], rx_time)
        else:
            logging.warn('Discarded unknown message type (%s) from %s' %(msg_type, addr))

    def _handle_init(self, data, addr):

        # Extract remote and local channels
        (rem_ch, loc_ch) = struct.unpack('>II', data[4:12])
        
        if rem_ch == 0:
            logging.debug('Client should not handle incomming tests!')
        else:
            # Ensure we have this test
            lt = self._tests.get(rem_ch)
            if lt is not None:
                lt.init_ack_received(loc_ch)
            else:
                logging.debug('Received INIT-ACK for unknown test %s' %rem_ch)
        
    def start_client(self, remote_ip, remote_port):
        """Start the functioning of the client"""

        # Create instance of this test
        lt = ledbat_test.LedbatTest(True, remote_ip, remote_port, self)
        lt.local_channel = random.randint(1, 65534)

        # Save in the list of tests
        self._tests[lt.local_channel] = lt

        # Send the init message to the server
        lt.start_init()

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
