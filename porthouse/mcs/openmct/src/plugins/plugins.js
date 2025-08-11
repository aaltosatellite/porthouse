
import HousekeepingPlugin from './housekeeping/HousekeepingPlugin.js';
import EventsPlugin from './events/EventsPlugin.js';
import GroundstationPlugin from './groundstation.js';
import MeasurementsPlugin from './measurements/MeasurementsPlugin.js';
//import OrbitsPlugin from './orbits/OrbitsPlugin.js';

const plugins = {};
plugins.Housekeeping = HousekeepingPlugin;
plugins.Events = EventsPlugin;
plugins.Groundstation = GroundstationPlugin;
plugins.Measurements = MeasurementsPlugin;
//plugins.Orbits = OrbitsPlugin;

export default plugins;
