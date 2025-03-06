import logging
from web3.logs import DISCARD
from collections import defaultdict
from bots.util import get_logs_by_names
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.contracts.util import get_erc1155_contract, get_web3_instance

def net_deposit_withdrawal_stalk(event_logs, remove_from_logs=False):
    # Determine net deposit/withdraw of each token
    # Sums total bdv/stalk as well

    beanstalk_client = BeanstalkClient()

    stem_tips = {}
    net_deposits = defaultdict(lambda: {"amount": 0, "bdv": 0, "stalk": 0})
    silo_deposit_logs = get_logs_by_names(["AddDeposit", "RemoveDeposit", "RemoveDeposits"], event_logs)
    for event_log in silo_deposit_logs:
        sign = 1 if event_log.event == "AddDeposit" else -1
        token = event_log.args.get("token")
        if token not in stem_tips:
            stem_tips[token] = beanstalk_client.get_stem_tip(token)

        net_deposits[token]["amount"] += sign * event_log.args.get("amount")
        # Sum bdv/stalk. Assumes 1 bdv credits 1 stalk upon deposit.
        if event_log.event != "RemoveDeposits":
            bdv = event_log.args.get("bdv")
            grown_stalk = bdv * (stem_tips[token] - event_log.args.get("stem"))
            net_deposits[token]["bdv"] += sign * bdv
            net_deposits[token]["stalk"] += sign * (1 * bdv * 10 ** 10 + grown_stalk)
        else:
            for i in range(len(event_log.args.get("bdvs"))):
                bdv = event_log.args.get("bdvs")[i]
                grown_stalk = bdv * (stem_tips[token] - event_log.args.get("stems")[i])
                net_deposits[token]["bdv"] += sign * bdv
                net_deposits[token]["stalk"] += sign * (1 * bdv * 10 ** 10 + grown_stalk)

        if remove_from_logs:
            event_logs.remove(event_log)
    
    return net_deposits


def net_erc1155_transfers(token, owner, receipt):
    """Returns the net transfer amount of token from/to owner in the given transaction"""
    erc1155_contract = get_erc1155_contract(get_web3_instance(), token)

    event_names = ["TransferSingle", "TransferBatch"]
    all_events = []

    for event_name in event_names:
        event_obj = getattr(erc1155_contract.events, event_name)()
        processed_events = event_obj.processReceipt(receipt, errors=DISCARD)
        all_events.extend(processed_events)

    # Filter events
    owner_evts = [evt for evt in all_events if evt.args.get("from") == owner or evt.args.get("to") == owner]
    
    # Sum totals
    net_transfers = defaultdict(int)
    for evt_xfer in owner_evts:
        sign = -1 if evt_xfer.args.get("from") == owner else 1

        if evt_xfer.event == "TransferSingle":
            id = evt_xfer.args.get("id")
            value = evt_xfer.args.get("value")
            net_transfers[id] += sign * value
        else:
            for i in range(len(evt_xfer.args.get("ids"))):
                id = evt_xfer.args.get("ids")[i]
                value = evt_xfer.args.get("values")[i]
                net_transfers[id] += sign * value
    return net_transfers

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    web3 = get_web3_instance()
    receipt = web3.eth.get_transaction_receipt("0x4d5e3f3d6a5c77c0a35e308f0380cfd9e10fcfa3ff9bd51d45708e8e33c9dc84")
    xfers = net_erc1155_transfers(
        "0xD1A0D188E861ed9d15773a2F3574a2e94134bA8f",
        "0x00b174d66adA7d63789087F50A9b9e0e48446dc1",
        receipt
    )
