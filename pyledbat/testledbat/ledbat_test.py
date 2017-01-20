import logging
import asyncio
import struct
import time

from ledbat import swiftledbat

T_INIT_ACK = 5.0    # Time to wait for INIT-ACK
T_INIT_DATA = 5.0   # Time to wait for DATA after sending INIT-ACK
T_IDLE = 10.0       # Time to wait when idle before destroying

SZ_DATA = 1024      # Data size in each message

class LedbatTest(object):
    """An instance representing a single LEDBAT test"""

    def __init__(self, is_client, remote_ip, remote_port, owner):
        self._is_client = is_client
        self._remote_ip = remote_ip
        self._remote_port = remote_port
        self._owner = owner
        self._print_every = 1000        # How often to print status

        self._num_init_sent = 0
        self._hdl_init_ack = None       # Receive INIT-ACK after ACK

        self._num_init_ack_sent = 0
        self._hdl_act_to_data = None    # Receive DATA after INIT-ACK

        self._hdl_send_data = None      # Used to schedule data sending
        self._hdl_idle = None           # Idle check handle

        self._ledbat = swiftledbat.SwiftLedbat()
        self._direct_send = False       # Send immediately before checking next
        self._next_seq = 1
        self._set_outstanding = set()
        self._sent_ts = {}

        self._cnt_loss = 0              # Each time ACK is not for the min({seq_outstanding}), this gets increased. Once its 3, loss happened
        self._lost_seq = None           # Which piece to resend

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
        self._hdl_idle = asyncio.get_event_loop().call_later(T_IDLE, self._check_for_idle)

    def start_init(self):
        """Start the test initialization procedure"""

        # We can start init only when er are the client
        assert self._is_client

        # Prevent re-starting the test
        assert not self.is_init

        # Send the init message
        self._build_and_send_init()

        # Schedule re-sender / disposer
        self._hdl_init_ack = asyncio.get_event_loop().call_later(T_INIT_ACK, self._check_for_idle)

    def _check_for_idle(self):
        """Periodic check to see if idle test should be removed"""

        if self._time_last_rx is None or time.time() - self._time_last_rx > T_IDLE:
            logging.info('%s Destroying due to being idle' %self)
            self.dispose()
        else:
            self._hdl_init_ack = asyncio.get_event_loop().call_later(T_INIT_ACK, self._check_for_idle)

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
        logging.info('{} Sent INIT message ({})'.format(self, self._num_init_sent))

    def _init_ack_missing(self):
        """Called by when init ACK not received within time interval"""

        # Keep resending INIT for up to 3 times
        if self._num_init_sent < 3:
            self._build_and_send_init()
            self._hdl_init_ack = asyncio.get_event_loop().call_later(T_INIT_ACK, self._init_ack_missing)
        else:
            # After 3 time, dispose the test
            logging.info('{} INI-ACK missing!'.format(self))
            self.dispose()

    def send_init_ack(self):
        """Send the INIT-ACK reply to INIT"""

        # Send INIT-ACK
        self._build_and_send_init_ack()

        # Start timer to wait for data
        self._hdl_act_to_data = asyncio.get_event_loop().call_later(T_INIT_DATA, self._init_data_missing)

    def _init_data_missing(self):
        """Called when DATA is not received after INIT-ACK"""
        
        # Keep resending INIT-ACK up to 3 times
        if self._num_init_ack_sent < 3:
            self._build_and_send_init_ack()
            self._hdl_act_to_data = asyncio.get_event_loop().call_later(T_INIT_DATA, self._init_data_missing)
        else:
            # After 3 times dispose
            logging.info('{} DATA missing after 3 INIT-ACK'.format(self))
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
        logging.info('{} Sent INIT-ACK message ({})'.format(self, self._num_init_ack_sent))

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

            logging.info('%s Test initialized' %self)

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
        logging.info('{} Starting test'.format(self))
        self._hdl_send_data = asyncio.get_event_loop().call_soon(self._try_next_send)

    def stop_test(self):
        """Stop the test and print results"""
        
        logging.info('%s Request to stop!' %self)
        self._time_stop = time.time()
        self._print_status()
        
    def _try_next_send(self):
        """Try sending next data piece"""

        # If we were delayed - now send immediately
        if self._direct_send:
            
            # Print stats
            if self._chunks_sent % self._print_every == 0:
                self._print_status()

            self._build_and_send_data()
            self._direct_send = False
            self._hdl_send_data = asyncio.get_event_loop().call_soon(self._try_next_send)
            return

        # Check we we can send now
        can_send, delay = self._ledbat.try_sending(SZ_DATA)

        if can_send:
            # Print stats
            if self._chunks_sent % self._print_every == 0:
                self._print_status()

            # If we can send now - send and try immediately again
            self._build_and_send_data()
            self._hdl_send_data = asyncio.get_event_loop().call_soon(self._try_next_send)
            
        else:
            # Send after waiting and then try again
            self._hdl_send_data = asyncio.get_event_loop().call_later(delay, self._try_next_send)
            self._direct_send = True

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
        logging.info('Time: %.2f All Sent/Resent: %d/%d TxR: %.2f' %(test_time, all_sent, self._chunks_resent, tx_rate))

        # Print debug data if enabled
        logging.debug('cwnd: %d; cto: %.2f; qd: %.2f; flsz: %d' %(self._ledbat._cwnd, self._ledbat._cto, self._ledbat._queuing_delay, self._ledbat._flightsize))

    def _build_and_send_data(self):
        """Build and send data message"""
        
        # Check what next to send
        resend = False
        if self._lost_seq is not None:
            this_seq = self._lost_seq
            resend = True
            self._lost_seq = None
        else:
            this_seq = self._next_seq
            self._next_seq += 1

        # Get time now
        t_now = time.time()

        # Build the header
        msg_data = bytearray()
        msg_data.extend(struct.pack(
            '>IIIIQ', # Type, Rem_ch, Loc_ch, Seq, Timestamp
            2,
            self.remote_channel, 
            self.local_channel,
            this_seq,
            int(t_now * 1000000)))
        msg_data.extend(SZ_DATA * bytes([127]))

        # Send the message
        self._owner.send_data(msg_data, (self._remote_ip, self._remote_port))

        # Update LEDBAT
        self._ledbat.last_send_time = t_now

        # Append to list of outstanding
        # RTTs are not calculated from resends
        if resend and this_seq in self._sent_ts:
            # Delete stale data if present
            del self._sent_ts[this_seq]
        else:
            self._sent_ts[this_seq] = t_now
        self._set_outstanding.add(this_seq)

        # Update counters
        if resend:
            self._chunks_resent += 1
        else:
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
            logging.info('%s Got first data. Test is init' %self)

        # data is binary data _without_ the header
        (seq, ts) = struct.unpack('>IQ', data[0:12])

        # Get the delay
        one_way_delay = (receive_time * 1000000) - ts 

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

    def ack_received(self, ack_data, rx_time):
        """Handle the ACK"""

        # Update time of latest datain
        self._time_last_rx = time.time()

        # Extract the data
        (ack_from, ack_to, num_delays) = struct.unpack('>III', ack_data[0:12])

        # Check if this is loss event
        if any(self._set_outstanding):

            # If we ack something higher than min outstanding, it might be a loss
            min_outstanding = min(self._set_outstanding)
            if ack_from > min_outstanding:
                self._cnt_loss += 1

            # Check if this is a loss event
            if self._cnt_loss == 3:
                # Declare loss to LEDBAT
                self._ledbat.data_loss(True, SZ_DATA)
                
                # Request resend
                self._lost_seq = min_outstanding

                # Reset the counter
                self._cnt_loss = 0
                
        # Extract list of delays
        delays = []
        for n in range(0, num_delays):
            delays.append(int(struct.unpack('>Q', ack_data[12+n*8:20+n*8])[0]))

        # Move to milliseconds from microseconds
        delays = [x / 1000 for x in delays]

        # Extract RT measurements
        rtts = []
        for seq in range(ack_from, ack_to+1):
            # Try getting from sent timestamps 
            sent_ts = self._sent_ts.get(seq)
            if sent_ts is not None:
                rtts.append(rx_time - sent_ts)
        
        # Update state
        for seq in range(ack_from, ack_to+1):
            self._set_outstanding.discard(seq)
            if seq in self._sent_ts:
                del self._sent_ts[seq]

        # Feed new data to LEDBAT
        self._ledbat.ack_received(delays, (ack_to - ack_from + 1) * SZ_DATA, rtts)

        # Update stats
        self._chunks_acked += ack_to - ack_from + 1

    def dispose(self):
        """Cleanup this test"""

        # Log information
        logging.info('{} Disposing'.format(self))

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

        # Remove from the owner
        self._owner.remove_test(self)

    def __str__(self, **kwargs):
        return 'TEST: LC:{} RC: {} ({}:{}):'.format(self.local_channel, self.remote_channel,
            self._remote_ip, self._remote_port)