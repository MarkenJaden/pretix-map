import os
from distutils.command.build import build
from os import path

from django.core.management import call_command
from setuptools import find_packages, setup

# Make sure pretix_plugin_build is installed before running setup.py
try:
    from pretix_plugin_build.commands import CompileMessages, CustomBuild
except ImportError:
    print("Error: pretix_plugin_build is not installed.")
    print("Please run 'pip install pretix-plugin-build' and try again.")
    import sys

    sys.exit(1)


# --- Custom Command Class ---
# This prevents compilemessages from running if DJANGO_SETTINGS_MODULE is set
# during the build process, which often causes the ModuleNotFoundError.
class CustomBuildCommand(CustomBuild):
    def run_compilemessages(self):
        # Only run compilemessages if settings are NOT explicitly set
        # (indicating it might be a real environment, not just a build)
        if not os.environ.get("DJANGO_SETTINGS_MODULE"):
            super().run_compilemessages()
        else:
            print("Skipping compilemessages because DJANGO_SETTINGS_MODULE is set.")


# --- /Custom Command Class ---


# Read README for long description
try:
    long_description = open(path.join(path.dirname(__file__), 'README.rst')).read()
except IOError:
    long_description = ''

setup(
    name='pretix-map-plugin',  # Or your actual package name
    version='1.0.0',  # Your plugin's version
    description='Map overview for Pretix orders',
    long_description=long_description,
    url='https://github.com/MarkenJaden/pretix-map',  # Your repo URL
    author='MarkenJaden',
    author_email='jjsch1410@gmail.com',  # Your email
    license='Apache License 2.0',  # Or match your chosen license

    install_requires=[
        # Add runtime dependencies here, e.g.:
        'geopy>=2.0',  # Make sure geopy is listed
        # Add others if needed
    ],
    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    # --- Use the custom build command ---
    cmdclass={
        'build': CustomBuildCommand,
        'compilemessages': CompileMessages,
    },
    # --- End Use the custom build command ---
    entry_points="""
[pretix.plugin]
pretix_mapplugin=pretix_mapplugin:PretixPluginMeta
""",
)
