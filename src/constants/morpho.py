from typing import NamedTuple

class MorphoMarket(NamedTuple):
    id: str
    loanToken: str
    collateralToken: str
    oracle: str
    irm: str
    lltv: float

SPINTO_USDC = MorphoMarket(
    "0x74918a8744b4a48d233e66d0f6a318ef847cc4da2910357897f94a33c3481280",
    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "0x00b174d66adA7d63789087F50A9b9e0e48446dc1",
    "0x774c111F471FBa61B13D63C9B585882e3c6cf7A6",
    "0x46415998764C29aB2a25CbeA6254146D50D22687",
    0.77
)

MORPHO = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
MORPHO_MARKETS = [SPINTO_USDC]
