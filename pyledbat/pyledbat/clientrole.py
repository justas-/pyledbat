import asyncio
import random

import ledbat_test

class clientrole(object):
    """description of class"""

    def __init__(self, udp_protocol):
        # Save reference to the receiver
        self._udp_protocol = udp_protocol

        # Inform receiver to deliver data to us
        self._udp_protocol.register_receiver(self)

        # Keep all tests here. LocalID -> ledbat_test
        self._tests = {}
        
    def start_client(self, remote_ip, remote_port):
        """Start the functioning of the client"""

        # Create instance of this test
        lt = ledbat_test.LedbatTest(True, remote_ip, remote_port, self)
        lt.local_channel = random.randint(1, 65534)

        # Save in the list of tests
        self._tests[lt.local_channel] = lt

        # Send the init message to the server
        lt.start_init()

    def send_data(self, data, addr):
        """Send the data to indicated addr"""
        self._udp_protocol.send_data(data, addr)

    def remove_test(self, test):
        """Remove the given test from the list of tests"""
        del self._tests[test.local_channel]

