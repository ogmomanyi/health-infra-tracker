# Faram Channel Constraints

`data/faram_channel_constraints.csv` records explicit evidence that affects how Faram can commercially position a manufacturer or product in a territory.

## Why this is separate

Channel constraints are not product catalogue records and are not external procurement events. They describe commercial route-to-market facts such as an explicitly identified appointed distributor, restricted territory, required reseller route, or other manufacturer-confirmed channel limitation.

Keeping this evidence separate prevents a quotation, tender-support request or supplier interaction from being mistaken for an active Faram principal appointment.

## Evidence policy

- Add a constraint only when the underlying source explicitly identifies the channel fact.
- Do not infer exclusivity unless the source explicitly states exclusivity.
- Do not infer a country-wide restriction from product-specific evidence unless the source supports that scope.
- A channel constraint must never promote a Faram catalogue record to `active`.
- A historical quotation or direct manufacturer correspondence remains commercial evidence unless current authorization and territory are explicitly established.
- `recommended_action` is decision support; it does not replace a human commercial decision.

## Initial controlled record

The first record captures DiaSys correspondence concerning the Gertrude's Hospital SYS 680 ci opportunity. DiaSys explicitly identified Keton Consulting Limited as its valued distributor in Kenya and directed Faram to Keton. The record therefore prevents the system from treating that correspondence as evidence that Faram is DiaSys's direct Kenya distributor.
