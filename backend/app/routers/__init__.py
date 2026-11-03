"""Router package.

Each module is also exposed under the ``api_*`` alias used by ``app.main`` so the
application entry point stays readable while the files keep short names.
"""

from . import auth as api_auth
from . import aws as api_aws
from . import dashboard as api_dashboard
from . import data_quality as api_data_quality
from . import demo_ai as api_demo_ai
from . import gates as api_gates
from . import ingest as api_ingest
from . import metrics as api_metrics
from . import performance as api_performance
from . import reports as api_reports
from . import runs as api_runs

__all__ = [
    "api_auth",
    "api_aws",
    "api_dashboard",
    "api_data_quality",
    "api_demo_ai",
    "api_gates",
    "api_ingest",
    "api_metrics",
    "api_performance",
    "api_reports",
    "api_runs",
]
