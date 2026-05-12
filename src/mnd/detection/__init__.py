"""Layer 2 detection: narrative emergence signaling via Media Cloud.

Media Cloud provides daily story count time series by keyword/topic query
across thousands of outlets. Its sole role is to detect when a topic is
receiving anomalous volume attention — firing a candidate narrative flag
before institutional sources have characterized it in embeddable text.

This layer does NOT feed embedding or clustering. It is a parallel signal
pipeline that runs independently of the semantic corpus (Layer 1A).

API key: MEDIACLOUD_API_KEY in .env
Output: data/detection/mediacloud/
"""

from mnd.detection.mediacloud import MediaCloudDetector

__all__ = ["MediaCloudDetector"]
