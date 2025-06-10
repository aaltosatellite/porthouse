/*
 * OpenMCT Plugin for connecting to porthouse housekeeping backend
 */

export default function (connector, args)
{


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


    let defaults = {
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
            //limits: LIMITS
        }
    }

    // Merge args with defaults
    args = Object.assign({}, defaults, args || {});
    console.info("HK: args", args);

    if (connector == undefined)
        throw "No porthouse connector defined!";

    const rootKey = args.rootKey;
    const styling = args.styling;

    if (rootKey == undefined)
        throw "No root key defined!";
    if (styling == undefined)
        throw "No styling defined!";

    // Cached schema from the server
    let schema = null;
    let subscriptions = {};
    let buffered_promises = {};

    // Start to download the schema straight away (can be omitted)
    var schemaPromise = null;

    /*
     * OpenMCT installation part starts here
     */
    return function install(openmct) {

        /*
        * Get housekeeping schema
        */
        function getSchema() {
            if (schema !== null) {
                return Promise.resolve(schema);
            }
            if (schemaPromise !== null) {
                return schemaPromise;
            }

            schemaPromise = connector.remoteCall("housekeeping", "get_schema")
                .then(data => {
                    schema = data.result.schema;
                    console.log(schema);
                    return schema;
                })
        }

        getSchema(); // FIXME: Timing hack!

        /*
         * Return dictionary object based on the key
         */
        function getHousekeepingObject(key, rootKey) {

            let keys = key.split(".");
            if (keys[0] !== rootKey)
                return;


            if (keys.length == 1) {
                // Root
                return schema;
            }
            else if (keys.length == 2) {
                // Get subsystem object
                let subsystem = schema.subsystems.filter(m => (m.key === keys[1]))[0];
                if (subsystem === undefined)
                    throw "No such subsystem" + identifier.key;
                return subsystem;
            }
            else if (keys.length == 3) {
                // Get subsystem object
                let subsystem = schema.subsystems.filter(m => (m.key === keys[1]))[0];
                if (subsystem === undefined)
                    throw "No such subsystem" + identifier.key;

                // Get housekeeping object
                let field = subsystem.fields.filter(m => (m.key === keys[2]))[0];
                if (subsystem === undefined)
                    throw "No such field" + identifier.key;

                return field;
            }

        }


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
                        callback({
                            id: subsystem + "." + field,
                            timestamp: timestamp,
                            value: data[field]
                        });
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

                        console.debug("HK: Requesting history", subsKey, promises.map(promise => promise.field), options);
                       
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
                                    // strategy: options.strategy, Just plot normally for now
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

                                let unrolled_housekeeping;
                                let field_key = subsKey + "." + promise.field;
                                // if (options.strategy == "minmax") { Disabled until normal plotting is functional again.
                                //     // Unroll housekeeping min/max values for OpenMCT
                                //     unrolled_housekeeping = hk.map(
                                //         data => {
                                //             return { // Object.assign({}, {
                                //                 id: field_key,
                                //                 timestamp: new Date(data.timestamp).getTime(),
                                //                 value: data[promise.field].value
                                //             }; //, data[promise.field])
                                //         }
                                //     );
                                // }
                                // else {
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
                                // } // Disable minmax for now

                                // Pass the values to OpenMCT
                                //console.debug(promise.field, unrolled_housekeeping);
                                promise.promise(unrolled_housekeeping);
                            }
                        }, result => { // rejected
                            console.debug("HK: rejected", result);
                            let error = { name: "AbortError" };
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
                    evaluate: function (datum, valueMetadata) { // "LimitEvaluator"

                        // datum = { "timestamp": 1491267051538, "id": "prop.fuel",  "value": 77 }
                        // valueMetadata = ??
                        if (valueMetadata == null || datum == null){
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
                    }

                };
            }
        });


        /*
         * Provide object defintions
         */
        openmct.objects.addProvider("porthouse.housekeeping", {
            get: function (identifier) {
                //console.debug("HK: Provider object definition", identifier.namespace, identifier.key);
                let keys = identifier.key.split(".");

                if (identifier.key === rootKey) {
                    // Return the root object description
                    // Can be loaded without the schema
                    return Promise.resolve({
                        identifier: identifier,
                        name: styling.rootFolderName,
                        type: 'folder',
                        location: 'ROOT'
                    });
                }
                else if (keys.length == 2) {


                    return getSchema().then(function () {
                        let subsystem = getHousekeepingObject(identifier.key, rootKey);
                        if (subsystem === undefined)
                            throw "No such subsystem" + identifier.key; // TODO: should call reject

                        return { //} Promise.resolve({
                            identifier: identifier,
                            name: subsystem.name,
                            type: "porthouse.housekeeping.frame",
                            location: "porthouse.housekeeping:" + rootKey
                        };
                    });

                } else {
                    return getSchema().then(function () {// Ensure the schema has been loaded

                        // Get parameter object from the schema
                        let param = getHousekeepingObject(identifier.key, rootKey);
                        if (param === undefined) {
                            console.error("No such field", identifier.key);
                            return;
                        }

                        // Resolve OpenMCT's display format type
                        let display_format = param.format_type;
                        if (display_format == "integer") display_format = "number";
                        if (display_format == "enumeration") display_format = "enum";

                        // Construct object defition in OpenMCT's format
                        let def = {
                            identifier: identifier,
                            name: param.name,
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
                                        unit: param.units,
                                        format: display_format
                                        //min:
                                        //max:
                                    }
                                ]
                            }
                        };

                        // Only values that have calibration can be minmaxed
                        //if(param.calibration !== undefined){
                        //    def.telemetry.values[1].hints = {range : 1};
                        //}

                        if (param.enumeration !== undefined) {
                            //def.telemetry.values[1].format = "enum";
                            def.telemetry.values[1].enumerations = param.enumeration;
                            //def.telemetry.values[1].hints = { range: 1 };
                        }
                        else
                            def.telemetry.values[1].hints = { range: 1 };

                        if (param.limits !== undefined) {
                            def.telemetry.values[1].limits = param.limits;
                        }

                        return def;

                    });
                }
            }
        });


        /*
         * Provide structure composition aka description of the object hierarchy.
         */
        openmct.composition.addProvider( {
            appliesTo: function (domainObject) {
                // Provider serves only folders (Porthouse Houseeeping root) and Porthouse Frame structures
                //console.debug("HK: Provides objects? namespace:", domainObject.identifier.namespace, "key:", domainObject.identifier.key, "type:", domainObject.type);
                return domainObject.identifier.namespace === "porthouse.housekeeping"  &&
                       (domainObject.type === 'folder' || domainObject.type === "porthouse.housekeeping.frame");
            },
            load: function (domainObject) {
                // Return the composition
                //console.debug("HK: Composition provider: key:", domainObject.identifier.key);

                let keys = domainObject.identifier.key.split(".");
                if (domainObject.identifier.key === rootKey)
                {
                    /*
                     * For the root, return list of subsystem
                     * Note: Makes sure the schema has been loaded before returning the root so that
                     * it doesn't need to be check later.
                     */
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
                    /*
                     * For the subsystems, return a list of all telemetry fields
                     */

                    // Find the subsystem object from the schema
                    let subsystem = schema.subsystems.filter(function (sub) {
                        return sub.key == keys[1];
                    })[0];

                    if (subsystem == undefined)
                        throw "No such subsystem" + identifier.key;

                    return Promise.resolve(subsystem.fields.map(function (m) {
                        return {
                            namespace: "porthouse.housekeeping",
                            key: domainObject.identifier.key + "." + m.key
                        };
                    }));

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

    } // end of install()

}

