from django import template
from datetime import timedelta

from basiclive.utils.misc import natural_seconds

register = template.Library()  

_h = 4.13566733e-15  # eV.s
_c = 299792458e10    # A/s


@register.filter("energy_to_wavelength")  
def energy_to_wavelength(energy): 
    """Convert energy in keV to wavelength in angstroms."""
    energy = float(energy)
    if energy == 0.0:
        return 0.0
    return (_h*_c)/(energy*1000.0)


@register.filter("humanize_duration")
def humanize_duration(duration, sec=False):
    if isinstance(duration, (int, float)):
        return natural_seconds(timedelta(hours=duration).total_seconds())
    return natural_seconds(duration.total_seconds())


@register.filter("natural_duration")
def natural_duration(delta):
    return natural_seconds(delta.total_seconds())
