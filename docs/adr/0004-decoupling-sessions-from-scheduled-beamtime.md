# Decoupling Experimental Sessions from Scheduled Beamtime

Synchrotron beamline operations frequently involve mail-in queues, automated screening, and emergency shift adjustments that occur outside strictly booked calendar slots. We decided that `Session` (experimental work) and `Stretch` (active beam usage intervals) operate independently of `Beamtime` (scheduled reservations), associating them dynamically via timestamp overlap rather than enforcing foreign key constraints.
