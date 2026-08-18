import numpy as np
from scipy import signal


class ECGFilter:

    def __init__(
        self,
        fs: float = 250.0,
        hp_cutoff: float = 0.5,
        lp_cutoff: float = 40.0,
        notch_freq: float = 50.0,
        notch_q: float = 30.0,
    ):
        self.fs = fs
        self.hp_cutoff = hp_cutoff
        self.lp_cutoff = lp_cutoff
        self.notch_freq = notch_freq
        
        nyq = 0.5 * fs

        # 1. High-pass filter (Butterworth 2nd order)
        # 0.5 Hz removes baseline wander strongly
        self.b_hp, self.a_hp = signal.butter(2, hp_cutoff / nyq, btype='highpass')
        self.zi_hp = signal.lfilter_zi(self.b_hp, self.a_hp)
        self.zi_hp_state = np.zeros_like(self.zi_hp)
        
        # 2. Low-pass filter (Butterworth 2nd order)
        self.b_lp, self.a_lp = signal.butter(2, lp_cutoff / nyq, btype='lowpass')
        self.zi_lp = signal.lfilter_zi(self.b_lp, self.a_lp)
        self.zi_lp_state = np.zeros_like(self.zi_lp)

        # 3. Notch filter
        self.notch_enabled = notch_freq > 0
        if self.notch_enabled:
            w0 = notch_freq / nyq
            self.b_notch, self.a_notch = signal.iirnotch(w0, notch_q)
            self.zi_notch = signal.lfilter_zi(self.b_notch, self.a_notch)
            self.zi_notch_state = np.zeros_like(self.zi_notch)

    def process(self, x: float) -> float:
        """
        Feed one raw ADC sample, get one filtered sample back.
        """
        # High-pass
        y_hp, self.zi_hp_state = signal.lfilter(
            self.b_hp, self.a_hp, [x], zi=self.zi_hp_state
        )
        val = y_hp[0]
        
        # Low-pass
        y_lp, self.zi_lp_state = signal.lfilter(
            self.b_lp, self.a_lp, [val], zi=self.zi_lp_state
        )
        val = y_lp[0]

        # Notch
        if self.notch_enabled:
            y_n, self.zi_notch_state = signal.lfilter(
                self.b_notch, self.a_notch, [val], zi=self.zi_notch_state
            )
            val = y_n[0]

        return float(val)

    def reset(self, value: float = 0.0):
        """
        Reset all filter states (call after a leads-off reconnect).
        Multiplies the steady-state step response (zi) by the DC value.
        """
        # Prime the high-pass filter with the raw ADC DC offset
        # This prevents the massive baseline swing transient on startup!
        self.zi_hp_state = self.zi_hp * value
        
        # After the HP filter, the DC offset is 0, so seed downstream filters with 0
        self.zi_lp_state = self.zi_lp * 0.0
        if self.notch_enabled:
            self.zi_notch_state = self.zi_notch * 0.0
