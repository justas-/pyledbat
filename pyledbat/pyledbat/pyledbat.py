import time
import datetime
import math
import logging

class LEDBAT(object):
    CURRENT_FILTER = 4          # Number of elements in current delay filter
    BASE_HISTORY = 4            # Number of elements in base delay history
    INIT_CWND = 2               # Number of MSSes in initial cwnd value
    MSS = 1500                  # Maximum segment size
    TARGET = 100000
    GAIN = 1                    # Congestion window to delay response rate
    ALLOWED_INCREASE = 1
    MIN_CWND = 2

    def __init__(self):
        """Initialize the instance"""
        self._current_delays = LEDBAT.CURRENT_FILTER * [1000000]
        self._base_delays = LEDBAT.BASE_HISTORY * [float('inf')]
        self._flightsize = 0
        self._cwnd = LEDBAT.INIT_CWND * LEDBAT.MSS                        # Congestion window
        self._last_rollover = 0                             # Time last X rollover occured
        self._cto = 1                                       # Congestion timeout
        self._queuing_delay = 0
        self._rtt = 0                                       # Round Trip Time
        self._last_data_loss = 0                            # When was latest dataloss event observed

    def ack_received(self, delays, bytes_acked = None):
        """Parse the received delay sample(s)"""

        if bytes_acked is None:
            bytes_acked = LEDBAT.MSS

        # Process all received delay samples
        for delay_sample in delays:
            self._update_base_delay(delay)
            self._update_current_delay(delay)

        # Update values
        self._queuing_delay = self._filter_alg(self._current_delays) - min(_base_delays)
        off_target = (LEDBAT.TARGET - self._queuing_delay) / LEDBAT.TARGET
        self._cwnd += LEDBAT.GAIN * off_target * bytes_acked * LEDBAT.MSS / self._cwnd
        max_allowed_cwnd = self._flightsize + LEDBAT.ALLOWED_INCREASE * LEDBAT.MSS
        self._cwnd = min([self._cwnd, max_allowed_cwnd])
        self._cwnd = max([self._cwnd, LEDBAT.MIN_CWND * LEDBAT.MSS])
        self._flightsize = max([0, self._flightsize - bytes_acked])

        # Update RTT, assuming symetric delay
        self._rtt = 2 * self._filter_alg(self._current_delays)

        self._update_cto()

    def data_loss(self, will_retransmit = True, loss_size = None):
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

    def _update_cto():
        """Calculate congestion timeout (CTO)"""
        pass

    def _filter_alg(self, filter_data):
        """Implements FILTER() algorithm"""
        return min(filter_data)

    def _update_base_delay(self, delay):
        """Update base delay value"""
        pass

    def _update_current_delay(self, delay):
        """Update current delay value"""
        pass
