

# Installing CouchDB

The CouchDB is a.


Installing CouchDB 3.2 on Ubuntu, goes somewhat like this. For most recent installation tutorial goto https://couchdb.apache.org/.

```
sudo apt update && sudo apt install -y curl apt-transport-https gnupg
curl https://couchdb.apache.org/repo/keys.asc | gpg --dearmor | sudo tee /usr/share/keyrings/couchdb-archive-keyring.gpg >/dev/null 2>&1
source /etc/os-release
echo "deb [signed-by=/usr/share/keyrings/couchdb-archive-keyring.gpg] https://apache.jfrog.io/artifactory/couchdb-deb/ ${VERSION_CODENAME} main" \
    | sudo tee /etc/apt/sources.list.d/couchdb.list >/dev/null

sudo apt update
sudo apt install couchdb

service couchdb status
```

Do relevant changes to configuration in `/opt/couchdb/etc/local.ini` and restart if needed.

Create new admin user
https://docs.couchdb.org/en/stable/intro/security.html?highlight=admin#creating-a-new-admin-user

```
[admins]
admin = password
```

Create a database for OpenMCT.

```
curl -X PUT http://admin:password@127.0.0.1:5984/openmct
```



# CouchDB and Cross-origin resource sharing

To operate CouchDB and OpenMCT in a local installation it is required to install Cross-origin resource sharing support to couch.
This can be enabled by installation following script from npm and executing it.

```
sudo npm install -g add-cors-to-couchdb
add-cors-to-couchdb
```

More information about CORS support can be found from: https://github.com/pouchdb/add-cors-to-couchdb
