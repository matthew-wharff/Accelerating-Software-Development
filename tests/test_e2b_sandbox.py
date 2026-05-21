import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from dotenv import load_dotenv

load_dotenv()
from e2b_code_interpreter import Sandbox  # noqa: E402


@pytest.mark.integration
def test_e2b_sandbox():
    sandbox = Sandbox.create()  # Needs E2B_API_KEY environment variable
    result = sandbox.commands.run('echo "Hello from E2B Sandbox!"')
    assert "Hello from E2B Sandbox!" in result.stdout
