PyPI Cloud - GCS Backend
============
Installation
============

Create a new virtualenv for the project and activate it

Download the package, install with python setup.py install - this will also handle basic requirements.

Working with GCS required a fix of gcs-oauth2-boto-plugin, install the gcs-oauth2-boto-plugin-hexadite version.

Set up and configure the .boto file as described here: https://cloud.google.com/storage/docs/gspythonlibrary - using a service account! User account will not work.

In the .boto file, set the value of gs_access_key_id equal to the value of gs_service_client_id

Run the command 'pypicloud-make-config', choose the relevant env, set the storage backend to gcs

Configure the cache as described here: http://pypicloud.readthedocs.org/en/latest/topics/cache.html

Run the server! If using waitress, 'pserve <configfile.ini>'.



Sources
=======

https://github.com/GoogleCloudPlatform/gcs-oauth2-boto-plugin

Google Cloud Storage Python: https://cloud.google.com/storage/docs/gspythonlibrary

Boto Docs: http://boto.cloudhackers.com/en/latest/ref/gs.html
