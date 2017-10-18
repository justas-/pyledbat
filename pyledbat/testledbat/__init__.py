"""
Ledbat testing application.
"""

import logging
import asyncio
import socket
import os

from testledbat import udpserver
from testledbat import clientrole
from testledbat import serverrole

UDP_PORT = 6888

def test_ledbat(params):
    """
    Entry function for LEDBAT testing application.
    """

    # Validate the params
    if params.role == 'client' and params.remote is None:
        logging.error('Address of the remote server must be provided for the client role!')
        return

    # Print debug information
    if params.role == 'client':
        logging.info('Starting LEDBAT test client. Remote: %s', params.remote)
    else:
        logging.info('Starting LEDBAT test server.')

    if params.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug('Debug output enabled!')

    # Init the events loop and udp transport
    loop = asyncio.get_event_loop()
    listen = loop.create_datagram_endpoint(udpserver.UdpServer, local_addr=('0.0.0.0', UDP_PORT))
    transport, protocol = loop.run_until_complete(listen)

    # Enable Ctrl-C closing in WinNT
    # Ref: http://stackoverflow.com/questions/24774980/why-cant-i-catch-sigint-when-asyncio-event-loop-is-running
    if os.name == 'nt':
        def wakeup():
            loop.call_later(0.5, wakeup)
        loop.call_later(0.5, wakeup)

    # Start the instance based on the type
    if params.role == 'client':
        # Run the client
        client = clientrole.ClientRole(protocol)
        client.start_client(params.remote, UDP_PORT)
    else:
        # Do the Server thing
        server = serverrole.ServerRole(protocol)
        server.start_server()

    # Wait for Ctrl-C
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    if params.role == 'client':
        client.stop_all_tests()

    # Cleanup
    transport.close()
    loop.close()
