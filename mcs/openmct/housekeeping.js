/*
 * OpenMCT Plugin for connecting to porthouse housekeeping backend
 */


 /*
 *   Default arguments and styling.
 */
 function HousekeepingDefaultArgs() {
     return {
         rootKey:   "satellite",
         namespace: "porthouse",

         styling : {
             rootFolderName: "porthouse Raw Housekeeping",
             dataPointText: "porthouse Raw Housekeeping",
             frameName:  'porthouse Housekeeping Frame',
             frameCssClass: 'icon-info',
             frameDesc: 'porthouse housekeeping frame',
             dataPointName: 'porthouse Housekeeping Data Point',
             dataPointDesc: 'porthouse housekeeping data point',
             dataPointCssClass: 'icon-telemetry',
             limits : LIMITS
         }
     }
 }

function PorthouseHousekeepingPlugin(connector, args=HousekeepingDefaultArgs()) {
    const rootKey = args.rootKey;             // rootkey of the satellite (fs1)
    const namespace = args.namespace;         // namespace for openmct
    const styling = args.styling;             // styling choices (see below)

    // Cached schema from the server
    let schema = null;
    let subscriptions = {};
    let buffered_promises = {};

    // Start to download the schema straight away (can be omitted)
    var schemaPromise = null;

    getSchema();

    /*
     * Get housekeeping schema
     */
    function getSchema() {

        if (schema !== null) {
            return Promise.resolve(schema);
        }
        if (schemaPromise !== null){
            return schemaPromise;
        }

        schemaPromise = connector.remoteCall("housekeeping", "get_schema")
        .then(data => {
            schema = data.result.schema;
            console.log(schema);
            return schema;
        })
    }


    /*
    * OpenMCT installation part starts here
    */
    return function install(openmct) {

        //Check whether there is subscription for subsystem+telemetry
        function isSubscribed(subskey, telemetry) {
            if(subskey in subscriptions) {
                return (telemetry in subscriptions[subskey]);
            }
            return false;
        }

         /*
         * Foresail telemetry provider defines the interface for telemetry transfer
         */
        openmct.telemetry.addProvider({

            /*
             * Support subscribing only for Foresail
             */
            supportsSubscribe: function (domainObject, callback, options) {
                return domainObject.type === telemetryType;
            },

            /*
             * Callback to subscribe a Foreasail data point
             */
            subscribe: function (domainObject, callback) {
                //console.log("subscribe " + domainObject.identifier.key);

                /*
                * if just reconnecting, dont clear subscriptions
                * just ask new subscription from the server.
                * Subscribe to subsystem+telemetry
                */
                function subscribe(subsKey, telemetry){
                    //Check if there is subscription for subsystem
                    if(!(subsKey in subscriptions)){
                        subscriptions[subsKey] = {};
                    }

                    //check if there is subscription for telemetry in subsystem
                    if(!(telemetry in subscriptions[subsKey])){
                        subscriptions[subsKey][telemetry] = {};
                    }
                }

                function subscriptionReturnCallback(message){
                    let key = message.subscription.subsystem;
                    //console.log("subs",subscriptions[key]);
                    for (let val of message.subscription.data){
                        //console.log(subscriptions, key, val.id);
                        if (val.id in subscriptions[key]){
                            subscriptions[key][val.id](val);
                        }
                    }
                }

                let key = domainObject.identifier.key;
                let keys = key.split(".");
                let satellite = keys[0];
                let subsystem = keys[1];
                let field = keys[2];
                let subsKey = satellite+"."+subsystem;

                if (!isSubscribed(subsKey, key)) {
                    // Frame has not been subscribed
                    subscribe(subsKey, key);
                    connector.subscribe("housekeeping", { "subsystem": subsystem, "fields": field }, subscriptionReturnCallback);
                }
                // Add callback to list
                subscriptions[subsKey][key] = callback;

                // Return the unsubscribing callback
                return function unsubscribe() {
                    //console.log("unsubscribe", subsKey, key);
                    delete subscriptions[subsKey][key];
                    if (Object.keys(subscriptions[subsKey]).length === 0) {
                        delete subscriptions[subsKey];
                    }
                    //console.log(JSON.stringify(params));
                    connector.unsubscribe("housekeeping", { "subsystem": subsystem, "fields": field });
                }.bind(this);

            },


            /*
             * Support history requests for housekeeping
             */
            supportsRequest: function (domainObject, options) {
                return domainObject.type === telemetryType;
            },

            /*
             * History request for a Foresail data point
             * Promise data (create buffer)
             * Wait (timeout) during which new requests can be asked (buffer filled)
             * Handle all buffered requests and ask data from backend
             * When message is received from the backend process the data
             */
            request: function(domainObject, options) {

                console.log("Request", domainObject.identifier.key, "(", options.strategy, ")");

                let key = domainObject.identifier.key; // example : fs1.eps.uptime
                let keys = key.split(".");
                let satellite = keys[0];
                let subsystem = keys[1];
                let telemetry = keys[2];


                function promiseToBeFulfilled(req_ident, key, options) {
                    return new Promise((resolve, reject) => {
                        if(buffered_promises[req_ident] == null)
                            buffered_promises[req_ident] = [];
                        buffered_promises[req_ident].push({
                                            id: key,
                                            options: options,
                                            promise: resolve,
                                            reject: reject });
                    });
                };

                function params(promises, options) {
                    return {
                       "key": promises.map(o => o.id),
                       "options": options
                    };
                 };

                 function handleMessage(msg, promises) {
                     let hk = msg.result.housekeeping; // Housekeeping data from the backend
                     for (let promise of promises) {
                         // Fullfill all buffered promises with the received data
                         //console.log(promise.id, hk.filter( data => (n data.id == promise.id) ));
                         promise.promise(hk.filter( data => (data.id == promise.id) ));
                     }
                };

                // Request identifier for grouping
                var req_ident = satellite + "." + subsystem + "_" + options.strategy;

                // Has very similar request call made recently
                if (req_ident in buffered_promises) {
                    // If you return a promise
                    return promiseToBeFulfilled(req_ident, key, options);
                }
                else {
                    // If no
                    buffered_promises[req_ident] = [ ];

                    // Initiate the actual RPC call when 100ms has passed from the first call
                    setTimeout(function() {
                        // Returns currently pending RPCcall and list of promises
                        let promises = buffered_promises[req_ident];
                        delete buffered_promises[req_ident];

                        console.log("Requesting", promises.map(promise => promise.id));

                        connector.remoteCall("housekeeping", "request", params(promises, options)).then(response => {
                            handleMessage(response, promises);
                        });
                    }, 100);

                    return promiseToBeFulfilled(req_ident, key, options);
                }
            },

            /*
             * For dynamic metadata
             */
            supportsMetadata: function (domainObject, options) {
                return false; // domainObject.type === 'foresail.telemetry';
            },
            getMetadata: function (domainObject) {
                return;
            },


            /*
             * Limit provider that uses the styling given during initialization
             */
            supportsLimits: function(domainObject) {
                return domainObject.type === telemetryType;
            },

            getLimitEvaluator: function(domainObject) {
                return {
                    evaluate: function (datum, valueMetadata) {
                        if(valueMetadata == null || datum == null){
                            return;
                        }

                        //Not everything has limits
                        if(valueMetadata["limits"] == null){
                            return;
                        }

                        let lower_limit = valueMetadata["limits"][0];
                        let upper_limit = valueMetadata["limits"][1];

                        //use styling if true
                        if (datum.value < lower_limit) {
                            return styling.limits.rl;
                        }else if (datum.value > upper_limit) {
                            return styling.limits.rh;
                        }

                        return;
                    }

                };
            }
        });


        /*
         * Foresail object provider tells the detailed information to OpenMCT about the object
         */
        openmct.objects.addProvider(namespace, {
            get: function (identifier) {
                return getSchema().then(function (schema) {
                    //console.log("get " + identifier.key,identifier);
                    let keys = identifier.key.split(".");

                    if (identifier.key === rootKey) {
                        //var satellite = getHousekeepingObject(schema, identifier.key);
                        return {
                            identifier: identifier,
                            name: styling.rootFolderName,
                            type: 'folder',
                            location: 'ROOT'
                        };
                    }
                    else if (keys.length == 2) {

                        let subsystem = getHousekeepingObject(schema, identifier.key, rootKey);
                        if (subsystem === undefined)
                            throw "No such subsystem" + identifier.key;

                        return {
                            identifier: identifier,
                            name: subsystem.name,
                            type: namespace+'.frame',
                            location: namespace+':'+rootKey
                        };

                    } else {

                        let param = getHousekeepingObject(schema, identifier.key, rootKey);
                        if (param === undefined) {
                            console.error("No such field", identifier.key);
                            return;
                        }

                        let dict = {
                            identifier: identifier,
                            name: param.name,  // TODO: TypeError: param is undefined
                            type: telemetryType,
                            location: namespace+':'+rootKey+"." + keys[1],
                            telemetry: {
                                values: [
                                    {
                                        key: "utc",
                                        source: "timestamp",
                                        name: "Timestamp",
                                        format: "utc",
                                        hints: { domain: 1 }
                                    },
                                    {
                                        key: "value",
                                        name: "Value",
                                        units: param.units,
                                        format: param.format
                                    }
                                ]
                            }
                        };

                        //Only values that have calibration can be minmaxed
                        if(param.calibration !== undefined || param.enumeration){
                            dict.telemetry.values[1].hints = {range : 1};
                            //console.log(dict.telemetry.values[1]);
                        }

                        if(param.limits !== undefined){
                            dict.telemetry.values[1].limits = param.limits;
                            //console.log(dict.telemetry.values[1]);
                        }

                        return dict;
                    }
                });

            }
        });


        /*
         * Composition provider tells the hierarchy of the objects. Aka what is inside of what.
         */
        openmct.composition.addProvider( {
            appliesTo: function (domainObject) {
                // Serve only folders (Foresail root) and Foresail Frame structures
                return domainObject.identifier.namespace === namespace &&
                       (domainObject.type === 'folder' || domainObject.type === namespace+'.frame');
            },
            load: function (domainObject) {

                //console.log("load " + domainObject.identifier.key, domainObject);

                let keys = domainObject.identifier.key.split(".");
                if (domainObject.identifier.key === rootKey) // FS root
                {
                    return getSchema().then(function (schema){
                        return Promise.resolve(schema.subsystems.map(function (m) {
                            return {
                                namespace: namespace,
                                key: domainObject.identifier.key + "." + m.key
                            };
                        }));
                    })

                }
                else {

                    // Return simple list of all telemetry data points under the subsystem
                    return getSchema().then(function (schema) {
                        let subsystem = schema.subsystems.filter(function (m) {
                            return rootKey+"." + m.key ===  domainObject.identifier.key;
                        })[0];
                        //console.log("add providers",subsystem);

                        if (subsystem == undefined)
                            return [];

                        return subsystem.fields.map(function (m) {
                            return {
                                namespace: namespace,
                                key: domainObject.identifier.key + "." + m.key
                            };
                        });
                    });

                }

                return getSchema().then(function (schema) {
                        return schema.measurements.map(function (m) {
                            return {
                                namespace: namespace,
                                key: m.key
                            };
                        });
                    });
            }
        });


        /*
         * Create root object for all the housekeeping stuff
         */
        openmct.objects.addRoot({
            namespace: namespace,
            key: rootKey
        });

        /*
         * Custom type identificator for housekeeping frames/subsystems
         */
        openmct.types.addType(namespace+'.frame', {
            name: styling.frameName,
            description: styling.frameDesc,
            cssClass: styling.frameCssClass
        });

        /*
         * Custom type identificator for telemetry points
         */
        const telemetryType = namespace+'.telemetry';
        openmct.types.addType(telemetryType, {
            name: styling.dataPointName,
            description: styling.dataPointDesc,
            cssClass: styling.dataPointCssClass
        });

    }
}






/*
 * Return dictionary object based on the key
 */
function getHousekeepingObject(dictionary, key, rootKey) {

    let keys = key.split(".");
    if (keys[0] !== rootKey)
        return;

    if (keys.length == 1) {
        // Root
        return dictionary;
    }
    else if (keys.length == 2) {
        // Get housekeeping obejct
        subsystem = dictionary.subsystems.filter( m => (m.key === keys[1]) )[0];
        if (subsystem === undefined)
            throw "No such subsystem" + identifier.key;
        return subsystem;
    }
    else if (keys.length == 3) {
        let subsystem = dictionary.subsystems.filter(m => (m.key === keys[1]))[0];
        if (subsystem === undefined)
            throw "No such subsystem" + identifier.key;

        field = subsystem.fields.filter(m => (m.key === keys[2]))[0];
        if (subsystem === undefined)
            throw "No such field" + identifier.key;

        return field;
    }

}



const LIMITS = {

    rh: {
        cssClass: "is-limit--upr is-limit--red",
        name: "Red High"
    },
    rl: {
        cssClass: "is-limit--lwr is-limit--red",
        name: "Red Low"
    },
    yh: {
        cssClass: "is-limit--upr is-limit--yellow",
        name: "Yellow High"
    },
    yl: {
        cssClass: "is-limit--lwr is-limit--yellow",
        name: "Yellow Low"
    }
};
