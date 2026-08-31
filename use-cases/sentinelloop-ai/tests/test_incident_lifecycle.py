"""Future incident lifecycle tests.

Intended coverage: allowed transitions; reject CLOSED from IN_PROGRESS;
close only after verification; worker No → REOPENED; same incident id on
reopen; concurrent worker rejection vs officer complete.

No assertions in this scaffold.
"""
