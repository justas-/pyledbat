import asyncio
import logging

class udpserver(asyncio.DatagramProtocol):
    """description of class"""

    def __init__(self, **kwargs):
        self._transport = None
        self._receiver = None

    def send_data(self, data, addr):
        self._transport.sendto(data, addr)
    
    def register_receiver(self, receiver):
        self._receiver = receiver

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data, addr):
        self._receiver.datagram_received(data, addr)

    def error_received(self, exc):
        logging.warn('Error received: %s' %exc)

    def connection_lost(self, exc):
        logging.error('Connection lost: %s' %exc)

    def pause_writing(self):
        logging.info('Socket is above high-water mark')

    def resume_writing(self):
        logging.info('Socket is below high-water mark')
