"""Press-volume overlay via Media Cloud (ADR-042).

Media Cloud provides free daily story-count time series by keyword query across
large news collections. Its role is a display/validation overlay: plot broad/
premium press volume against institutional discourse volume to show the
institutional-vs-press timing of a narrative ("timing, not cause").

This layer does NOT feed embedding, clustering, or dynamics fitting — Media
Cloud text is outside the ADR-020 basis set and these counts are a post-hoc
overlay (ADR-042). A forward-looking early-detector is a deferred add-on.

API key: MEDIACLOUD_API_KEY in .env (free signup at search.mediacloud.org)
Output: data/detection/mediacloud/
"""

from mnd.detection.markets import MarketsOverlay
from mnd.detection.mediacloud import MediaCloudDetector

__all__ = ["MarketsOverlay", "MediaCloudDetector"]
