from bots.util import get_logs_by_names
from web3.datastructures import AttributeDict

class TractorEvents:
    def __init__(self, receipt, decoded_logs):
        self.receipt = receipt
        # Events within Tractor execution contexts
        self.tractor_events: list[list[AttributeDict]] = []
        self.range: list[tuple[int, int]] = []
        self.operators: list[str] = []
        self.publishers: list[str] = []

        # Events not falling within a Tractor execution context
        self.outer_events: list[AttributeDict] = []

        evt_began = get_logs_by_names(["TractorExecutionBegan"], decoded_logs)
        evt_end = get_logs_by_names(["Tractor"], decoded_logs)

        for start in evt_began:
            end = [evt for evt in evt_end if evt.args.blueprintHash == start.args.blueprintHash and evt.args.nonce == start.args.nonce][0]
            range = [start.logIndex, end.logIndex]
            self.tractor_events.append(sorted([log for log in decoded_logs if range[0] <= log.logIndex <= range[1]], key=lambda x: x.logIndex))
            self.range.append(range)
            self.operators.append(start.args.operator)
            self.publishers.append(start.args.publisher)

        self.outer_events = [log for log in decoded_logs if not any(log in tractor_range for tractor_range in self.tractor_events)]

    # Returns a list of all separate event contexts
    def all_separated_events(self):
        return self.tractor_events + ([self.outer_events] if self.outer_events else [])

    # Returns all events matching the context of the given index (finds all other related events)
    def events_matching_index(self, index: int):
        for i, (start, end) in enumerate(self.range):
            if start <= index <= end:
                return self.tractor_events[i]
        return self.outer_events
