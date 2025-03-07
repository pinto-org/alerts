from data_access.contracts.util import get_beanstalk_contract, get_web3_instance
from tools.silo import StemTipCache, net_erc1155_transfers, unpack_address_and_stem
from web3.logs import DISCARD


def spinto_deposit_info(wrapped_info, owner, event_log):
    """
    Returns whether the Pinto was already deposited, and the amount of stalk
    on the deposit which was added/removed to spinto
    """

    beanstalk_contract = get_beanstalk_contract(get_web3_instance())

    stalk = 0
    stem_tips = StemTipCache()
    farmer_transfers = net_erc1155_transfers(wrapped_info.addr, owner, event_log.receipt)
    if len(farmer_transfers) > 0:
        is_deposited = True
        evt_add_deposit = beanstalk_contract.events["AddDeposit"]().processReceipt(event_log.receipt, errors=DISCARD)
        # Silo wrap/unwrap: in both directions, use the IDs from 1155 transfer events
        for id in farmer_transfers:
            token, stem = unpack_address_and_stem(id)
            stem_tip = stem_tips.get_stem_tip(token)
            amount = abs(farmer_transfers[id])

            # Identify the corresponding AddDeposit event to get the associated bdv
            add_deposit = [evt for evt in evt_add_deposit if evt.args.get("token") == token and evt.args.get("stem") == stem and evt.args.get("amount") == amount]
            bdv = add_deposit[0].args.get("bdv")

            # Return stalk amount
            grown_stalk = bdv * (stem_tip - stem)
            stalk += bdv * 10 ** 10 + grown_stalk
    else:
        is_deposited = False
        # Direct wrap/unwrap are identifiable by no Transfer event between farmer and spinto
        if event_log.event == "Deposit":
            # Direct wrap: always brings zero grown stalk
            stalk = 10 ** 10 * event_log.args.get("assets")
        else:
            # Direct unwrap: analyze all of the Remove events after the final AddDeposit event
            evt_add_deposit = beanstalk_contract.events["AddDeposit"]().processReceipt(event_log.receipt, errors=DISCARD)
            evt_remove_deposits = beanstalk_contract.events["RemoveDeposits"]().processReceipt(event_log.receipt, errors=DISCARD)

            max_deposit_idx = max(evt_add_deposit, key=lambda evt: evt.logIndex).logIndex
            evt_remove_deposits = [evt for evt in evt_remove_deposits if evt.logIndex > max_deposit_idx]

            for evt_remove in evt_remove_deposits:
                token = evt_remove.args.get("token")
                stem_tip = stem_tips.get_stem_tip(token)
                for i in range(len(evt_remove.args.get("bdvs"))):
                    bdv = evt_remove.args.get("bdvs")[i]
                    grown_stalk = bdv * (stem_tip - evt_remove.args.get("stems")[i])
                    stalk += bdv * 10 ** 10 + grown_stalk

    return is_deposited, stalk

def has_spinto_action_size(receipt, amount):
    """Returns true if the given transaction receipt contains a spinto deposit/withdraw of the given size"""
    # TODO
    return False