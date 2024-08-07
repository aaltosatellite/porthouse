/*
 * OpenMCT Plugin for connecting to porthouse housekeeping backend
 */


function PorthouseHousekeepingPlugin(connector, args)
{

    // Merge args with defaults
    args = Object.assign( {},
        {
            rootKey: "satellite",
            styling: {
                rootFolderName: "porthouse Raw Housekeeping",
                dataPointText: "porthouse Raw Housekeeping",
                frameName: 'porthouse Housekeeping Frame',
                frameCssClass: 'icon-info', // node_modules/openmct/src/styles/_glyphs.scss
                frameDesc: 'porthouse housekeeping frame',
                dataPointName: 'porthouse Housekeeping Data Point',
                dataPointDesc: 'porthouse housekeeping data point',
                dataPointCssClass: 'icon-telemetry',
                limits: LIMITS
            }
        },
        args || {}
    );
    console.info("args", args);

    if (connector == undefined)
        throw "No Porthouse connector defined!";

    const rootKey = args.rootKey;             // rootkey of the satellite (fs1)
    const namespace = "porthouse.housekeeping";         // namespace for openmct
    const styling = args.styling;             // styling choices (see below)

    if (rootKey == undefined)
        throw "No root key defined!";
    if ("porthouse.housekeeping" == undefined)
        throw "No root key defined!";
    if (styling == undefined)
        throw "No root key defined!";

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

        /*
         * Porthouse telemetry provider defines the interface for telemetry transfer
         */
        openmct.telemetry.addProvider({

            /*
             * Support subscribing only for Porthouse
             */
            supportsSubscribe: function (domainObject, callback, options) {
                return domainObject.type === "porthouse.housekeeping";
            },

            /*
             * Callback to subscribe a Foreasail data point
             */
            subscribe: function (domainObject, callback) {
                console.debug("HK: subscribe housekeeping", domainObject.identifier.key);

                let key = domainObject.identifier.key.split(".");
                let satellite = key[0];
                let subsystem = key[1];
                let field = key[2];
                let subsKey = satellite+"."+subsystem;
                //let subsKey = key.splice(-1).join(".");


                function subscriptionReceived(subscription)
                {
                    // New subscribed housekeeping data was received
                    console.debug("HK: Subscription received", subscription.subsystem);

                    // Call per-field callback functions with new data
                    let subsystem = subscription.subsystem; // fs1.eps
                    let timestamp = subscription.timestamp; // unixtimestamp in milliseconds
                    let data = subscription.data; // dict of housekeeping fields

                    console.debug(subscriptions[subsystem])
                    for (const [field, callback] of Object.entries(subscriptions[subsystem])) {
                        console.debug(field, callback);
                        let c = {
                            id: subsystem + "." + field,
                            timestamp: timestamp,
                            value: data[field]
                        };
                        callback(c);
                    }
                }

                if (!(subsKey in subscriptions)) {
                    // New subsystem subscription
                    subscriptions[subsKey] = {};
                    connector.subscribe("housekeeping", subsKey, subscriptionReceived);
                }

                // Add callback to list
                subscriptions[subsKey][field] = callback;

                // Return the unsubscribing callback
                return function unsubscribe() {
                    console.debug("unsubscribe", subsKey, field);
                    delete subscriptions[subsKey][field];
                    if (Object.keys(subscriptions[subsKey]).length === 0) {
                        delete subscriptions[subsKey];
                        connector.unsubscribe("housekeeping", subsKey);
                    }
                }.bind(this);

            },


            /*
             * Support history requests for housekeeping
             */
            supportsRequest: function (domainObject, options) {
                return domainObject.type === "porthouse.housekeeping";
            },

            /*
             * History request for a Porthouse data point
             * Promise data (create buffer)
             * Wait (timeout) during which new requests can be asked (buffer filled)
             * Handle all buffered requests and ask data from backend
             * When message is received from the backend process the data
             */
            request: function(domainObject, options) {

                console.debug("HK: RequestHistory", domainObject.identifier.key, "(", options.strategy, ")");

                let key = domainObject.identifier.key; // example: fs1.eps.uptime
                let keys = key.split(".");
                let satellite = keys[0];
                let subsystem = keys[1];
                let field = keys[2];

                var subsKey = satellite + "." + subsystem;

                // Request identifier for grouping
                var req_ident = subsKey + "_" + options.strategy; // "${satellite}.${subsystem}_${options.strategy}";

                // Has very similar request call made recently
                if (!(req_ident in buffered_promises))
                {
                    // New request
                    buffered_promises[req_ident] = [ ];

                    // Initiate the actual RPC call when 50 ms has passed from the first call
                    setTimeout(function() {
                        // Returns currently pending RPCcall and list of promises
                        let promises = buffered_promises[req_ident];
                        delete buffered_promises[req_ident];

                        console.debug("HK: Requesting", subsKey, promises.map(promise => promise.field), options);

                        // Send RPC to backend
                        connector.remoteCall(
                            "housekeeping",
                            "request",
                            {
                                "subsystem": subsKey,
                                "fields": promises.map(promise => promise.field),
                                "options": {
                                    start: new Date(options.start).toISOString(),
                                    end: new Date(options.end).toISOString(),
                                    strategy: options.strategy,
                                    domain: options.domain,
                                    size: options.size,
                                }
                            }
                        ).then(response => {
                            // Received grouped result from backend
                            console.debug("HK: Received history", subsKey, response.result);

                            // Fullfill all buffered promises with the received data
                            let hk = response.result.housekeeping;
                            for (let promise of promises) {

                                let field_key = subsKey + "." + promise.field;
                                if (options.strategy == "minmax") {
                                    // Unroll housekeeping min/max values for OpenMCT
                                    unrolled_housekeeping = hk.map(
                                        data => {
                                            return { // Object.assign({}, {
                                                id: field_key,
                                                timestamp: new Date(data.timestamp).getTime(),
                                                value: data[promise.field].value
                                            }; //, data[promise.field])
                                        }
                                    );
                                }
                                else {
                                    // Unroll housekeeping values for OpenMCT
                                    unrolled_housekeeping = hk.map(
                                        data => {
                                            return {
                                                id: field_key,
                                                timestamp: new Date(data.timestamp).getTime(),
                                                value: data[promise.field]
                                            };
                                        }
                                    );
                                }

                                // Pass the values to OpenMCT
                                //console.debug(promise.field, unrolled_housekeeping);
                                promise.promise(unrolled_housekeeping);
                            }
                        }, result => { // rejected
                            console.debug("HK: rejected", result);
                            error = { name: "AbortError" };
                            for (let promise of promises)
                                promise.reject(result);
                        });

                    }, 50);

                }

                // Return a promise about future data
                return new Promise((resolve, reject) => {
                    if (buffered_promises[req_ident] == null)
                        buffered_promises[req_ident] = [];
                    buffered_promises[req_ident].push({
                        field: field,
                        options: options,
                        promise: resolve,
                        reject: reject
                    });
                });

            },

            /*
             * For dynamic metadata
             */
            supportsMetadata: function (domainObject, options) {
                return false; // domainObject.type === 'porthouse.telemetry';
            },
            getMetadata: function (domainObject) {
                return;
            },


            /*
             * Limit provider that uses the styling given during initialization
             */
            supportsLimits: function(domainObject) {
                return domainObject.type === "porthouse.housekeeping";
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
                        } else if (datum.value > upper_limit) {
                            return styling.limits.rh;
                        }

                        return;
                    }

                };
            }
        });


        /*
         * Porthouse object provider
         */
        openmct.objects.addProvider("porthouse.housekeeping", {
            get: function (identifier) {
                console.debug("HK: Object provider", identifier.namespace, identifier.key);
                return getSchema().then(function (schema) {
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
                            type: "porthouse.housekeeping.frame",
                            location: "porthouse.housekeeping:" + rootKey
                        };

                    } else {

                        let param = getHousekeepingObject(schema, identifier.key, rootKey);
                        if (param === undefined) {
                            console.error("No such field", identifier.key);
                            return;
                        }

                        let formatt = param.format_type;
                        if (formatt == "integer") formatt = "number";
                        if (formatt == "enumeration") formatt = "string";

                        let dict = {
                            identifier: identifier,
                            name: param.name,  // TODO: TypeError: param is undefined
                            type: "porthouse.housekeeping",
                            location: "porthouse.housekeeping:"+rootKey+"." + keys[1],
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
                                        format: formatt
                                    }
                                ]
                            }
                        };

                        // Only values that have calibration can be minmaxed
                        if(param.calibration !== undefined){
                            dict.telemetry.values[1].hints = {range : 1};

                        }

                        if (param.enumeration !== undefined) {
                            //dict.telemetry.values[1].format = "enum";
                            dict.telemetry.values[1].enumerations = param.enumeration;
                            //dict.telemetry.values[1].hints = { range: 1 };
                        }
                        else
                            dict.telemetry.values[1].hints = { range: 1 };

                        if(param.limits !== undefined){
                            dict.telemetry.values[1].limits = param.limits;
                        }

                        console.debug(dict);
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
                // Serve only folders (Porthouse Houseeeping root) and Porthouse Frame structures
                console.debug("HK: Provides objects? namespace:", domainObject.identifier.namespace, "key:", domainObject.identifier.key, "type: ", domainObject.type);
                return domainObject.identifier.namespace === "porthouse.housekeeping"  &&
                       (domainObject.type === 'folder' || domainObject.type === "porthouse.housekeeping.frame");
            },
            load: function (domainObject) {

                console.debug("HK: Composition provider ", domainObject.identifier.key);

                let keys = domainObject.identifier.key.split(".");
                if (domainObject.identifier.key === rootKey)
                {
                    // namespace=porthouse.housekeeping, key=fs1, type=folder
                    return getSchema().then(function (schema){
                        return Promise.resolve(schema.subsystems.map(function (m) {
                            return {
                                namespace: "porthouse.housekeeping",
                                key: domainObject.identifier.key + "." + m.key
                            };
                        }));
                    })

                }
                else {
                    // namespace=porthouse.housekeeping, key=fs1.obc.arbiter_temperature, type=porthouse.housekeeping

                    // Return simple list of all telemetry data points under the subsystem
                    return getSchema().then(function (schema) {
                        let subsystem = schema.subsystems.filter(function (m) {
                            return rootKey+"." + m.key ===  domainObject.identifier.key;
                        })[0];
                        //console.debug("add providers",subsystem);

                        if (subsystem == undefined)
                            return [];

                        return subsystem.fields.map(function (m) {
                            return {
                                namespace: "porthouse.housekeeping",
                                key: domainObject.identifier.key + "." + m.key
                            };
                        });
                    });

                }

            }
        });


        /*
         * Create root object for all the housekeeping stuff
         */
        openmct.objects.addRoot({
            namespace: "porthouse.housekeeping",
            key: rootKey
        }, openmct.priority.HIGH);

        /*
         * Custom type identificator for housekeeping frames/subsystems
         */
        openmct.types.addType("porthouse.housekeeping.frame", {
            name: styling.frameName,
            description: styling.frameDesc,
            cssClass: styling.frameCssClass
        });

        /*
         * Custom type identificator for telemetry points
         */
        openmct.types.addType("porthouse.housekeeping.field", {
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
