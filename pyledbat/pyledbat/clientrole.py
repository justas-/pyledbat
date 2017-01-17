import asyncio
import random
import struct
import logging

import baserole
import ledbat_test

class clientrole(baserole.baserole):
    """description of class"""

    def __init__(self, udp_protocol):
        return super().__init__(udp_protocol)

    def datagram_received(self, data, addr):
        """Process the received datagram"""

        # Extract the message type
        msg_type = struct.unpack('>I', data[0:4])[0]

        # Handle each type
        if msg_type == 1:
            self._handle_init(data, addr)
        elif msg_type == 2:
            self._handle_data(data, addr)
        elif msg_type == 3:
            self._handle_ack(data, addr)
        else:
            logging.warn('Discarded unknown message type ({}) from {}'
                         .format(msg_type, addr))

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

    def _handle_data(self, data, addr):
        logging.warn('Client should not receive DATA')

    def _handle_ack(self, data, addr):
        pass
        
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
