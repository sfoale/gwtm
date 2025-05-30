from enum import IntEnum

class frequency_units(IntEnum):
    """Enumeration for frequency units."""
    Hz = 1
    kHz = 2
    GHz = 3
    MHz = 4
    THz = 5

    @staticmethod
    def get_scale(unit):
        """Return the scale factor for the given frequency unit."""
        if unit == frequency_units.Hz:
            return 1.0
        if unit == frequency_units.kHz:
            return 1000.0
        if unit == frequency_units.MHz:
            return 1000000.0
        if unit == frequency_units.GHz:
            return 1000000000.0
        if unit == frequency_units.THz:
            return 1000000000000.0