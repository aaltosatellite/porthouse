/*
* Plugin that displays info from the mcc
*/
function PorthouseGroundStationPlugin(connector, args) {

    // Combine given arguments and defaults
    args = Object.assign({}, args, FSLogsDefaultArgs());

    const rootKey = args.rootKey;
    const namespace = args.namespace;
    const styling = args.styling;

    let subscribed = false;

    /*
    * OpenMCT installation part starts here
    */
    return function install (openmct) {

        openmct.telemetry.addProvider({

            supportsSubscribe: function (domainObject, callback, options) {
                return domainObject.type === telemetryType;
            },

            subscribe: function (domainObject, callback) {
                console.log("subscribe " + domainObject.identifier.key);

                if (!subscribed) {
                    function subscriptionReturnCallback(callback, message){
                        callback(message.subscription.log);
                    };

                    connector.subscribe("system", { "fields": "logs" }, subscriptionReturnCallback.bind(null, callback));
                    subscribed = true;
                }

                // Return the unsubscribing callback
                return function unsubscribe() {
                    subscribed = false;
                    connector.unsubscribe("system", { "fields": "logs" });
                };

            },

            supportsRequest: function (domainObject, options) {
                return domainObject.type === telemetryType;
            },

            request: function(domainObject, options) {

                console.log("Request " + options.strategy + ": " + domainObject.identifier.key);

                var key = domainObject.identifier.key;

                return connector.remoteCall(
                    "system", "request", { "options": options }
                ).then(msg => {
                    //console.log("message", msg.result.entries);
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
                        //console.log(datum);
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


         openmct.objects.addProvider(namespace, {
            get: function (identifier) {
                console.log(identifier);
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
            namespace: namespace,
            key: rootKey
        });


        /*
         * Custom type identificator for event log
         */
        const telemetryType = namespace+'.logentry';
        openmct.types.addType(telemetryType, {
            name: styling.LogEventName,
            description: styling.LogEventDesc,
            cssClass: styling.LogEventCssClass
        });

    }
}


/*
*   Default arguments
*/
function FSLogsDefaultArgs() {
    return {
        rootKey   : "logentry",
        namespace  : "logs",

        styling : {
            rootFolderName: "MCC Raw Log events",
            LogEventText: "MCC Raw Log events",
            LogEventName: 'MCC Housekeeping Log Events',
            LogEventDesc: 'MCC housekeeping logs',
            LogEventCssClass: 'icon-datatable',

        }
    }
}
