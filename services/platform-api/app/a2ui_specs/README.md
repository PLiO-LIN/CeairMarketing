# A2UI upstream schemas

Source: https://github.com/a2ui-project/a2ui/tree/main/specification/v0_9_1
Retrieved 2026-10-10, stable protocol v0.9.1, Apache-2.0 (see LICENSE).

The original server, client, common and basic catalog JSON files are preserved.
The upstream schema identifiers still use `v0_9`; their allowed wire versions
include `v0.9.1`. `app/a2ui.py` builds the limited platform catalog in memory,
retaining standard Text, Column, Row, Card, Button and Divider definitions and
adding Chart, DataTable and TaskCard as catalog components with JSON Pointer
bindings. Validation resolves references from local files without network access.

Specification: https://a2ui.org/specification/v0.9.1-a2ui/
Renderer guidance: https://a2ui.org/reference/renderers/
