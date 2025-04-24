// import './porthouse.scss';

// https://github.com/thvaisa/orbit_view_for_openmct-/tree/master/src
// https://gist.github.com/tuckergordon/5cdd5cc346b6b1d1fd0120562ac23d5f
// https://celestrak.org/NORAD/elements/stations.txt
// https://github.com/ilovetensor/sat-track
// https://github.com/nsat/jspredict
// https://gitlab.com/librespacefoundation/satnogs/satnogs-network/-/blob/master/network/static/js/polar_svg.js?ref_type=heads


// https://github.com/shashwatak/satellite-js
// https://db-satnogs.freetls.fastly.net/static/js/map.js



import OrbitsView from './OrbitsView.vue';
//import Skymap from './Skymap.vue';


let defaultConfig = {
    background: "static/world.topo.bathy.200407.3x5400x2700.jpg",
    groundStation: {
        "icon": "./icons/gs.png",
        "name": "Helsinki",
        "position": [ 60.168417, 24.9433348 ],
        "elevation": 0,
        "visibility": 0
    },

    TLEUpdateInterval: 3600000, // [ms]
    updateInterval: 2000
};



function PorthouseOrbitsPlugin(connector, options)
{
    function getSatellites() {
        let params = {};
        return connector.remoteCall("tracking", "get_targets", params)
            .then(data => {
                schema = data.result.schema;
                console.log(schema);
                return schema;
            });
    }

    function getGroundstations() {
        let params = {};
        return connector.remoteCall("tracking", "get_groundstations", params)
            .then(data => {
                schema = data.result.schema;
                console.log(schema);
                return schema;
            });
    }
    return OrbitsPlugin(getSatellites, getGroundstations, options);
}


//export default function () {


function OrbitsPlugin(getSatellites, getGoundstations, options)
{
    options = Object.assign({}, {
        rootKey: "orbits",
    }, options || {});

    const config = Object.assign({}, defaultConfig, options);
    //const getSatellites = getSatellites;
    //const getGoundstations = getGoundstations;


    return function install(openmct)
    {
        openmct.telemetry.addProvider({
            request: function (domainObject, options) {
                console.log("ORBIT: Provide", domainObject, options);
                return getSatellites();
            },
            supportsRequest: function (domainObject, options) {
                return domainObject.type === "porthouse.orbitmap";
            },
            supportsSubscribe: function (domainObject, callback, options) {
                return false; // return domainObject.type === "porthouse.orbitmap";
             },
            supportsMetadata: function (domainObject, options) { return false; },
            supportsLimits: function (domainObject) { return false; },
        });

        openmct.types.addType("porthouse.orbitmap", {
            name: "OrbitViewer",
            creatable: true,
            description: "View orbits",
            cssClass: 'icon-gauge',
            initialize(domainObject) {

            }
            /*form: Object.keys(options.trackables).map(function (trackable) {
                return {
                    "key": trackable,
                    "name": trackable,
                    "control": "checkbox",
                    property: [
                        "trackables",
                        trackable
                    ]
                }
            })*/
        });


        openmct.objectViews.addProvider({
            name: 'Orbit Map',
            key: 'orbitmap',
            cssClass: 'icon-clock',
            canView: function (domainObject) {
                return domainObject.type === "porthouse.orbitmap";
            },
            view: function (domainObject) {

                // Define how view can access openmct's clock
                let getTime = function (current = false) {
                    return openmct.time.boundsVal.end;
                }

                //Set update loop for trackables
                let TLEUpdateLoop = function (domainObject) {
                    return openmct.telemetry.request(domainObject);
                }.bind(null, domainObject);

                return new OrbitMapView.OrbitMapView(
                    domainObject, options, getTime, TLEUpdateLoop, document, openmct);
            }
        });

        //openmct.composition.addPolicy(new GaugeCompositionPolicy(openmct).allow);
    }
}

//

// https://visibleearth.nasa.gov/images/73751/july-blue-marble-next-generation-w-topography-and-bathymetry
// https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73751/world.topo.bathy.200407.3x5400x2700.jpg

/*const L = require('leaflet');
const orbits = require('./orbitSolver.js');
const DataDisplay = require('./dataDisplay.js');
const AOSDataDisplay = require('./aosDataDisplay.js');
const LineDrawer = require('./lineDrawer.js');
const MarkerDrawer = require('./markerDrawer.js');*/

/*

var satrec = satellite.twoline2satrec(tleLine1, tleLine2);

function OrbitMapView(domainObject, config, getTime, TLEUpdateLoop, document, openmct)
{

    //store local config for easier use
    domainObject.trackedObjects = [];

    //Create list of trackableObjects
    Object.entries(domainObject.trackables).forEach((values, i) => {
        //Check whether we are even interested of any of these
        if (!values[1]) return;
        if (!(Object.keys(config.trackables).includes(values[0]))) {
            console.error("config.json lacks definition of the trackable", values[0]);
        } else {
            domainObject.trackedObjects.push(new orbits.Trackable(values[0],
                config.trackables[values[0]]));
        }
    });

    //We store the input parameters for further use
    this.domainObject = domainObject;
    this.getTime = getTime;
    this.document = document;
    this.config = config;
    this.openmct = openmct;

    //Loop that updates TLE's remember to destry loops when not needed
    TLEUpdateLoop();
    this.TLEUpdateLoopID = setInterval(
        TLEUpdateLoop,
        config.timings.TLEUpdateInterval)

    //Store how of then markers are updated and what was the last
    //time markers were updated (lastTick)
    this.tmpData = {};
    this.tmpData.updateInterval = config.timings.updateInterval;
    this.tmpData.lastTick = this.getTime();

    //Store observer(ground station) data
    this.observer = new orbits.Observer(this.config.groundStation);

    this.cached_timeouts = [];
}


//import OrbitView from './plugins/orbits/asd.vue'

/*
mounted() {
    this.openmct.time.on('tick', this.tick);
},
beforeUnmount() {
    this.openmct.time.off('tick', this.tick);

}
tick(timestamp) { this.timestamp = timestamp; }
*

OrbitMapView.prototype.show = function (container)
{
    console.debug("ORBIT container:", container);

    this.myContainer = document.createElement("div");
    this.myContainer.style.cssText = "display: flex; width: 100%; height: 100%; flex-wrap: wrap; overflow-y: scroll;";
    container.appendChild(this.myContainer);

    // Create a new div element inside the OpenMCT container for the map
    this.leftPanel = document.createElement("div");
    //this.leftPanel.className += " inline-block-child";
    this.leftPanel.style.cssText = "width: 60%; height: 0; padding-bottom: 60%; margin: 10px 10px;";

    this.rightPanel = document.createElement("div");
    //this.rightPanel.className += " inline-block-child";
    this.rightPanel.style.cssText = "width: 35%; margin: 10px 10px; border: 10px; display: flex; flex-direction: column;";

    //Left and right panel
    this.myContainer.appendChild(this.leftPanel);
    this.myContainer.appendChild(this.rightPanel);

    //put map to the left panel
    this.elemOrbitMapView = this.leftPanel;

    //Display passes
    this.AOSdisplayPanel = document.createElement("div");
    this.AOSdisplayPanel.style.cssText = "width: 100%; margin-bottom: 10px; ";

    //Display current information
    this.dataDisplayPanel = document.createElement("div");
    this.dataDisplayPanel.style.cssText = "width: 100%;   border-top: 40px";

    this.rightPanel.appendChild(this.AOSdisplayPanel);
    this.rightPanel.appendChild(this.dataDisplayPanel);

    this.dataDisplay = new DataDisplay(this.domainObject.trackedObjects,
        this.document, this.dataDisplayPanel);
    this.AOSdisplay = new AOSDataDisplay(this.domainObject.trackedObjects,
        this.observer, this.document,
        this.AOSdisplayPanel);

    //Create map and
    this.map = new L.Map(this.elemOrbitMapView, {
        attributionControl: false,
        center: [0, 0],			//Center map to [0, 0]
        zoomSnap: 0.0				//Fractional zoom is disabled by default.
    });


    var style = document.createElement('style');



    //Max bounds for the map
    this.map.setMaxBounds([[-90, -180], [90, 180]]);
    this.map.fitBounds([[-90, -180], [90, 180]]);


    //Let's create markers and bind them on the map
    this.markerDrawer = new MarkerDrawer(this.domainObject.trackedObjects, this.config);
    this.markerDrawer.getDrawableObjects().map(function (obj) { obj.addTo(this.map) }.bind(this));
    //Draw ground station
    MarkerDrawer.createGroundStation(this.config).addTo(this.map);

    //Let's make orbit drawers
    this.lineDrawer = new LineDrawer(this.domainObject.trackedObjects, this.map);


    //store are listeners so can they can removed when the view goes out of scope
    this.funcRegistry = [];
    this.funcRegistry.push(this.markerDrawer.updateMe.bind(this.markerDrawer));
    this.funcRegistry.push(this.lineDrawer.updateMe.bind(this.lineDrawer));
    this.funcRegistry.push(this.dataDisplay.updateMe.bind(this.dataDisplay));
    this.funcRegistry.push(this.AOSdisplay.updateMe.bind(this.AOSdisplay));

    this.funcRegistry.map(function (func) {
        this.elemOrbitMapView.addEventListener("updateAll", func);
    }.bind(this));





    // Add map tiling service
    L.tileLayer(this.config.map.mapTiles, {
        attribution: "&copy; " + this.config.map.attribution + " contributors",
        maxZoom: 5,
        minZoom: 0.5,
        tileSize: 512,
        zoomOffset: -1,
        backgroundColor: "#AAAA",
        noWrap: true
    }).addTo(this.map);

    //Attribution to the leaflet and map tile provider
    L.control.attribution({
        position: 'topright'
    }).addTo(this.map);

    //var paneClass = document.getElementsByClassName('leaflet-pane');
    //paneClass.zIndex = "40"; //Important z-indexin (draw order).

    //resize map properly
    this.cached_timeouts.push(setTimeout(function () { this.map.invalidateSize() }.bind(this), 1000));
    //setInterval(function(){ this.map.invalidateSize()}.bind(this), 1000);

    //Update map when screen is resized.
    //Kind of hacky, but works okay
    function resizeMap(map) {
        map.invalidateSize();
        let bounds = L.latLngBounds([[90, 180], [-90, -180]]);
        let wantedZoom = map.getBoundsZoom(bounds, true);
        let center = bounds.getCenter();
        map.setView(center, wantedZoom);
        map.fitBounds(bounds, true);
    }

    resizeMap(this.map);
    this.resizeMap = resizeMap.bind(null, this.map);
    window.onresize = this.resizeMap;

    this.updateLoop = updateFunction.bind(null, this.domainObject,
        this.map, this.getTime, this.tmpData,
        this.elemOrbitMapView, this.observer);
    this.openmct.time.on('bounds', this.updateLoop);

};



function updateFunction(domainObject, map, getTime, tmpData, elem, observer, redraw = true) {

    let sendUpdateMessage = true;
    let timestamp = getTime();

    //Check time between lastTick
    if (Math.abs(timestamp - tmpData.lastTick) < tmpData.updateInterval) {
        return;
    }
    tmpData.lastTick = timestamp;


    //Check that each trackedObject has TLE
    domainObject.trackedObjects.forEach(function (obj) {
        let values = obj.getPositionAndCoverage(timestamp, observer);
        if (values == null) {
            sendUpdateMessage = false;
        }
    });

    //Allow update if every trackedobject has TLE
    if (sendUpdateMessage) {
        var event = new CustomEvent('updateAll', {
            detail: {
                timestamp: timestamp,
                redraw: redraw
            }
        });
        elem.dispatchEvent(event);
    } else {
        console.warn("TLE data not set, trying again soon");
    }

};

OrbitMapView.prototype.destroy = function () {

    this.cached_timeouts.map(function (func) {
        clearTimeout(func);
    });


    this.openmct.time.off('bounds', this.updateMarks);

    this.funcRegistry.map(function (func) {
        this.elemOrbitMapView.removeEventListener("updateAll", func);
    }.bind(this));

    clearInterval(this.updateLoop);
    clearInterval(this.TLEUpdateLoopID);

    window.removeEventListener('resize', this.resizeMap);

    this.elemOrbitMapView.parentNode.removeChild(this.elemOrbitMapView);
    this.myContainer.parentNode.removeChild(this.myContainer);
    this.myContainer = null;
    this.elemOrbitMapView = null;
    this.map.remove();
};*/


//module.exports = { OrbitsPlugin: OrbitsPlugin };
