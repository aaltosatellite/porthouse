

export default function (connector, args)
{

    return function install(openmct) {

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
            rootFolderName: "porthouse Signal Data Measurements",
            dataPointText: "porthouse Signal Data Measurement",
            frameName: 'porthouse Signal Data Measurement Frame',
            frameCssClass: 'icon-info',
            frameDesc: 'porthouse signal data measurement frame',
            dataPointName: 'porthouse Signal Data Measurement Data Point',
            dataPointDesc: 'porthouse signal data measurement data point',
            dataPointCssClass: 'icon-telemetry',
            limits: LIMITS
        }
    }
    let schema = null;
    var schemaPromise = null;
    const rootKey = args.rootKey;
    const styling = args.styling;
    let subscribed = false;
    let buffered_promises = {};

        /*
        * Get measurements schema
        */
        function getSchema() {
            if (schema !== null) {
                return Promise.resolve(schema);
            }
            if (schemaPromise !== null) {
                return schemaPromise;
            }

            schemaPromise = connector.remoteCall("measurements", "get_schema")
                .then(data => {
                    schema = data.result;
                    return schema;
                })
        }

        getSchema();

        function getMeasurementsObjects(key, rootKey) {
            let keys = key.split(".");
            if (keys[0] !== rootKey)
                return;

            if (keys.length == 1) {
                // Root
                return schema;
            }
            else if (keys.length == 2) {
                // Get measurements object
                let field = schema.fields.filter(m => (m.key === keys[1]))[0];
                if (field === undefined)
                    throw "No such field" + identifier.key;

                return field;
            }
        }

        /*
         * Porthouse telemetry provider defines the interface for telemetry transfer
         */
        openmct.telemetry.addProvider({
            supportsSubscribe: function (domainObject, callback, options) {
                return domainObject.type === "porthouse.measurements.field";
            },

            subscribe: function (domainObject, callback, options) {
                console.debug("MeasurementsPlugin: subscribe", domainObject, options);
                let key = domainObject.identifier.key.split(".");
                let satellite = key[0];
                let field = key[1];

                function subscriptionReturnCallback(callback, message){
                        callback(
                            {
                                id: "fs1p." + field,
                                timestamp: new Date(message.utc).getTime(),
                                value: message.measurements[field]
                            }
                        );
                    };
                if (!subscribed) {
                    connector.subscribe("measurements", "measurements",
                        subscriptionReturnCallback.bind(null, callback));
                    subscribed = true;
                }

                // Return the unsubscribing callback
                return function unsubscribe() {
                    // console.debug("MeasurementsPlugin: unsubscribe", domainObject);
                    subscribed = false;
                    connector.unsubscribe("measurements", "measurements");
                };
            },
            supportsRequest: function (domainObject, options) {
                return domainObject.type === "porthouse.measurements.field";
            },
            request: function (domainObject, options) {
                let key = domainObject.identifier.key;
                let keys = key.split(".");
                let satellite = keys[0];
                let field = keys[1];
                var req_ident = "measurements" + "_" + options.strategy;
                if (!(req_ident in buffered_promises)) {
                    buffered_promises[req_ident] = [ ];
                    setTimeout(function() {
                        let promises = buffered_promises[req_ident];
                        delete buffered_promises[req_ident];
                        connector.remoteCall("measurements", "history",
                                {
                                    "fields": promises.map(promise => promise.field),
                                    "satellite": satellite,
                                    "options": {
                                        start: new Date(options.start).toISOString(),
                                        end: new Date(options.end).toISOString(),
                                        strategy: options.strategy,
                                        domain: options.domain,
                                        size: options.size,
                                    }

                                }
                            ).then(function (response) {
                                let measurements = response.result.measurements;
                                for(let promise of promises) {
                                    let unrolled_measurement;
                                    unrolled_measurement = measurements.map(
                                            data => {
                                                return {
                                                    id: "fs1p." + promise.field,
                                                    timestamp: new Date(data.utc).getTime(),
                                                    value: data[promise.field]
                                                };
                                            }
                                        );
                                        promise.promise(unrolled_measurement);

                                    }
                            }, result => {
                            let error = { name: "AbortError" };
                            for (let promise of promises)
                                promise.reject(result);
                        });
                        }, 50);

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
                        
                }
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
             * Limit provider that uses the styling given during initialization: NOTE: TODO
             */
            supportsLimits: function(domainObject) {
                return false;
            },

            getLimitEvaluator: function (domainObject) { // TODO: Implement limit evaluator
                return{
                    evaluate: function (datum, valueMetadata) {
                        return;
                }
            }
            },
        });

        /*
         * Provide object definitions
         */
        openmct.objects.addProvider("porthouse.measurements", {
            get: function (identifier) {
                let key = identifier.key.split(".");
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
                else if (key.length === 2) {
                    return getSchema().then(function (schema) {
                    // Return the field object description
                    let param = getMeasurementsObjects(identifier.key, rootKey);
                    if (param === undefined) {
                        console.error("MeasurementsPlugin: No such field", identifier.key);
                        return;
                    }
                    // Currently all float or number, might be extended later
                    let display_format = param.display_format;

                    let def = {
                        identifier: identifier,
                        name: param.name,
                        type: 'porthouse.measurements.field',
                        location: 'porthouse.measurements:' + rootKey + "." + key[1],
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
                        },
                    };


                    def.telemetry.values[1].hints = { range: 1 };
                        if (param.limits !== undefined) {
                            def.telemetry.values[1].limits = param.limits;
                        }

                        return def;
                }
                );
                }
            }
        });
        openmct.composition.addProvider({
            appliesTo: function (domainObject) {
                return domainObject.identifier.namespace === "porthouse.measurements" && domainObject.type === "folder";
            },
            load: function (domainObject) {
                return getSchema().then(function (schema) {
                    console.debug("MeasurementsPlugin: load composition for", domainObject, schema);
                    return Promise.resolve(schema.fields.map(function (m) {
                        return {
                            namespace: "porthouse.measurements",
                            key: domainObject.identifier.key + "." + m.key
                        };
                    }));
                });
            }
        });

                                    



        openmct.objects.addRoot({
            namespace: "porthouse.measurements",
            key: rootKey
        }, openmct.priority.HIGH);

        openmct.types.addType("porthouse.measurements.field", {
            name: "Porthouse Signal Data Measurement Object",
            description: styling.dataPointDesc,
            cssClass: styling.dataPointCssClass,
            creatable: true,
            persistable: true
        });
    }
}
