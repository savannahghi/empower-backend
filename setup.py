"""Advantage Backend Python package setup."""

import os
import subprocess

from setuptools import find_packages, setup

VERSION = (0, 56, 0, "final", 0)

this_dir = os.path.dirname(os.path.abspath(__file__))
init_path = os.path.join(this_dir, "sil_advantage", "__init__.py")

with open("README.md", "r") as f:
    README = f.read()


def git(args: str) -> str:
    """Call `git` using `subprocess`.

    Args:
        args: Arguments to pass to `git` as one string.
                e.g. "rev-parse --abbrev-ref HEAD"

    Returns:
        Text output from `git`.
    """
    cmd = ["git"] + args.split(" ")
    res = subprocess.check_output(cmd)
    res = res[:-1]  # get rid of the newline
    return res.decode("utf-8")


def write_version_to_init(version: str) -> None:
    """Write version to sil_advantage' package `__init__` file.

    Args:
        version: sil_advantage' version.
    """
    version_file = f'__version__ = "{version}"\n'
    with open(init_path, "w") as f:
        f.write(version_file)


def get_version(version=None) -> str:
    """Return a PEP-440 compliant version.

    Inspired by `django.utils.version.get_version`.

    Returns:
        A version string.
    """
    assert len(version) == 5
    assert version[3] in ("alpha", "beta", "rc", "final")
    version_str = ".".join(str(i) for i in version[:3])
    if version[3] != "final":
        mapping = {"alpha": "a", "beta": "b", "rc": "rc"}
        version_str += mapping[version[3]] + str(version[4])

    try:
        branch_name = os.getenv("CI_COMMIT_REF_NAME") or git(  # get from CI
            "rev-parse --abbrev-ref HEAD"
        )  # get from git
        if branch_name not in ("master", "prod"):
            commit_sha = os.getenv("CI_COMMIT_SHORT_SHA") or git("rev-parse HEAD")[:8]
            version_str += f".dev0+{commit_sha}"
        write_version_to_init(version_str)
    except (subprocess.CalledProcessError, OSError):
        # Git not available
        main_ns = {}
        with open(init_path) as f:
            exec(f.read(), main_ns)
        version_str = main_ns["__version__"]

    return version_str


setup(
    name="sil_advantage",
    version=get_version(VERSION),
    packages=find_packages(exclude=["tests", "tests.*"]),
    description="Slade360 Advantage Project",
    long_description=README,
    url="https://pip.slade360.co.ke/docs/sil_advantage/",
    author="SIL",
    author_email="developers@savannahinformatics.com",
    license="Proprietary",
    classifiers=[
        "Development Status :: 1 - Alpha",
        "Intended Audience :: SIL Developers",
        "Topic :: Software Development :: Libraries",
        "Programming Language :: Python :: 3 :: Only",
    ],
    install_requires=[
        "django==4.2.1",
        "django-cors-headers==4.2.0",
        "django-extensions==3.2.3",
        "django-filter==23.2",
        "django-phonenumber-field==7.1.0",
        "django-ses==3.5.0",
        "django-storages[google]==1.13.2",
        "djangorestframework==3.14.0",
        "drf-writable-nested==0.7.0",
        "django_compression_middleware==0.5.0",
        "drf_orjson_renderer==1.7.1",
        "google-cloud-storage==2.10.0",
        "gunicorn==21.2.0",
        "phonenumbers==8.13.19",
        "psycopg==3.1.10",
        "pytz==2023.3",
        "fuzzywuzzy==0.18.0",
        "pyshorteners==1.0.1",
        "python-Levenshtein==0.26.1",
        "celery==5.3.1",
        "django-celery-beat==2.5.0",
        "cryptography==50.0.0",
        "weasyprint==58.1",
        "whitenoise==6.5.0",
        "sentry_sdk==1.29.2",
        "xlrd==1.2.0",
        "sarge==0.1.6",
        "ipython==8.14.0",
        "drf-yasg==1.21.7",
        "openpyxl==3.1.2",
        "cron-converter==1.0.2",
        "python-crontab==3.0.0",
        "Jinja2==3.1.2",
        "django-tree-queries==0.19.0",
        "pyotp==2.9.0",
        "pydyf==0.10.0",
        "django-modeltranslation==0.19.5",
        "dateparser==1.2.0",
        "types-dateparser==1.2.0.20240420",
        "behave==1.2.6",
        "behave-django==1.4.0",
        "psycopg2-binary==2.9.9",
        # SIL libs
        "charge-master-client==0.2.3",
        "sil-custom-exception-handler==1.3.8",
        "sil_sentry_middleware==0.1.3",
        "sil_auth_backends==0.0.1a31",
        "sil_edge_connection==3.3.0a16",
        "sil_transitions==2.1.1",
        "sil_renderers==0.6.1",
        "sil_excel_utils==0.1.1",
        "sil_comms_client==0.1.0",
        "sil-erp-client==0.1.8",
        "sil_cacheable==0.1.2",
        "sil-monitoring==0.1.1",
        "sil_backup_utils==1.7.2",
        "sil-healthcrm-client==1.1.0",
        "sil-is-client==0.0.4",
        "sil_shlink==0.0.1",
        # GCP libs
        "google-api-python-client==2.97.0",
        "googleapis-common-protos==1.60.0",
        # Redis
        "redis==5.0.0",
        "hiredis==2.2.3",
        # Templating
        "django-mjml==1.1",
        # GraphQL
        "gql[aiohttp]==3.5.0",
        # Matrix
        "matrix-nio==0.21.2",
        # JSON Schema
        "jsonschema==4.20.0",
    ],
    scripts=["bin/advantage_manage"],
    include_package_data=True,
)
