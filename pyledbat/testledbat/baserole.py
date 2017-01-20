"""Base class that is extended by Client and Server roles"""

class BaseRole(object):
    """BaseRole with minimal actions what are common
       for both client and the server.
    """

    def __init__(self, udp_protocol):
        # Save reference to the receiver
        self._udp_protocol = udp_protocol

        # Inform receiver to deliver data to us
        self._udp_protocol.register_receiver(self)

        # Keep all tests here. LocalID -> ledbat_test
        self._tests = {}

    def datagram_received(self, data, addr):
        """Callback on received datagram"""
        pass

    def send_data(self, data, addr):
        """Send the data to the indicated addr"""
        self._udp_protocol.send_data(data, addr)

    def remove_test(self, test):
        """Remove the given test from the list of tests"""
        del self._tests[test.local_channel]
