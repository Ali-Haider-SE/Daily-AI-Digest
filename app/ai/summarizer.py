"""AI summarization and contextual analysis using multi-provider failover with reliable local fallback."""
import json
import os
import re
import time
import logging
from typing import List, Dict, Any, Optional
from app.models import NewsItem, JobItem
from app.ai.provider_manager import get_provider_manager, AIProviderManager, AllProvidersExhaustedError

logger = logging.getLogger("summarizer")

def _pace_between_batches(batch_index: int) -> None:
    """Wait between AI calls so free-tier tokens-per-minute limits (e.g. 8000 TPM) are not hit."""
    if batch_index > 0:
        try:
            delay = float(os.getenv("AI_BATCH_DELAY_SECONDS", "20"))
        except ValueError:
            delay = 20.0
        if delay > 0:
            time.sleep(delay)

def fallback(text: str) -> str:
    """Clean fallback snippet extraction."""
    text = " ".join((text or "").split())
    if len(text) > 400:
        return text[:397] + "..."
    return text or "Details available at original source."

def clean_json_response(raw: str) -> str:
    """Safely extract JSON body from markdown fenced code blocks or raw LLM output."""
    raw = (raw or "").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if match:
        return match.group(1).strip()
    return raw

def summarize_news(
    items: List[NewsItem],
    api_key: Optional[str] = None,
    model: str = "qwen/qwen3.8-27b",
    provider_manager: Optional[Any] = None,
    groq_manager: Optional[Any] = None
) -> List[NewsItem]:
    """Summarize news items using multi-provider AI pipeline with batching, failover rotation, and graceful fallback."""
    if not items:
        return items

    manager = provider_manager or groq_manager
    if manager is None:
        if api_key is not None and api_key != "":
            from app.ai.groq_client import get_groq_manager
            groq_m = get_groq_manager(api_keys=[api_key], model=model)
            from app.ai.provider_manager import AIProviderManager
            manager = AIProviderManager(provider_priority=["groq"], groq_manager=groq_m)
        elif api_key == "":
            from app.ai.groq_client import GroqClientManager
            groq_m = GroqClientManager(api_keys=[], default_model=model)
            from app.ai.provider_manager import AIProviderManager
            manager = AIProviderManager(provider_priority=["groq"], groq_manager=groq_m)
        else:
            manager = get_provider_manager()

    stage_success = True
    # Batch articles into groups of 5 to fit well within OTPM limits
    batch_size = 5
    for i in range(0, len(items), batch_size):
        _pace_between_batches(i)
        batch = items[i:i + batch_size]
        articles_payload = []
        for idx, x in enumerate(batch):
            articles_payload.append({
                "id": idx,
                "title": x.title,
                "source": x.source,
                "description": x.description[:600] if x.description else "",
                "category": x.category
            })

        prompt = f"""You are a senior intelligence analyst and news editor.
Use ONLY the supplied article information. Never invent facts.
Analyze each article and return a JSON list of objects.
Each object must have:
- "id": integer matching the article id
- "summary": 2-3 concise, neutral sentences summarizing the event.
- "why_it_matters": 1 crisp sentence explaining why this development is important to Pakistan or global stakeholders.

Articles:
{json.dumps(articles_payload, ensure_ascii=False, indent=2)}

Return ONLY a valid JSON list of objects matching the above schema."""

        try:
            response = manager.create_chat_completion(
                model=None,
                messages=[
                    {"role": "system", "content": "You are a professional intelligence analyst. Output strictly valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_completion_tokens=750
            )
            raw_text = response.choices[0].message.content or ""
            clean_text = clean_json_response(raw_text)
            parsed = json.loads(clean_text)

            results_list = parsed if isinstance(parsed, list) else (
                parsed.get("articles") or parsed.get("results") or parsed.get("items") or list(parsed.values())[0]
                if isinstance(parsed, dict) and parsed else []
            )
            if not isinstance(results_list, list):
                results_list = []

            results_by_id: Dict[int, Dict[str, Any]] = {}
            for item in results_list:
                if isinstance(item, dict) and "id" in item:
                    try:
                        results_by_id[int(item["id"])] = item
                    except (ValueError, TypeError):
                        pass

            for idx, x in enumerate(batch):
                data = results_by_id.get(idx, {})
                s = str(data.get("summary", "")).strip()
                w = str(data.get("why_it_matters", "")).strip()
                x.summary = s or fallback(x.description or x.title)
                x.why_it_matters = w or f"Significant reporting for {x.category}."

        except (AllProvidersExhaustedError, Exception) as exc:
            stage_success = False
            print(f"[WARNING] AI providers exhausted during news summarization batch {i//batch_size + 1}: {exc}")
            for x in batch:
                x.summary = fallback(x.description or x.title)
                x.why_it_matters = f"Refer to original report on {x.source} for primary analysis."
            # Fill remaining batches with fallback immediately without wasting more calls
            for remaining_x in items[i + batch_size:]:
                remaining_x.summary = fallback(remaining_x.description or remaining_x.title)
                remaining_x.why_it_matters = f"Refer to original report on {remaining_x.source} for primary analysis."
            break

    if hasattr(manager, "record_stage_status"):
        manager.record_stage_status("Summarization", stage_success)
    return items

def _deterministic_job_fallback(j: JobItem) -> JobItem:
    """Set experience, responsibilities, key_skills from description without AI."""
    if not j.experience:
        j.experience = "Intern / Entry-level (0-2 years)"
    if not j.responsibilities:
        desc = (j.description or "").strip()
        if desc:
            sentences = re.split(r'(?<=[.!?])\s+', desc)
            j.responsibilities = " ".join(sentences[:2])[:300] or desc[:300]
        else:
            j.responsibilities = "See job listing for full responsibilities."
    if not j.key_skills and j.skills:
        j.key_skills = ", ".join(j.skills[:8])
    elif not j.key_skills:
        j.key_skills = "See job listing for requirements."
    return j

def summarize_jobs(
    items: List[JobItem],
    api_key: Optional[str] = None,
    model: str = "qwen/qwen3.8-27b",
    provider_manager: Optional[Any] = None,
    groq_manager: Optional[Any] = None
) -> List[JobItem]:
    """Refine job classification and extract responsibilities/skills using AI in batches."""
    if not items:
        return items

    manager = provider_manager or groq_manager
    if manager is None:
        if api_key is not None and api_key != "":
            from app.ai.groq_client import get_groq_manager
            groq_m = get_groq_manager(api_keys=[api_key], model=model)
            from app.ai.provider_manager import AIProviderManager
            manager = AIProviderManager(provider_priority=["groq"], groq_manager=groq_m)
        elif api_key == "":
            from app.ai.groq_client import GroqClientManager
            groq_m = GroqClientManager(api_keys=[], default_model=model)
            from app.ai.provider_manager import AIProviderManager
            manager = AIProviderManager(provider_priority=["groq"], groq_manager=groq_m)
        else:
            manager = get_provider_manager()

    # Batch jobs in groups of 8 to stay within token limits
    batch_size = 8
    for i in range(0, len(items), batch_size):
        _pace_between_batches(i)
        chunk = items[i:i + batch_size]
        jobs_payload = [
            {
                "id": idx,
                "title": j.title,
                "company": j.company,
                "description": (j.description or "")[:450]
            }
            for idx, j in enumerate(chunk)
        ]

        prompt = f"""Analyze these software/computing job listings for a fresh graduate audience.
Return a JSON list. Each object must have:
- "id": integer matching the job id
- "experience_level": one of "Internship", "Entry Level", or "Junior"
- "responsibilities": 1-3 plain English sentences describing what the candidate will actually do. Use only information from the description. Do not invent.
- "key_skills": comma-separated list of up to 6 main technical skills or technologies required.

Jobs:
{json.dumps(jobs_payload, ensure_ascii=False, indent=2)}

Return ONLY valid JSON."""

        try:
            response = manager.create_chat_completion(
                model=None,
                messages=[
                    {"role": "system", "content": "You extract job information accurately. Output strictly valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_completion_tokens=700
            )
            clean_text = clean_json_response(response.choices[0].message.content or "")
            parsed = json.loads(clean_text)
            results_list = parsed if isinstance(parsed, list) else (
                parsed.get("jobs") or parsed.get("results") or parsed.get("items") or []
            )
            res_by_id = {int(x["id"]): x for x in results_list if isinstance(x, dict) and "id" in x}

            for idx, j in enumerate(chunk):
                match = res_by_id.get(idx)
                if match:
                    if "experience_level" in match:
                        j.experience_level = str(match["experience_level"]).strip()
                        j.experience = j.experience_level
                    if "responsibilities" in match and str(match["responsibilities"]).strip():
                        j.responsibilities = str(match["responsibilities"]).strip()[:400]
                    if "key_skills" in match and str(match["key_skills"]).strip():
                        j.key_skills = str(match["key_skills"]).strip()[:200]
                _deterministic_job_fallback(j)

        except (AllProvidersExhaustedError, Exception) as exc:
            print(f"[WARNING] AI providers exhausted during job summarization batch {i // batch_size + 1}: {exc}")
            for j in items[i:]:
                _deterministic_job_fallback(j)
            break

    return items
