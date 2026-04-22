from __future__ import annotations

from .models import TrackerDefinition, TrackerDiscoveryBatch
from .platforms import canonicalize_job_urls, infer_job_platform
from .storage.base import TrackerStateStore


IGNORED_SECONDARY_SECTIONS = [
    "horizontal_carousel",
    "related_jobs",
    "detail_sidebar_recommendations",
]


class BrowserDiscoverySession:
    """Accumulate raw browser-discovered URLs from primary result lists only."""

    def __init__(self, tracker: TrackerDefinition, store: TrackerStateStore) -> None:
        self.tracker = tracker
        self.store = store
        self.source_platform = infer_job_platform(tracker.url)
        self._run_seen_urls: set[str] = set()
        self._new_job_urls: list[str] = []

    def ingest_raw_job_urls(
        self,
        raw_job_urls: list[str],
        *,
        source_exhausted: bool = False,
    ) -> TrackerDiscoveryBatch:
        canonical_job_urls = canonicalize_job_urls(
            raw_job_urls,
            platform=self.source_platform,
        )
        existing_job_urls = self.store.get_existing_job_urls(canonical_job_urls)

        new_job_urls: list[str] = []
        repeated_job_urls: list[str] = []
        globally_existing_job_urls: list[str] = []

        for job_url in canonical_job_urls:
            if job_url in self._run_seen_urls:
                repeated_job_urls.append(job_url)
                continue

            self._run_seen_urls.add(job_url)
            if job_url in existing_job_urls:
                globally_existing_job_urls.append(job_url)
                continue

            new_job_urls.append(job_url)
            self._new_job_urls.append(job_url)

        remaining_target_new_jobs = max(
            self.tracker.target_new_jobs - len(self._new_job_urls),
            0,
        )

        return TrackerDiscoveryBatch(
            tracker_id=self.tracker.id,
            source_platform=self.source_platform,
            submitted_count=len(raw_job_urls),
            canonical_count=len(canonical_job_urls),
            duplicate_input_count=max(len(raw_job_urls) - len(canonical_job_urls), 0),
            canonical_job_urls=canonical_job_urls,
            new_job_urls=new_job_urls,
            existing_job_urls=globally_existing_job_urls,
            run_duplicate_job_urls=repeated_job_urls,
            total_new_job_urls=list(self._new_job_urls),
            remaining_target_new_jobs=remaining_target_new_jobs,
            source_exhausted=source_exhausted,
            discovery_scope="main_results",
            ignored_sections=list(IGNORED_SECONDARY_SECTIONS),
        )
