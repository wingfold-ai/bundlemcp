"""How long state parked for a browser round trip through another site stays valid."""

# Seconds a login, consent or upstream-connect state survives in the live store, and
# how long the cookie binding a login to its browser lives alongside it.
BROWSER_STATE_TTL = 600
