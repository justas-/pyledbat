"""
Wrapper class implementing simple RT and RTT measurements.
"""
import time
import math

from ledbat import baseledbat

class SimpleLedbat(baseledbat.BaseLedbat):
    """Simple implementation of LEDBAT"""

    # [RFC6298] values
    COEF_G = 0.1
    COEF_K = 4
    COEF_ALPHA = 0.125               # alpha, beta per Jacobson, V. and M. Karels, "Congestion Avoidance and Control
    COEF_BETA = 0.25

    @property
    def cwnd(self):
        """Get Congestion Window Size"""
        return self._cwnd

    @property
    def flightsize(self):
        """Get amount of data in-flight (sent but not ACKed)"""
        return self._flightsize

    @property
    def rtt(self):
        """Get Round-trip time estimate"""
        return self._rtt

    @property
    def queuing_delay(self):
        """Get queuing delay estimate"""
        return self._queuing_delay

    def __init__(self):
        """Init the required variables"""

        self.last_send_time = None

        # RFC6298
        self._rt_measured = False  # Flag to check if the first measurement was done
        self._srtt = None
        self._rttvar = None

        super().__init__()

    def data_sent(self, data_len):
        """Increase amount of data in flight"""

        self._flightsize += data_len
        self.last_send_time = time.time()

    def update_measurements(self, data_acked, ow_times, rt_times):
        """Update LEDBAT calculations. data_acked - number of bytes acked,
        if None, will be num of ow_times * MSS, ow_limes - array of one-way
        delay measurements (oldest to newest), rt_time - round-trip time
        measurements, oldest to newest"""

        if data_acked is None:
            num_data = len(ow_times) * self.MSS
        else:
            num_data = data_acked

        self._ack_received(num_data, ow_times, rt_times)

    def _update_cto(self, rtt_values):
        """Calculate Congestion Timeout value"""

        # Code here is lifted from [RFC6298] with RTO in [RFC6298]
        # meaning self._cto here. rt_measurements is [float]

        # Filter value to the lowest value, as some measurements should be void
        # when using delayed ACKs

        rtt = min(rtt_values)

        if not self._rt_measured:
            # Set the params per [RFC6298]
            self._srtt = rtt
            self._rttvar = rtt / 2
            self._cto = self._srtt + max([self.COEF_G, self.COEF_K * self._rttvar])

            # Update state
            self._rt_measured = True

        else:
            # Update CTO based on round trip time measurements
            self._rttvar = (1 - self.COEF_BETA) * self._rttvar + self.COEF_BETA * math.fabs(self._srtt - rtt)
            self._srtt = (1 - self.COEF_ALPHA) * self._srtt + self.COEF_ALPHA * rtt
            self._cto = self._srtt + max(self.COEF_G, self.COEF_K * self._rttvar)

        # Per [RFC6298] p2.4
        if self._cto < 1.0:
            self._cto = 1.0
        
        self._rtt = rtt
