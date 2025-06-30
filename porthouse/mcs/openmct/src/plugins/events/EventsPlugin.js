/*
 * OpenMCT Plugin for connecting to Foresail events system backend
 */

// Default arguments
export function EventsDefaultArgs() {
    return {
        rootKey:  "events",

        styling : {
            rootFolderName: "Porthouse Raw events",
            EventText: "Porthouse Raw events",
            EventName: 'Porthouse Housekeeping Events',
            EventDesc: 'Porthouse housekeeping events',
            EventCssClass: 'icon-box-with-dashed-lines',
        }
    }
}

export default function (connector, args=EventsDefaultArgs())
{

    const rootKey = args.rootKey;
    const styling = args.styling;

    let subscribed = false;

    /*
     * OpenMCT installation part starts here
     */
    return function install(openmct) {

        openmct.telemetry.addProvider({

            supportsSubscribe: function (domainObject, callback, options) {
                return domainObject.type === "porthouse.event";
            },
            subscribe: function (domainObject, callback) {
                console.log("subscribe " + domainObject.identifier.key);

                let key = domainObject.identifier.key;

                if (!subscribed) {

                    function subscriptionReturnCallback(callback, message){
                        callback(message.events);
                    };

                    connector.subscribe("events", "events", subscriptionReturnCallback.bind(null, callback));
                    subscribed = true;
                }

                // Return the unsubscribing callback
                return function unsubscribe() {
                    subscribed = false;
                    connector.unsubscribe("events", "events");
                };
            },

            supportsRequest: function (domainObject, options) {
                return domainObject.type === "porthouse.event";
            },

            request: function(domainObject, options) {

                console.log("Request", domainObject.identifier.key);

                var key = domainObject.identifier.key;

                // Options was causing some issues, so we sanitize it to only include what is checked in the backend
                const allowedKeys = ["domain", "start", "end"];
                const sanitizedOptions = {};
                allowedKeys.forEach(key => {
                    if (options[key] !== undefined) {
                        sanitizedOptions[key] = options[key];
                    }
                });

                return connector.remoteCall("events", "request", { options: sanitizedOptions })
                .then(msg => {
                    console.log("message", msg.result.entries);
                    return msg.result.entries;
                }).catch(
                    e => {openmct.notifications.error("Events: "+e+" try shorter timespan");}
                );

            },

            /*
             * Limit provider that uses the styling given during initialization
             */
            supportsLimits: function(domainObject) {
                return domainObject.type === "porthouse.event";
            },

            getLimitEvaluator: function(domainObject) {
                return {
                    evaluate: function (datum, valueMetadata) {
                        // Normal styling for nominal events
                        if (datum.severity == "low") {
                            return {
                                cssClass: "is-limit--yellow  is-limit--upr",
                                name: "BLUE High"
                            };
                        }else if (datum.severity == "Critical") {
                            return {
                                cssClass: "is-limit--yellow",
                                name: "Yellow High"
                            };
                        }else if (datum.severity == "Error") {
                            return {
                                cssClass: "is-limit--red",
                                name: "Yellow High"
                            };
                        }
                        return;
                    }

                };
            }


        });


         openmct.objects.addProvider("porthouse.events", {
            get: function (identifier) {
                console.log(identifier);
                return Promise.resolve({
                    identifier: identifier,
                    name: 'Foresail-1p Events', // args.event_type_name
                    type: "porthouse.event",
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
                                key: "source",
                                name: "Source",
                                format: "string",
                                hints: { range: 1 }
                            },
                            {
                                key: "event_name",
                                name: "Event",
                                format: "string",
                                hints: { range: 1 }
                            },
                            {
                                key: "severity",
                                name: "Severity",
                                format: "string",
                                hints: { range: 1 }
                            },
                            {
                                key: "data",
                                name: "Data",
                                format: "string",
                                hints: { range: 1 }
                            },
                            {
                                key: "received",
                                name: "Received",
                                format: "utc",
                                hints: { domain: 1 }
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
            namespace: "porthouse.events",
            key: rootKey
        });


        /*
         * Custom type identificator for event log
         */
        openmct.types.addType("porthouse.event", {
            name: styling.EventName,
            description: styling.EventDesc,
            cssClass: styling.EventCssClass
        });

    } // end of install()
};
