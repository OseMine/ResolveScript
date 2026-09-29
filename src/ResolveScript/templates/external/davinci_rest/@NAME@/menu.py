"""@NAME@ package - using davinci-rest client."""

from typing import Any
from davinci_rest.client import DavinciRestClient


def run(client: DavinciRestClient) -> str:
    """Main entry point for the Resolve script using REST client."""
    # Create a test project
    response = client.create_project("TestProject")
    return f"Created project: {response}"