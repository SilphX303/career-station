import logging
import os
import httpx

log = logging.getLogger("career.notify")


async def discord(role: dict, score: int, reasons: list[str]) -> bool:
    url = os.environ.get("CAREER_DISCORD_WEBHOOK")
    if not url:
        return False
    base = os.environ.get("CAREER_PUBLIC_URL", "").rstrip("/")
    sal = role.get("salary_text") or (
        f"£{role['salary_min']:,} to £{role['salary_max']:,}" if role.get("salary_min") and role.get("salary_max")
        else "salary not stated")
    lines = [
        f"**{score}**  {role['title']}",
        f"{role.get('company') or 'Unknown company'}, {role.get('location') or ''}, {sal}",
        *[f"- {r}" for r in reasons[:2]],
        f"{base}/?role={role['id']}" if base else role["url"],
    ]
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(url, json={"content": "\n".join(lines)})
            return r.status_code < 300
    except Exception as e:  # noqa: BLE001
        log.warning("discord failed: %s", e)
        return False
