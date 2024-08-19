/*
 *
 */

export default function(connector, args)
{
    // Combine given arguments and defaults
    args = Object.assign({}, {
        rootKey: "gs",
        styling: {
            rootFolderName: "MCC Raw Log events",
            LogEventText: "MCC Raw Log events",
            LogEventName: 'MCC Housekeeping Log Events',
            LogEventDesc: 'MCC housekeeping logs',
            LogEventCssClass: 'icon-datatable',
        }
    }, args || {});

    const rootKey = args.rootKey;
    const styling = args.styling;

    let subscribed = false;

    /*
     * OpenMCT installation part starts here
     */
    return function install(openmct) {

        openmct.telemetry.addProvider({

            supportsSubscribe: function (domainObject, callback, options) {
                return domainObject.type === telemetryType;
            },

            subscribe: function (domainObject, callback) {
                console.debug("SYS: subscribe " + domainObject.identifier.key);

                if (!subscribed) {
                    function subscriptionReturnCallback(callback, message){
                        callback(message.subscription.log);
                    };

                    connector.subscribe("system", "logs", subscriptionReturnCallback.bind(null, callback));
                    subscribed = true;
                }

                // Return the unsubscribing callback
                return function unsubscribe() {
                    subscribed = false;
                    connector.unsubscribe("system", "logs");
                };

            },

            supportsRequest: function (domainObject, options) {
                return domainObject.type === telemetryType;
            },

            request: function(domainObject, options) {

                console.debug("SYS: Request history", options.strategy, ": ", domainObject.identifier.key);

                var key = domainObject.identifier.key;

                return connector.remoteCall(
                    "system",
                    "request",
                    {
                        "options": {
                            start: new Date(options.start).toISOString(),
                            end: new Date(options.end).toISOString(),
                            strategy: options.strategy,
                            domain: options.domain,
                            size: options.size,
                        }
                    }
                ).then(msg => {
                    //console.debug("SYS: message", msg.result.entries);
                    return msg.result.entries;
                }).catch(
                    e => {openmct.notifications.error("Logs: " + e);
                });

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
                        //console.debug(datum);
                        //use styling if true
                        if (datum.level == "error") {
                            return {
                                cssClass: "is-limit--red",
                                name: "BLUE High"
                            };
                        }else if (datum.level == "warning") {
                            return {
                                cssClass: "is-limit--yellow",
                                name: "Yellow High"
                            };
                        }
                        return;
                    }

                };
            }


        });


        openmct.objects.addProvider("porthouse.gs", {
            get: function (identifier) {
                //console.debug(identifier);
                return Promise.resolve({
                    identifier: identifier,
                    name: 'Server log',
                    type: telemetryType,
                    telemetry: {
                        values: [
                            {
                                key: "created",
                                source: "created",
                                name: "Timestamp",
                                format: "utc",
                                hints: { domain: 1 }
                            },
                            {
                                key: "module",
                                name: "Module",
                                format: "string",
                                hints: { range: 1 }
                            },
                            {
                                key: "level",
                                name: "Level",
                                format: "string",
                                hints: { range: 1 }
                            },
                            {
                                key: "message",
                                name: "Message",
                                format: "string",
                                hints: { range: 1 }
                            }
                        ]
                    }
                });
            }
        });


        /*
         * Create root object
         */
        openmct.objects.addRoot({
            "porthouse.gs": "porthouse.gs",
            key: rootKey
        });


        /*
         * Custom type identificator for event log
         */
        const telemetryType = "porthouse.gs"+'.logentry';
        openmct.types.addType(telemetryType, {
            name: styling.LogEventName,
            description: styling.LogEventDesc,
            cssClass: styling.LogEventCssClass
        });

    } // end of install()
};