import datetime
from typing import NamedTuple

class SpectraPool(NamedTuple):
    deployment_block: int
    maturity: datetime.datetime
    pool: str
    lp_token: str
    pt: str
    yt: str
    underlying: str
    ibt: str
    is_legacy_abi: bool

# September 17th 2025 maturity
SPINTO_1 = SpectraPool(
    27767837,
    datetime.datetime.fromtimestamp(1758153782, datetime.timezone.utc),
    "0xd8E4662ffd6b202cF85e3783Fb7252ff0A423a72",
    "0xba1F1eA8c269003aFe161aFAa0bd205E2c7F782a",
    "0x42AF817725D8cda8E69540d72f35dBfB17345178",
    "0xaF4f5bdF468861feF71Ed6f5ea0C01A75B62273d",
    "0xb170000aeeFa790fa61D6e837d1035906839a3c8",
    "0x00b174d66adA7d63789087F50A9b9e0e48446dc1",
    True
)

# January 15th 2026 maturity
SPINTO_2 = SpectraPool(
    32965381,
    datetime.datetime.fromtimestamp(1768518000, datetime.timezone.utc),
    "0xbcae0acad03b238b97b3158b1fe3eda3c4dc0b83",
    "0xbcae0acad03b238b97b3158b1fe3eda3c4dc0b83",
    "0x306e6ec73df3200c62a304cb8d6944e7543fb487",
    "0x52B1fce1784AC9dA1F31E04077F46388CC4AF7b3",
    "0xb170000aeefa790fa61d6e837d1035906839a3c8",
    "0x00b174d66ada7d63789087f50a9b9e0e48446dc1",
    False
)

SPECTRA_SPINTO_POOLS = [SPINTO_1, SPINTO_2]
