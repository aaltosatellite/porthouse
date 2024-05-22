
## Example target strings as given in processes.yaml and schedule.yaml:
### Satellite targets:
    Aalto-1         # the name given in the TLE.yaml file
    Suomi-100   
    norad:12345     # NORAD ID, TLE searched using space-track.org, doesn't need to be in the TLE.yaml. 
                    # However, if it is, the cached tle is used instead. 

### Celestial objects:
    # "cel:" prefix denotes celestial target type, otherwise satellite with a TLE assumed
    cel:Moon            # uses de440s.bsp by default
    cel:de440s.bsp/Sun  # can use some other ephemeris file also, incl spice kernels [TBC]
    cel:HIP/87937       # A star in the HIP catalog
    cel:34.7/23.4       # RA/DEC in degrees
