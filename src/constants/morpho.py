from typing import NamedTuple

class MorphoMarket(NamedTuple):
    id: str
    loanToken: str
    collateralToken: str
    oracle: str
    irm: str
    lltv: float

CBETH_USDC = MorphoMarket(
    "0x1c21c59df9db44bf6f645d854ee710a8ca17b479451447e9f56758aee10a2fad",
    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22",
    "0xb40d93F44411D8C09aD17d7F88195eF9b05cCD96",
    "0x46415998764C29aB2a25CbeA6254146D50D22687",
    0.86
)

MORPHO = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
MORPHO_MARKETS = [CBETH_USDC]
