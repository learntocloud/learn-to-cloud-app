"""Legacy redirect routes for old Docusaurus URLs.

The original LearnToCloud.Guide was a Docusaurus site with URLs like:
  /phase0/some-topic
  /phase1/some-topic
  ...up to /phase5/some-topic

Some users may still have these bookmarked. These routes catch the old
URL patterns and redirect to the homepage so visitors can sign in and
navigate the new app.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)


@router.get("/phase{phase_num:int}")
@router.get("/phase{phase_num:int}/{rest:path}")
async def legacy_phase_redirect(phase_num: int, rest: str = "") -> RedirectResponse:
    """Redirect old Docusaurus phase URLs to the homepage."""
    logger.info(
        "legacy.redirect",
        extra={"phase_num": phase_num, "rest": rest},
    )
    return RedirectResponse(url="/", status_code=301)
