from typing import NamedTuple

class SpectraPool(NamedTuple):
    maturity: str
    pool: str
    lp_token: str
    pt: str
    yt: str
    underlying: str
    ibt: str

SPINTO_1 = SpectraPool(
    "Sep 17 2025",
    "0xd8e4662ffd6b202cf85e3783fb7252ff0a423a72",
    "0xba1f1ea8c269003afe161afaa0bd205e2c7f782a",
    "0x42af817725d8cda8e69540d72f35dbfb17345178",
    "0xaF4f5bdF468861feF71Ed6f5ea0C01A75B62273d",
    "0xb170000aeefa790fa61d6e837d1035906839a3c8",
    "0x00b174d66ada7d63789087f50a9b9e0e48446dc1"
)
SPECTRA_SPINTO_POOLS = [SPINTO_1]
