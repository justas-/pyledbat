import logging
import struct
import random

import ledbat_test
import baserole

class serverrole(baserole.baserole):
    """description of class"""

    def start_server(self):
        """Start acting as a server"""
        pass

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
        """Handle INIT MESSAGE"""
        
        # Extract remote and local channels
        (rem_ch, loc_ch) = struct.unpack('>II', data[4:12])
        
        if rem_ch == 0:
            # This is attempt to start a new test
            lt = ledbat_test.LedbatTest(False, addr[0], addr[1], self)
            lt.remote_channel = loc_ch
            lt.local_channel = random.randint(1, 65534)

            # Add to a list of tests
            self._tests[lt.local_channel] = lt

            # Send INIT-ACK
            lt.send_init_ack()

    def _handle_ack(self, data, addr):
        logging.warn('Server should not receive ACK')

    def _handle_data(self, data, addr):
        pass