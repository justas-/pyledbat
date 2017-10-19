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

    # Prevent negative test times
    if not params.time or params.time < 0:
        params.time = None

    ledbat_params = None

    # Print debug information
    if params.role == 'client':
        # Extract any ledbat overwrites
        ledbat_params = extract_ledbat_params(params)

        if params.time:
            str_test_len = '{} s.'.format(params.time)
        else:
            str_test_len = 'Unlimited'

        logging.info('Starting LEDBAT test client. Remote: %s; Length: %s;',
                     params.remote, str_test_len)
    else:
        logging.info('Starting LEDBAT test server.')

    if params.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug('Debug output enabled!')

    if params.makelog:
        logging.info('Run-time values will be saved to the log file')

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
        client.start_client(remote_ip=params.remote,
                            remote_port=UDP_PORT,
                            make_log=params.makelog,
                            test_len=params.time,
                            ledbat_params=ledbat_params)
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

def extract_ledbat_params(parameters):
    """Extract LEDBAT settings"""

    ledbat_params = {}

    for attr, value in vars(parameters).items():
        try:
            if attr.startswith('ledbat'):
                ledbat_params[attr[attr.index('_')+1:]] = value
        except IndexError:
            # Better check your typos next time...
            logging.info('Failed to parse LEDBAT param: %s', attr)

    return ledbat_params
