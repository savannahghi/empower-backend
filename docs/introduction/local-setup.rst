Local Setup
-----------

Code


Install Python 3.11.5.

Clone the repo

Set up SIL pip registry:


    Create `/.pypirc` file on local machine(home): `sudo nano .pypirc` and add the configurtion:

.. code-block:: bash

    [distutils]
    index-servers =
        slade

    [slade]
    repository: https://pip.slade360.co.ke/
    username: SIL_PYPI_USER
    password: SIL_PYPI_PASSWORD


Create `/.pip/pip.conf` file on local machine(home): `sudo nano .pip/pip.conf` and add the configuration:

.. code-block:: bash

    [global]
    timeout = 60
    index-url = https://pypi.python.org/simple
    extra-index-url = (ask for the url)


Install pip using python 3.11. `Check this guide <https://www.linuxcapable.com/how-to-install-python-3-11-on-ubuntu-linux/>`_

Setup a `virtual environment <https://docs.python.org/3/library/venv.html>`_ & install requirements:


.. code-block:: bash

    python3.11 -m venv venv
    . venv/bin/activate
    pip install -r requirements/dev.txt

Get a copy of the `.env` file from a team member.

Refresh environment variables:

.. code-block:: bash

    source .env


Get a copy of the `speedy_lattice.json` file from a team member.This is used to setup the service account




Setup `Rabbit MQ <https://www.rabbitmq.com/>`_ & `Celery <https://docs.celeryq.dev/en/stable/getting-started/introduction.html>`_:


.. code-block:: bash

    sudo apt-get install rabbitmq-server
    sudo rabbitmqctl add_user <user> <password>
    sudo rabbitmqctl add_vhost <vhost>
    sudo rabbitmqctl set_permissions -p <vhost> <user> ".*" ".*" ".*"
    celery -A sil_advantage.config worker -l debug
    celery -A sil_advantage.config beat -l debug 

Setup Redis:

.. code-block:: bash

    curl -fsSL https://packages.redis.io/gpg | sudo gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/redis.list
    sudo apt-get update
    sudo apt-get install redis
    systemctl start redis-server.service

    redis-cli
    > ping  # Confirm we're good, should return PONG
    > INFO  # Check Redis installation information, like version etc
    > ACL SETUSER advantage_uat on >9sS8c6G4JIhVh8Rr ~* &* +@all
    > ACL LIST  # List users
    > ACL SETUSER default off  # Turn off default user
    # MAKE SURE REDIS IS NOT ACCESSIBLE PUBLICLY!!!
    > CONFIG SET protected-mode no
    # Persist the current server configuration
    # Not doing this will cause Redis to go back to the previous configuration after it is restarted
    > CONFIG REWRITE

    # Update binding to allow connections from remote IPs
    # Change `bind 127.0.0.1` to `bind 0.0.0.0`
    vi /etc/redis/redis.conf

    # Enable Redis auto-restart on boot
    systemctl enable redis-server.service

Setup PostgreSQL:

.. code-block:: bash
    
    sudo apt update
    sudo apt install postgresql postgresql-contrib
    # Start the postgressql service
    sudo systemctl start postgresql.service
    
Create Roles and Database

Open your terminal and log in to PostgreSQL as the `postgres` user:

.. code-block:: bash

    sudo -u postgres psql


Execute the following commands to create a new user named `app` with the password 'app', grant superuser privileges, and create a database named `slade_emr_poc` owned by the `app` user:

.. code-block:: bash

     CREATE USER app WITH PASSWORD 'your password';
     ALTER USER app SUPERUSER;
     CREATE DATABASE slade_emr_poc OWNER app;
     \q


Next, connect to the `slade_emr_poc` database using the `app` user:

.. code-block:: bash

    psql -U app -d slade_emr_poc


Create a role named `test_advantage_db_user` with a login password (replace `'your password'` with the actual password):

.. code-block:: bash

     CREATE ROLE test_advantage_db_user WITH LOGIN PASSWORD 'your password';


SQL Database Dump File

Get a copy of the SQL dump file named `dumpy.sql` from the team lead or team member, import it into the `slade_emr_poc` database using the following command:

.. code-block:: bash

     psql -U app -d slade_emr_poc -W < dumpy.sql
     # if the dumpy.sql file is located in a another directory specify the path with the file name ,path/dumpy.sql


Running Migrations

In your Django project directory, run the following commands to create and apply migrations:

.. code-block:: bash

     python manage.py makemigrations
     python manage.py migrate




Run local server

.. code-block:: bash

    python3 manage.py runserver

On the browser:

.. code-block:: bash

    http://127.0.0.1:8000

    http://127.0.0.1:8000/swagger/

    http://127.0.0.1:8000/redoc/


Create an organisation


Connect to the server by running the following command:

.. code-block:: bash

    ./manage.py shell


Once in the shell, make sure to import the following required dependencies

.. code-block:: bash

    from sil_advantage.common.models.organisation_models import Organisation
    from datetime import datetime


Once the required dependencies have been added, create Savannah as an Organisation:

**Please Note: that the code below will create an organisation with the slade code 1**

.. code-block:: bash

    org = Organisation.objects.create(
        slade_code="1",
        organisation_name="Savannah Informatics",
        email_address="portadmin+1@savannahinformatics.com",
        phone_number="+25490360360",
        financial_year_start_date=datetime(2023, 1, 1),
        created_by="cf1e1859-66b0-4925-9f16-fb3b8042de7f",
        updated_by="cf1e1859-66b0-4925-9f16-fb3b8042de7f",
        description="SIL Test Organisation"
    )

Generating passwords:
~~~

.. code-block:: bash

    # Random alphanumeric string of length 32
    head /dev/urandom | tr -dc A-Za-z0-9 | head -c32 ; echo ''

Docs
~~~~

Install docs requirements:

.. code-block:: bash

    # inside the virtual environment
    pip install -r requirements/docs.txt
    sudo apt install graphviz texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended latexmk

Generate HTML docs:

.. code-block:: bash

    cd docs/
    make html
    # output is stored in _build/html
    firefox _build/html/index.html

Generate PDF docs:

.. code-block:: bash

    # inside docs/
    make latexpdf
    # output is stored in _build/latex/advantagebackend.pdf



Docker Setup
-------------

Install docker and docker compose 

Export sil pypi user and password as follows:

.. code-block:: bash

    export SIL_PYPI_PASSWORD=(ask for credentials)
    export SIL_PYPI_USER=(ask for credentials)

Build and run containers using the following command:

.. code-block:: bash

    docker build  --build-arg "SIL_PYPI_USER=$SIL_PYPI_USER" --build-arg "SIL_PYPI_PASSWORD=$SIL_PYPI_PASSWORD" --build-arg "REQUIREMENTS=dev" -t sil/advantage-backend .

Everything should work if properly configured. And voilà! You're done! Now, access the backend using this link: http://127.0.0.1:8000.
