from constants.config import ENS_RPC_URL
from web3 import Web3

# ENS is always eth mainnet, needs separate Web3 instance
w3 = Web3(Web3.HTTPProvider(ENS_RPC_URL))

def format_address_ens(address):
    name = w3.ens.name(address)
    if name is None:
        return shorten_hash(address)
    return name

def shorten_hash(address: str) -> str:
    if len(address) > 10 and address.startswith("0x"):
        return f"{address[:6]}...{address[-4:]}"
    return address

if __name__ == '__main__':
    with_eth_ens = format_address_ens('0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045')
    with_base_ens = format_address_ens('0x9d32572997DA4948063E3Fc11c2552Eb82F7208E')
    with_no_ens = format_address_ens('0x12121212312312312312312312312312321abcde')
    print(with_eth_ens)
    print(with_base_ens)
    print(with_no_ens)
