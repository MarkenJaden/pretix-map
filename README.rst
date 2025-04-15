Map-Plugin
==========================

This is a plugin for `pretix`_.

It provides an overview map visualizing the geographic location of attendees based on the addresses provided in their orders. The plugin automatically geocodes order addresses upon payment and displays the locations on an interactive map within the event control panel.

Features:

*   Automatic geocoding of paid order addresses using a configured geocoding service.
*   Interactive map display (Leaflet) showing locations as clustered pins or a heatmap.
*   Option to toggle between pin view and heatmap view.
*   Pins show tooltips with Order Code, Date, and Item Count on hover.
*   Clicking a pin navigates directly to the corresponding order details page.
*   Adds a "Sales Map" link to the event navigation sidebar.
*   Includes a management command to geocode orders placed *before* the plugin was installed or configured.

Requirements
------------

*   A working `pretix installation`_.
*   A **Celery worker** configured and running for your Pretix instance. This is essential for the background geocoding tasks.
*   Access to a **Geocoding Service**. This plugin requires configuration to use an external service to convert addresses to latitude/longitude coordinates. See the **Configuration** section below.


Installation (Production)
--------------------------

1.  Ensure you meet the requirements above, especially a running Celery worker.
2.  Activate the virtual environment used for your Pretix installation.
3.  Install the plugin via pip:

    .. code-block:: bash

        pip install pretix-map-plugin

    *(Note: If the plugin is not on PyPI yet, you might need to install from the git repository URL)*
4.  Configure the required geocoding service settings in your `pretix.cfg` file (see **Configuration** below).
5.  Restart your Pretix webserver (`gunicorn`/`uwsgi`) **and** your Pretix Celery worker(s).
6.  Log in to your Pretix backend and go to Organizer Settings -> Plugins. Enable the "Sales Map" plugin for the desired organizer(s).
7.  Go into an event, then navigate to Event Settings -> Plugins and ensure the "Sales Map" plugin is checked (enabled) for that event.


Configuration (`pretix.cfg`)
------------------------------

This plugin requires configuration in your `pretix.cfg` file to specify which geocoding service to use. Add a section `[pretix_mapplugin]` if it doesn't exist.

**Required Setting (Choose ONE method):**

*   **Method 1: Nominatim (OpenStreetMap - Free, Requires User-Agent)**
    Nominatim is a free geocoding service based on OpenStreetMap data. It has usage policies that **require** you to set a descriptive User-Agent header, typically including your application name and contact email. Failure to do so may result in your IP being blocked.

    .. code-block:: ini

        [pretix_mapplugin]
        # REQUIRED for Nominatim: Set a descriptive User-Agent including application name and contact info.
        # Replace with your actual details! See: https://operations.osmfoundation.org/policies/nominatim/
        nominatim_user_agent=YourTicketingSite/1.0 (Contact: admin@yourdomain.com) pretix-map-plugin/1.0

*   **Method 2: Other Geocoding Services (e.g., Google, Mapbox - API Key likely needed)**
    *(This example assumes you have modified `tasks.py` to use a different geocoder like GeoPy with GoogleV3. Adjust the setting name and value based on your implementation.)*

    .. code-block:: ini

        [pretix_mapplugin]
        # Example for Google Geocoding API (if implemented in tasks.py)
        # google_geocoding_api_key=YOUR_GOOGLE_GEOCODING_API_KEY

**Important:** After adding or changing settings in `pretix.cfg`, you **must restart** the Pretix webserver and Celery workers for the changes to take effect.

Usage
-----

1.  Once installed, configured, and enabled, the plugin works mostly automatically.
2.  When an order is marked as paid, a background task is queued to geocode the address associated with the order (typically the invoice address). This requires your Celery worker to be running.
3.  A "Sales Map" link will appear in the event control panel's sidebar navigation (usually near other order-related items or plugin links) for users with the "Can view orders" permission.
4.  Clicking this link displays the map. You can toggle between the pin view (markers clustered) and the heatmap view using the button provided.
5.  In the pin view:

    *   Hover over a marker cluster to see the number of orders it represents.
    *   Zoom in to break clusters apart.
    *   Hover over an individual pin to see a tooltip with Order Code, Date, and Item Count.
    *   Click an individual pin to open the corresponding order details page in a new tab.

Management Command: `geocode_existing_orders`
---------------------------------------------

This command is essential for processing orders that were placed *before* the map plugin was installed, enabled, or correctly configured with geocoding credentials. It scans paid orders and queues geocoding tasks for those that haven't been geocoded yet.

**When to Run:**

*   After installing and configuring the plugin for the first time.
*   If you previously ran the plugin without a working geocoding configuration or Celery worker.
*   If you want to force-reprocess orders (e.g., if geocoding logic changed).

**Prerequisites:**

*   Your Pretix Celery worker **must** be running to process the tasks queued by this command.
*   Geocoding settings must be correctly configured in `pretix.cfg`.

**How to Run:**

1.  Navigate to your Pretix installation directory (containing `manage.py`) in your server terminal.
2.  Activate your Pretix virtual environment.
3.  Execute the command using `manage.py`.

**Basic Command:**

.. code-block:: bash

    python manage.py geocode_existing_orders [options]

**Available Options:**

*   `--organizer <slug>`: Process orders only for the organizer with the given slug.
    *   Example: `python manage.py geocode_existing_orders --organizer=myorg`
*   `--event <slug>`: Process orders only for the event with the given slug. **Requires** `--organizer` to be specified as well.
    *   Example: `python manage.py geocode_existing_orders --organizer=myorg --event=myevent2024`
*   `--dry-run`: **Highly Recommended for first use!** Simulates the process and shows which orders *would* be queued, but doesn't actually queue any tasks. Use this to verify the scope and count before running for real.
    *   Example: `python manage.py geocode_existing_orders --dry-run`
*   `--force-recode`: Queues geocoding tasks even for orders that already have an entry in the geocoding data table. Use this if you suspect previous geocoding attempts were incomplete or incorrect, or if the geocoding logic has been updated.
    *   Example: `python manage.py geocode_existing_orders --organizer=myorg --force-recode`

**Example Workflow:**

1.  **Test with Dry Run (All Organizers):**
    .. code-block:: bash

        python manage.py geocode_existing_orders --dry-run
2.  **(If satisfied) Run for Real (All Organizers):**
    .. code-block:: bash

        python manage.py geocode_existing_orders
3.  **Monitor your Celery worker** logs to ensure tasks are being processed without errors.


Development setup
-----------------

1. Make sure that you have a working `pretix development setup`_. Ensure your dev setup includes a running Celery worker if you want to test the background tasks.
2. Clone this repository.
3. Activate the virtual environment you use for pretix development.
4. Execute ``python setup.py develop`` within this directory to register this application with pretix's plugin registry.
5. Execute ``make`` within this directory to compile translations.
6. **Configure Geocoding:** Add the necessary geocoding settings (e.g., `nominatim_user_agent`) to your local `pretix.cfg` file for testing the geocoding feature.
7. Restart your local pretix server and Celery worker. You can now use the plugin from this repository for your events by enabling it in the 'plugins' tab in the settings.

This plugin has CI set up to enforce a few code style rules. To check locally, you need these packages installed::

    pip install flake8 isort black

To check your plugin for rule violations, run::

    black --check .
    isort -c .
    flake8 .

You can auto-fix some of these issues by running::

    isort .
    black .

To automatically check for these issues before you commit, you can run ``.install-hooks``.


License
-------

Copyright 2025 MarkenJaden

Released under the terms of the Apache License 2.0



.. _pretix: https://github.com/pretix/pretix
.. _pretix installation: https://docs.pretix.eu/en/latest/administrator/installation/index.html
.. _pretix development setup: https://docs.pretix.eu/en/latest/development/setup.html