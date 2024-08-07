var cachedConnections = {};

/*
 * Create communication system that can be used to access
 * the openmct_backend. Can be used reused with other foresail OpenMCT
 * plugins. Can be bad, solve later if needed.
 */
function getConnector(url, createNew=false){

    if (createNew) {
        return new Connector(url);
    }

    if (cachedConnections[url] == null){
        cachedConnections[url] = new Connector(url);
    }
    return cachedConnections[url];
}

/*
 * requires reconnecting web sockets
 */
class Connector {

    constructor(url) {
        cachedConnections = this;

        this.rpc_id = 0;
        this.rpc_calls = { };
        this.subscriptions = {};
        this.url = url;

        console.log("Connecting to", url);
        this.socket = new ReconnectingWebSocket(url);
        this.connect();

    }

    /*
     * WebSocket receive callback
     */
    connect() {

        this.socket.addEventListener('message', function(event) {
            let message;

            // Parse JSON
            try { message = JSON.parse(event.data) }
            catch (error) { return }

            //console.debug(message);

            /*
             * New real-time data data
             */
            if ("subscription" in message) {
                let subscription = message.subscription;
                //console.log("New subscribed data:", subscription.service, subscription);
                var callback = this.subscriptions[subscription.service][subscription.subsystem];
                if (callback !== undefined)
                    callback(subscription);
                return;
            }

            /*
             * RPC error response
             */
            if ("error" in message) {
                // example: {"error": {"code": -500, "message": "<text>"}, "id": 4}
                if ("id" in message && message.id in this.rpc_calls)
                    this.rpc_calls[message.id].reject("WebSocket error: " + message.error.message);
                return;
            }

            /*
             * RPC response
             */
            if ("id" in message) {
                let id = message.id;

                // Full fill the promise
                if (id in this.rpc_calls)
                    this.rpc_calls[id].promise(message);
            }

        }.bind(this));


        /*
        * Try reconnecting
        */
        this.socket.addEventListener('open', function(event) {
            console.log("Websocket connected")
            // Resubscribe everything on the list
            Object.keys(this.subscriptions).forEach(service => {
                var fields = Object.keys(this.subscriptions[service]);
                console.log("Resubscribing:", service, fields);
                this.remoteCall(service, "subscribe", fields);
            });
        }.bind(this));


        this.socket.addEventListener('close', function(event) {
            console.log("Socket close");
            this.subscriptions = { };
        }.bind(this));

    }

    /*
     * Helper function to create WebSocket RPC calls
     */
    remoteCall(service, method, params) {

        let id = this.rpc_id++;

        let rpc_call = {
            service: service,
            method: method,
            params: params,
            id: id,
        };

        return new Promise((resolve, reject) =>
        {
            this.socket.send(JSON.stringify(rpc_call));
            this.rpc_calls[id] = { promise: resolve, reject: reject };
        }).finally(function() {
            delete this.rpc_calls[id];
        }.bind(this));

    }

    /*
     * if just reconnecting, dont clear subscriptions
     * just ask new subscription from the server.
     * Subscribe to subsystem+telemetry.
     * promise can be used to make more robust.
     */
    subscribe(service, fields, callback) {
        console.log("Subscribing", fields);
        this.remoteCall(service, "subscribe", { "fields": fields });

        if (!(service in this.subscriptions))
            this.subscriptions[service] = { };

        if (Array.isArray(fields)) {
            fields.forEach(value => {
                this.subscriptions[service][value] = callback;
            });
        }
        else {
            this.subscriptions[service][fields] = callback;
        }
    }

    /*
     * Unsubscribe
     */
    unsubscribe(service, fields) {
        //console.log("Unsubscribing", fields);
        this.remoteCall(service, "unsubscribe", { "fields": fields });

        if (Array.isArray(fields)) {
            fields.forEach(field => {
                delete this.subscriptions[service][field];
            });
        }
        else {
            delete this.subscriptions[service][fields];
        }
    }



}
