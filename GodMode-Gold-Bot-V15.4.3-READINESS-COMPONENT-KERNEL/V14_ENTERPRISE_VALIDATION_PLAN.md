# V14 Enterprise Validation Plan

A+ production certification requires evidence from the target Windows terminal and broker demo account:

1. Compile Tick Guard in MetaEditor with zero errors and zero warnings.
2. Run broker contract discovery for the configured gold symbol.
3. Validate order placement, modification, partial close, full close and read-back reconciliation.
4. Execute disconnect, terminal restart, backend restart and uncertain-submission tests.
5. Complete replay/property testing and a minimum 20-trading-day demo soak.
6. Enable unattended live mode only after Tick Guard heartbeat, build identity, account and broker checks pass.
