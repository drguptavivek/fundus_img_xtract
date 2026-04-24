"""Celery task root package."""

# Import CVE scanner tasks
from .tasks.cve_tasks import (
    run_cve_scan_task,
)

# Import package update scanner tasks
from .tasks.package_update_tasks import (
    run_package_update_scan_task,
    cleanup_old_package_scans_task,
)

# Import Wadhwani glaucoma batch task
from .tasks.wadhwani_tasks import (
    run_wadhwani_glaucoma_batch_task,
)
