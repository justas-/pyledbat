"""Test LEDBAT implementation in iperf-ish way"""

import logging
import asyncio
import socket
import argparse
import os

import udpserver
import clientrole
import serverrole

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s %(message)s')

UDP_PORT = 6888

def main(params):
    # Validate the params
    if args.role == 'client' and args.remote is None:
        logging.error('Address of the remote server must be provided for the client role!')
        return

    # Print debug information
    if args.role == 'client':
        logging.info('Starting LEDBAT test client. Remote: %s' %args.remote)
    else:
        logging.info('Starting LEDBAT test server.')

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug('Debug output enabled!')

    # Init the events loop and udp transport
    loop = asyncio.get_event_loop()
    listen = loop.create_datagram_endpoint(udpserver.udpserver, local_addr=('0.0.0.0', UDP_PORT))
    transport, protocol = loop.run_until_complete(listen)

    # Enable Ctrl-C closing in WinNT
    # Ref: http://stackoverflow.com/questions/24774980/why-cant-i-catch-sigint-when-asyncio-event-loop-is-running
    if os.name == 'nt':
        def wakeup():
            loop.call_later(0.5, wakeup)
        loop.call_later(0.5, wakeup)

    # Start the instance based on the type
    if args.role == 'client':
        # Run the client
        client = clientrole.clientrole(args, protocol)
        client.start_client(args.remote, UDP_PORT)
    else:
        # Do the Server thing
        server = serverrole.serverrole(args, protocol)
        server.start_server()

    # Wait for Ctrl-C
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    if args.role == 'client':
        client.stop_all_tests()

    # Cleanup
    transport.close()
    loop.close()

if __name__ == '__main__':
    # Parse the command line params
    parser = argparse.ArgumentParser(description='LEDBAT Test program')

    parser.add_argument('--role', help='Role of the instance {client|server}', default='server')
    parser.add_argument('--remote', help='IP Address of the test server')
    parser.add_argument('--debug', help='Enable verbose output', action='store_true')

    args = parser.parse_args()

    args.role = 'client'
    args.remote = '10.51.32.211'
    args.debug = True

    main(args)