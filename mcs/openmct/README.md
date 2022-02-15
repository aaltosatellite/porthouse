
# Local test installation

```
$ sudo apt install npm
$ npm install
$ npm run build
```

This bakes out `node_modules` folder.
```
$ npm start
```


# Installing CouchDB

Installing CouchDB on Ubuntu
```
sudo apt update && sudo apt install -y curl apt-transport-https gnupg
curl https://couchdb.apache.org/repo/keys.asc | gpg --dearmor | sudo tee /usr/share/keyrings/couchdb-archive-keyring.gpg >/dev/null 2>&1
source /etc/os-release
echo "deb [signed-by=/usr/share/keyrings/couchdb-archive-keyring.gpg] https://apache.jfrog.io/artifactory/couchdb-deb/ ${VERSION_CODENAME} main" \
    | sudo tee /etc/apt/sources.list.d/couchdb.list >/dev/null

sudo apt update
sudo apt install couchdb
```

Create database
```
curl -X PUT http://admin:password@127.0.0.1:5984/openmct
```



# Client plugins:

- `housekeeping.js`: provides realtime and historical housekeeping data. System is subscribable and it is updated by the backend.  

- `groundstation.js`: provides realtime info from the mcc system. Historical data is not currently supported due to the implementation of mcc system (stores data to rotating files). system is subscribable and it is by the backend.

- `events.js`: provides realtime and historical events from the system. system is subscribable and it is by the backend.


# Building and running:
```


```


# file structure:

each of the system use backend_comm_system that keeps track of the socket to the backend and reconnects if needed (keeping subscriptions alive) and keeps subscriptions alive. it also sends the messages to the correct js module.



shortly how everything works:

basic openmct tutorial:

short introduction:

specify types, provide keys, give request, give subscriptions



housekeeping specific: housekeeping collects multiple requests and makes one request to the backend. Subscriptions are stored per module and also send. e.g. if one is subscribed to system uhf.asd and uhf.asd2, both can be updated during the same call. a

map specific: map has a special tle class that holds the objects necessary to calculate the previous, current and future orbit and location of the satellite. osmmview has two interval loops that keep updating the satellite position and the orbits at the client side (tlejs).



backend:

requirements:

the same stuff as the mcc. mcc needs to be running. need to test reconnection to that. anyway, the open_mct backend contains the protocols that handle data and requests of the client. protocol contains logic of how to interact with each system (housekeeping, events, log, map). each of these system implements logic for the subscribe, unsubscribe, ws_request and also subscription. requests can contain any kind of information from the client side whereas subscription are invoked from the mcc side according whether the client has subscribed.







Ports:

defaults 8888 for connecting to the backend and 8080 for accessing the open mct telemetry interface.



Todo:

during reconnect, ask refresh.

limit the number of messages when events are displayed

minmax limits not working properly

alerts are not properly shown.
