Development
-----------

Code Documentation
~~~~~~~~~~~~~~~~~~

Docstring Convention: `Google's Style Guide <https://google.github.io/styleguide/pyguide.html>`_

Testing
~~~~~~~

Unit and Coverage Testing
"""""""""""""""""""""""""

.. code-block:: bash

    make test # run Pytest
    make test # Run Pytest using Make

- Use classes that inherit `django.test.TestCase` to group unit tests
- Assertions Order: `assert expected == actual`

Linting
"""""""

.. code-block:: bash

    make lint # Run flake8

- Blanket `noqa`s are discouraged e.g. `# noqa`. They should be specific, like `# noqa: W503` to ignore the `line break before binary operator` error
- Code formatters: `black` & `isort` (`make format`)
