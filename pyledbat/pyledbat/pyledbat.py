import time
import datetime
import math

class LEDBAT(object):
    CURRENT_FILTER = 8          # Number of elements in current delay filter
    BASE_HISTORY = 10           # Number of elements in base delay history
    INIT_CWND = 2               # Number of MSSes in initial cwnd value
    MSS = 1500                  # Maximum segment size
    TARGET = 100000
    GAIN = 1                    # Congestion window to delay response rate
    ALLOWED_INCREASE = 1
    MIN_CWND = 2

    # [RFC6298] values
    G = 0.1                     # Clock granuality
    K = 4
    ALPHA = 0.125               # alpha, beta per Jacobson, V. and M. Karels, "Congestion Avoidance and Control
    BETA = 0.25

    def __init__(self):
        """Initialize the instance"""
        self._current_delays = LEDBAT.CURRENT_FILTER * [1000000]
        self._base_delays = LEDBAT.BASE_HISTORY * [float('inf')]
        self._flightsize = 0
        self._cwnd = LEDBAT.INIT_CWND * LEDBAT.MSS      # Congestion window
        self._last_rollover = time.time()               # Time last base-delay rollover occured
        self._cto = 1                                   # Congestion timeout (seconds)
        self._queuing_delay = 0
        self._rtt = None                                # Round Trip Time
        self._last_data_loss = 0                        # When was latest dataloss event observed
        self._last_ack_received = None                  # When was the last ACK received
        self._sent_data = []                            # Used to track when and how much is sent values -> (time, data_len)

        # RFC6298
        self._rt_measured = False                       # Flag to check if the first measurement was done
        self._srtt = None
        self._rttvar = None

    def ack_received(self, delays, bytes_acked=None, rt_measurements = None):
        """Parse the received delay sample(s)"""

        # If not provided assume Max segment size
        if bytes_acked is None:
            bytes_acked = LEDBAT.MSS

        # Update time of last ACK
        self._last_ack_received = time.time()

        # Process all received delay samples
        for delay_sample in delays:
            self._update_base_delay(delay_sample)
            self._update_current_delay(delay_sample)

        # Update values
        self._queuing_delay = self._filter_alg(self._current_delays) - min(self._base_delays)
        off_target = (LEDBAT.TARGET - self._queuing_delay) / LEDBAT.TARGET
        self._cwnd += LEDBAT.GAIN * off_target * bytes_acked * LEDBAT.MSS / self._cwnd
        max_allowed_cwnd = self._flightsize + LEDBAT.ALLOWED_INCREASE * LEDBAT.MSS
        self._cwnd = min([self._cwnd, max_allowed_cwnd])
        self._cwnd = max([self._cwnd, LEDBAT.MIN_CWND * LEDBAT.MSS])
        self._flightsize = max([0, self._flightsize - bytes_acked])

        # If we don't have RT measurements, keep CTO unchanged
        if rt_measurements is not None:
            self._update_cto(rt_measurements)

    def data_loss(self, will_retransmit=True, loss_size=None):
        """Reduce cwnd if data loss is experienced"""

        if loss_size is None:
            loss_size = LEDBAT.MSS
        
        # Prevent calling too often
        if self._last_data_loss != 0:
            if time.time() - self._last_data_loss < self._rtt:
                # At most once per RTT
                return

        # Save time when last dataloss event happened
        self._last_data_loss = time.time()

        # Reduce the congestion window size
        self._cwnd = min([
            self._cwnd, 
            max([self._cwnd / 2, LEDBAT.MIN_CWND * LEDBAT.MSS])
        ])

        # Account for data in-flight
        if not will_retransmit:
            self._flightsize = self._flightsize - loss_size

    def try_sending(self, data_len):
        """Check if data can be sent"""
        
        # Per [RFC6817] use cwnd to gate the amount of data
        # that is sent to the network in one RTT.

        # Check for extreme congestion
        if self._last_ack_received != None and self._flightsize > 0 and time.time() - self._last_ack_received > self._cto:
            self._no_ack_in_cto()

        # Check if we have any RT measurements? (Slow start some-day)
        if self._rtt is None:
            # Send now
            self._flightsize += data_len
            self._sent_data.append((time.time(), data_len))
            return (True, None)

        # Per [RFC6817] p2.4.2 cwnd is the amount of data that is allowed to
        # be outstanding in an RTT

        # Calculate data sent in last RTT
        sends_in_rtt = []
        cutoff_time = time.time() - self._rtt
        sent_data = 0       # Flightsize during last RTT

        for entry in self._sent_data:
            if entry[0] > cutoff_time:
                sent_data += entry[1]
                sends_in_rtt.append(entry)
            else:
                # All remaining entries are older
                break

        # Prevent list for growing too big
        self._sent_data = sends_in_rtt

        # Check if the flightsize in last RTT is less than cwnd
        if sent_data + data_len <= self._cwnd:
            # Data can be sent to the socket now
            self._flightsize += data_len
            self._sent_data.append((time.time(), data_len))
            return (True, None)
        
        else:
            # Calculate backoff when retry can be made (for this data size)
            # This it TODO to define best way to calc
            backoff = self._cto / 2
            return (False, backoff)

    def _no_ack_in_cto(self):
        """Update CWND if no ACK was received in CTO"""

        self._cwnd = 1 * LEDBAT.MSS
        self._cto = 2 * self._cto 

    def _update_cto(self, rt_measurements):
        """Calculate congestion timeout (CTO)"""

        # Code here is lifted from [RFC6298] with RTO in [RFC6298]
        # meaning self._cto here. rt_measurements is [float]

        if not self._rt_measured:
            # Set the params per RFC
            r = rt_measurements[0]
            self._srtt = r
            self._rttvar = r / 2
            self._cto = self._srtt + max([LEDBAT.G, LEDBAT.K * self._rttvar])

            # Per RFC6298 p2.4
            if self._cto < 1.0:
                self._cto = 1.0

            # Update state
            self._rt_measured = True
            self._rtt = r
            
            # If we have more than 1 measurement - rerun this
            if len(rt_measurements) > 1:
                self._update_cto(rt_measurements[1:])
        else:
            # Update CTO based on round trip time measurements
            for r in rt_measurements:
                self._rttvar = (1 - LEDBAT.BETA) * self._rttvar + LEDBAT.BETA * math.fabs(self._srtt - r)
                self._srtt = (1 - LEDBAT.ALPHA) * self._srtt + LEDBAT.ALPHA * r
                self._cto = self._srtt + max(LEDBAT.G, LEDBAT.K * self._rttvar)

                # Update lates RTT
                self._rtt = r

                # Per RFC6298 p2.4
                if self._cto < 1.0:
                    self._cto = 1.0

    def _filter_alg(self, filter_data):
        """Implements FILTER() algorithm"""

        # Implemented per [RFC6817] MIN filter over a small window
        # multiplied by -1 to get latest window_size values
        window_size = -1 * math.ceil(LEDBAT.BASE_HISTORY/4)
        return min(filter_data[window_size:])

    def _update_base_delay(self, delay):
        """Update value in base_delay tracker list"""

        # Implemented per [RFC6817]
        minute_now = datetime.datetime.fromtimestamp(time.time()).minute
        minute_then = datetime.datetime.fromtimestamp(self._last_rollover).minute

        if minute_now != minute_then:
            # Shift value at next minute
            self._last_rollover = time.time()
            self._base_delays = self._base_delays[1:]
            self._base_delays.append(delay)
        else:
            # For each measurements during the same minute keep minimum value
            # at the end of the list
            self._base_delays[-1] = min([self._base_delays[-1], delay])

    def _update_current_delay(self, delay):
        """Add new value to the current delays list"""

        # Implemented per [RFC6817]
        self._current_delays = self._current_delays[1:]
        self._current_delays.append(delay)
