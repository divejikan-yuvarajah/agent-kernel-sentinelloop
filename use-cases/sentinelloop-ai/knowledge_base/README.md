# SentinelLoop knowledge base

This directory will eventually contain or reference **approved** workplace safety material only:

- company safety procedures
- SOPs
- emergency guidance
- PPE guidance
- hazard-specific procedures

`sources/` is reserved for those files. It is empty in this scaffold.

SentinelLoop safety guidance must be retrieval-grounded and must never be fabricated when approved source material is unavailable.

Do not invent policies here. Do not download external documents in this phase. Retrieval wiring (Agent Kernel `KnowledgeBuilder` / Chroma or another configured backend) is a later implementation prompt.

If retrieval fails, the workflow records the failure and continues required Slack escalation, especially for Critical incidents.
