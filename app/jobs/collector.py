"""Job collection orchestrator: aggregates, deduplicates, filters, ranks, and caps at 30."""
import hashlib
import re
from datetime import timezone
from typing import List

from app.models import JobItem
from app.jobs.remotive import collect_remotive
from app.jobs.remoteok import collect_remoteok
from app.jobs.himalayas import collect_himalayas
from app.jobs.weworkremotely import collect_weworkremotely
from app.jobs.arbeitnow import collect_arbeitnow
from app.jobs.rozee import collect_rozee
from app.jobs.linkedin import collect_linkedin

MAX_DISPLAY_JOBS = 30


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for dedup key."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return " ".join(text.split())


def _job_dedup_key(j: JobItem) -> str:
    """Stable dedup key: normalized title + company (ignores URL variations)."""
    t = _normalize(j.title)
    c = _normalize(j.company)
    return hashlib.md5(f"{t}|{c}".encode()).hexdigest()


def _aware(dt):
    """Treat naive datetimes as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _merge_duplicate(existing: JobItem, new: JobItem) -> JobItem:
    """Keep the more complete record; preserve source info."""
    # Prefer richer description
    if len(new.description) > len(existing.description):
        existing.description = new.description
    # Prefer disclosed salary
    if existing.salary in ("Not disclosed", "", None) and new.salary not in ("Not disclosed", "", None):
        existing.salary = new.salary
    # Prefer known work_mode
    if not existing.work_mode and new.work_mode:
        existing.work_mode = new.work_mode
    # Accumulate skills
    combined_skills = list(set((existing.skills or []) + (new.skills or [])))
    existing.skills = combined_skills
    # Prefer earlier published date (if new is older, it's the canonical listing)
    if new.published_at and existing.published_at and _aware(new.published_at) < _aware(existing.published_at):
        existing.published_at = new.published_at
    # Note additional source
    if new.source and new.source != existing.source:
        existing.source = f"{existing.source}, {new.source}"
    return existing


def collect_jobs(settings) -> List[JobItem]:
    """Collect jobs from all configured sources, merge duplicates, filter, and return best 30."""
    all_raw: List[JobItem] = []
    source_counts = {}

    def _run_source(name, fn, *args, **kwargs):
        try:
            results = fn(*args, **kwargs)
            source_counts[name] = len(results)
            print(f"[INFO] Job source '{name}' returned {len(results)} listings.")
            return results
        except Exception as exc:
            print(f"[WARNING] Job source '{name}' failed with unexpected error: {exc}")
            source_counts[name] = 0
            return []

    # --- Run all collectors independently ---
    all_raw += _run_source(
        "Remotive",
        collect_remotive,
        settings.request_timeout
    )
    all_raw += _run_source(
        "RemoteOK",
        collect_remoteok,
        settings.request_timeout
    )
    all_raw += _run_source(
        "Himalayas",
        collect_himalayas,
        settings.request_timeout
    )
    all_raw += _run_source(
        "WeWorkRemotely",
        collect_weworkremotely,
        settings.request_timeout
    )
    all_raw += _run_source(
        "Arbeitnow",
        collect_arbeitnow,
        settings.request_timeout
    )
    all_raw += _run_source(
        "Rozee.pk",
        collect_rozee,
        settings.request_timeout
    )
    all_raw += _run_source(
        "LinkedIn",
        collect_linkedin,
        settings.request_timeout
    )

    print(f"[INFO] Total raw job listings before dedup: {len(all_raw)}")

    # --- Deduplicate by normalized title + company ---
    deduped: dict[str, JobItem] = {}
    for j in all_raw:
        key = _job_dedup_key(j)
        if key in deduped:
            deduped[key] = _merge_duplicate(deduped[key], j)
        else:
            deduped[key] = j

    unique = list(deduped.values())
    print(f"[INFO] {len(unique)} unique job listings after deduplication.")

    return unique
