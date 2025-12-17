import sys
import os
import pytest
from unittest.mock import MagicMock

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_version_info():
    """Test that version_info can be imported and has expected fields."""
    try:
        import version_info
        assert hasattr(version_info, "VERSION")
        assert hasattr(version_info, "BUILD_DATE")
    except ImportError:
        pytest.fail("Could not import version_info")

def test_imports():
    """Test that critical modules can be imported (mocking gui/network if needed)."""
    # Set dummy env vars required by inventory_ai
    os.environ["GEMINI_API_KEY"] = "dummy_key"

    # Mocking google.generativeai since we don't have API key in CI
    sys.modules["google.generativeai"] = MagicMock()

    try:
        import inventory_ai
        assert inventory_ai is not None
    except ImportError as e:
        pytest.fail(f"Could not import inventory_ai: {e}")

    try:
        import ui_utils
        assert ui_utils is not None
    except ImportError as e:
        pytest.fail(f"Could not import ui_utils: {e}")
