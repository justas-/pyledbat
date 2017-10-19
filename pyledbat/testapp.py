"""Test LEDBAT implementation in iperf-ish way"""
import logging
import argparse

from testledbat import test_ledbat

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s %(message)s')

def main():
    """Main entrance point, mainly to stop PyLint from nagging"""

    # Setup the command line parser
    parser = argparse.ArgumentParser(description='LEDBAT Test program')

    parser.add_argument('--role', help='Role of the instance {client|server}', default='server')
    parser.add_argument('--remote', help='IP Address of the test server')
    parser.add_argument('--debug', help='Enable verbose output', action='store_true')
    parser.add_argument('--makelog', help='Save runtime values into CSV file', action='store_true')
    parser.add_argument('--time', help='Time to run the test (Client only)', type=int)
    parser.add_argument('--ledbat-set-target', help='Set LEDBAT target queuing delay', type=int)

    # Parse the command line params
    args = parser.parse_args()

    # Run the test
    test_ledbat(args)

# Move scope to main() (I hate PyLint...)
if __name__ == '__main__':
    main()
