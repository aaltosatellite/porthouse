/*
 * Connector class to handle WebSocket connection to the porthouse backend
 */
export default class Connector {

    constructor(url) {

        // Reconnect args
        this.reconnectAttempts = 0;
        this.reconnectInterval = 500;
        this.maxReconnectInterval = 10000;
        this.reconnectDecay = 1.5;

        // RPC state
        this.rpc_id = 0;
        this.rpc_calls = { };
        this.subscriptions = {};
        this.url = url;

        this.pending = [];

        // Socket
        this.connect();
    }

    connect()
    {
        // Create socket
        console.info("CON: Connecting to", this.url);
        this.socket = new WebSocket(this.url);

        /*
         * WebSocket receive callback
         */
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
                //console.info("CON: New subscribed data:", subscription.service, subscription);
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
                if ("id" in message && message.id in this.rpc_calls) {
                    let request = this.rpc_calls[message.id];
                    clearTimeout(request.timeout);
                    request.reject("WebSocket error: " + message.error.message);
                }
                return;
            }

            /*
             * RPC response
             */
            if ("id" in message) {
                let id = message.id;

                // Full fill the promise
                if (id in this.rpc_calls) {
                    let request = this.rpc_calls[message.id];
                    clearTimeout(request.timeout);
                    request.resolve(message);
                }
            }

        }.bind(this));


        /*
         * Try reconnecting
         */
        this.socket.addEventListener('open', function(event) {
            console.info("CON: Connected to backend")


            for (const rpc_call of this.pending)
                this.socket.send(rpc_call);
            this.pending = [];

            // Resubscribe everything on the list
            Object.keys(this.subscriptions).forEach(service => {
                var fields = Object.keys(this.subscriptions[service]);
                console.info("CON: Resubscribing:", service, fields);
                this.remoteCall(service, "subscribe", fields);
            });
        }.bind(this));


        this.socket.addEventListener('close', function(event) {
            console.info("CON: Connection closed");
            this.socket = null;

            // Reconnect
            /*var timeout = this.reconnectInterval * Math.pow(this.reconnectDecay, this.reconnectAttempts);
            setTimeout(function () {

                console.info("CON: Socket reconnecting");
                this.connect();

            }, timeout > this.maxReconnectInterval ? this.maxReconnectInterval : timeout);*/

        }.bind(this));

    }

    /*
     * Helper function to create WebSocket RPC calls
     */
    remoteCall(service, method, params) {

        let id = this.rpc_id++;
        console.debug("CON: RPC call", service, method, params, id);
        try {
            console.debug("CON: params", params, JSON.stringify(params, null, 2));
        } catch (e) {
            console.error("CON: params could not be stringified", params, e);
        }
        let rpc_call = {
            service: service,
            method: method,
            params: params,
            id: id,
        };
        rpc_call = JSON.stringify(rpc_call);
        console.debug("CON: Remote call", service, method, params, rpc_call);

        return new Promise((resolve, reject) =>
        {
            if (this.socket.readyState == WebSocket.OPEN) {
                console.debug("CON: Sending RPC call", rpc_call);
                this.socket.send(rpc_call);
            }
            else {
                console.debug("CON: Socket not open, queuing RPC call", rpc_call);
                this.pending.push(rpc_call);
            }

            this.rpc_calls[id] = {
                resolve: resolve, reject: reject,
                timeout: setTimeout(reject, 500)
            };
            // resolve/reject called later on socket.onmessage

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
        //console.info("CON: Subscribing", fields);
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
        //console.info("CON: Unsubscribing", fields);
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
