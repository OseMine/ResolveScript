"""In-app entry point for @NAME@ using davinci-rest client.

Run inside DaVinci Resolve (Workspace → Scripts) after installing.
Uses davinci-rest Python client to interact with the REST API server.
"""

import sys
from davinci_rest.client import DavinciRestClient
from @NAME@.menu import run

# Connect to davinci-rest server (must be running in Resolve)
client = DavinciRestClient()
print(run(client))