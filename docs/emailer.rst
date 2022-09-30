
Emailer
#######

The Emailer module is a general module which can be used to send email notifications to operators.
The module itself implement



Installation
------------

For the module, following python libraries shall be installed:

.. code-block:: console

    $ pip3 install aiosmtplib tag-expressions

By default, the module tries to open ``~/.porthouse/emailer.yaml`` file. The configuration file is
expected to have following content:

.. code-block:: yaml

    SMTP:
      sender: asd@gmail.com
      host: 123
      port:
      username:
      password: PASSWORD
      start_tls: False
      use_tls: True


To start module to launcher configuration.

.. code-block:: yaml

    - module: porthouse.notifications.emailer.Emailer
      params:
      - name: config_file
        value: dsadsa.yaml
