"""
LedbatTest - class representing a single test instance and used in both client
and server.
"""
import logging
import asyncio
import struct
import time
import csv

from ledbat import simpleledbat
from .inflight_track import InflightTrack

T_INIT_ACK = 5.0    # Time to wait for INIT-ACK
T_INIT_DATA = 5.0   # Time to wait for DATA after sending INIT-ACK
T_IDLE = 10.0       # Time to wait when idle before destroying

SZ_DATA = 1024      # Data size in each message
OOO_THRESH = 3      # When to declare dataloss
PRINT_EVERY = 5000  # Print debug every this many packets sent
LOG_INTERVAL = 0.1  # Log every 0.1 sec

class LedbatTest(object):
    """An instance representing a single LEDBAT test"""

    def __init__(self, **kwargs):

        self._is_client = kwargs.get('is_client')
        self._remote_ip = kwargs.get('remote_ip')
        self._remote_port = kwargs.get('remote_port')
        self._owner = kwargs.get('owner')
        self._make_log = kwargs.get('make_log')

        self._ev_loop = asyncio.get_event_loop()

        self._num_init_sent = 0
        self._hdl_init_ack = None       # Receive INIT-ACK after ACK

        self._num_init_ack_sent = 0
        self._hdl_act_to_data = None    # Receive DATA after INIT-ACK

        self._hdl_send_data = None      # Used to schedule data sending
        self._hdl_idle = None           # Idle check handle

        self._ledbat = simpleledbat.SimpleLedbat()
        self._direct_send = False       # Send immediately before checking next
        self._next_seq = 1
        self._set_outstanding = set()
        self._sent_ts = {}

        self._inflight = InflightTrack()
        self._cnt_ooo = 0               # Count of Out-of-Order packets

        self.is_init = False
        self.local_channel = None
        self.remote_channel = None

        self._time_start = None
        self._time_stop = None
        self._time_last_rx = None

        self._chunks_sent = 0
        self._chunks_resent = 0
        self._chunks_acked = 0

        # Run periodic checks if object should be removed due to being idle
        self._hdl_idle = self._ev_loop.call_later(T_IDLE, self._check_for_idle)

        self._hdl_log = None
        self._log_data_list = []

        self.stop_hdl = None    # Stop event handle (if any)

    def start_init(self):
        """Start the test initialization procedure"""

        # We can start init only when er are the client
        assert self._is_client

        # Prevent re-starting the test
        assert not self.is_init

        # Send the init message
        self._build_and_send_init()

        # Schedule re-sender / disposer
        self._hdl_init_ack = self._ev_loop.call_later(T_INIT_ACK, self._check_for_idle)

    def _check_for_idle(self):
        """Periodic check to see if idle test should be removed"""

        if self._time_last_rx is None or time.time() - self._time_last_rx > T_IDLE:
            logging.info('%s Destroying due to being idle', self)
            self.dispose()
        else:
            self._hdl_init_ack = self._ev_loop.call_later(T_INIT_ACK, self._check_for_idle)

    def _build_and_send_init(self):
        """Build and send the INIT message"""

        # Build the message
        msg_bytes = bytearray(12)
        struct.pack_into('>III', msg_bytes, 0,
                         1,                     # Type - ACK
                         0,                     # Remote Channel
                         self.local_channel     # Local channel
                        )

        # Send it to the remote
        self._owner.send_data(msg_bytes, (self._remote_ip, self._remote_port))
        self._num_init_sent += 1

        # Print log
        logging.info('%s Sent INIT message (%s)', self, self._num_init_sent)

    def _init_ack_missing(self):
        """Called by when init ACK not received within time interval"""

        # Keep resending INIT for up to 3 times
        if self._num_init_sent < 3:
            self._build_and_send_init()
            self._hdl_init_ack = self._ev_loop.call_later(T_INIT_ACK, self._init_ack_missing)
        else:
            # After 3 time, dispose the test
            logging.info('%s INI-ACK missing!', self)
            self.dispose()

    def send_init_ack(self):
        """Send the INIT-ACK reply to INIT"""

        # Send INIT-ACK
        self._build_and_send_init_ack()

        # Start timer to wait for data
        self._hdl_act_to_data = self._ev_loop.call_later(T_INIT_DATA, self._init_data_missing)

    def _init_data_missing(self):
        """Called when DATA is not received after INIT-ACK"""

        # Keep resending INIT-ACK up to 3 times
        if self._num_init_ack_sent < 3:
            self._build_and_send_init_ack()
            self._hdl_act_to_data = self._ev_loop.call_later(T_INIT_DATA, self._init_data_missing)
        else:
            # After 3 times dispose
            logging.info('%s DATA missing after 3 INIT-ACK', self)
            self.dispose()

    def _build_and_send_init_ack(self):
        """Build and send INI-ACK message"""

        # Build message bytes
        msg_bytes = bytearray(12)
        struct.pack_into('>III', msg_bytes, 0,
                         1,                     # Type
                         self.remote_channel,   # Remote channel
                         self.local_channel     # Local channel
                        )

        # Send it
        self._owner.send_data(msg_bytes, (self._remote_ip, self._remote_port))
        self._num_init_ack_sent += 1

        # Print log
        logging.info('%s Sent INIT-ACK message (%s)', self, self._num_init_ack_sent)

    def init_ack_received(self, remote_channel):
        """Handle INIT-ACK message from remote"""

        # Update time of latest datain
        self._time_last_rx = time.time()

        # Check if we are laready init
        if self.is_init:
            # Ignore message, most probably duplicate
            return
        else:
            # Save details. We are init now
            self.remote_channel = remote_channel
            self.is_init = True

            logging.info('%s Test initialized', self)

            # Cancel timer
            self._hdl_init_ack.cancel()
            self._hdl_init_ack = None

            # Start the TEST
            self._start_test()

    def _start_test(self):
        """Start testing"""

        # Take time when starting
        self._time_start = time.time()

        # Scedule sending event on the loop
        logging.info('%s Starting test', self)
        self._hdl_send_data = self._ev_loop.call_soon(self._try_next_send)

        self._log_data()

    def _log_data(self):
        """Make LOG entry"""

        # Cancel pending if any
        if self._hdl_log is not None:
            self._hdl_log.cancel()

        self._log_data_list.append([
            time.time(),
            self._chunks_sent,
            self._chunks_resent,
            self._chunks_acked,
            self._ledbat.cwnd,
            self._ledbat.flightsize,
            self._ledbat.queuing_delay,
            self._ledbat.rtt,
            self._ledbat.srtt,
            self._ledbat.rttvar,
        ])

        # Schedule next call
        self._hdl_log = self._ev_loop.call_later(LOG_INTERVAL, self._log_data)

    def _save_log(self):
        """Save log to the file"""

        filename = '{}-{}-{}.csv'.format(
            int(self._time_start),
            self._remote_ip,
            self._remote_port)

        with open(filename, 'w', newline='') as fp_csv:
            csvwriter = csv.writer(fp_csv)

            # Make header
            csvwriter.writerow(
                [
                    'Time', 'Sent', 'Resent', 'Acked', 'Cwnd', 'Flightsz',
                    'Queuind_delay', 'Rtt', 'Srtt', 'Rttvar'
                ])

            # Write all rows
            for row in self._log_data_list:
                csvwriter.writerow(row)

    def stop_test(self):
        """Stop the test and print results"""

        logging.info('%s Request to stop!', self)
        self._time_stop = time.time()
        self._print_status()

        # Make the last log entry
        if self._log_data:
            self._log_data()
            if self._hdl_log is not None:
                self._hdl_log.cancel()
            self._save_log()

    def _try_next_send(self):
        """Try sending next data segment. This implementation sends data
           as fast as possible using polling. A more elegant solution using
           semaphore would be nicer.
        """

        # TODO: Use semaphore(?) to release sending instead of polling.

        if self._ledbat.cwnd - self._ledbat.flightsize >= SZ_DATA:
            self._build_and_send_data()
            self._ledbat.data_sent(SZ_DATA)
            self._hdl_send_data = self._ev_loop.call_soon(self._try_next_send)

            # Print stats
            if self._chunks_sent % PRINT_EVERY == 0:
                self._print_status()
        else:
            self._hdl_send_data = self._ev_loop.call_soon(self._try_next_send)

    def _print_status(self):
        """Print status during sending"""

        # Calculate values
        test_time = time.time() - self._time_start

        # Prevent div/0 early on
        if test_time == 0:
            return

        all_sent = self._chunks_sent + self._chunks_resent
        tx_rate = all_sent / test_time

        # Print data
        logging.info('Time: %.2f TX/ACK/RES: %s/%s/%s TxR: %.2f',
                     test_time, self._chunks_sent, self._chunks_acked,
                     self._chunks_resent, tx_rate)

        # Print debug data if enabled
        logging.debug('cwnd: %d; flsz: %d; qd: %.2f; rtt: %.6f;',
                      self._ledbat.cwnd, self._ledbat.flightsize,
                      self._ledbat.queuing_delay, self._ledbat.rtt)

    def _send_data(self, seq_num, time_sent, data):
        """Frame given data and send it"""

        # Build the header
        msg_data = bytearray()
        msg_data.extend(struct.pack(
            '>IIIIQ', # Type, Rem_ch, Loc_ch, Seq, Timestamp
            2,
            self.remote_channel,
            self.local_channel,
            seq_num,
            int(time_sent * 1000000)))

        if data is None:
            msg_data.extend(SZ_DATA * bytes([127]))
        else:
            msg_data.extend(data)

        # Send the message
        self._owner.send_data(msg_data, (self._remote_ip, self._remote_port))

    def _build_and_send_data(self):
        """Build and send data message"""

        # Set useful vars
        time_now = time.time()
        seq_num = self._next_seq
        self._next_seq += 1

        # Build and send message
        self._send_data(seq_num, time_now, None)

        # Add to in-flight tracker
        self._inflight.add(seq_num, time_now, None)

        # Update stats
        self._chunks_sent += 1

    def data_received(self, data, receive_time):
        """Handle the DATA message for this test"""

        # Update time of latest datain
        self._time_last_rx = time.time()

        # If we are acceptor, update the stat
        if not self._is_client and not self.is_init:
            if self._hdl_act_to_data is not None:
                self._hdl_act_to_data.cancel()
                self._hdl_act_to_data = None

            self.is_init = True
            logging.info('%s Got first data. Test is init', self)

        # data is binary data _without_ the header
        (seq, time_stamp) = struct.unpack('>IQ', data[0:12])

        # Get the delay
        one_way_delay = (receive_time * 1000000) - time_stamp

        # Send ACK, no delays/grouping
        self._send_ack(seq, seq, [one_way_delay])

    def _send_ack(self, ack_from, ack_to, one_way_delays):
        """Build and send ACK message"""

        msg_bytes = bytearray()

        # Header
        msg_bytes.extend(struct.pack('>III', 3, self.remote_channel, self.local_channel))

        # ACK data
        msg_bytes.extend(struct.pack('>II', ack_from, ack_to))

        # Delay samples
        num_samples = len(one_way_delays)
        msg_bytes.extend(struct.pack('>I', num_samples))
        for sample in one_way_delays:
            msg_bytes.extend(struct.pack('>Q', int(sample)))

        # Send ACK
        self._owner.send_data(msg_bytes, (self._remote_ip, self._remote_port))

    def _resend_indicated(self, resendable_list):
        """Resend items with given SEQ numbers"""

        for seq_num in resendable_list:
            (_, _, data) = self._inflight.get_item(seq_num)
            self._send_data(seq_num, time.time(), data)
            self._inflight.set_resent(seq_num)
            self._chunks_resent += 1

    def ack_received(self, ack_data, rx_time):
        """Handle the ACK"""

        delays = []
        rtts = []

        # Update time of latest datain
        self._time_last_rx = rx_time

        # Extract the data
        (ack_from, ack_to, num_delays) = struct.unpack('>III', ack_data[0:12])

        # Do not process duplicates
        if ack_to < self._inflight.peek():
            logging.info('Duplciate ACK packet. ACKed: %s:%s', ack_from, ack_to)
            return

        # Check for out-of-order and calculate rtts
        for acked_seq_num in range(ack_from, ack_to + 1):

            if acked_seq_num == self._inflight.peek():
                (time_stamp, resent, _) = self._inflight.pop()
            else:
                (time_stamp, resent, _) = self._inflight.pop_given(acked_seq_num)
                self._cnt_ooo += 1

            self._chunks_acked += 1
            last_acked = acked_seq_num

            if not resent:
                rtts.append(rx_time - time_stamp)

        if self._cnt_ooo > OOO_THRESH:
            resendable = self._inflight.get_resendable(last_acked)
            self._resend_indicated(resendable)
            self._ledbat.data_loss()
            logging.info('Dataloss, num-ooo: %s', self._cnt_ooo)

        self._cnt_ooo = 0

        # Extract list of delays
        for dalay in range(0, num_delays):
            delays.append(int(struct.unpack('>Q', ack_data[12+dalay*8:20+dalay*8])[0]))

        # Move to milliseconds from microseconds
        delays = [x / 1000 for x in delays]

        # Feed new data to LEDBAT
        self._ledbat.update_measurements((ack_to - ack_from + 1) * SZ_DATA, delays, rtts)

    def dispose(self):
        """Cleanup this test"""

        # Log information
        logging.info('%s Disposing', self)

        # Cancel all event handles
        if self._hdl_init_ack is not None:
            self._hdl_init_ack.cancel()
            self._hdl_init_ack = None

        if self._hdl_act_to_data is not None:
            self._hdl_act_to_data.cancel()
            self._hdl_act_to_data = None

        if self._hdl_send_data is not None:
            self._hdl_send_data.cancel()
            self._hdl_send_data = None

        if self._hdl_idle is not None:
            self._hdl_idle.cancel()
            self._hdl_idle = None

        if self._hdl_log is not None:
            self._hdl_log.cancel()
            self._hdl_log = None

        if self.stop_hdl is not None:
            self.stop_hdl.cancel()
            self.stop_hdl = None

        # Remove from the owner
        self._owner.remove_test(self)

    def __str__(self, **kwargs):
        return 'TEST: LC:{} RC: {} ({}:{}):'.format(
            self.local_channel, self.remote_channel,
            self._remote_ip, self._remote_port)
