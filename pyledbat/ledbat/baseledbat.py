"""
This is a base implementation of LEDBAT following the [RFC6817] for LEDBAT
specification and [RFC6298] for round-trip time calculations. This file is
not enough on its own, and must be extended to gate the sending. An example
of such extending is provided by swiftledbat implementation.

N.B. Swiftledbat is not specific branch of ledbat, but merely combination
of libswift and ledbat.
"""

import time
import datetime
import math

class BaseLedbat(object):
    """Base class with constante defined"""

    CURRENT_FILTER = 8          # Number of elements in current delay filter
    BASE_HISTORY = 10           # Number of elements in base delay history
    INIT_CWND = 2               # Number of MSSes in initial cwnd value
    MSS = 1500                  # Maximum segment size
    TARGET = 50                 # Target in milliseconds. Per [RFC6817] must be <= 100ms
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
        self._current_delays = BaseLedbat.CURRENT_FILTER * [1000000]
        self._base_delays = BaseLedbat.BASE_HISTORY * [float('inf')]
        self._flightsize = 0
        self._cwnd = BaseLedbat.INIT_CWND * BaseLedbat.MSS  # Congestion window
        self._last_rollover = time.time()                   # Time last base-delay rollover occured
        self._cto = 1                                       # Congestion timeout (seconds)
        self._queuing_delay = 0
        self._rtt = None                                # Round Trip Time
        self._last_data_loss = 0                        # When was latest dataloss event observed
        self._last_ack_received = None                  # When was the last ACK received
        self._sent_data = []                            # Used to track when and how much is sent values -> (time, data_len)

        # RFC6298
        self._rt_measured = False                       # Flag to check if the first measurement was done
        self._srtt = None
        self._rttvar = None

    def ack_received(self, delays, bytes_acked=None, rt_measurements=None):
        """Parse the received delay sample(s)
           delays is milliseconds, rt_measurements in seconds!
        """

        # If not provided assume Max segment size
        if bytes_acked is None:
            bytes_acked = BaseLedbat.MSS

        # Update time of last ACK
        self._last_ack_received = time.time()

        # Process all received delay samples
        for delay_sample in delays:
            self._update_base_delay(delay_sample)
            self._update_current_delay(delay_sample)

        # Update values
        self._queuing_delay = self._filter_alg(self._current_delays) - min(self._base_delays)
        off_target = (BaseLedbat.TARGET - self._queuing_delay) / BaseLedbat.TARGET
        self._cwnd += BaseLedbat.GAIN * off_target * bytes_acked * BaseLedbat.MSS / self._cwnd
        max_allowed_cwnd = self._flightsize + BaseLedbat.ALLOWED_INCREASE * BaseLedbat.MSS
        self._cwnd = min([self._cwnd, max_allowed_cwnd])
        self._cwnd = max([self._cwnd, BaseLedbat.MIN_CWND * BaseLedbat.MSS])
        self._flightsize = max([0, self._flightsize - bytes_acked])

        # If we don't have RT measurements, keep CTO unchanged
        if rt_measurements is not None:
            self._update_cto(rt_measurements)

    def data_loss(self, will_retransmit=True, loss_size=None):
        """Reduce cwnd if data loss is experienced"""

        # Get the current time
        t_now = time.time()

        if loss_size is None:
            loss_size = BaseLedbat.MSS
        
        # Prevent calling too often
        if self._last_data_loss != 0:
            if t_now - self._last_data_loss < self._rtt:
                # At most once per RTT
                return

        # Save time when last dataloss event happened
        self._last_data_loss = t_now

        # Reduce the congestion window size
        self._cwnd = min([
            self._cwnd, 
            max([self._cwnd / 2, BaseLedbat.MIN_CWND * BaseLedbat.MSS])
        ])

        # Account for data in-flight
        if not will_retransmit:
            self._flightsize = self._flightsize - loss_size

    def _no_ack_in_cto(self):
        """Update CWND if no ACK was received in CTO"""

        self._cwnd = 1 * BaseLedbat.MSS
        self._cto = 2 * self._cto 

    def _update_cto(self, rt_measurements):
        """Calculate congestion timeout (CTO)"""

        # Code here is lifted from [RFC6298] with RTO in [RFC6298]
        # meaning self._cto here. rt_measurements is [float]

        if not self._rt_measured:
            # Set the params per [RFC6298]
            r = rt_measurements[0]
            self._srtt = r
            self._rttvar = r / 2
            self._cto = self._srtt + max([BaseLedbat.G, BaseLedbat.K * self._rttvar])

            # Per [RFC6298] p2.4
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
                self._rttvar = (1 - BaseLedbat.BETA) * self._rttvar + BaseLedbat.BETA * math.fabs(self._srtt - r)
                self._srtt = (1 - BaseLedbat.ALPHA) * self._srtt + BaseLedbat.ALPHA * r
                self._cto = self._srtt + max(BaseLedbat.G, BaseLedbat.K * self._rttvar)

                # Update lates RTT
                self._rtt = r

                # Per RFC6298 p2.4
                if self._cto < 1.0:
                    self._cto = 1.0

    def _filter_alg(self, filter_data):
        """Implements FILTER() algorithm"""

        # Implemented per [RFC6817] MIN filter over a small window
        # multiplied by -1 to get latest window_size values
        window_size = -1 * math.ceil(BaseLedbat.BASE_HISTORY/4)
        return min(filter_data[window_size:])

    def _update_base_delay(self, delay):
        """Update value in base_delay tracker list"""

        t_now = time.time()

        # Implemented per [RFC6817]
        minute_now = datetime.datetime.fromtimestamp(t_now).minute
        minute_then = datetime.datetime.fromtimestamp(self._last_rollover).minute

        if minute_now != minute_then:
            # Shift value at next minute
            self._last_rollover = t_now
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
