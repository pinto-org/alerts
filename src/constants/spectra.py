import datetime
from typing import NamedTuple

class SpectraPool(NamedTuple):
    maturity: int
    pool: str
    lp_token: str
    pt: str
    yt: str
    underlying: str
    ibt: str

SPINTO_1 = SpectraPool(
    datetime.datetime.fromtimestamp(1758153782, datetime.timezone.utc),
    "0xd8E4662ffd6b202cF85e3783Fb7252ff0A423a72",
    "0xba1F1eA8c269003aFe161aFAa0bd205E2c7F782a",
    "0x42AF817725D8cda8E69540d72f35dBfB17345178",
    "0xaF4f5bdF468861feF71Ed6f5ea0C01A75B62273d",
    "0xb170000aeeFa790fa61D6e837d1035906839a3c8",
    "0x00b174d66adA7d63789087F50A9b9e0e48446dc1"
)
SPECTRA_SPINTO_POOLS = [SPINTO_1]
