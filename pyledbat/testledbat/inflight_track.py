"""
Helper class to track data that is inflight and hide data structure.
"""
import collections

class InflightTrack(object):
    """In-Flight data tracker"""

    def __init__(self):
        """Initialize data structures"""
        self._deq = collections.deque() # Contains only seq numbers
        self._store = {}                # Contains [timestamp_sent, resent, data]

    def add(self, seq, time_stamp, data):
        """Add item to the list of data in-flight"""

        self._deq.appendleft(seq)
        self._store[seq] = [time_stamp, False, data]

    def peek(self):
        """Get the seq number of the right-most item"""
        return self._deq[-1]

    def pop(self, get_item=True):
        """Remove the rightmost item"""
        seq_num = self._deq.pop()

        if get_item:
            item = self._store[seq_num]
            del self._store[seq_num]
            return item
        else:
            del self._store[seq_num]

    def get_item(self, seq_num):
        """Get the indicated item"""
        return self._store[seq_num]

    def set_resent(self, seq_num):
        """Set given item as resent"""
        self._store[seq_num][1] = True

    def get_resendable(self, last_seq_acked):
        """Going right-to-left get all seq nums until last_seq_acked"""

        resendable = []
        for seq in reversed(self._deq):
            if last_seq_acked > seq:
                resendable.append(seq)

        return resendable

    def pop_given(self, seq, return_item=True):
        """Remove diven SEQ number"""
        self._deq.remove(seq)
        item = self._store[seq]
        del self._store[seq]

        if return_item:
            return item

    def size(self):
        """Get size of deque"""
        return len(self._deq)
